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
    expectancy: float | None = None       # in-sample (train)
    samples: int = 0
    test_expectancy: float | None = None  # out-of-sample check
    test_samples: int = 0


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


def expectancy(trades: list[dict], sl: float, tp: float) -> float:
    res = [simulate(t["path"], t["r_multiple_raw"], sl, tp) for t in trades]
    return sum(res) / len(res) if res else 0.0


def optimize_setup(trades: list[dict], cfg: ExitConfig, min_trades: int | None = None
                   ) -> tuple[float, float, float] | None:
    usable = [t for t in trades if t.get("path")]
    if len(usable) < (cfg.min_trades_to_optimize if min_trades is None else min_trades):
        return None
    best = None
    for sl in cfg.sl_grid:
        for tp in cfg.tp_grid:
            exp = expectancy(usable, sl, tp)
            if best is None or exp > best[2]:
                best = (sl, tp, exp)
    return best


class ExitPolicy:
    def __init__(self, cfg: ExitConfig, store: Path | None = None):
        self.cfg = cfg
        self.store = store
        self.plans: dict[str, ExitPlan] = {}
        self.rejected: dict[str, dict] = {}
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
            if len(ts) < self.cfg.min_trades_to_optimize:
                continue
            # Walk-forward: fit on the older trades, verify on the newer ones.
            ts.sort(key=lambda t: t["entry_time"])
            cut = int(len(ts) * self.cfg.train_fraction)
            train, test = ts[:cut], ts[cut:]
            best = optimize_setup(train, self.cfg, min_trades=1)
            if not best:
                continue
            sl, tp, exp = best
            test_exp = expectancy(test, sl, tp)
            baseline = expectancy(test, 1.0, float("inf"))  # learning-mode exits
            if exp > 0 and test_exp > 0 and test_exp >= baseline:
                self.plans[setup] = ExitPlan(setup, sl, tp, self.cfg.learning_hold_bars * 3, "optimized",
                                             round(exp, 4), len(train), round(test_exp, 4), len(test))
            else:
                self.plans.pop(setup, None)
                self.rejected[setup] = {"train_exp": round(exp, 4), "test_exp": round(test_exp, 4),
                                        "baseline_test_exp": round(baseline, 4)}
        if self.store:
            Path(self.store).parent.mkdir(parents=True, exist_ok=True)
            Path(self.store).write_text(json.dumps({k: asdict(v) for k, v in self.plans.items()}, indent=2))
        return self.plans
