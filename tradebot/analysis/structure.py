"""Market structure shared by Price Action and SMC: HH/HL/LH/LL, BOS, CHoCH."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from ..indicators import Swing


@dataclass
class StructureEvent:
    idx: int
    kind: str       # BOS_UP, BOS_DOWN, CHOCH_UP, CHOCH_DOWN
    level: float
    swing_idx: int


def label_swings(swings: list[Swing]) -> list[tuple[Swing, str]]:
    out, last_h, last_l = [], None, None
    for s in swings:
        if s.kind == "H":
            lab = "H" if last_h is None else ("HH" if s.price > last_h else "LH")
            last_h = s.price
        else:
            lab = "L" if last_l is None else ("HL" if s.price > last_l else "LL")
            last_l = s.price
        out.append((s, lab))
    return out


def swing_trend(labeled: list[tuple[Swing, str]]) -> str:
    hs = [lab for s, lab in labeled if s.kind == "H"]
    ls = [lab for s, lab in labeled if s.kind == "L"]
    if not hs or not ls:
        return "range"
    if hs[-1] == "HH" and ls[-1] == "HL":
        return "bull"
    if hs[-1] == "LH" and ls[-1] == "LL":
        return "bear"
    return "range"


def structure_events(df: pd.DataFrame, swings: list[Swing]) -> tuple[list[StructureEvent], str]:
    """Walk bars forward; a close beyond the latest confirmed swing is a break.
    Break with the prevailing state = BOS, against it = CHoCH."""
    close = df["close"].to_numpy()
    events: list[StructureEvent] = []
    state = "range"
    hi = lo = None
    hi_used = lo_used = True
    by_conf: dict[int, list[Swing]] = {}
    for s in swings:
        by_conf.setdefault(s.confirmed_at, []).append(s)
    for i in range(len(df)):
        for s in by_conf.get(i, []):
            if s.kind == "H":
                hi, hi_used = s, False
            else:
                lo, lo_used = s, False
        if hi is not None and not hi_used and close[i] > hi.price:
            kind = "BOS_UP" if state == "bull" else "CHOCH_UP"
            events.append(StructureEvent(i, kind, hi.price, hi.idx))
            state, hi_used = "bull", True
        if lo is not None and not lo_used and close[i] < lo.price:
            kind = "BOS_DOWN" if state == "bear" else "CHOCH_DOWN"
            events.append(StructureEvent(i, kind, lo.price, lo.idx))
            state, lo_used = "bear", True
    return events, state
