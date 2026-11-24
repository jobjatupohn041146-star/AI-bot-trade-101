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
    sub.add_parser("stats")
    sub.add_parser("learn-exits")
    b = sub.add_parser("backtest")
    b.add_argument("--csv")
    b.add_argument("--yf", help="yfinance ticker, e.g. GC=F")
    b.add_argument("--interval", default="1h")
    b.add_argument("--bars", type=int, default=2000)
    b.add_argument("--seed", type=int, default=7)
    b.add_argument("--ai", action="store_true", help="Claude makes the final decision")
    b.add_argument("--daily", action="store_true", help="data is daily (disables killzones)")
    b.add_argument("--db", default=str(DATA_DIR / "journal.db"))
    lv = sub.add_parser("live", help="trade the newest closed bar on a loop")
    lv.add_argument("--broker", choices=["sim", "ccxt", "mt5"], default="sim")
    lv.add_argument("--yf", help="data source for --broker sim (yfinance ticker)")
    lv.add_argument("--exchange", default="bybit")
    lv.add_argument("--symbol")
    lv.add_argument("--timeframe", default="1h")
    lv.add_argument("--poll", type=int, default=60, help="seconds between polls")
    lv.add_argument("--ai", action="store_true")
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
        _print(Journal(DATA_DIR / "journal.db").stats())
        return
    if a.cmd == "learn-exits":
        cfg = BotConfig()
        pol = ExitPolicy(cfg.exits, POLICY)
        plans = pol.learn(Journal(cfg.db_path))
        if not plans and not pol.rejected:
            print(f"Not enough learning-mode trades yet (need {cfg.exits.min_trades_to_optimize} per setup).")
        _print({"adopted": {k: v.__dict__ for k, v in plans.items()},
                "rejected_overfit_or_no_edge": pol.rejected})
        return

    cfg = BotConfig()
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
    eng = TradingEngine(cfg, Journal(a.db), ai=ai, exit_policy=ExitPolicy(cfg.exits, POLICY),
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

    broker = make_broker(a)
    if broker.live and broker.open_positions():
        sys.exit("Broker already has an open position for this symbol — close it or manage it "
                 "manually before starting the bot (the bot does not adopt unknown positions).")
    cfg.symbol = a.symbol or a.yf
    cfg.timeframe = a.timeframe
    eng = TradingEngine(cfg, Journal(cfg.db_path), ai=ai, exit_policy=ExitPolicy(cfg.exits, POLICY),
                        intraday=a.timeframe not in ("1d", "1w", "1wk"), broker=broker)
    mode = "REAL MONEY" if a.real else ("testnet/demo" if broker.live else "paper")
    print(f"[{mode}] {broker.name} {cfg.symbol} {a.timeframe} — Ctrl+C to stop")
    last = None
    while True:
        try:
            df = broker.fetch_ohlcv(1500)
            i = len(df) - 2  # newest fully closed bar
            if i > 0 and df.index[i] != last:
                last = df.index[i]
                d = eng.step(df, i)
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
