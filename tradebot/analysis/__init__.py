"""Builds the full MarketContext from the four schools of analysis."""
from __future__ import annotations

import pandas as pd

from ..indicators import atr, ema, find_swings
from . import elliott, ict, price_action, smc
from .structure import label_swings, structure_events, swing_trend


def analyze(df: pd.DataFrame, intraday: bool = True) -> dict:
    """df must contain only bars up to *now* (no future data)."""
    a = atr(df)
    ind = {
        "atr": float(a.iloc[-1]),
        "ema20": float(ema(df["close"], 20).iloc[-1]),
        "ema50": float(ema(df["close"], 50).iloc[-1]),
        "ema200": float(ema(df["close"], 200).iloc[-1]),
    }
    swings = find_swings(df)
    labeled = label_swings(swings)
    events, state = structure_events(df, swings)
    last = df.iloc[-1]
    return {
        "time": df.index[-1].isoformat(),
        "close": float(last["close"]),
        "high": float(last["high"]),
        "low": float(last["low"]),
        "bar_range_atr": float((last["high"] - last["low"]) / ind["atr"]) if ind["atr"] else 0.0,
        "indicators": ind,
        "structure": {
            "swing_trend": swing_trend(labeled),
            "break_state": state,
            "last_swings": [{"idx": s.idx, "price": s.price, "label": lab} for s, lab in labeled[-6:]],
            "recent_events": [e.__dict__ for e in events[-4:]],
            "last_event_age": (len(df) - 1 - events[-1].idx) if events else None,
        },
        "swings": swings,
        "price_action": price_action.analyze(df, swings, ind),
        "smc": smc.analyze(df, swings, events, ind),
        "ict": ict.analyze(df, swings, events, ind, intraday),
        "elliott": elliott.analyze(swings),
    }


def resample(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    return df.resample(rule, label="left", closed="left").agg(agg).dropna()


def htf_context(ltf: pd.DataFrame, rule: str) -> dict | None:
    """Multi-timeframe bias: structure + EMA trend + premium/discount on the HTF."""
    htf = resample(ltf, rule)
    if len(htf) < 60:
        return None
    swings = find_swings(htf)
    events, state = structure_events(htf, swings)
    close = htf["close"]
    e50, e200 = float(ema(close, 50).iloc[-1]), float(ema(close, 200).iloc[-1])
    c = float(close.iloc[-1])
    ema_trend = "bull" if e50 > e200 and c > e50 else "bear" if e50 < e200 and c < e50 else "range"
    st = state if state != "range" else swing_trend(label_swings(swings))
    bias = st if st == ema_trend or ema_trend == "range" else "range"
    pd_zone = smc.premium_discount(htf, swings)
    return {"timeframe": rule, "structure": st, "ema_trend": ema_trend, "bias": bias,
            "zone": pd_zone["zone"] if pd_zone else None, "bars": len(htf),
            "last_event": events[-1].kind if events else None}
