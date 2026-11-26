"""SQLite persistence so a crash/restart keeps the queue, leaderboard and like goal."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .engine import Engine


class Store:
    def __init__(self, path: str | Path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path))
        self.db.execute("CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT NOT NULL)")
        self.db.commit()

    def load(self, engine: Engine) -> bool:
        row = self.db.execute("SELECT v FROM kv WHERE k='engine'").fetchone()
        if not row:
            return False
        try:
            engine.restore(json.loads(row[0]))
            return True
        except (ValueError, TypeError, KeyError) as e:  # corrupt file must not block going live
            print(f"[store] ignoring unreadable state: {e}")
            return False

    def save(self, engine: Engine) -> None:
        self.db.execute("INSERT OR REPLACE INTO kv(k, v) VALUES('engine', ?)",
                        (json.dumps(engine.dump(), ensure_ascii=False),))
        self.db.commit()

    def close(self) -> None:
        self.db.close()
