"""Descriptive win rate of every single technique on every market, full history to today."""
import json
from pathlib import Path

import pandas as pd

from .run import NAMES
from .simulate import POSITIVE, load_market, simulate, stats

MARKETS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT", "GOLD"]


def main() -> None:
    mk = [load_market(s, f"data/market/{s}_1h_now.csv", f"data/scans/{s}.pkl") for s in MARKETS]
    rows = []
    for comp in POSITIVE:
        for rr in (2.0, 3.0):
            trs = []
            for m in mk:
                tr = simulate(m, (comp,), rr).assign(market=m.name)
                s = stats(tr, rr)
                if s["trades"]:
                    rows.append({"technique": comp, "label": NAMES[comp], "rr": rr, "market": m.name, **s})
                trs.append(tr)
            s = stats(pd.concat(trs, ignore_index=True), rr)
            rows.append({"technique": comp, "label": NAMES[comp], "rr": rr, "market": "ALL", **s})
    df = pd.DataFrame(rows)
    Path("data/research").mkdir(parents=True, exist_ok=True)
    df.to_json("data/research/techniques.json", orient="records", force_ascii=False, indent=1)
    allm = df[df.market == "ALL"].sort_values(["rr", "exp_r"], ascending=[True, False])
    print(allm[["label", "rr", "trades", "win_rate", "breakeven_win_rate", "exp_r", "profit_factor"]].to_string(index=False))
    pos = df[df.market != "ALL"].assign(pos=lambda d: d.exp_r > 0).groupby(["technique", "rr"]).pos.sum()
    print("\nmarkets (of 6) with positive expectancy:\n", pos.unstack().to_string())


if __name__ == "__main__":
    main()
