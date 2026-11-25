"""Export the always-on statistics in stats/ to data/dashboard/*.json for the website.
Needs only stats/ (committed), so the daily job can run it in a fresh checkout."""
import json
from pathlib import Path

import pandas as pd

OUT = Path("data/dashboard")
OUT.mkdir(parents=True, exist_ok=True)


def write(name, rows, inputs):
    meta = [{"label": "Input", "value": ", ".join(inputs)}]
    (OUT / f"{name}.json").write_text(json.dumps({"rows": rows, "meta": meta}, ensure_ascii=False))


# ---- Round 4: all assets + forward test (stats/ is the always-on record) ----
ST = Path("stats")


def csv_rows(name, cols=None, n=None):
    p = ST / name
    if not p.exists():
        return None
    df = pd.read_csv(p)
    if cols:
        df = df[[c for c in cols if c in df.columns]]
    if n:
        df = df.head(n)
    return json.loads(df.to_json(orient="records", force_ascii=False))


if (ST / "strategy1_by_asset.csv").exists():
    write("s1_assets", csv_rows("strategy1_by_asset.csv", ["rank", "asset", "class", "from", "trades", "win_rate",
                                                           "exp_r", "profit_factor", "max_losing_streak",
                                                           "cost_pct"]), ["stats/strategy1_by_asset.csv"])
    write("leaderboard", csv_rows("leaderboard.csv", ["rank", "strategy", "rr", "assets", "positive_assets",
                                                      "median_exp_r", "worst_exp_r", "win_rate",
                                                      "breakeven_win_rate", "trades", "best_asset"], 20),
          ["stats/leaderboard.csv"])
    t = pd.read_csv(ST / "technique_by_asset.csv")
    t = t[t.rr == 3.0]
    g = t.groupby(["technique", "label", "class"]).agg(pos=("exp_r", lambda x: float((x > 0).mean() * 100)),
                                                       med=("exp_r", "median"), n=("asset", "count")).reset_index()
    write("tech_by_class", json.loads(g.round(3).to_json(orient="records", force_ascii=False)),
          ["stats/technique_by_asset.csv"])
if (ST / "forward_summary.json").exists():
    fs = json.loads((ST / "forward_summary.json").read_text())
    write("forward_summary", [{"id": "forward", "start": fs["start"], "days": fs["days"], "updated": fs["updated"],
                               "assets": fs["assets"], "open": fs["open_trades"],
                               **{k: v for k, v in fs["closed"].items()}}], ["stats/forward_summary.json"])
    write("forward_assets", csv_rows("forward_by_asset.csv"), ["stats/forward_by_asset.csv"])
    write("forward_techniques", csv_rows("forward_techniques.csv") or [], ["stats/forward_techniques.csv"])
print("round 4 exported")
