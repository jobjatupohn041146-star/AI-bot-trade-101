#!/usr/bin/env bash
# Daily forward test, safe to run in a fresh checkout (only needs stats/ and data/dashboard/).
#   new bars since 2026-11-25 -> scan -> strategy #1 + every technique -> stats/ -> website
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH=.
python -m pip install -q -r requirements.txt yfinance >/dev/null 2>&1 || true
python -m tradebot.research.forward
python scripts/export_stats.py
python scripts/build_site.py
