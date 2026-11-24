from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    pc = df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"], (df["high"] - pc).abs(), (df["low"] - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


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
    for i in range(left, n - right):
        if h[i] > h[i - left:i].max() and h[i] >= h[i + 1:i + right + 1].max():
            raw.append(Swing(i, float(h[i]), "H", i + right))
        if l[i] < l[i - left:i].min() and l[i] <= l[i + 1:i + right + 1].min():
            raw.append(Swing(i, float(l[i]), "L", i + right))
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
