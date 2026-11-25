from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    h, l, c = df["high"].to_numpy(), df["low"].to_numpy(), df["close"].to_numpy()
    tr = h - l
    if len(c) > 1:
        pc = c[:-1]
        tr[1:] = np.maximum.reduce([tr[1:], np.abs(h[1:] - pc), np.abs(l[1:] - pc)])
    return pd.Series(tr, index=df.index).ewm(alpha=1 / n, adjust=False).mean()


@dataclass
class Swing:
    idx: int          # bar index of the pivot
    price: float
    kind: str         # "H" or "L"
    confirmed_at: int  # first bar at which the pivot is known (no lookahead)


def find_swings(df: pd.DataFrame, left: int = 3, right: int = 3) -> list[Swing]:
    """Fractal pivots, then forced to alternate H/L keeping the extreme."""
    h, l = df["high"].to_numpy(), df["low"].to_numpy()
    n = len(df)
    raw: list[Swing] = []
    if n >= left + right + 1:
        from numpy.lib.stride_tricks import sliding_window_view as win
        idx = np.arange(left, n - right)
        lh = win(h, left)[: n - left - right].max(axis=1)        # max(h[i-left:i])
        rh = win(h[1:], right)[left: n - right].max(axis=1)      # max(h[i+1:i+right+1])
        ll = win(l, left)[: n - left - right].min(axis=1)
        rl = win(l[1:], right)[left: n - right].min(axis=1)
        hc, lc = h[idx], l[idx]
        is_h = (hc > lh) & (hc >= rh)
        is_l = (lc < ll) & (lc <= rl)
        for i, ih, il in zip(idx, is_h, is_l):
            if ih:
                raw.append(Swing(int(i), float(h[i]), "H", int(i) + right))
            if il:
                raw.append(Swing(int(i), float(l[i]), "L", int(i) + right))
    out: list[Swing] = []
    for s in raw:
        if out and out[-1].kind == s.kind:
            better = s.price > out[-1].price if s.kind == "H" else s.price < out[-1].price
            if better:
                out[-1] = s
        else:
            out.append(s)
    return out


def last_of(swings: list[Swing], kind: str) -> Swing | None:
    for s in reversed(swings):
        if s.kind == kind:
            return s
    return None


def body(df: pd.DataFrame) -> np.ndarray:
    return (df["close"] - df["open"]).abs().to_numpy()
