"""Summarise backtest journals: python scripts/summarize.py data/runs/dev/*.db"""
import sqlite3
import sys

import pandas as pd

rows = []
for db in sys.argv[1:]:
    t = pd.read_sql("select setup, pnl, r_multiple, risk_amount from trades order by id", sqlite3.connect(db))
    if t.empty:
        rows.append({"run": db, "trades": 0})
        continue
    eq = 10_000 + t.pnl.cumsum()
    dd = ((eq.cummax() - eq) / eq.cummax()).max() * 100
    by = t.groupby("setup").r_multiple.agg(["count", "mean"]).round(3)
    rows.append({"run": db.split("/")[-1], "trades": len(t), "net_R": round(t.r_multiple.sum(), 1),
                 "exp_R": round(t.r_multiple.mean(), 3), "win%": round((t.r_multiple > 0).mean() * 100, 1),
                 "return%": round((eq.iloc[-1] / 10_000 - 1) * 100, 1), "maxDD%": round(dd, 1),
                 "setups": "; ".join(f"{k}:{int(v['count'])}/{v['mean']:+.2f}" for k, v in by.iterrows())})
print(pd.DataFrame(rows).to_string(index=False))
