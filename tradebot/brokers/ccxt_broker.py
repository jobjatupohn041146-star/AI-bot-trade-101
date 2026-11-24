"""Crypto exchanges through ccxt (Bybit, OKX, Binance USDⓈ-M futures, ...).
Defaults to the exchange SANDBOX / testnet. Shorts need a derivatives market
(e.g. symbol 'BTC/USDT:USDT')."""
from __future__ import annotations

import os

import pandas as pd

from ..data import normalize
from .base import Broker, Fill


class CCXTBroker(Broker):
    name = "ccxt"
    live = True

    def __init__(self, exchange: str, symbol: str, timeframe: str = "1h", sandbox: bool = True,
                 client=None):
        if client is None:
            import ccxt

            client = getattr(ccxt, exchange)({
                "apiKey": os.environ.get("TRADEBOT_API_KEY", ""),
                "secret": os.environ.get("TRADEBOT_API_SECRET", ""),
                "password": os.environ.get("TRADEBOT_API_PASSWORD") or None,
                "enableRateLimit": True,
            })
            if sandbox:
                client.set_sandbox_mode(True)
            client.load_markets()
        self.ex = client
        self.symbol = symbol
        self.timeframe = timeframe
        self.sandbox = sandbox

    def normalize_size(self, size: float, price: float) -> float:
        try:
            amt = float(self.ex.amount_to_precision(self.symbol, size))
        except Exception:  # below minimum precision
            return 0.0
        return min(amt, size)

    def open(self, direction, size, price_hint, stop, take_profit) -> Fill:
        side = "buy" if direction == "long" else "sell"
        exit_side = "sell" if side == "buy" else "buy"
        o = self.ex.create_order(self.symbol, "market", side, size)
        price = float(o.get("average") or o.get("price") or price_hint)
        filled = float(o.get("filled") or size)
        # Protective orders live on the exchange, so the stop survives a crash.
        try:
            self.ex.create_stop_loss_order(self.symbol, "market", exit_side, filled, None, stop,
                                           {"reduceOnly": True})
        except Exception:
            # Never sit in a position without a stop: flatten and re-raise.
            self.ex.create_order(self.symbol, "market", exit_side, filled, None, {"reduceOnly": True})
            raise
        if take_profit is not None:
            self.ex.create_take_profit_order(self.symbol, "market", exit_side, filled, None, take_profit,
                                             {"reduceOnly": True})
        return Fill(price, filled, str(o.get("id")))

    def _position_size(self) -> float:
        for p in self.ex.fetch_positions([self.symbol]):
            if p.get("symbol") == self.symbol and float(p.get("contracts") or 0) > 0:
                return float(p["contracts"])
        return 0.0

    def has_position(self, fill: Fill) -> bool:
        return self._position_size() > 0

    def open_positions(self) -> int:
        return 1 if self._position_size() > 0 else 0

    def close(self, fill, direction, price_hint) -> float:
        self.ex.cancel_all_orders(self.symbol)  # drop leftover SL/TP
        qty = self._position_size()
        if qty <= 0:
            return price_hint  # already closed by SL/TP on the exchange
        side = "sell" if direction == "long" else "buy"
        o = self.ex.create_order(self.symbol, "market", side, qty, None, {"reduceOnly": True})
        return float(o.get("average") or o.get("price") or price_hint)

    def equity(self) -> float | None:
        bal = self.ex.fetch_balance()
        quote = self.symbol.split("/")[1].split(":")[0]
        total = bal.get("total", {}).get(quote)
        return float(total) if total is not None else None

    def fetch_ohlcv(self, limit: int = 1500) -> pd.DataFrame:
        rows = self.ex.fetch_ohlcv(self.symbol, self.timeframe, limit=limit)
        df = pd.DataFrame(rows, columns=["time", "open", "high", "low", "close", "volume"])
        df["time"] = pd.to_datetime(df["time"], unit="ms", utc=True)
        return normalize(df)
