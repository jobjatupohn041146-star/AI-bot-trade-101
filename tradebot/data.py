"""Market data loading. Every frame is OHLCV with a UTC DatetimeIndex."""
from __future__ import annotations

import numpy as np
import pandas as pd

COLS = ["open", "high", "low", "close", "volume"]


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns={c: c.lower() for c in df.columns})
    if "volume" not in df:
        df["volume"] = 0.0
    if not isinstance(df.index, pd.DatetimeIndex):
        for c in ("time", "date", "datetime", "timestamp"):
            if c in df:
                df = df.set_index(pd.to_datetime(df[c], utc=True)).drop(columns=c)
                break
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    else:
        df.index = df.index.tz_convert("UTC")  # killzones are defined in UTC
    return df[COLS].astype(float).sort_index()


def load_csv(path: str) -> pd.DataFrame:
    return normalize(pd.read_csv(path))


def synthetic(n: int = 2000, seed: int = 7, start: float = 2000.0, freq: str = "1h") -> pd.DataFrame:
    """Regime-switching random walk with trends, pullbacks and stop-hunt wicks.
    Only for offline testing — it has no real edge."""
    rng = np.random.default_rng(seed)
    drift, price, rows = 0.0, start, []
    for i in range(n):
        if i % rng.integers(60, 200) == 0:
            drift = rng.choice([-1, 0, 1]) * rng.uniform(0.0003, 0.0012)
        vol = price * rng.uniform(0.002, 0.005)
        o = price
        c = o + o * drift + rng.normal(0, vol)
        h = max(o, c) + abs(rng.normal(0, vol * 0.6))
        l = min(o, c) - abs(rng.normal(0, vol * 0.6))
        if rng.random() < 0.04:  # liquidity grab wick
            if rng.random() < 0.5:
                h += vol * rng.uniform(1.5, 3)
            else:
                l -= vol * rng.uniform(1.5, 3)
        rows.append((o, h, l, c, rng.uniform(100, 1000)))
        price = c
    idx = pd.date_range("2024-01-01", periods=n, freq=freq, tz="UTC")
    return pd.DataFrame(rows, columns=COLS, index=idx)


def load_yfinance(ticker: str, period: str = "730d", interval: str = "1h") -> pd.DataFrame:
    import yfinance as yf  # optional dependency

    df = yf.download(ticker, period=period, interval=interval, progress=False, auto_adjust=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return normalize(df)


def load_binance_vision(symbol: str = "BTCUSDT", interval: str = "1h", start: str = "2020-01",
                        end: str = "2025-10", cache_dir: str | None = None) -> pd.DataFrame:
    """Monthly kline archives from data.binance.vision (public, no key, multi-year)."""
    import io
    import urllib.request
    import zipfile
    from pathlib import Path

    cache = Path(cache_dir) if cache_dir else None
    frames = []
    for month in pd.period_range(start, end, freq="M"):
        name = f"{symbol}-{interval}-{month}"
        local = cache / f"{name}.csv" if cache else None
        if local and local.exists():
            raw = local.read_bytes()
        else:
            url = f"https://data.binance.vision/data/spot/monthly/klines/{symbol}/{interval}/{name}.zip"
            with urllib.request.urlopen(url, timeout=60) as r:
                raw = zipfile.ZipFile(io.BytesIO(r.read())).read(f"{name}.csv")
            if local:
                local.parent.mkdir(parents=True, exist_ok=True)
                local.write_bytes(raw)
        frames.append(pd.read_csv(io.BytesIO(raw), header=None, usecols=range(6)))
    df = pd.concat(frames, ignore_index=True)
    df.columns = ["time", "open", "high", "low", "close", "volume"]
    df = df[pd.to_numeric(df["time"], errors="coerce").notna()]  # drop header rows if any
    t = df["time"].astype("int64")
    unit_us = t > 10**14  # archives switched from ms to µs timestamps in 2025
    df["time"] = pd.to_datetime(t.where(~unit_us, t // 1000), unit="ms", utc=True)
    return normalize(df).loc[lambda d: ~d.index.duplicated()]
