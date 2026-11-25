"""Always-on statistics: per asset x technique, a ranked leaderboard of strategies,
and the forward test of strategy #1 on bars that did not exist when it was chosen.

    PYTHONPATH=. python -m tradebot.research.ledger
Writes git-friendly files under stats/ (and a dated snapshot under stats/history/).
"""
from __future__ import annotations

import itertools
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .run import NAMES
from .simulate import POSITIVE, load_market, simulate, stats
from .universe import ALL, CLASS, cost, csv_path, scan_path

STATS = Path("stats")
RRS = (2.0, 3.0)
FORWARD_STRATEGY = ("structure_bias", "ema_bias", "htf_bias")
FORWARD_RR = 3.0
FORWARD_START = "2026-11-25"   # strategy chosen on data up to 2026-11-24
MIN_TRADES = 30


def markets():
    out = []
    for name in ALL:
        if csv_path(name).exists() and scan_path(name).exists():
            out.append(load_market(name, str(csv_path(name)), str(scan_path(name))))
    return out


def technique_table(mk) -> pd.DataFrame:
    rows = []
    for m in mk:
        first, last = str(m.times[0])[:10], str(m.times[-1])[:10]
        for comp in POSITIVE:
            for rr in RRS:
                s = stats(simulate(m, (comp,), rr, end=FORWARD_START, fee_pct=cost(m.name)), rr)
                if s.get("trades"):
                    rows.append({"asset": m.name, "class": CLASS.get(m.name, ""), "cost_pct": cost(m.name), "technique": comp,
                                 "label": NAMES[comp], "rr": rr, "from": first, "to": min(last, FORWARD_START),
                                 **s})
    return pd.DataFrame(rows)


def _asset_combos(name: str) -> list:
    m = load_market(name, str(csv_path(name)), str(scan_path(name)))
    out = []
    for req in [c for k in (1, 2, 3) for c in itertools.combinations(POSITIVE, k)]:
        for rr in RRS:
            s = stats(simulate(m, req, rr, end=FORWARD_START, fee_pct=cost(name)), rr)
            if s.get("trades", 0) >= MIN_TRADES:
                out.append((req, rr, name, s))
    return out


def leaderboard(mk, workers: int = 4) -> pd.DataFrame:
    """Rank every 1–3 technique combination by how consistently it works across assets."""
    from multiprocessing import Pool

    with Pool(workers) as pool:
        results = [r for part in pool.map(_asset_combos, [m.name for m in mk]) for r in part]
    by: dict = {}
    for req, rr, name, s in results:
        by.setdefault((req, rr), []).append((name, s))
    rows = []
    for (req, rr), per in by.items():
        if len(per) < 5:
            continue
        exps = np.array([s["exp_r"] for _, s in per])
        n = sum(s["trades"] for _, s in per)
        wins = sum(s["trades"] * s["win_rate"] / 100 for _, s in per)
        rows.append({
            "strategy": " + ".join(NAMES[c] for c in req), "components": ",".join(req), "rr": rr,
            "assets": len(per), "positive_assets": int((exps > 0).sum()),
            "positive_share": round(float((exps > 0).mean() * 100), 1),
            "median_exp_r": round(float(np.median(exps)), 3), "mean_exp_r": round(float(exps.mean()), 3),
            "worst_exp_r": round(float(exps.min()), 3), "trades": int(n),
            "win_rate": round(wins / n * 100, 1), "breakeven_win_rate": round(100 / (1 + rr), 1),
            "best_asset": max(per, key=lambda x: x[1]["exp_r"])[0],
        })
    df = pd.DataFrame(rows)
    # Rank: consistency across assets first, then typical edge. RR is always 1:2 or 1:3.
    df = df.sort_values(["positive_share", "median_exp_r", "trades"], ascending=False).reset_index(drop=True)
    df.insert(0, "rank", np.arange(1, len(df) + 1))
    return df


def forward(mk) -> tuple[pd.DataFrame, dict]:
    trades, per = [], {}
    for m in mk:
        tr = simulate(m, FORWARD_STRATEGY, FORWARD_RR, start=FORWARD_START, fee_pct=cost(m.name))
        if len(tr):
            trades.append(tr.assign(asset=m.name, cls=CLASS.get(m.name, "")))
        closed = tr[tr["exit"] != "open"] if len(tr) else tr
        per[m.name] = {"closed": int(len(closed)), "open": int((tr["exit"] == "open").sum()) if len(tr) else 0,
                       "total_r": round(float(closed["r"].sum()), 2) if len(closed) else 0.0,
                       "last_bar": str(m.times[-1])}
    tr = pd.concat(trades, ignore_index=True) if trades else pd.DataFrame(
        columns=["time", "sign", "r", "exit", "fee_r", "bars", "entry", "stop", "target", "asset", "cls"])
    s = stats(tr, FORWARD_RR)
    summary = {"strategy": " + ".join(NAMES[c] for c in FORWARD_STRATEGY), "rr": FORWARD_RR,
               "start": FORWARD_START, "assets": len(mk), "open_trades": int((tr["exit"] == "open").sum()),
               "closed": s, "per_asset": per,
               "equity_pct_at_1pct_risk": round(float(tr.loc[tr["exit"] != "open", "r"].sum()), 2)}
    return tr, summary


def strategy_by_asset(mk) -> pd.DataFrame:
    rows = []
    for m in mk:
        s = stats(simulate(m, FORWARD_STRATEGY, FORWARD_RR, end=FORWARD_START, fee_pct=cost(m.name)), FORWARD_RR)
        rows.append({"asset": m.name, "class": CLASS.get(m.name, ""), "cost_pct": cost(m.name),
                     "from": str(m.times[0])[:10], **s})
    df = pd.DataFrame(rows).sort_values("exp_r", ascending=False).reset_index(drop=True)
    df.insert(0, "rank", np.arange(1, len(df) + 1))
    return df


def main() -> None:
    STATS.mkdir(exist_ok=True)
    (STATS / "history").mkdir(exist_ok=True)
    mk = markets()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    tech = technique_table(mk)
    tech.to_csv(STATS / "technique_by_asset.csv", index=False)
    sba = strategy_by_asset(mk)
    sba.to_csv(STATS / "strategy1_by_asset.csv", index=False)
    lb = leaderboard(mk)
    lb.to_csv(STATS / "leaderboard.csv", index=False)
    snap = {"updated": now, "assets": [m.name for m in mk], "leaderboard_top10": lb.head(10).to_dict("records")}
    (STATS / "history" / f"historical_{now[:10]}.json").write_text(
        json.dumps(snap, ensure_ascii=False, indent=1, default=str))
    print(f"assets {len(mk)} | technique rows {len(tech)} | ranked strategies {len(lb)}")
    print(lb.head(15)[["rank", "strategy", "rr", "assets", "positive_assets", "median_exp_r", "win_rate",
                       "breakeven_win_rate"]].to_string(index=False))
    print(sba[["rank", "asset", "class", "trades", "win_rate", "exp_r", "profit_factor"]].to_string(index=False))


if __name__ == "__main__":
    main()
