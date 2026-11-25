"""Download every market used by the research up to today."""
from pathlib import Path

from tradebot.data import load_binance_until_now, load_yfinance

OUT = Path("data/market")
OUT.mkdir(parents=True, exist_ok=True)
for sym, start in [("BTCUSDT", "2019-01"), ("ETHUSDT", "2019-01"), ("SOLUSDT", "2021-01"),
                   ("XRPUSDT", "2019-01"), ("BNBUSDT", "2019-01")]:
    df = load_binance_until_now(sym, "1h", start, cache_dir="data/market/cache")
    df.to_csv(OUT / f"{sym}_1h_now.csv", index_label="time")
    print(sym, len(df), df.index[0], "->", df.index[-1], flush=True)
g = load_yfinance("GC=F", period="730d", interval="1h")
g.to_csv(OUT / "GOLD_1h_now.csv", index_label="time")
print("GOLD", len(g), g.index[0], "->", g.index[-1])
