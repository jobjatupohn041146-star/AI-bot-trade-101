"""Broker interface. The engine only talks to this, so the same logic runs in
backtest (simulated fills), paper trading and real/demo accounts."""
from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd


@dataclass
class Fill:
    price: float
    size: float
    ref: str | None = None      # broker order / position id


class Broker:
    name = "base"
    live = False                # True = orders leave this process

    def normalize_size(self, size: float, price: float) -> float:
        """Round DOWN to what the venue accepts (never increases risk)."""
        return size

    def open(self, direction: str, size: float, price_hint: float, stop: float,
             take_profit: float | None) -> Fill:
        raise NotImplementedError

    def close(self, fill: Fill, direction: str, price_hint: float) -> float:
        raise NotImplementedError

    def has_position(self, fill: Fill) -> bool:
        return True

    def equity(self) -> float | None:
        return None

    def open_positions(self) -> int:
        return 0

    def fetch_ohlcv(self, limit: int = 1500) -> pd.DataFrame:
        raise NotImplementedError


def round_down(x: float, step: float) -> float:
    if step <= 0:
        return x
    return math.floor(x / step + 1e-9) * step


class SimBroker(Broker):
    """Simulated fills at the hinted price (backtests and paper trading)."""
    name = "sim"

    def __init__(self, size_step: float = 0.0):
        self.size_step = size_step
        self._n = 0

    def normalize_size(self, size: float, price: float) -> float:
        return round_down(size, self.size_step)

    def open(self, direction, size, price_hint, stop, take_profit) -> Fill:
        self._n += 1
        return Fill(price_hint, size, f"sim-{self._n}")

    def close(self, fill, direction, price_hint) -> float:
        return price_hint
