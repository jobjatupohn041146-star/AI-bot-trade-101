"""Gate 1 — trading psychology. Hard rules that the AI cannot override."""
from __future__ import annotations

from dataclasses import dataclass, field

from .config import PsychologyConfig


@dataclass
class MindState:
    consecutive_losses: int = 0
    consecutive_wins: int = 0
    last_loss_bar: int | None = None
    tilt_until_bar: int | None = None
    day: str | None = None
    trades_today: int = 0
    pnl_today: float = 0.0
    equity_day_start: float = 0.0
    last_risk_pct: float = 0.0
    log: list = field(default_factory=list)


class PsychologyGate:
    def __init__(self, cfg: PsychologyConfig):
        self.cfg = cfg
        self.state = MindState()

    def new_bar(self, bar: int, day: str, equity: float) -> None:
        if self.state.day != day:
            self.state.day = day
            self.state.trades_today = 0
            self.state.pnl_today = 0.0
            self.state.equity_day_start = equity

    def record_trade(self, bar: int, pnl: float, risk_pct: float) -> None:
        s = self.state
        s.pnl_today += pnl
        s.last_risk_pct = risk_pct
        if pnl < 0:
            s.consecutive_losses += 1
            s.consecutive_wins = 0
            s.last_loss_bar = bar
            if s.consecutive_losses >= self.cfg.max_consecutive_losses:
                s.tilt_until_bar = bar + self.cfg.tilt_cooldown_bars
                s.log.append(f"bar {bar}: tilt guard — {s.consecutive_losses} losses in a row")
        else:
            s.consecutive_wins += 1
            s.consecutive_losses = 0

    def record_entry(self) -> None:
        self.state.trades_today += 1

    def check_state(self, bar: int) -> tuple[bool, list[str]]:
        """Before even looking at the chart: is the trader (bot) fit to trade?"""
        c, s, why = self.cfg, self.state, []
        if s.tilt_until_bar is not None:
            if bar < s.tilt_until_bar:
                why.append(f"TILT: {c.max_consecutive_losses} losses in a row, cooling down until bar {s.tilt_until_bar}")
            else:
                s.tilt_until_bar, s.consecutive_losses = None, 0
        if s.last_loss_bar is not None and bar - s.last_loss_bar < c.loss_cooldown_bars:
            why.append("REVENGE: too soon after a loss")
        if s.trades_today >= c.max_trades_per_day:
            why.append("OVERTRADING: daily trade limit reached")
        if s.equity_day_start > 0 and -s.pnl_today / s.equity_day_start * 100 >= c.daily_loss_limit_pct:
            why.append("DAILY LOSS LIMIT: stop trading today")
        return (not why), why

    def check_entry(self, ctx: dict, confidence: float) -> tuple[bool, list[str]]:
        """After a setup appears: am I chasing, and am I actually confident?"""
        c, why = self.cfg, []
        if abs(ctx["price_action"]["dist_ema20_atr"]) > c.fomo_ema_atr:
            why.append("FOMO: price stretched from EMA20, wait for a pullback")
        if ctx["bar_range_atr"] > c.fomo_candle_atr:
            why.append("FOMO: chasing a giant candle")
        if confidence < c.min_confidence:
            why.append(f"LOW CONFIDENCE: {confidence:.2f} < {c.min_confidence}")
        return (not why), why

    def summary(self) -> dict:
        s = self.state
        return {"consecutive_losses": s.consecutive_losses, "consecutive_wins": s.consecutive_wins,
                "trades_today": s.trades_today, "pnl_today": round(s.pnl_today, 2),
                "in_tilt_cooldown": s.tilt_until_bar is not None}
