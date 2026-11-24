"""MetaTrader 5 (Forex / Gold / CFD). Needs the MetaTrader5 Python package and a
running MT5 terminal on Windows. Refuses real accounts unless allowed."""
from __future__ import annotations

import os

import pandas as pd

from ..data import normalize
from .base import Broker, Fill, round_down

TIMEFRAMES = {"1m": "TIMEFRAME_M1", "5m": "TIMEFRAME_M5", "15m": "TIMEFRAME_M15", "30m": "TIMEFRAME_M30",
              "1h": "TIMEFRAME_H1", "4h": "TIMEFRAME_H4", "1d": "TIMEFRAME_D1"}
MAGIC = 101_101


class MT5Broker(Broker):
    name = "mt5"
    live = True

    def __init__(self, symbol: str, timeframe: str = "1h", allow_real: bool = False, mt5=None):
        if mt5 is None:
            import MetaTrader5 as mt5  # Windows only
        self.mt5 = mt5
        kw = {}
        if os.environ.get("MT5_LOGIN"):
            kw = {"login": int(os.environ["MT5_LOGIN"]), "password": os.environ.get("MT5_PASSWORD", ""),
                  "server": os.environ.get("MT5_SERVER", "")}
        if not mt5.initialize(**kw):
            raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")
        acc = mt5.account_info()
        if acc is None:
            raise RuntimeError("MT5: no account logged in")
        if acc.trade_mode == mt5.ACCOUNT_TRADE_MODE_REAL and not allow_real:
            raise RuntimeError("MT5 account is REAL. Use a demo account, or pass --real with "
                               "TRADEBOT_I_UNDERSTAND_RISK=YES")
        if not mt5.symbol_select(symbol, True):
            raise RuntimeError(f"MT5: symbol {symbol} not available")
        self.symbol = symbol
        self.timeframe = timeframe
        self.info = mt5.symbol_info(symbol)

    # engine sizes in units of the asset; MT5 trades lots
    def _to_lots(self, units: float) -> float:
        lots = units / (self.info.trade_contract_size or 1)
        lots = min(round_down(lots, self.info.volume_step), self.info.volume_max)
        return lots if lots >= self.info.volume_min else 0.0

    def normalize_size(self, size: float, price: float) -> float:
        return self._to_lots(size) * (self.info.trade_contract_size or 1)

    def _send(self, req: dict):
        r = self.mt5.order_send(req)
        if r is None or r.retcode != self.mt5.TRADE_RETCODE_DONE:
            raise RuntimeError(f"MT5 order failed: {getattr(r, 'retcode', None)} {getattr(r, 'comment', '')}")
        return r

    def open(self, direction, size, price_hint, stop, take_profit) -> Fill:
        m, tick = self.mt5, self.mt5.symbol_info_tick(self.symbol)
        buy = direction == "long"
        req = {
            "action": m.TRADE_ACTION_DEAL, "symbol": self.symbol, "volume": self._to_lots(size),
            "type": m.ORDER_TYPE_BUY if buy else m.ORDER_TYPE_SELL,
            "price": tick.ask if buy else tick.bid,
            "sl": round(stop, self.info.digits),
            "tp": round(take_profit, self.info.digits) if take_profit else 0.0,
            "deviation": 20, "magic": MAGIC, "comment": "tradebot",
            "type_time": m.ORDER_TIME_GTC, "type_filling": m.ORDER_FILLING_IOC,
        }
        r = self._send(req)
        return Fill(float(r.price), r.volume * (self.info.trade_contract_size or 1), str(r.order))

    def _positions(self):
        return [p for p in (self.mt5.positions_get(symbol=self.symbol) or []) if p.magic == MAGIC]

    def has_position(self, fill: Fill) -> bool:
        return bool(self._positions())

    def open_positions(self) -> int:
        return len(self._positions())

    def close(self, fill, direction, price_hint) -> float:
        m, px = self.mt5, price_hint
        for p in self._positions():
            tick = m.symbol_info_tick(self.symbol)
            long_pos = p.type == m.POSITION_TYPE_BUY
            r = self._send({
                "action": m.TRADE_ACTION_DEAL, "symbol": self.symbol, "volume": p.volume, "position": p.ticket,
                "type": m.ORDER_TYPE_SELL if long_pos else m.ORDER_TYPE_BUY,
                "price": tick.bid if long_pos else tick.ask,
                "deviation": 20, "magic": MAGIC, "comment": "tradebot close",
                "type_time": m.ORDER_TIME_GTC, "type_filling": m.ORDER_FILLING_IOC,
            })
            px = float(r.price)
        return px

    def equity(self) -> float | None:
        return float(self.mt5.account_info().equity)

    def fetch_ohlcv(self, limit: int = 1500) -> pd.DataFrame:
        tf = getattr(self.mt5, TIMEFRAMES[self.timeframe])
        rates = self.mt5.copy_rates_from_pos(self.symbol, tf, 0, limit)
        df = pd.DataFrame(rates)
        # MT5 bar times are in broker-server time; shift to UTC so killzones line up.
        offset = float(os.environ.get("MT5_SERVER_UTC_OFFSET", "0"))
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True) - pd.Timedelta(hours=offset)
        df = df.rename(columns={"tick_volume": "volume"})
        return normalize(df[["time", "open", "high", "low", "close", "volume"]])
