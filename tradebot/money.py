"""Gate 3 — money management: sizing, drawdown control, kill switch."""
from __future__ import annotations

from dataclasses import dataclass

from .config import MoneyConfig


@dataclass
class SizeDecision:
    ok: bool
    size: float
    risk_pct: float
    risk_amount: float
    reasons: list


class MoneyManager:
    def __init__(self, cfg: MoneyConfig, equity: float):
        self.cfg = cfg
        self.peak = equity
        self.halted = False

    def drawdown_pct(self, equity: float) -> float:
        self.peak = max(self.peak, equity)
        return (self.peak - equity) / self.peak * 100 if self.peak else 0.0

    def risk_pct(self, equity: float) -> float:
        dd = self.drawdown_pct(equity)
        r = self.cfg.risk_per_trade_pct
        if dd >= self.cfg.drawdown_reduce_pct:
            r /= 2
        return r

    def size(self, equity: float, entry: float, stop: float, atr: float,
             open_risk_pct: float, open_positions: int, setup_disabled: bool = False) -> SizeDecision:
        c, why = self.cfg, []
        dd = self.drawdown_pct(equity)
        if dd >= c.max_drawdown_pct:
            self.halted = True
        if self.halted:
            why.append(f"KILL SWITCH: drawdown {dd:.1f}% >= {c.max_drawdown_pct}%")
        dist = abs(entry - stop)
        if atr > 0 and dist < c.min_stop_atr * atr:
            why.append("stop too tight vs ATR (noise)")
        if atr > 0 and dist > c.max_stop_atr * atr:
            why.append("stop too wide vs ATR")
        if open_positions >= c.max_positions:
            why.append("max positions open")
        if setup_disabled:
            why.append("setup disabled: negative expectancy in journal")
        rp = self.risk_pct(equity)
        if open_risk_pct + rp > c.max_open_risk_pct:
            why.append("total open risk limit")
        amount = equity * rp / 100
        size = amount / dist if dist > 0 else 0.0
        if size <= 0:
            why.append("size = 0")
        return SizeDecision(not why, size if not why else 0.0, rp, amount, why)
