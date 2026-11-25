"""Every asset the bot studies, where its data comes from, and incremental updates."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from ..data import load_binance_until_now, load_csv, load_yfinance

MARKET = Path("data/market")
SCANS = Path("data/scans")

CRYPTO = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT", "DOGEUSDT", "TRXUSDT",
          "AVAXUSDT", "LINKUSDT", "DOTUSDT", "LTCUSDT", "BCHUSDT", "ATOMUSDT", "UNIUSDT", "NEARUSDT",
          "XLMUSDT", "ETCUSDT", "FILUSDT", "AAVEUSDT"]
YAHOO = {  # name -> ticker (1h history is limited to ~730 days by Yahoo)
    "GOLD": "GC=F", "SILVER": "SI=F", "OIL": "CL=F", "SP500": "ES=F", "NASDAQ": "NQ=F", "DOW": "YM=F",
    "EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X", "USDJPY": "USDJPY=X", "AUDUSD": "AUDUSD=X", "USDCHF": "USDCHF=X",
}
CLASS = {**{c: "Crypto" for c in CRYPTO}, "GOLD": "Metals", "SILVER": "Metals", "OIL": "Energy",
         "SP500": "Index", "NASDAQ": "Index", "DOW": "Index",
         **{k: "Forex" for k in ("EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCHF")}}
ALL = CRYPTO + list(YAHOO)
# Round-trip cost per side in % of price (taker fee or typical spread + commission)
COST = {"Crypto": 0.05, "Metals": 0.02, "Energy": 0.02, "Index": 0.01, "Forex": 0.007}


def cost(name: str) -> float:
    return COST.get(CLASS.get(name, "Crypto"), 0.05)
CRYPTO_START = "2021-01"


def csv_path(name: str) -> Path:
    return MARKET / f"{name}_1h_now.csv"


def scan_path(name: str) -> Path:
    return SCANS / f"{name}.pkl"


def update_data(name: str) -> pd.DataFrame:
    """Download / extend one asset's hourly history up to the latest closed bar."""
    MARKET.mkdir(parents=True, exist_ok=True)
    p = csv_path(name)
    if name in YAHOO:
        new = load_yfinance(YAHOO[name], period="730d", interval="1h")
        new = new.iloc[:-1]  # the newest Yahoo bar is still forming
    else:
        new = load_binance_until_now(name, "1h", CRYPTO_START, cache_dir=str(MARKET / "cache"))
    if p.exists():  # keep old history that the source no longer serves (Yahoo's 730-day window)
        old = load_csv(str(p))
        new = pd.concat([old[old.index < new.index[0]], new])
    new = new[~new.index.duplicated(keep="last")].sort_index()
    new.to_csv(p, index_label="time")
    return new


def update_scan(name: str, progress: bool = False) -> pd.DataFrame:
    """Scan only the bars that are not in the stored scan yet."""
    from .scan import scan

    df = load_csv(str(csv_path(name)))
    p = scan_path(name)
    old = pd.read_pickle(p) if p.exists() else None
    if old is not None and len(old):
        # re-align by time: indices shift when old history is prepended/kept
        pos = {t: k for k, t in enumerate(df.index)}
        old = old[old["time"].isin(pos)].copy()
        old["i"] = old["time"].map(pos)
        last_i = int(old["i"].max())
    else:
        last_i = None
    new = scan(df, start=None if last_i is None else last_i + 1, progress=progress)
    res = pd.concat([old, new], ignore_index=True) if old is not None else new
    res = res.drop_duplicates("time", keep="last").sort_values("i").reset_index(drop=True)
    SCANS.mkdir(parents=True, exist_ok=True)
    res.to_pickle(p)
    return res
