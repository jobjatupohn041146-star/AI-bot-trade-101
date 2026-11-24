# Frozen configuration (committed BEFORE looking at the hold-out data)

Selected on BTCUSDT 1h 2019–2023 (train), confirmed on 2024-01 → 2025-10 (validation).

```
python -m tradebot backtest --hold 48      # everything else = defaults
```
- learning_hold_bars = 48 (was 24)
- no optimized SL/TP policy (the only candidate, SMC_OB_FVG sl=0.6/tp=5R, failed validation)
- fees 0.05% per side, risk 1%, HTF 4h, all setups enabled

Hold-out sets (never used for any decision):
1. BTCUSDT 1h 2025-11-01 → 2026-10-31
2. ETHUSDT 1h 2023-01-01 → 2026-10-31 (different market)

Pass criteria, fixed in advance: expectancy > 0R after fees on BOTH sets, and max drawdown < 20%.
Compared against: the original config (hold 24) and buy & hold.
