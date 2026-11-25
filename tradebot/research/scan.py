"""Run the full multi-school analysis on every bar ONCE and store, per bar and
direction, which technique components are active plus the structural stop.
Strategies are then simulated from this table without re-analysing."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from ..analysis import analyze, htf_context
from ..data import load_csv
from ..decision.rules import _components, structural_stop

COMPONENTS = ["structure_bias", "ema_bias", "htf_bias", "order_block", "fvg", "premium_discount",
              "sr_zone", "liquidity_sweep", "choch_mss", "candle", "killzone", "ote", "elliott_with",
              "counter_trend", "htf_counter", "elliott_against"]


def scan(df: pd.DataFrame, lookback: int = 300, htf: str = "4h", htf_lookback: int = 1600,
         intraday: bool = True, progress: bool = False) -> pd.DataFrame:
    rows = []
    htf_key, htf_ctx = None, None
    for i in range(lookback, len(df)):
        window = df.iloc[i - lookback + 1: i + 1]
        ctx = analyze(window, intraday=intraday)
        # HTF bias from completed higher-timeframe bars only (same rule as the engine)
        ts, step = df.index[i], df.index[i] - df.index[i - 1]
        key = (ts + step).floor(htf)
        if key != htf_key:
            src = df.iloc[max(0, i - htf_lookback + 1): i + 1]
            htf_key, htf_ctx = key, htf_context(src[src.index < key], htf)
        ctx["htf"] = htf_ctx
        row = {"i": i, "time": ts, "atr": ctx["indicators"]["atr"], "close": ctx["close"]}
        for d, p in (("bull", "L_"), ("bear", "S_")):
            comp = _components(ctx, d)
            for k in COMPONENTS:
                row[p + k] = bool(comp.get(k, False))
            row[p + "stop"] = structural_stop(ctx, d, 0.6)
        rows.append(row)
        if progress and i % 5000 == 0:
            print(f"  {i}/{len(df)}", flush=True)
    return pd.DataFrame(rows)


if __name__ == "__main__":  # python -m tradebot.research.scan data/market/X.csv out.pkl
    src, out = sys.argv[1], sys.argv[2]
    df = load_csv(src)
    res = scan(df, intraday=True, progress=True)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    res.to_pickle(out)
    print("saved", out, len(res))
