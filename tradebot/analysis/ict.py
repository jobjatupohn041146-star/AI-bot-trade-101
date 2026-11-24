from __future__ import annotations

import pandas as pd

from ..indicators import Swing
from .structure import StructureEvent

KILLZONES = {  # UTC hours, [start, end)
    "asia": (0, 6),
    "london": (7, 10),
    "ny_am": (12, 15),
    "london_close": (15, 17),
}
ACTIVE_KILLZONES = ("london", "ny_am")


def killzone(ts: pd.Timestamp, intraday: bool) -> str | None:
    if not intraday:
        return None
    for name, (a, b) in KILLZONES.items():
        if a <= ts.hour < b:
            return name
    return None


def displacement(df: pd.DataFrame, atr_now: float, lookback: int = 6, mult: float = 1.5) -> dict | None:
    o, c = df["open"].to_numpy(), df["close"].to_numpy()
    n = len(df)
    for i in range(n - 1, max(n - lookback, 0) - 1, -1):
        if abs(c[i] - o[i]) >= mult * atr_now:
            return {"dir": "bull" if c[i] > o[i] else "bear", "idx": i}
    return None


def ote(df: pd.DataFrame, swings: list[Swing]) -> dict | None:
    """Retracement of the most recent leg (last two swings)."""
    if len(swings) < 2:
        return None
    a, b = swings[-2], swings[-1]
    close = float(df["close"].iloc[-1])
    leg = b.price - a.price
    if leg == 0:
        return None
    retr = (b.price - close) / leg  # fraction retraced back toward a
    leg_dir = "bull" if leg > 0 else "bear"
    return {"leg_dir": leg_dir, "retracement": float(retr), "in_ote": bool(0.62 <= retr <= 0.79)}


def asian_range_sweep(df: pd.DataFrame) -> dict | None:
    """Judas swing: today's London/NY took out the Asian high or low."""
    ts = df.index[-1]
    day = df[df.index.normalize() == ts.normalize()]
    asia = day[(day.index.hour >= 0) & (day.index.hour < 6)]
    after = day[day.index.hour >= 7]
    if len(asia) < 3 or after.empty:
        return None
    return {"asia_high": float(asia["high"].max()), "asia_low": float(asia["low"].min()),
            "swept_high": bool(after["high"].max() > asia["high"].max()),
            "swept_low": bool(after["low"].min() < asia["low"].min())}


def analyze(df: pd.DataFrame, swings: list[Swing], events: list[StructureEvent], ind: dict, intraday: bool) -> dict:
    n = len(df)
    disp = displacement(df, ind["atr"])
    recent = [e for e in events if e.idx >= n - 12]
    mss = None
    for e in reversed(recent):
        if e.kind.startswith("CHOCH") and disp:
            want = "bull" if e.kind.endswith("UP") else "bear"
            if disp["dir"] == want and abs(disp["idx"] - e.idx) <= 4:
                mss = {"dir": want, "idx": e.idx}
                break
    return {
        "killzone": killzone(df.index[-1], intraday),
        "in_active_killzone": killzone(df.index[-1], intraday) in ACTIVE_KILLZONES,
        "displacement": disp,
        "mss": mss,
        "ote": ote(df, swings),
        "asian_sweep": asian_range_sweep(df) if intraday else None,
    }
