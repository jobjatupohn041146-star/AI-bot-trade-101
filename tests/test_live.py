from types import SimpleNamespace

import pandas as pd
import pytest

from tradebot.analysis import htf_context, resample
from tradebot.brokers.base import Broker, Fill
from tradebot.brokers.ccxt_broker import CCXTBroker
from tradebot.cli import make_broker
from tradebot.config import BotConfig, ExitConfig
from tradebot.data import synthetic
from tradebot.engine import TradingEngine
from tradebot.exits import ExitPolicy
from tradebot.journal import Journal


def test_htf_uses_only_completed_bars():
    df = synthetic(1200, seed=2)
    eng = TradingEngine(BotConfig(), Journal())
    i = 1001  # 1h bars: 1001 -> mid 4h bucket
    eng._htf(df, i)
    # the cached key is the first incomplete bucket; nothing at/after it was used
    assert eng._htf_key > df.index[i] - pd.Timedelta("4h")
    future = df.copy()
    future.iloc[i + 1:, :] = future.iloc[i + 1:, :] * 3  # change the future drastically
    e2 = TradingEngine(BotConfig(), Journal())
    assert e2._htf(future, i) == eng._htf(df, i)


def test_htf_context_shape():
    ctx = htf_context(synthetic(1600, seed=4), "4h")
    assert ctx["bias"] in ("bull", "bear", "range") and ctx["timeframe"] == "4h"
    assert len(resample(synthetic(8), "4h")) == 2


def _learning_trades(j, setup, rows):
    for k, (path, final) in enumerate(rows):
        j.add({"run_id": "x", "setup": setup, "direction": "long", "mode": "learning",
               "entry_time": f"2024-01-{1 + k // 24:02d}T{k % 24:02d}:00", "r_multiple": final,
               "path": [p + [final] for p in path]})


def test_walk_forward_rejects_edge_that_disappears():
    j = Journal()
    good = ([[0.2, 0.3], [3.2, 0.1]], 3.0)
    bad = ([[0.1, 1.0]], -1.0)
    _learning_trades(j, "S", [good] * 35 + [bad] * 15)   # newest 30% are all losers
    pol = ExitPolicy(ExitConfig(min_trades_to_optimize=30))
    assert "S" not in pol.learn(j) and "S" in pol.rejected


def test_walk_forward_adopts_stable_edge():
    j = Journal()
    good = ([[0.2, 0.3], [3.2, 0.1]], 0.5)
    bad = ([[0.1, 1.0]], -1.0)
    _learning_trades(j, "S", ([good, bad] * 25))
    plans = ExitPolicy(ExitConfig(min_trades_to_optimize=30)).learn(j)
    assert plans["S"].mode == "optimized" and plans["S"].test_expectancy > 0


class FakeExchange:
    def __init__(self):
        self.orders, self.pos = [], 0.0

    def amount_to_precision(self, sym, amt):
        return f"{int(amt * 1000) / 1000:.3f}"

    def create_order(self, sym, typ, side, amt, price=None, params=None):
        self.orders.append(("order", side, amt, params))
        self.pos = 0.0 if (params or {}).get("reduceOnly") else amt
        return {"id": str(len(self.orders)), "average": 100.0, "filled": amt}

    def create_stop_loss_order(self, sym, typ, side, amt, price, stop, params):
        self.orders.append(("sl", side, amt, stop))

    def create_take_profit_order(self, sym, typ, side, amt, price, tp, params):
        self.orders.append(("tp", side, amt, tp))

    def fetch_positions(self, syms):
        return [{"symbol": syms[0], "contracts": self.pos}]

    def cancel_all_orders(self, sym):
        self.orders.append(("cancel",))

    def fetch_balance(self):
        return {"total": {"USDT": 1000.0}}


def test_ccxt_broker_places_protective_stop_and_closes():
    ex = FakeExchange()
    b = CCXTBroker("x", "BTC/USDT:USDT", client=ex)
    assert b.normalize_size(0.12345, 100) == pytest.approx(0.123)
    f = b.open("long", 0.123, 100, 95.0, 110.0)
    kinds = [o[0] for o in ex.orders]
    assert kinds == ["order", "sl", "tp"] and ex.orders[1][1] == "sell"
    assert b.has_position(f)
    b.close(f, "long", 101)
    assert not b.has_position(f) and ("cancel",) in ex.orders
    assert b.equity() == 1000.0


def test_ccxt_broker_flattens_if_stop_rejected():
    ex = FakeExchange()
    ex.create_stop_loss_order = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("rejected"))
    b = CCXTBroker("x", "BTC/USDT:USDT", client=ex)
    with pytest.raises(RuntimeError):
        b.open("long", 0.1, 100, 95.0, None)
    assert ex.pos == 0.0


class FakeLiveBroker(Broker):
    name, live = "fake", True

    def __init__(self):
        self.opened = self.closed = 0
        self.pos = False

    def open(self, direction, size, price_hint, stop, take_profit):
        self.opened += 1
        self.pos = True
        return Fill(price_hint, size, "1")

    def close(self, fill, direction, price_hint):
        self.closed += 1
        self.pos = False
        return price_hint

    def has_position(self, fill):
        return self.pos

    def open_positions(self):
        return int(self.pos)


def test_engine_with_live_broker_opens_and_closes():
    b = FakeLiveBroker()
    eng = TradingEngine(BotConfig(), Journal(), broker=b)
    rep = eng.run(synthetic(1500, seed=11))
    assert b.opened > 0 and b.opened == b.closed + (1 if b.pos else 0)
    assert rep["trades"] >= b.closed - 1


def test_real_money_requires_explicit_env(monkeypatch):
    monkeypatch.delenv("TRADEBOT_I_UNDERSTAND_RISK", raising=False)
    args = SimpleNamespace(real=True, broker="ccxt", symbol="BTC/USDT:USDT", exchange="bybit",
                           timeframe="1h", yf=None)
    with pytest.raises(SystemExit):
        make_broker(args)


def test_live_clock_time_exit_and_state_roundtrip(tmp_path):
    """In live mode the newest index i is constant; holding time must still advance."""
    from tradebot.engine import PendingOrder, load_state, save_state

    df = synthetic(400, seed=9)
    b = FakeLiveBroker()
    cfg = BotConfig()
    cfg.exits.learning_hold_bars = 3
    eng = TradingEngine(cfg, Journal(), broker=b)
    i = 300
    eng.step(df, i)
    from tradebot.indicators import atr
    close, a = float(df["close"].iloc[i]), float(atr(df.iloc[:i + 1]).iloc[-1])
    eng.pending = PendingOrder("long", "TEST", close - 30 * a, {}, {})  # far stop: no stop-out
    eng.cfg.money.max_stop_atr = 100
    eng._fill(df, i, atr_now=a, price_hint=close)
    assert eng.position is not None
    eng.last_bar = str(df.index[i])
    save_state(eng, tmp_path / "s.json")
    e2 = TradingEngine(cfg, Journal(), broker=b)
    assert load_state(e2, tmp_path / "s.json")
    assert e2.position.setup == "TEST" and e2.position.fill.ref == "1" and e2.last_bar == eng.last_bar
    for _ in range(3):  # same i every time, as in the live loop
        e2.step(df, i)
    assert e2.position is None and b.closed == 1
    assert e2.journal.trades()[0]["exit_reason"] == "time"
