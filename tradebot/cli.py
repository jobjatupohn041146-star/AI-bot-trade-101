"""Command line:
  python -m tradebot study [--claude]          # learn the curriculum first
  python -m tradebot status                    # learned? stats? exit policy?
  python -m tradebot backtest [--csv f] [--ai] # paper-trade history bar by bar
  python -m tradebot learn-exits               # fit SL/TP from journal stats
  python -m tradebot live --broker sim --yf GC=F          # paper (simulated fills)
  python -m tradebot live --broker ccxt --exchange bybit --symbol BTC/USDT:USDT   # testnet
  python -m tradebot live --broker mt5 --symbol XAUUSD    # MT5 demo account
  python -m tradebot stats
"""
from __future__ import annotations

import argparse

import pandas as pd
import json
import sys

from . import curriculum
from .config import DATA_DIR, BotConfig
from .data import load_csv, load_yfinance, synthetic
from .engine import TradingEngine
from .exits import ExitPolicy
from .journal import Journal

POLICY = DATA_DIR / "sltp_policy.json"


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False, default=str))


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="tradebot")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("study")
    s.add_argument("--claude", action="store_true", help="let Claude read and distil the curriculum")
    sub.add_parser("status")
    st = sub.add_parser("stats")
    st.add_argument("--db", default=str(DATA_DIR / "journal.db"))
    le = sub.add_parser("learn-exits")
    le.add_argument("--db", default=str(DATA_DIR / "journal.db"))
    le.add_argument("--policy", default=str(POLICY))
    b = sub.add_parser("backtest")
    b.add_argument("--csv")
    b.add_argument("--yf", help="yfinance ticker, e.g. GC=F")
    b.add_argument("--interval", default="1h")
    b.add_argument("--bars", type=int, default=2000)
    b.add_argument("--seed", type=int, default=7)
    b.add_argument("--ai", action="store_true", help="Claude makes the final decision")
    b.add_argument("--daily", action="store_true", help="data is daily (disables killzones)")
    b.add_argument("--db", default=str(DATA_DIR / "journal.db"))
    b.add_argument("--policy", default=str(POLICY), help="SL/TP policy file to trade with")
    b.add_argument("--htf", help="higher timeframe, e.g. 4h, or 'none' (default from config)")
    b.add_argument("--commission", type=float, default=0.05, help="fee %% per side (default 0.05)")
    b.add_argument("--stop-min-atr", type=float)
    b.add_argument("--hold", type=int, help="learning-mode holding bars")
    b.add_argument("--min-score", type=float)
    b.add_argument("--require-htf", action="store_true")
    b.add_argument("--max-fee-r", type=float)
    b.add_argument("--setups", help="comma-separated setup whitelist")
    b.add_argument("--start", help="only bars from this date (e.g. 2024-01-01)")
    b.add_argument("--end", help="only bars before this date")
    lv = sub.add_parser("live", help="trade the newest closed bar on a loop")
    lv.add_argument("--broker", choices=["sim", "ccxt", "mt5"], default="sim")
    lv.add_argument("--yf", help="data source for --broker sim (yfinance ticker)")
    lv.add_argument("--exchange", default="bybit")
    lv.add_argument("--symbol")
    lv.add_argument("--timeframe", default="1h")
    lv.add_argument("--poll", type=int, default=60, help="seconds between polls")
    lv.add_argument("--ai", action="store_true")
    lv.add_argument("--state", default=str(DATA_DIR / "live_state.json"), help="resume file")
    lv.add_argument("--db", default=str(DATA_DIR / "live_journal.db"))
    lv.add_argument("--policy", default=str(POLICY))
    lv.add_argument("--real", action="store_true",
                    help="REAL money. Also requires env TRADEBOT_I_UNDERSTAND_RISK=YES")
    a = ap.parse_args(argv)

    if a.cmd == "study":
        rec = curriculum.study(use_claude=a.claude)
        print("Study complete. Playbook:", curriculum.PLAYBOOK)
        _print(rec)
        return
    if a.cmd == "status":
        ok, msg = curriculum.is_learned()
        _print({"learned": ok, "detail": msg, "exit_policy": {k: v.__dict__ for k, v in ExitPolicy(BotConfig().exits, POLICY).plans.items()}})
        return
    if a.cmd == "stats":
        _print(Journal(a.db).stats())
        return
    if a.cmd == "learn-exits":
        cfg = BotConfig()
        pol = ExitPolicy(cfg.exits, a.policy)
        plans = pol.learn(Journal(a.db))
        if not plans and not pol.rejected:
            print(f"Not enough learning-mode trades yet (need {cfg.exits.min_trades_to_optimize} per setup).")
        _print({"adopted": {k: v.__dict__ for k, v in plans.items()},
                "rejected_overfit_or_no_edge": pol.rejected})
        return

    cfg = BotConfig()
    if getattr(a, "commission", None) is not None:
        cfg.commission_pct = a.commission
    if getattr(a, "stop_min_atr", None) is not None:
        cfg.stop_min_atr = a.stop_min_atr
    if getattr(a, "hold", None):
        cfg.exits.learning_hold_bars = a.hold
    if getattr(a, "min_score", None):
        cfg.min_score = a.min_score
    if getattr(a, "require_htf", False):
        cfg.require_htf_alignment = True
    if getattr(a, "max_fee_r", None) is not None:
        cfg.money.max_fee_r = a.max_fee_r
    if getattr(a, "setups", None):
        cfg.enabled_setups = tuple(x.strip() for x in a.setups.split(","))
    if getattr(a, "htf", None):
        cfg.htf = None if a.htf.lower() == "none" else a.htf
    ok, msg = curriculum.is_learned()
    if cfg.require_learning and not ok:
        sys.exit(f"Refusing to trade: {msg}")
    ai = None
    if a.ai:
        from .decision.claude_agent import ClaudeTrader

        ai = ClaudeTrader(curriculum.load_playbook(), cfg.ai.model, cfg.ai.effort)
    if a.cmd == "live":
        return live_loop(cfg, a, ai)
    if a.csv:
        df = load_csv(a.csv)
    elif a.yf:
        df = load_yfinance(a.yf, interval=a.interval)
    else:
        print("No data source given: using SYNTHETIC data (for testing only).")
        df = synthetic(a.bars, a.seed)
    if a.start:
        df = df[df.index >= pd.Timestamp(a.start, tz="UTC")]
    if a.end:
        df = df[df.index < pd.Timestamp(a.end, tz="UTC")]
    print(f"Data: {len(df)} bars {df.index[0]} -> {df.index[-1]}")
    eng = TradingEngine(cfg, Journal(a.db), ai=ai, exit_policy=ExitPolicy(cfg.exits, a.policy),
                        intraday=not a.daily)
    _print(eng.run(df, progress=True))


def make_broker(a):
    """Build the broker. Real money needs two explicit opt-ins."""
    import os

    real = bool(a.real)
    if real and os.environ.get("TRADEBOT_I_UNDERSTAND_RISK") != "YES":
        sys.exit("--real needs env TRADEBOT_I_UNDERSTAND_RISK=YES (start on testnet/demo first!)")
    if a.broker == "sim":
        if not a.yf:
            sys.exit("--broker sim needs --yf TICKER for data")
        from .brokers import SimBroker

        b = SimBroker()
        b.fetch_ohlcv = lambda limit=1500: load_yfinance(a.yf, period="60d", interval=a.timeframe)
        return b
    if not a.symbol:
        sys.exit("--symbol is required")
    if a.broker == "ccxt":
        from .brokers.ccxt_broker import CCXTBroker

        return CCXTBroker(a.exchange, a.symbol, a.timeframe, sandbox=not real)
    from .brokers.mt5_broker import MT5Broker

    return MT5Broker(a.symbol, a.timeframe, allow_real=real)


def live_loop(cfg: BotConfig, a, ai) -> None:
    import time

    from .engine import load_state, save_state

    broker = make_broker(a)
    cfg.symbol = a.symbol or a.yf
    cfg.timeframe = a.timeframe
    eng = TradingEngine(cfg, Journal(a.db), ai=ai, exit_policy=ExitPolicy(cfg.exits, a.policy),
                        intraday=a.timeframe not in ("1d", "1w", "1wk"), broker=broker)
    resumed = load_state(eng, a.state)
    if broker.live and broker.open_positions() and eng.position is None:
        sys.exit("Broker already has an open position the bot does not know about — close it or "
                 "manage it manually before starting (the bot never adopts unknown positions).")
    if resumed:
        print(f"Resumed state from {a.state} (equity {eng.equity:,.2f}, "
              f"position: {eng.position.direction if eng.position else 'none'})")
    mode = "REAL MONEY" if a.real else ("testnet/demo" if broker.live else "paper")
    print(f"[{mode}] {broker.name} {cfg.symbol} {a.timeframe} — Ctrl+C to stop")
    last = eng.last_bar
    while True:
        try:
            df = broker.fetch_ohlcv(1500)
            i = len(df) - 2  # newest fully closed bar
            if i > 0 and str(df.index[i]) != last:
                last = eng.last_bar = str(df.index[i])
                d = eng.step(df, i)
                save_state(eng, a.state)
                pos = eng.position
                _print({"bar": str(last), "equity": round(eng.equity, 2), "decision": d,
                        "htf": eng._htf_ctx,
                        "position": None if pos is None else {
                            "direction": pos.direction, "setup": pos.setup, "entry": pos.entry,
                            "stop": pos.stop, "take_profit": pos.take_profit, "size": pos.size}})
            if eng.mm.halted:
                print("KILL SWITCH active — stopping.")
                break
        except KeyboardInterrupt:
            break
        except Exception as e:  # keep the loop alive on data hiccups
            print("poll error:", type(e).__name__, e)
        try:
            time.sleep(a.poll)
        except KeyboardInterrupt:
            break
