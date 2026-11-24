#!/usr/bin/env bash
# One-time setup on an Ubuntu VPS (run as root). Testnet only.
set -euo pipefail
id tradebot >/dev/null 2>&1 || useradd -m -s /bin/bash tradebot
apt-get update -y && apt-get install -y python3-venv git
cd /opt
[ -d AI-bot-trade-101 ] || git clone https://github.com/jobjatupohn041146-star/AI-bot-trade-101.git
cd AI-bot-trade-101
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt ccxt yfinance
chown -R tradebot:tradebot /opt/AI-bot-trade-101
[ -f /etc/tradebot.env ] || { cp deploy/env.example /etc/tradebot.env; chmod 600 /etc/tradebot.env; }
echo "Now: edit /etc/tradebot.env, then run (as tradebot): .venv/bin/python -m tradebot study --claude"
echo "Then: cp deploy/tradebot-testnet.service /etc/systemd/system/ && systemctl enable --now tradebot-testnet"
