"""Download new bars and scan them for every asset (incremental).

    PYTHONPATH=. python scripts/update_all.py [--workers 4]
"""
import sys
import time
from multiprocessing import Pool

from tradebot.research.universe import ALL, update_data, update_scan


def one(name):
    t = time.time()
    try:
        df = update_data(name)
        sc = update_scan(name)
        return name, len(df), len(sc), str(df.index[-1]), round(time.time() - t), None
    except Exception as e:  # one bad asset must not stop the rest
        return name, 0, 0, "", round(time.time() - t), f"{type(e).__name__}: {e}"


if __name__ == "__main__":
    workers = int(sys.argv[sys.argv.index("--workers") + 1]) if "--workers" in sys.argv else 4
    with Pool(workers) as pool:
        for name, nbars, nscan, last, secs, err in pool.imap_unordered(one, ALL):
            print(f"{name:10s} bars={nbars:6d} scanned={nscan:6d} last={last} {secs}s {err or ''}", flush=True)
