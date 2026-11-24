"""Export backtest journals to JSON files for the results dashboard."""
import json
import sqlite3
from pathlib import Path

import pandas as pd

RUNS = Path("data/runs")
OUT = Path("data/dashboard")
OUT.mkdir(parents=True, exist_ok=True)
CODE = Path(__file__).read_text()
START = 10_000.0


def trades(db):
    return pd.read_sql("select setup, pnl, r_multiple, entry, stop, exit_time from trades order by id",
                       sqlite3.connect(db))


def summary(db, fees_in_backtest=True):
    t = trades(db)
    eq = START + t.pnl.cumsum()
    peak = pd.concat([pd.Series([START]), eq]).cummax().iloc[1:]
    r = t.r_multiple
    if not fees_in_backtest:  # round 1 ran without fees: subtract 0.05%/side in R
        r = r - 0.001 * t.entry / (t.entry - t.stop).abs()
    return {"trades": int(len(t)), "exp_r": round(float(r.mean()), 3),
            "return_pct": round(float(eq.iloc[-1] / START - 1) * 100, 1),
            "max_dd_pct": round(float(((peak - eq) / peak).max() * 100), 1),
            "win_pct": round(float((r > 0).mean() * 100), 1)}


def write(name, rows, inputs):
    meta = [{"label": "export_dashboard.py", "value": CODE, "type": "code", "lang": "python"},
            {"label": "Input", "value": ", ".join(inputs)}]
    (OUT / f"{name}.json").write_text(json.dumps({"rows": rows, "meta": meta}, ensure_ascii=False))


# Hold-out (final, one-shot test)
bh = {"BTC": -29.3, "ETH": 88.9}
period = {"BTC": "พ.ย. 2025 – ต.ค. 2026", "ETH": "ม.ค. 2023 – ต.ค. 2026"}
rows, eq_rows, setup_rows = [], [], []
for m in ("BTC", "ETH"):
    for cfg, label in (("A", "กฎเดิม (ถือ 24 แท่ง)"), ("E", "ชุดที่ล็อกไว้ (ถือ 48 แท่ง)")):
        db = RUNS / "holdout" / f"{m.lower()}_{cfg}.db"
        s = summary(db)
        rows.append({"id": f"{m}-{cfg}", "market": m, "period": period[m], "config": cfg, "config_label": label,
                     **s, "buy_hold_pct": bh[m]})
        t = trades(db)
        eq = (START + t.pnl.cumsum()).round(2)
        for i, (ts, e) in enumerate(zip(t.exit_time, eq), 1):
            eq_rows.append({"series": f"{m}-{cfg}", "market": m, "config": cfg, "trade_no": i,
                            "date": ts[:10], "equity": float(e)})
        for setup, g in t.groupby("setup"):
            setup_rows.append({"id": f"{m}-{cfg}-{setup}", "market": m, "config": cfg, "setup": setup,
                               "trades": int(len(g)), "avg_r": round(float(g.r_multiple.mean()), 3),
                               "total_r": round(float(g.r_multiple.sum()), 1)})
write("holdout", rows, ["data/runs/holdout/*.db"])
write("holdout_equity", eq_rows, ["data/runs/holdout/*.db"])
write("holdout_setups", setup_rows, ["data/runs/holdout/*.db"])

# Tuning on BTC 2019–2023
desc = {"A": "กฎเดิม (ถือ 24 แท่ง)", "B": "stop ≥ 1.0 ATR + กรองค่าธรรมเนียม",
        "C": "stop ≥ 1.5 ATR + กรองค่าธรรมเนียม", "D": "B + เฉพาะ 2 setup",
        "E": "ถือ 48 แท่ง", "F": "เทรดตาม TF ใหญ่เท่านั้น", "G": "คะแนนขั้นต่ำ 0.65",
        "H": "G + เทรดตาม TF ใหญ่"}
write("tuning", [{"config": k, "change": v, **summary(RUNS / "dev" / f"{k}.db")} for k, v in desc.items()],
      ["data/runs/dev/*.db"])

# Validation on BTC 2024-01 → 2025-10
vdesc = {"A": "กฎเดิม (ถือ 24 แท่ง)", "E": "ถือ 48 แท่ง",
         "E_pol": "ถือ 48 แท่ง + TP/SL จาก learn-exits"}
write("validation", [{"config": k, "change": v, **summary(RUNS / "val" / f"{k}.db")} for k, v in vdesc.items()],
      ["data/runs/val/*.db"])

# Round 1 (no fees inside the backtest; fees subtracted here)
r1 = [("BTC 1h", "2019–2023", "btc_learn"), ("BTC 1h", "2024 – ต.ค. 2025", "btc_oos_base"),
      ("ทองคำ 1h", "ก.ค. 2024 – ธ.ค. 2025", "gold_learn"), ("ทองคำ 1d", "2000–2017", "goldd_learn")]
write("round1", [{"id": db, "market": m, "period": p, **summary(RUNS / f"{db}.db", fees_in_backtest=False)}
                 for m, p, db in r1], ["data/runs/*.db"])
print("ok", [p.name for p in OUT.iterdir()])
