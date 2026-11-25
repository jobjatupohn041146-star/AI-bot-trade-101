# Technique research plan (written BEFORE any result was seen)

## Question
Which of the techniques taught to the bot (Price Action, SMC, ICT, Elliott Wave), alone or
combined, give a profitable edge with a fixed risk:reward of **1:2 or 1:3**, after fees?

## Method
- Every bar is analysed once with the bot's own logic (`tradebot/research/scan.py`).
- Entry next bar open, stop = structural invalidation, target = 2R or 3R, max hold 240 bars,
  fees 0.05 % per side, one position at a time, stop counted first if both touch in one bar.
- Break-even win rate: 33.3 % at 1:2, 25 % at 1:3 (a bit higher after fees).

## Data split
| Role | Markets | Period |
|---|---|---|
| Train (choose) | BTCUSDT + ETHUSDT 1h | 2019-01 → 2023-12 |
| Validation (confirm) | BTCUSDT + ETHUSDT 1h | 2024-01 → 2025-06 |
| **Final test (never used before)** | SOLUSDT, XRPUSDT, BNBUSDT 1h (full history) + Gold 1h 2026-01 → now | once only |

## Candidates
Each single technique and every combination of 2 or 3 of these 13 components, each at RR 2 and 3
(754 strategies): structure_bias, ema_bias, htf_bias, order_block, fvg, premium_discount, sr_zone,
liquidity_sweep, choch_mss, candle, killzone, ote, elliott_with.

## Selection rule (fixed now)
1. Train: ≥ 100 trades and expectancy > 0 R after fees.
2. Validation: ≥ 30 trades and expectancy > 0 R.
3. Rank survivors by min(train expectancy, validation expectancy); take the top 3.

## Pass rule for the final test (fixed now)
A selected strategy passes if its pooled expectancy on the final markets is > 0 R **and** it is
positive on at least 3 of the 4 final markets. Anything else is reported as a failure.
Testing ~750 strategies guarantees some look good by luck; only the final test can tell.
