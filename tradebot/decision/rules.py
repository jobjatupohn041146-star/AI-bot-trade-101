"""Gate 2 — technical confluence across PA / SMC / ICT / Elliott.
Produces a score in [0, 1], the dominant setup name and a structural
invalidation level (used only for sizing / protective stop)."""
from __future__ import annotations

from dataclasses import dataclass, field

WEIGHTS = {
    "structure_bias": 2.0, "ema_bias": 1.0, "counter_trend": -2.0,
    "order_block": 2.0, "fvg": 1.0, "premium_discount": 1.0, "sr_zone": 1.0,
    "liquidity_sweep": 2.0, "choch_mss": 1.5, "candle": 1.0, "killzone": 0.5, "ote": 1.0,
    "elliott_with": 1.5, "elliott_against": -2.0,
}
MAX_SCORE = sum(v for v in WEIGHTS.values() if v > 0)

SETUP_GROUPS = {
    "SMC_OB_FVG": ("order_block", "fvg", "premium_discount"),
    "LIQ_SWEEP_REVERSAL": ("liquidity_sweep", "choch_mss"),
    "ICT_OTE_KILLZONE": ("ote", "killzone", "choch_mss"),
    "PA_SR_CANDLE": ("sr_zone", "candle"),
    "EW_WAVE_ENTRY": ("elliott_with",),
}


@dataclass
class Signal:
    direction: str            # "long" / "short"
    score: float
    setup: str
    components: dict
    stop: float
    reasons: list = field(default_factory=list)


def _components(ctx: dict, d: str) -> dict:
    bull = d == "bull"
    st, pa, smc, ict, ew = (ctx[k] for k in ("structure", "price_action", "smc", "ict", "elliott"))
    comp: dict[str, bool] = {}
    trend = st["break_state"] if st["break_state"] != "range" else st["swing_trend"]
    comp["structure_bias"] = trend == d
    comp["counter_trend"] = trend not in (d, "range")
    comp["ema_bias"] = pa["ema_trend"] == d
    comp["order_block"] = bool(smc["in_bull_ob"] if bull else smc["in_bear_ob"])
    comp["fvg"] = bool(smc["in_bull_fvg"] if bull else smc["in_bear_fvg"])
    pdz = smc["premium_discount"]
    comp["premium_discount"] = bool(pdz and pdz["zone"] == ("discount" if bull else "premium"))
    comp["sr_zone"] = pa["at_support"] if bull else pa["at_resistance"]
    liq = smc["liquidity"]
    comp["liquidity_sweep"] = bool(liq["sellside_sweep"] if bull else liq["buyside_sweep"])
    ev = st["recent_events"][-1] if st["recent_events"] else None
    fresh = st["last_event_age"] is not None and st["last_event_age"] <= 10
    comp["choch_mss"] = bool(
        (ict["mss"] and ict["mss"]["dir"] == d)
        or (fresh and ev and ev["kind"] == ("CHOCH_UP" if bull else "CHOCH_DOWN")))
    cd = pa["candle"]
    comp["candle"] = (cd["bullish_pin"] or cd["bullish_engulf"]) if bull else (cd["bearish_pin"] or cd["bearish_engulf"])
    comp["killzone"] = bool(ict["in_active_killzone"])
    o = ict["ote"]
    comp["ote"] = bool(o and o["in_ote"] and o["leg_dir"] == d)
    comp["elliott_with"] = ew["bias"] == d and not str(ew["count"]).startswith("impulse_complete")
    comp["elliott_against"] = bool(ew["count"]) and ew["bias"] not in (None, d)
    return comp


def structural_stop(ctx: dict, d: str) -> float:
    """Invalidation: beyond the zone / swept wick / last swing, plus a buffer."""
    a = ctx["indicators"]["atr"]
    close, smc = ctx["close"], ctx["smc"]
    cands = []
    if d == "bull":
        if smc["in_bull_ob"]:
            cands.append(smc["in_bull_ob"]["bottom"])
        if smc["liquidity"]["sellside_sweep"]:
            cands.append(smc["liquidity"]["sellside_sweep"]["low"])
        lows = [s.price for s in ctx["swings"] if s.kind == "L" and s.price < close]
        if lows:
            cands.append(lows[-1])
        stop = min(cands) - 0.2 * a if cands else close - 1.5 * a
        return max(min(stop, close - 0.6 * a), close - 3.5 * a)
    if smc["in_bear_ob"]:
        cands.append(smc["in_bear_ob"]["top"])
    if smc["liquidity"]["buyside_sweep"]:
        cands.append(smc["liquidity"]["buyside_sweep"]["high"])
    highs = [s.price for s in ctx["swings"] if s.kind == "H" and s.price > close]
    if highs:
        cands.append(highs[-1])
    stop = max(cands) + 0.2 * a if cands else close + 1.5 * a
    return min(max(stop, close + 0.6 * a), close + 3.5 * a)


def evaluate(ctx: dict) -> Signal | None:
    best = None
    for d in ("bull", "bear"):
        comp = _components(ctx, d)
        raw = sum(WEIGHTS[k] for k, on in comp.items() if on)
        score = max(0.0, raw) / MAX_SCORE
        # The dominant setup = group with the most weight switched on.
        group_w = {g: sum(WEIGHTS[k] for k in ks if comp[k]) for g, ks in SETUP_GROUPS.items()}
        setup = max(group_w, key=group_w.get)
        if group_w[setup] == 0:
            continue
        sig = Signal("long" if d == "bull" else "short", score, setup, comp,
                     structural_stop(ctx, d), [k for k, on in comp.items() if on])
        if best is None or sig.score > best.score:
            best = sig
    return best


def confidence_from_score(score: float, min_score: float) -> float:
    """Map confluence score into a confidence used by the psychology gate."""
    if score <= 0:
        return 0.0
    return min(1.0, 0.55 * score / max(min_score, 1e-9))
