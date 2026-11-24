from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE_DIR = ROOT / "knowledge"
DATA_DIR = ROOT / "data"


@dataclass
class PsychologyConfig:
    max_consecutive_losses: int = 3       # tilt guard
    tilt_cooldown_bars: int = 24          # pause after hitting the loss streak
    loss_cooldown_bars: int = 3           # anti-revenge pause after any loss
    max_trades_per_day: int = 4           # anti-overtrading
    daily_loss_limit_pct: float = 3.0     # stop for the day
    fomo_ema_atr: float = 3.0             # price stretched from EMA20 by > N ATR
    fomo_candle_atr: float = 3.0          # chasing a giant candle
    min_confidence: float = 0.55


@dataclass
class MoneyConfig:
    risk_per_trade_pct: float = 1.0
    drawdown_reduce_pct: float = 10.0     # halve risk beyond this drawdown
    max_drawdown_pct: float = 20.0        # kill switch
    max_open_risk_pct: float = 3.0
    max_positions: int = 1
    min_stop_atr: float = 0.5
    max_stop_atr: float = 4.0
    disable_setup_after: int = 30         # trades before a losing setup is disabled


@dataclass
class ExitConfig:
    learning_hold_bars: int = 24          # time exit while collecting stats
    min_trades_to_optimize: int = 30      # per setup
    sl_grid: tuple = (0.5, 0.6, 0.7, 0.8, 0.9, 1.0)          # fraction of structural stop
    tp_grid: tuple = (0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0)  # in R of structural stop


@dataclass
class AIConfig:
    enabled: bool = False                 # use Claude for the final decision
    model: str = "claude-opus-5-5"
    effort: str = "medium"
    prefilter_score: float = 0.35         # only ask Claude when rules see a candidate


@dataclass
class BotConfig:
    symbol: str = "XAUUSD"
    timeframe: str = "1h"
    initial_equity: float = 10_000.0
    commission_pct: float = 0.0
    lookback_bars: int = 300
    min_score: float = 0.55
    require_learning: bool = True
    db_path: Path = DATA_DIR / "journal.db"
    psychology: PsychologyConfig = field(default_factory=PsychologyConfig)
    money: MoneyConfig = field(default_factory=MoneyConfig)
    exits: ExitConfig = field(default_factory=ExitConfig)
    ai: AIConfig = field(default_factory=AIConfig)
