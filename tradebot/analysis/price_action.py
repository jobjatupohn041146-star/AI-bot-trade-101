from __future__ import annotations

import numpy as np
import pandas as pd

from ..indicators import Swing


def candle_pattern(df: pd.DataFrame) -> dict:
    """Pattern on the last closed bar."""
    o, h, l, c = (df[k].to_numpy() for k in ("open", "high", "low", "close"))
    rng = max(h[-1] - l[-1], 1e-12)
    bd = abs(c[-1] - o[-1])
    upper, lower = h[-1] - max(o[-1], c[-1]), min(o[-1], c[-1]) - l[-1]
    res = {"bullish_pin": False, "bearish_pin": False, "bullish_engulf": False,
           "bearish_engulf": False, "inside_bar": False}
    if lower >= 2 * bd and lower >= 0.6 * rng:
        res["bullish_pin"] = True
    if upper >= 2 * bd and upper >= 0.6 * rng:
        res["bearish_pin"] = True
    if len(df) >= 2:
        if c[-1] > o[-1] and c[-2] < o[-2] and c[-1] >= o[-2] and o[-1] <= c[-2]:
            res["bullish_engulf"] = True
        if c[-1] < o[-1] and c[-2] > o[-2] and c[-1] <= o[-2] and o[-1] >= c[-2]:
            res["bearish_engulf"] = True
        res["inside_bar"] = bool(h[-1] < h[-2] and l[-1] > l[-2])
    return res


def sr_levels(swings: list[Swing], atr_now: float, tol_atr: float = 0.5) -> list[dict]:
    """Cluster swing prices into S/R zones; touches = strength."""
    levels: list[dict] = []
    for s in sorted(swings, key=lambda x: x.price):
        if levels and abs(s.price - levels[-1]["price"]) <= tol_atr * atr_now:
            lv = levels[-1]
            lv["price"] = (lv["price"] * lv["touches"] + s.price) / (lv["touches"] + 1)
            lv["touches"] += 1
        else:
            levels.append({"price": s.price, "touches": 1})
    return levels


def analyze(df: pd.DataFrame, swings: list[Swing], ind: dict) -> dict:
    close = float(df["close"].iloc[-1])
    a = ind["atr"]
    levels = [lv for lv in sr_levels(swings, a) if lv["touches"] >= 2]
    sup = [lv for lv in levels if lv["price"] <= close]
    res = [lv for lv in levels if lv["price"] > close]
    near_sup = max(sup, key=lambda x: x["price"]) if sup else None
    near_res = min(res, key=lambda x: x["price"]) if res else None
    ema_trend = "bull" if ind["ema50"] > ind["ema200"] and close > ind["ema50"] else \
        "bear" if ind["ema50"] < ind["ema200"] and close < ind["ema50"] else "range"
    return {
        "ema_trend": ema_trend,
        "candle": candle_pattern(df),
        "support": near_sup,
        "resistance": near_res,
        "at_support": bool(near_sup and (close - near_sup["price"]) <= 0.75 * a),
        "at_resistance": bool(near_res and (near_res["price"] - close) <= 0.75 * a),
        "dist_ema20_atr": float((close - ind["ema20"]) / a) if a else 0.0,
    }
