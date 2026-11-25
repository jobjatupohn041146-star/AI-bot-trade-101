"""Fast fixed risk:reward simulation over a pre-computed scan.

Entry  : open of the bar after the signal
Stop   : structural invalidation from the scan (Price Action / SMC levels)
Target : entry ± RR × risk
Exit   : stop or target, stop first if both touch in one bar (conservative);
         otherwise close after `max_hold` bars
Costs  : fee % per side, converted to R
One position at a time per strategy.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

POSITIVE = ["structure_bias", "ema_bias", "htf_bias", "order_block", "fvg", "premium_discount", "sr_zone",
            "liquidity_sweep", "choch_mss", "candle", "killzone", "ote", "elliott_with"]


@dataclass
class Market:
    name: str
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray
    times: pd.DatetimeIndex
    scan: pd.DataFrame


def load_market(name: str, csv: str, scan_pkl: str) -> Market:
    from ..data import load_csv

    df = load_csv(csv)
    sc = pd.read_pickle(scan_pkl)
    return Market(name, df["open"].to_numpy(), df["high"].to_numpy(), df["low"].to_numpy(),
                  df["close"].to_numpy(), df.index, sc)


def signals(m: Market, required: tuple, start=None, end=None) -> pd.DataFrame:
    sc = m.scan
    mask = pd.Series(True, index=sc.index)
    if start is not None:
        mask &= sc["time"] >= pd.Timestamp(start, tz="UTC")
    if end is not None:
        mask &= sc["time"] < pd.Timestamp(end, tz="UTC")
    L = mask.copy()
    S = mask.copy()
    for c in required:
        L &= sc["L_" + c]
        S &= sc["S_" + c]
    both = L & S
    L, S = L & ~both, S & ~both
    out = pd.concat([sc.loc[L, ["i", "time", "L_stop"]].rename(columns={"L_stop": "stop"}).assign(sign=1),
                     sc.loc[S, ["i", "time", "S_stop"]].rename(columns={"S_stop": "stop"}).assign(sign=-1)])
    return out.sort_values("i")


def simulate(m: Market, required: tuple, rr: float, start=None, end=None, max_hold: int = 240,
             fee_pct: float = 0.05) -> pd.DataFrame:
    sig = signals(m, required, start, end)
    n = len(m.o)
    busy = -1
    rec = []
    for i, ts, stop, sign in sig[["i", "time", "stop", "sign"]].itertuples(index=False):
        if i <= busy or i + 1 >= n:
            continue
        e = i + 1
        entry = m.o[e]
        risk = (entry - stop) * sign
        if risk <= entry * 1e-5:
            continue
        tp = entry + sign * rr * risk
        last = min(n, e + max_hold)
        hi, lo = m.h[e:last], m.l[e:last]
        if sign > 0:
            sl_hit, tp_hit = lo <= stop, hi >= tp
        else:
            sl_hit, tp_hit = hi >= stop, lo <= tp
        k_sl = int(np.argmax(sl_hit)) if sl_hit.any() else None
        k_tp = int(np.argmax(tp_hit)) if tp_hit.any() else None
        if k_sl is not None and (k_tp is None or k_sl <= k_tp):
            r, k, how = -1.0, k_sl, "sl"
            gap = (m.o[e + k] - stop) * sign  # gapped through the stop
            if k > 0 and gap < 0:
                r = -1.0 + gap / risk
        elif k_tp is not None:
            r, k, how = rr, k_tp, "tp"
        else:
            k = last - e - 1
            r, how = (m.c[e + k] - entry) * sign / risk, "time"
        fee_r = 2 * fee_pct / 100 * entry / risk
        rec.append((ts, sign, r - fee_r, how, fee_r, k + 1))
        busy = e + k
    return pd.DataFrame(rec, columns=["time", "sign", "r", "exit", "fee_r", "bars"])


def stats(tr: pd.DataFrame, rr: float | None = None) -> dict:
    if tr.empty:
        return {"trades": 0}
    r = tr["r"]
    wins, losses = r[r > 0], r[r <= 0]
    eq = r.cumsum()
    streak = mx = 0
    for x in r:
        streak = streak + 1 if x <= 0 else 0
        mx = max(mx, streak)
    out = {
        "trades": int(len(r)),
        "win_rate": round(float((r > 0).mean() * 100), 1),
        "tp_rate": round(float((tr["exit"] == "tp").mean() * 100), 1),
        "exp_r": round(float(r.mean()), 3),
        "total_r": round(float(r.sum()), 1),
        "profit_factor": round(float(wins.sum() / -losses.sum()), 2) if losses.sum() < 0 else None,
        "max_dd_r": round(float((eq.cummax() - eq).max()), 1),
        "max_losing_streak": int(mx),
        "avg_fee_r": round(float(tr["fee_r"].mean()), 3),
        "avg_bars": round(float(tr["bars"].mean()), 1),
    }
    if rr:
        out["breakeven_win_rate"] = round(100 / (1 + rr), 1)
    return out
