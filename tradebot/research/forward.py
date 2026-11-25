"""Daily forward test: only bars that did not exist when the strategy was chosen.

Fetches recent history (enough warm-up for the 300-bar window and 4h bias), scans
the bars from FORWARD_START, then records:
  stats/forward_trades.csv        every forward trade of strategy #1 (open ones too)
  stats/forward_techniques.csv    each single technique's forward win rate (RR 1:2, 1:3)
  stats/forward_by_asset.csv      ranking of assets on the forward test
  stats/forward_summary.json      headline numbers
  stats/history/<date>.json       daily snapshot
    PYTHONPATH=. python -m tradebot.research.forward [--start YYYY-MM-DD]
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

from ..data import load_binance_daily, load_binance_vision, load_yfinance
from .ledger import FORWARD_RR, FORWARD_START, FORWARD_STRATEGY
from .run import NAMES
from .scan import scan
from .simulate import POSITIVE, Market, simulate, stats
from .universe import ALL, CLASS, YAHOO, cost

STATS = Path("stats")
WARMUP_DAYS = 100
CACHE = "data/market/cache"


def recent(name: str, start: pd.Timestamp) -> pd.DataFrame:
    begin = start - pd.Timedelta(days=WARMUP_DAYS)
    if name in YAHOO:
        df = load_yfinance(YAHOO[name], period="180d", interval="1h").iloc[:-1]  # drop forming bar
    else:
        today = pd.Timestamp.now(tz="UTC").normalize()
        this_month = today.replace(day=1)
        parts = []
        last_full = (this_month - pd.Timedelta(days=1)).tz_localize(None).to_period("M")
        first = begin.tz_localize(None).to_period("M")
        if first <= last_full:
            parts.append(load_binance_vision(name, "1h", str(first), str(last_full), CACHE))
        days = [d.strftime("%Y-%m-%d") for d in pd.date_range(this_month, today - pd.Timedelta(days=1))]
        parts.append(load_binance_daily(name, "1h", days, CACHE))
        df = pd.concat(parts)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df[df.index >= begin]


def one(args):
    name, start = args
    try:
        df = recent(name, start)
        first = int(np.searchsorted(df.index, start))
        sc = scan(df, start=first)
        if sc.empty:  # no closed bar after the start yet (e.g. today's archive not published)
            return name, pd.DataFrame(), pd.DataFrame(), str(df.index[-1]), None
        m = Market(name, df["open"].to_numpy(), df["high"].to_numpy(), df["low"].to_numpy(),
                   df["close"].to_numpy(), df.index, sc)
        fee = cost(name)
        tr = simulate(m, FORWARD_STRATEGY, FORWARD_RR, start=start, fee_pct=fee).assign(asset=name)
        tech = []
        for comp in POSITIVE:
            for rr in (2.0, 3.0):
                t = simulate(m, (comp,), rr, start=start, fee_pct=fee)
                if len(t):
                    tech.append(t.assign(asset=name, technique=comp, rr=rr))
        tech = pd.concat(tech, ignore_index=True) if tech else pd.DataFrame()
        return name, tr, tech, str(df.index[-1]), None
    except Exception as e:
        return name, pd.DataFrame(), pd.DataFrame(), "", f"{type(e).__name__}: {e}"


def main(start_s: str = FORWARD_START) -> None:
    start = pd.Timestamp(start_s, tz="UTC")
    STATS.mkdir(exist_ok=True)
    (STATS / "history").mkdir(exist_ok=True)
    with Pool(4) as pool:
        res = pool.map(one, [(n, start) for n in ALL])
    trades, techs, per, errors = [], [], [], {}
    for name, tr, tech, last, err in res:
        if err:
            errors[name] = err
            continue
        if len(tr):
            trades.append(tr)
        if len(tech):
            techs.append(tech)
        s = stats(tr, FORWARD_RR)
        per.append({"asset": name, "class": CLASS[name], "last_bar": last,
                    "open": int((tr["exit"] == "open").sum()) if len(tr) else 0,
                    "closed": s.get("trades", 0), "win_rate": s.get("win_rate"),
                    "total_r": s.get("total_r", 0.0), "exp_r": s.get("exp_r")})
    cols = ["time", "sign", "r", "exit", "fee_r", "bars", "entry", "stop", "target", "asset"]
    tr = pd.concat(trades, ignore_index=True) if trades else pd.DataFrame(columns=cols)
    tr.sort_values("time").to_csv(STATS / "forward_trades.csv", index=False)
    pa = pd.DataFrame(per, columns=["asset", "class", "last_bar", "open", "closed", "win_rate", "total_r", "exp_r"])
    pa = pa.sort_values(["total_r", "closed"], ascending=False).reset_index(drop=True)
    pa.insert(0, "rank", np.arange(1, len(pa) + 1))
    pa.to_csv(STATS / "forward_by_asset.csv", index=False)
    trows = []
    tech = pd.concat(techs, ignore_index=True) if techs else pd.DataFrame()
    if len(tech):
        for (comp, rr), g in tech.groupby(["technique", "rr"]):
            s = stats(g, rr)
            trows.append({"technique": comp, "label": NAMES[comp], "rr": rr,
                          "open": int((g["exit"] == "open").sum()), **s})
    ft = pd.DataFrame(trows)
    if len(ft):
        ft = ft.sort_values(["rr", "exp_r"], ascending=[True, False], na_position="last")
    ft.to_csv(STATS / "forward_techniques.csv", index=False)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    closed = stats(tr, FORWARD_RR)
    summary = {
        "updated": now, "start": start_s, "strategy": " + ".join(NAMES[c] for c in FORWARD_STRATEGY),
        "rr": FORWARD_RR, "assets": len(per), "open_trades": int((tr["exit"] == "open").sum()) if len(tr) else 0,
        "closed": closed, "days": round((pd.Timestamp.now(tz="UTC") - start).total_seconds() / 86400, 1),
        "result_pct_at_1pct_risk_per_trade": closed.get("total_r", 0.0), "errors": errors,
    }
    (STATS / "forward_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1, default=str))
    (STATS / "history" / f"{now[:10]}.json").write_text(json.dumps(
        {"forward": summary, "by_asset": pa.to_dict("records"),
         "techniques": ft.to_dict("records") if len(ft) else []}, ensure_ascii=False, indent=1, default=str))
    print(json.dumps({k: summary[k] for k in ("updated", "days", "open_trades", "closed", "errors")},
                     ensure_ascii=False, default=str))


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--start") + 1] if "--start" in sys.argv else FORWARD_START)
