"""Bar-by-bar trading engine (shared by backtest and paper trading).

At the close of bar i the engine decides; orders fill at the open of bar i+1.
Pipeline per bar:  psychology(state) -> analysis -> rules (+Claude) ->
psychology(entry) -> money management -> order."""
from __future__ import annotations

import uuid
from collections import Counter
from dataclasses import dataclass, field

import pandas as pd

from .analysis import analyze, htf_context
from .brokers import Broker, Fill, SimBroker
from .config import BotConfig
from .decision.rules import Signal, confidence_from_score, evaluate, evaluate_strategy, structural_stop
from .exits import ExitPolicy
from .journal import Journal
from .money import MoneyManager
from .psychology import PsychologyGate


@dataclass
class Position:
    direction: str
    setup: str
    entry: float
    entry_bar: int
    entry_time: str
    r0: float                  # structural stop distance
    stop: float
    take_profit: float | None
    size: float
    risk_amount: float
    risk_pct: float
    max_bars: int
    mode: str
    components: dict
    decision: dict
    fill: Fill | None = None
    path: list = field(default_factory=list)


@dataclass
class PendingOrder:
    direction: str
    setup: str
    structural_stop: float
    components: dict
    decision: dict


class TradingEngine:
    def __init__(self, cfg: BotConfig, journal: Journal, ai=None, exit_policy: ExitPolicy | None = None,
                 intraday: bool = True, run_id: str | None = None, broker: Broker | None = None):
        self.cfg = cfg
        self.journal = journal
        self.ai = ai
        self.exits = exit_policy or ExitPolicy(cfg.exits)
        self.intraday = intraday
        self.run_id = run_id or uuid.uuid4().hex[:8]
        self.broker = broker or SimBroker()
        self.equity = cfg.initial_equity
        if self.broker.live and self.broker.equity() is not None:
            self.equity = self.broker.equity()
        self.psych = PsychologyGate(cfg.psychology)
        self.mm = MoneyManager(cfg.money, self.equity)
        self.position: Position | None = None
        self.pending: PendingOrder | None = None
        self.blocked = Counter()
        self.decisions: list[dict] = []
        self.equity_curve: list[tuple] = []
        self._htf_key = None
        self._htf_ctx = None
        self.bar_clock = 0
        self.last_bar: str | None = None   # newest bar processed (live resume)

    # ---------------------------------------------------------------- helpers
    def _setup_disabled(self, setup: str) -> bool:
        st = self.journal.stats().get(setup)
        return bool(st and st["trades"] >= self.cfg.money.disable_setup_after and st["expectancy_r"] < 0)

    def _fill(self, df: pd.DataFrame, i: int, atr_now: float, price_hint: float | None = None,
              first_bar: int | None = None) -> None:
        po, self.pending = self.pending, None
        entry = float(df["open"].iloc[i]) if price_hint is None else price_hint
        sign = 1 if po.direction == "long" else -1
        r0 = (entry - po.structural_stop) * sign
        if r0 <= 0:
            self.blocked["gap through invalidation"] += 1
            return
        plan = self._plan(po.setup)
        stop = entry - sign * plan.sl_mult * r0
        if self.cfg.money.max_fee_r is not None:
            fee_r = 2 * self.cfg.commission_pct / 100 * entry / abs(entry - stop)
            if fee_r > self.cfg.money.max_fee_r:
                self.blocked["MM: fees too large vs stop"] += 1
                return
        venue_positions = self.broker.open_positions() if self.broker.live else 0
        sd = self.mm.size(self.equity, entry, stop, atr_now, 0.0, venue_positions, self._setup_disabled(po.setup))
        if not sd.ok:
            for r in sd.reasons:
                self.blocked[f"MM: {r}"] += 1
            return
        tp = entry + sign * plan.tp_r * r0 if plan.tp_r else None
        size = self.broker.normalize_size(sd.size, entry)
        if size <= 0:
            self.blocked["MM: size below broker minimum"] += 1
            return
        fill = self.broker.open(po.direction, size, entry, stop, tp)
        entry = fill.price
        r0 = (entry - po.structural_stop) * sign
        if r0 <= 0:  # slipped through the invalidation level: get out
            self.broker.close(fill, po.direction, entry)
            self.blocked["slippage through invalidation"] += 1
            return
        risk_amount = abs(entry - stop) * fill.size
        start = i if first_bar is None else first_bar
        self.position = Position(po.direction, po.setup, entry, start, df.index[i].isoformat(), r0, stop, tp,
                                 fill.size, risk_amount, sd.risk_pct, plan.max_bars, plan.mode,
                                 po.components, po.decision, fill)
        self.psych.record_entry()

    def _plan(self, setup: str):
        from .exits import ExitPlan

        if self.cfg.fixed_rr:
            return ExitPlan(setup, 1.0, self.cfg.fixed_rr, self.cfg.max_hold_bars, "fixed_rr")
        return self.exits.plan_for(setup)

    def _htf(self, df: pd.DataFrame, i: int) -> dict | None:
        """Higher-timeframe bias from COMPLETED higher-timeframe bars only."""
        rule = self.cfg.htf
        if not rule or i < 1:
            return None
        ts, step = df.index[i], df.index[i] - df.index[i - 1]
        complete_upto = (ts + step).floor(rule)          # first HTF bucket not yet complete
        if complete_upto == self._htf_key:
            return self._htf_ctx
        src = df.iloc[max(0, i - self.cfg.htf_lookback_bars + 1): i + 1]
        src = src[src.index < complete_upto]
        self._htf_key, self._htf_ctx = complete_upto, htf_context(src, rule)
        return self._htf_ctx

    def _manage(self, df: pd.DataFrame, i: int) -> None:
        p = self.position
        o, h, l, c = (float(df[k].iloc[i]) for k in ("open", "high", "low", "close"))
        sign = 1 if p.direction == "long" else -1
        fav = ((h - p.entry) if sign > 0 else (p.entry - l)) / p.r0
        adv = ((p.entry - l) if sign > 0 else (h - p.entry)) / p.r0
        close_r = (c - p.entry) * sign / p.r0
        p.path.append([round(fav, 4), round(adv, 4), round(close_r, 4)])
        exit_px = reason = None
        stop_hit = (l <= p.stop) if sign > 0 else (h >= p.stop)
        tp_hit = p.take_profit is not None and ((h >= p.take_profit) if sign > 0 else (l <= p.take_profit))
        if stop_hit:  # conservative: stop first when both are touched
            exit_px = min(o, p.stop) if sign > 0 else max(o, p.stop)
            reason = "stop"
        elif tp_hit:
            exit_px = max(o, p.take_profit) if sign > 0 else min(o, p.take_profit)
            reason = "take_profit"
        elif len(p.path) >= p.max_bars:
            exit_px, reason = c, "time"
        if exit_px is None and self.broker.live and not self.broker.has_position(p.fill):
            exit_px, reason = c, "broker_closed"  # SL/TP filled on the venue intrabar
        if exit_px is not None:
            if self.broker.live:
                exit_px = self.broker.close(p.fill, p.direction, exit_px)
            self._close(df, i, exit_px, reason)

    def _close(self, df: pd.DataFrame, i: int, px: float, reason: str) -> None:
        p, self.position = self.position, None
        sign = 1 if p.direction == "long" else -1
        gross = (px - p.entry) * sign * p.size
        fees = (p.entry + px) * p.size * self.cfg.commission_pct / 100
        pnl = gross - fees
        self.equity += pnl
        r_mult = pnl / p.risk_amount if p.risk_amount else 0.0
        if p.path and reason == "stop" and p.mode == "learning":
            p.path[-1][2] = -1.0  # realised at the structural stop
        self.journal.add({
            "run_id": self.run_id, "symbol": self.cfg.symbol, "setup": p.setup, "direction": p.direction,
            "mode": p.mode, "entry_time": p.entry_time, "entry": p.entry, "stop": p.stop,
            "take_profit": p.take_profit, "size": p.size, "risk_amount": p.risk_amount,
            "exit_time": df.index[i].isoformat(), "exit": px, "exit_reason": reason,
            "pnl": pnl, "r_multiple": r_mult,
            "mfe_r": max((x[0] for x in p.path), default=0.0),
            "mae_r": max((x[1] for x in p.path), default=0.0),
            "bars_held": len(p.path), "path": p.path, "components": p.components, "decision": p.decision,
        })
        self.psych.record_trade(self.bar_clock, pnl, p.risk_pct)
        if self.broker.live and self.broker.equity() is not None:
            self.equity = self.broker.equity()

    # ------------------------------------------------------------------- step
    def step(self, df: pd.DataFrame, i: int) -> dict | None:
        # bar_clock counts processed bars; it keeps growing in live mode where the
        # newest bar index i stays ~constant, so cooldowns and holding time work.
        self.bar_clock += 1
        window = df.iloc[max(0, i - self.cfg.lookback_bars + 1): i + 1]
        if len(window) < 60:
            return None
        ts = df.index[i]
        self.psych.new_bar(self.bar_clock, ts.strftime("%Y-%m-%d"), self.equity)

        if self.pending is not None:
            from .indicators import atr
            self._fill(df, i, float(atr(window).iloc[-1]))
        if self.position is not None:
            self._manage(df, i)
        self.equity_curve.append((ts, self.equity))
        if self.position is not None or self.mm.halted:
            return None

        # Gate 1a: psychological state, before looking at the chart.
        ok, why = self.psych.check_state(self.bar_clock)
        if not ok:
            for r in why:
                self.blocked[f"PSY: {r.split(':')[0]}"] += 1
            return None

        # Gate 2: technical analysis (rules) and optional Claude judgement.
        ctx = analyze(window, intraday=self.intraday)
        ctx["htf"] = self._htf(df, i)
        if self.cfg.strategy:
            sig = evaluate_strategy(ctx, tuple(self.cfg.strategy), self.cfg.stop_min_atr)
        else:
            sig = evaluate(ctx, self.cfg.enabled_setups, self.cfg.stop_min_atr, self.cfg.require_htf_alignment)
        if sig is None:
            return None
        direction, setup, stop = sig.direction, sig.setup, sig.stop
        confidence = confidence_from_score(sig.score, self.cfg.min_score)
        decision = {"source": "rules", "score": round(sig.score, 3), "components": sig.reasons}

        if self.ai is not None:
            if sig.score < self.cfg.ai.prefilter_score:
                return None
            d = self.ai.decide(
                ctx, {"direction": sig.direction, "setup": sig.setup, "score": sig.score,
                      "components": sig.reasons, "structural_stop": sig.stop},
                self.psych.summary(),
                {"equity": round(self.equity, 2), "drawdown_pct": round(self.mm.drawdown_pct(self.equity), 2),
                 "risk_pct_next": self.mm.risk_pct(self.equity)},
                self.journal.stats(), self._plan(sig.setup).__dict__)
            decision = {"source": "claude", **d}
            self.decisions.append({"time": ts.isoformat(), **decision})
            if d["action"] == "HOLD":
                self.blocked["AI: HOLD"] += 1
                return decision
            direction = "long" if d["action"] == "BUY" else "short"
            setup = d["setup"] or sig.setup
            confidence = d["confidence"]
            stop = structural_stop(ctx, "bull" if direction == "long" else "bear", self.cfg.stop_min_atr)
            inv = d.get("invalidation_price")
            if inv and ((direction == "long" and inv < ctx["close"]) or (direction == "short" and inv > ctx["close"])):
                stop = float(inv)
        elif sig.score < self.cfg.min_score:
            return None

        # Gate 1b: psychology at the moment of entry (FOMO, confidence).
        ok, why = self.psych.check_entry(ctx, confidence)
        if not ok:
            for r in why:
                self.blocked[f"PSY: {r.split(':')[0]}"] += 1
            return decision

        # Gate 3 runs at fill time (needs the real entry price).
        self.pending = PendingOrder(direction, setup, stop, sig.components, decision)
        if self.broker.live:  # live: the next bar is starting now, send the order immediately
            self._fill(df, i, ctx["indicators"]["atr"], price_hint=ctx["close"], first_bar=i + 1)
        return decision

    def run(self, df: pd.DataFrame, progress: bool = False) -> dict:
        for i in range(len(df)):
            self.step(df, i)
            if progress and i % 250 == 0:
                print(f"  bar {i}/{len(df)} equity={self.equity:,.2f}")
        if self.position is not None:
            px = float(df["close"].iloc[-1])
            if self.broker.live:
                px = self.broker.close(self.position.fill, self.position.direction, px)
            self._close(df, len(df) - 1, px, "end_of_data")
        return self.report()

    def report(self) -> dict:
        trades = self.journal.trades()
        trades = [t for t in trades if t["run_id"] == self.run_id]
        eq = pd.Series([e for _, e in self.equity_curve]) if self.equity_curve else pd.Series([self.equity])
        max_dd = float(((eq.cummax() - eq) / eq.cummax()).max() * 100)
        rs = [t["r_multiple"] for t in trades]
        return {
            "run_id": self.run_id,
            "trades": len(trades),
            "final_equity": round(self.equity, 2),
            "return_pct": round((self.equity / self.cfg.initial_equity - 1) * 100, 2),
            "max_drawdown_pct": round(max_dd, 2),
            "win_rate": round(sum(r > 0 for r in rs) / len(rs), 3) if rs else None,
            "expectancy_r": round(sum(rs) / len(rs), 3) if rs else None,
            "kill_switch": self.mm.halted,
            "blocked": dict(self.blocked.most_common()),
            "by_setup": self.journal.stats(),
        }


# ------------------------------------------------------------- persistence
def save_state(eng: TradingEngine, path) -> None:
    """Persist everything needed to resume after a restart (live runs)."""
    import json
    from dataclasses import asdict
    from pathlib import Path

    s = eng.psych.state
    state = {
        "run_id": eng.run_id, "equity": eng.equity,
        "mm": {"peak": eng.mm.peak, "halted": eng.mm.halted},
        "psych": {k: getattr(s, k) for k in ("consecutive_losses", "consecutive_wins", "last_loss_bar",
                                              "tilt_until_bar", "day", "trades_today", "pnl_today",
                                              "equity_day_start", "last_risk_pct")},
        "position": asdict(eng.position) if eng.position else None,
        "bar_clock": eng.bar_clock,
        "last_bar": eng.last_bar,
    }
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, default=str, indent=2))
    tmp.replace(p)  # atomic


def load_state(eng: TradingEngine, path) -> bool:
    import json
    from pathlib import Path

    p = Path(path)
    if not p.exists():
        return False
    st = json.loads(p.read_text())
    eng.run_id = st["run_id"]
    eng.equity = st["equity"]
    eng.mm.peak, eng.mm.halted = st["mm"]["peak"], st["mm"]["halted"]
    for k, v in st["psych"].items():
        setattr(eng.psych.state, k, v)
    eng.bar_clock = st.get("bar_clock", 0)
    eng.last_bar = st.get("last_bar")
    if st["position"]:
        pos = dict(st["position"])
        pos["fill"] = Fill(**pos["fill"]) if pos.get("fill") else None
        eng.position = Position(**pos)
    return True
