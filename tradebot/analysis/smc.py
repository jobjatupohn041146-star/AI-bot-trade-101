from __future__ import annotations

import numpy as np
import pandas as pd

from ..indicators import Swing, last_of
from .structure import StructureEvent


def fair_value_gaps(df: pd.DataFrame, max_age: int = 60) -> list[dict]:
    """Unmitigated FVGs. Bullish: low[i] > high[i-2]."""
    h, l, c = df["high"].to_numpy(), df["low"].to_numpy(), df["close"].to_numpy()
    n, out = len(df), []
    for i in range(max(2, n - max_age), n):
        if l[i] > h[i - 2]:
            zone = {"dir": "bull", "top": float(l[i]), "bottom": float(h[i - 2]), "idx": i}
        elif h[i] < l[i - 2]:
            zone = {"dir": "bear", "top": float(l[i - 2]), "bottom": float(h[i]), "idx": i}
        else:
            continue
        after = slice(i + 1, n)
        if zone["dir"] == "bull":
            if (c[after] < zone["bottom"]).any():
                continue  # invalidated
            zone["tested"] = bool((l[after] <= zone["top"]).any())
        else:
            if (c[after] > zone["top"]).any():
                continue
            zone["tested"] = bool((h[after] >= zone["bottom"]).any())
        out.append(zone)
    return out


def order_blocks(df: pd.DataFrame, events: list[StructureEvent], search: int = 15) -> list[dict]:
    """Last opposite candle before the break; dropped once price closes through it."""
    o, h, l, c = (df[k].to_numpy() for k in ("open", "high", "low", "close"))
    n, out = len(df), []
    for ev in events[-12:]:
        up = ev.kind.endswith("UP")
        for j in range(ev.idx - 1, max(ev.idx - search, 0) - 1, -1):
            if (up and c[j] < o[j]) or (not up and c[j] > o[j]):
                ob = {"dir": "bull" if up else "bear", "top": float(h[j]), "bottom": float(l[j]),
                      "idx": j, "event": ev.kind}
                later = c[ev.idx + 1:n]
                broken = (later < ob["bottom"]).any() if up else (later > ob["top"]).any()
                if not broken:
                    out.append(ob)
                break
    return out


def liquidity(df: pd.DataFrame, swings: list[Swing], atr_now: float, lookback: int = 3) -> dict:
    h, l, c = df["high"].to_numpy(), df["low"].to_numpy(), df["close"].to_numpy()
    n = len(df)
    highs = [s for s in swings if s.kind == "H"][-6:]
    lows = [s for s in swings if s.kind == "L"][-6:]
    tol = 0.15 * atr_now
    eqh = any(abs(a.price - b.price) <= tol for a, b in zip(highs, highs[1:]))
    eql = any(abs(a.price - b.price) <= tol for a, b in zip(lows, lows[1:]))
    swept_ssl = swept_bsl = None
    for i in range(max(0, n - lookback), n):
        for s in lows:
            if s.idx < i and l[i] < s.price < c[i] and not (l[s.idx + 1:i] < s.price).any():
                swept_ssl = {"level": s.price, "low": float(l[i]), "idx": i}
        for s in highs:
            if s.idx < i and h[i] > s.price > c[i] and not (h[s.idx + 1:i] > s.price).any():
                swept_bsl = {"level": s.price, "high": float(h[i]), "idx": i}
    return {"equal_highs": eqh, "equal_lows": eql,
            "sellside_sweep": swept_ssl, "buyside_sweep": swept_bsl}


def premium_discount(df: pd.DataFrame, swings: list[Swing]) -> dict | None:
    sh, sl = last_of(swings, "H"), last_of(swings, "L")
    if not sh or not sl or sh.price <= sl.price:
        return None
    close = float(df["close"].iloc[-1])
    pos = (close - sl.price) / (sh.price - sl.price)
    return {"range_high": sh.price, "range_low": sl.price, "position": float(pos),
            "zone": "premium" if pos > 0.5 else "discount"}


def in_zone(price: float, zones: list[dict], direction: str, pad: float = 0.0) -> dict | None:
    for z in reversed(zones):
        if z["dir"] == direction and z["bottom"] - pad <= price <= z["top"] + pad:
            return z
    return None


def analyze(df: pd.DataFrame, swings: list[Swing], events: list[StructureEvent], ind: dict) -> dict:
    close = float(df["close"].iloc[-1])
    a = ind["atr"]
    fvgs = fair_value_gaps(df)
    obs = order_blocks(df, events)
    return {
        "fvgs": fvgs[-6:],
        "order_blocks": obs[-6:],
        "in_bull_ob": in_zone(close, obs, "bull", 0.1 * a),
        "in_bear_ob": in_zone(close, obs, "bear", 0.1 * a),
        "in_bull_fvg": in_zone(close, fvgs, "bull"),
        "in_bear_fvg": in_zone(close, fvgs, "bear"),
        "liquidity": liquidity(df, swings, a),
        "premium_discount": premium_discount(df, swings),
    }
