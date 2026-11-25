"""Technique research, following docs/RESEARCH_PLAN.md.

  python -m tradebot.research.run select   # train + validation only
  python -m tradebot.research.run final    # one-shot test of the selected strategies
"""
from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

import pandas as pd

from .simulate import POSITIVE, load_market, simulate, stats

OUT = Path("data/research")
TRAIN = ("2019-01-01", "2024-01-01")
VAL = ("2024-01-01", "2025-07-01")
RRS = (2.0, 3.0)
NAMES = {
    "structure_bias": "โครงสร้างตลาดตามเทรนด์ (PA/SMC)", "ema_bias": "EMA 50/200 ตามเทรนด์ (PA)",
    "htf_bias": "ทิศทาง TF 4 ชม. (MTF)", "order_block": "Order Block (SMC)", "fvg": "Fair Value Gap (SMC)",
    "premium_discount": "Premium/Discount (SMC)", "sr_zone": "แนวรับ/แนวต้าน (PA)",
    "liquidity_sweep": "Liquidity Sweep (SMC)", "choch_mss": "CHoCH / MSS (SMC/ICT)",
    "candle": "Pin bar / Engulfing (PA)", "killzone": "Killzone London/NY (ICT)", "ote": "OTE 62–79% (ICT)",
    "elliott_with": "ปลายคลื่น 2 หรือ 4 (Elliott)",
}


def label(req: tuple) -> str:
    return " + ".join(NAMES[c] for c in req)


def pooled(markets, req, rr, period) -> tuple[dict, pd.DataFrame]:
    trs = [simulate(m, req, rr, *period).assign(market=m.name) for m in markets]
    tr = pd.concat(trs, ignore_index=True) if trs else pd.DataFrame()
    return stats(tr, rr), tr


def dev_markets():
    return [load_market(s, f"data/market/{s}_1h_now.csv", f"data/scans/{s}.pkl") for s in ("BTCUSDT", "ETHUSDT")]


def select() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    mk = dev_markets()
    combos = [c for k in (1, 2, 3) for c in itertools.combinations(POSITIVE, k)]
    rows = []
    for req in combos:
        for rr in RRS:
            tr_s, _ = pooled(mk, req, rr, TRAIN)
            if tr_s["trades"] == 0:
                continue
            row = {"req": list(req), "label": label(req), "size": len(req), "rr": rr,
                   **{f"train_{k}": v for k, v in tr_s.items()}}
            if tr_s["trades"] >= 100 and tr_s["exp_r"] > 0:
                va_s, _ = pooled(mk, req, rr, VAL)
                row.update({f"val_{k}": v for k, v in va_s.items()})
            rows.append(row)
    df = pd.DataFrame(rows)
    df.to_json(OUT / "all_strategies.json", orient="records", force_ascii=False, indent=1)
    singles = df[df["size"] == 1].sort_values(["rr", "train_exp_r"], ascending=[True, False])
    surv = df[(df["train_trades"] >= 100) & (df["train_exp_r"] > 0)
              & (df.get("val_trades", 0) >= 30) & (df.get("val_exp_r", -1) > 0)].copy()
    surv["score"] = surv[["train_exp_r", "val_exp_r"]].min(axis=1)
    top = surv.sort_values("score", ascending=False).head(3)
    summary = {
        "tested": int(len(df)),
        "train_positive_100": int(((df["train_trades"] >= 100) & (df["train_exp_r"] > 0)).sum()),
        "survived_validation": int(len(surv)),
        "selected": top.to_dict("records"),
    }
    (OUT / "selection.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1, default=str))
    cols = ["label", "rr", "train_trades", "train_win_rate", "breakeven", "train_exp_r", "val_trades",
            "val_win_rate", "val_exp_r"]
    singles = singles.assign(breakeven=singles["train_breakeven_win_rate"])
    print("== single techniques (train BTC+ETH 2019-2023, validation 2024-H1 2025) ==")
    print(singles.reindex(columns=cols).to_string(index=False))
    print(f"\ntested {summary['tested']} | train>0 & >=100 trades: {summary['train_positive_100']} "
          f"| also >0 on validation: {summary['survived_validation']}")
    print("\n== selected ==")
    print(top.assign(breakeven=top["train_breakeven_win_rate"]).reindex(columns=cols + ["score"]).to_string(index=False))


def final() -> None:
    sel = json.loads((OUT / "selection.json").read_text())["selected"]
    finals = [load_market(s, f"data/market/{s}_1h_now.csv", f"data/scans/{s}.pkl")
              for s in ("SOLUSDT", "XRPUSDT", "BNBUSDT")]
    gold = load_market("GOLD", "data/market/GOLD_1h_now.csv", "data/scans/GOLD.pkl")
    plan = [(m, (None, None)) for m in finals] + [(gold, ("2026-01-01", None))]
    res = []
    for s in sel:
        req, rr = tuple(s["req"]), s["rr"]
        per, trs = {}, []
        for m, period in plan:
            tr = simulate(m, req, rr, *period).assign(market=m.name)
            per[m.name] = stats(tr, rr)
            trs.append(tr)
        allt = pd.concat(trs, ignore_index=True)
        pool = stats(allt, rr)
        positive = sum(1 for v in per.values() if v.get("trades", 0) and v["exp_r"] > 0)
        passed = pool.get("exp_r", -1) > 0 and positive >= 3
        res.append({"label": s["label"], "req": s["req"], "rr": rr, "pooled": pool, "per_market": per,
                    "positive_markets": positive, "passed": passed})
        allt.to_csv(OUT / f"final_trades_{'_'.join(req)}_rr{int(rr)}.csv", index=False)
    (OUT / "final.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str))
    for r in res:
        print(f"\n{r['label']}  RR 1:{int(r['rr'])}  -> {'PASS' if r['passed'] else 'FAIL'}")
        print("  pooled:", r["pooled"])
        for k, v in r["per_market"].items():
            print(f"  {k}: trades {v.get('trades')} win {v.get('win_rate')}% exp {v.get('exp_r')}R")


if __name__ == "__main__":
    {"select": select, "final": final}[sys.argv[1]]()
