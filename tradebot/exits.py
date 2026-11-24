"""Exit policy.

Learning mode  : no fixed TP. Protective stop = structural invalidation (needed
                 for sizing and survival). Position is closed after N bars so
                 every trade yields a clean excursion path (MFE/MAE).
Optimized mode : once a setup has enough samples, every SL/TP pair on a grid is
                 replayed over the recorded paths and the best expectancy wins.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .config import ExitConfig
from .journal import Journal


@dataclass
class ExitPlan:
    setup: str
    sl_mult: float          # fraction of structural stop distance (<= 1.0)
    tp_r: float | None      # target in R of the structural stop; None = learning
    max_bars: int
    mode: str               # "learning" | "optimized"
    expectancy: float | None = None
    samples: int = 0


def simulate(path: list[list[float]], final_r: float, sl: float, tp: float) -> float:
    """Return P/L in units of the *new* risk (sl). path rows are [fav_r, adv_r]
    per bar relative to the structural stop distance. Conservative: if both SL
    and TP are touched in the same bar, the stop wins."""
    for fav, adv in path:
        if adv >= sl:
            return -1.0
        if fav >= tp:
            return tp / sl
    return max(final_r, -sl) / sl


def optimize_setup(trades: list[dict], cfg: ExitConfig) -> tuple[float, float, float] | None:
    usable = [t for t in trades if t.get("path")]
    if len(usable) < cfg.min_trades_to_optimize:
        return None
    best = None
    for sl in cfg.sl_grid:
        for tp in cfg.tp_grid:
            res = [simulate(t["path"], t["r_multiple_raw"], sl, tp) for t in usable]
            exp = sum(res) / len(res)
            if best is None or exp > best[2]:
                best = (sl, tp, exp)
    return best


class ExitPolicy:
    def __init__(self, cfg: ExitConfig, store: Path | None = None):
        self.cfg = cfg
        self.store = store
        self.plans: dict[str, ExitPlan] = {}
        if store and Path(store).exists():
            for k, v in json.loads(Path(store).read_text()).items():
                self.plans[k] = ExitPlan(**v)

    def plan_for(self, setup: str) -> ExitPlan:
        return self.plans.get(setup) or ExitPlan(setup, 1.0, None, self.cfg.learning_hold_bars, "learning")

    def learn(self, journal: Journal) -> dict[str, ExitPlan]:
        """Re-fit SL/TP per setup from learning-mode paths only (unbiased by old TPs)."""
        by_setup: dict[str, list[dict]] = {}
        for t in journal.trades(mode="learning"):
            t["r_multiple_raw"] = t["path"][-1][2] if t["path"] and len(t["path"][-1]) > 2 else t["r_multiple"]
            t["path"] = [p[:2] for p in t["path"] or []]
            by_setup.setdefault(t["setup"], []).append(t)
        for setup, ts in by_setup.items():
            best = optimize_setup(ts, self.cfg)
            if best and best[2] > 0:
                sl, tp, exp = best
                self.plans[setup] = ExitPlan(setup, sl, tp, self.cfg.learning_hold_bars * 3,
                                             "optimized", round(exp, 4), len(ts))
        if self.store:
            Path(self.store).parent.mkdir(parents=True, exist_ok=True)
            Path(self.store).write_text(json.dumps({k: asdict(v) for k, v in self.plans.items()}, indent=2))
        return self.plans
