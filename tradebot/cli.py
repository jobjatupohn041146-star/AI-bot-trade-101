"""Command line:
  python -m tradebot study [--claude]          # learn the curriculum first
  python -m tradebot status                    # learned? stats? exit policy?
  python -m tradebot backtest [--csv f] [--ai] # paper-trade history bar by bar
  python -m tradebot learn-exits               # fit SL/TP from journal stats
  python -m tradebot paper --yf GC=F --ai      # live PAPER trading loop
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
    pp = sub.add_parser("paper", help="poll live data and paper-trade the newest closed bar")
    pp.add_argument("--yf", required=True)
    pp.add_argument("--interval", default="1h")
    pp.add_argument("--poll", type=int, default=60, help="seconds between polls")
    pp.add_argument("--ai", action="store_true")
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
        plans = ExitPolicy(cfg.exits, POLICY).learn(Journal(cfg.db_path))
        if not plans:
            print(f"Not enough learning-mode trades yet (need {cfg.exits.min_trades_to_optimize} per setup).")
        _print({k: v.__dict__ for k, v in plans.items()})
        return

    cfg = BotConfig()
    ok, msg = curriculum.is_learned()
    if cfg.require_learning and not ok:
        sys.exit(f"Refusing to trade: {msg}")
    ai = None
    if a.ai:
        from .decision.claude_agent import ClaudeTrader

        ai = ClaudeTrader(curriculum.load_playbook(), cfg.ai.model, cfg.ai.effort)
    if a.cmd == "paper":
        return paper_loop(cfg, a, ai)
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


def paper_loop(cfg: BotConfig, a, ai) -> None:
    """Paper trading only: no real orders are sent anywhere."""
    import time

    eng = TradingEngine(cfg, Journal(cfg.db_path), ai=ai, exit_policy=ExitPolicy(cfg.exits, POLICY),
                        intraday=a.interval not in ("1d", "1wk"))
    last = None
    print(f"PAPER trading {a.yf} {a.interval} — Ctrl+C to stop")
    while True:
        try:
            df = load_yfinance(a.yf, period="60d", interval=a.interval)
            i = len(df) - 2  # newest fully closed bar
            if i > 0 and df.index[i] != last:
                last = df.index[i]
                d = eng.step(df, i)
                pos = eng.position.__dict__ if eng.position else None
                _print({"bar": str(last), "equity": round(eng.equity, 2), "decision": d,
                        "position": {k: pos[k] for k in ("direction", "setup", "entry", "stop", "take_profit", "size")} if pos else None})
        except KeyboardInterrupt:
            break
        except Exception as e:  # keep the loop alive on data hiccups
            print("poll error:", e)
        try:
            time.sleep(a.poll)
        except KeyboardInterrupt:
            break
