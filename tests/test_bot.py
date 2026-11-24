import json
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from tradebot import curriculum
from tradebot.analysis import analyze
from tradebot.analysis.elliott import analyze as ew
from tradebot.analysis.smc import fair_value_gaps
from tradebot.analysis.structure import structure_events
from tradebot.config import BotConfig, ExitConfig, MoneyConfig, PsychologyConfig
from tradebot.data import synthetic
from tradebot.decision.claude_agent import ClaudeTrader
from tradebot.engine import TradingEngine
from tradebot.exits import ExitPolicy, optimize_setup, simulate
from tradebot.indicators import Swing, find_swings
from tradebot.journal import Journal
from tradebot.money import MoneyManager
from tradebot.psychology import PsychologyGate


def frame(closes, spread=0.5):
    c = np.array(closes, float)
    o = np.r_[c[0], c[:-1]]
    idx = pd.date_range("2024-01-01", periods=len(c), freq="1h", tz="UTC")
    return pd.DataFrame({"open": o, "high": np.maximum(o, c) + spread, "low": np.minimum(o, c) - spread,
                         "close": c, "volume": 1.0}, index=idx)


def test_swings_have_no_lookahead():
    df = synthetic(400, seed=1)
    full = find_swings(df)
    part = find_swings(df.iloc[:300])
    for s in part:
        assert s.confirmed_at < 300
    # pivots confirmed early never change when more data arrives
    early = {(s.idx, s.kind) for s in part if s.confirmed_at < 250}
    assert early <= {(s.idx, s.kind) for s in full} | early


def test_bos_and_choch():
    zig = [10, 12, 14, 12, 11, 13, 16, 18, 15, 14, 16, 20, 22, 19, 17, 15, 13, 11, 9, 12, 8, 6]
    df = frame(np.repeat(zig, 3).astype(float))
    events, state = structure_events(df, find_swings(df, 2, 2))
    kinds = [e.kind for e in events]
    assert "BOS_UP" in kinds or "CHOCH_UP" in kinds
    assert any(k.startswith("CHOCH_DOWN") for k in kinds)
    assert state == "bear"


def test_bullish_fvg_detected():
    df = frame([100, 100, 100, 101, 106, 108, 109, 110], spread=0.2)
    gaps = fair_value_gaps(df)
    assert any(g["dir"] == "bull" for g in gaps)


def test_elliott_wave2_and_rule_violation():
    sw = [Swing(0, 100, "L", 0), Swing(5, 120, "H", 0), Swing(9, 108, "L", 0)]
    assert ew(sw)["count"] == "wave2_end_bull"
    bad = [Swing(0, 100, "L", 0), Swing(5, 120, "H", 0), Swing(9, 95, "L", 0)]  # >100% retrace
    assert ew(bad)["count"] != "wave2_end_bull"


def test_analyze_context_keys():
    ctx = analyze(synthetic(300, seed=3))
    for k in ("structure", "price_action", "smc", "ict", "elliott"):
        assert k in ctx


def test_psychology_tilt_and_revenge():
    g = PsychologyGate(PsychologyConfig(max_consecutive_losses=2, tilt_cooldown_bars=10, loss_cooldown_bars=3))
    g.new_bar(0, "d1", 10_000)
    g.record_trade(5, -100, 1)
    ok, why = g.check_state(6)
    assert not ok and any("REVENGE" in w for w in why)
    g.record_trade(8, -100, 1)
    ok, why = g.check_state(12)
    assert not ok and any("TILT" in w for w in why)
    assert g.check_state(30)[0]


def test_psychology_daily_loss_limit():
    g = PsychologyGate(PsychologyConfig(daily_loss_limit_pct=2, loss_cooldown_bars=0, max_consecutive_losses=99))
    g.new_bar(0, "d1", 10_000)
    g.record_trade(1, -250, 1)
    assert any("DAILY" in w for w in g.check_state(50)[1])
    g.new_bar(60, "d2", 9_750)
    assert g.check_state(60)[0]


def test_money_sizing_and_kill_switch():
    mm = MoneyManager(MoneyConfig(risk_per_trade_pct=1), 10_000)
    d = mm.size(10_000, 100, 98, atr=2, open_risk_pct=0, open_positions=0)
    assert d.ok and d.size == pytest.approx(50)
    d = mm.size(8_500, 100, 98, atr=2, open_risk_pct=0, open_positions=0)  # 15% DD -> half risk
    assert d.risk_pct == 0.5
    d = mm.size(7_900, 100, 98, atr=2, open_risk_pct=0, open_positions=0)
    assert not d.ok and mm.halted


def test_exit_simulation_and_optimizer():
    assert simulate([[0.5, 0.2], [2.1, 0.3]], 1.0, sl=1.0, tp=2.0) == 2.0
    assert simulate([[0.5, 0.7]], 0.1, sl=0.6, tp=2.0) == -1.0
    # winners run to 3R after a shallow dip, losers dip 1R
    trades = [{"path": [[0.2, 0.3], [3.2, 0.1]], "r_multiple_raw": 3.0}] * 20 + \
             [{"path": [[0.1, 1.0]], "r_multiple_raw": -1.0}] * 20
    sl, tp, exp = optimize_setup(trades, ExitConfig(min_trades_to_optimize=10))
    assert sl <= 1.0 and tp >= 3.0 and exp > 0


def test_learning_gate(tmp_path):
    kdir = tmp_path / "k"
    kdir.mkdir()
    for i, name in enumerate(["01_pa", "02_smc", "03_ict", "04_ew", "05_psy", "06_mm", "07_entry"]):
        (kdir / f"{name}.md").write_text(f"# x\n## กฎสำคัญ (Key Rules)\n- rule {i}\n", encoding="utf-8")
    out = tmp_path / "out"
    assert not curriculum.is_learned(kdir, out)[0]
    curriculum.study(kdir=kdir, out_dir=out)
    assert curriculum.is_learned(kdir, out)[0]
    (kdir / "01_pa.md").write_text("changed", encoding="utf-8")
    assert not curriculum.is_learned(kdir, out)[0]


def test_engine_end_to_end_and_exit_learning():
    cfg = BotConfig()
    cfg.exits.min_trades_to_optimize = 5
    j = Journal()
    eng = TradingEngine(cfg, j)
    rep = eng.run(synthetic(1500, seed=11))
    assert rep["trades"] > 0
    t = j.trades()[0]
    assert t["path"] and t["mode"] == "learning" and t["take_profit"] is None
    plans = ExitPolicy(cfg.exits).learn(j)
    for p in plans.values():
        assert p.mode == "optimized" and p.tp_r is not None


class FakeClient:
    def __init__(self, decision):
        self.calls = 0
        self.decision = decision
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.calls += 1
        assert kw["output_config"]["format"]["type"] == "json_schema"
        return SimpleNamespace(stop_reason="end_turn", model="fake",
                               content=[SimpleNamespace(type="text", text=json.dumps(self.decision))])


def test_claude_agent_decisions_flow_through_hard_gates():
    hold = ClaudeTrader._hold("x")
    fake = FakeClient(hold)
    cfg = BotConfig()
    cfg.ai.prefilter_score = 0.0
    eng = TradingEngine(cfg, Journal(), ai=ClaudeTrader("pb", client=fake))
    rep = eng.run(synthetic(400, seed=5))
    assert fake.calls > 0 and rep["trades"] == 0  # HOLD always respected


def test_claude_refusal_becomes_hold():
    fake = FakeClient({})
    fake.beta.messages.create = lambda **kw: SimpleNamespace(stop_reason="refusal", content=[])
    d = ClaudeTrader("pb", client=fake).decide({}, {}, {}, {}, {}, {})
    assert d["action"] == "HOLD"
