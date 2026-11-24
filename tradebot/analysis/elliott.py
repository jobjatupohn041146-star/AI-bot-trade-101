"""Simplified Elliott Wave counter. Validates the three hard rules on the most
recent swings and reports where we probably are. Probabilistic by design."""
from __future__ import annotations

from ..indicators import Swing


def _impulse_ok(p: list[float], up: bool) -> tuple[bool, dict]:
    """p = prices of points 0..k (k<=5). Check the rules that apply so far."""
    s = 1 if up else -1
    w = [s * (p[i + 1] - p[i]) for i in range(len(p) - 1)]  # signed legs
    info: dict = {}
    if len(w) >= 1 and w[0] <= 0:
        return False, info
    if len(w) >= 2:
        if w[1] >= 0 or -w[1] >= w[0]:          # rule 1: wave 2 < 100% of wave 1
            return False, info
        info["w2_retrace"] = -w[1] / w[0]
    if len(w) >= 3 and w[2] <= 0:
        return False, info
    if len(w) >= 4:
        if w[3] >= 0:
            return False, info
        if s * (p[4] - p[1]) <= 0:              # rule 3: no overlap with wave 1
            return False, info
        info["w4_retrace"] = -w[3] / w[2]
    if len(w) >= 5:
        if w[4] <= 0:
            return False, info
        if w[2] < w[0] and w[2] < w[4]:         # rule 2: wave 3 not the shortest
            return False, info
        info["w3_ext"] = w[2] / w[0]
    return True, info


def analyze(swings: list[Swing]) -> dict:
    best = {"count": None, "bias": None, "confidence": 0.0}
    pts = swings[-6:]
    for k in (5, 4, 2):  # complete impulse, end of wave 4, end of wave 2
        if len(pts) < k + 1:
            continue
        seq = pts[-(k + 1):]
        prices = [x.price for x in seq]
        for up in (True, False):
            start_kind = "L" if up else "H"
            if seq[0].kind != start_kind:
                continue
            ok, info = _impulse_ok(prices, up)
            if not ok:
                continue
            d = "bull" if up else "bear"
            if k == 5:
                conf = 0.5 + (0.2 if 1.3 <= info.get("w3_ext", 0) <= 2.0 else 0)
                return {"count": f"impulse_complete_{d}", "bias": "bear" if up else "bull",
                        "confidence": conf, **info}
            if k == 4:
                fib = 0.2 <= info.get("w4_retrace", 0) <= 0.5
                return {"count": f"wave4_end_{d}", "bias": d,
                        "confidence": 0.45 + (0.15 if fib else 0), **info}
            fib = 0.38 <= info.get("w2_retrace", 0) <= 0.79
            best = {"count": f"wave2_end_{d}", "bias": d,
                    "confidence": 0.4 + (0.2 if fib else 0), **info}
            return best
    return best
