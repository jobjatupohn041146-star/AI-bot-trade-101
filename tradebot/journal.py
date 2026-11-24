"""Trade journal (SQLite). Every trade stores its full bar-by-bar excursion
path in R units so SL/TP can be optimised later from real statistics."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT, symbol TEXT, setup TEXT, direction TEXT, mode TEXT,
    entry_time TEXT, entry REAL, stop REAL, take_profit REAL, size REAL, risk_amount REAL,
    exit_time TEXT, exit REAL, exit_reason TEXT,
    pnl REAL, r_multiple REAL, mfe_r REAL, mae_r REAL, bars_held INTEGER,
    path_json TEXT, components_json TEXT, decision_json TEXT
);
"""


class Journal:
    def __init__(self, path: str | Path = ":memory:"):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def add(self, t: dict) -> int:
        t = dict(t)
        for k in ("path", "components", "decision"):
            t[f"{k}_json"] = json.dumps(t.pop(k, None), default=str)
        cols = ",".join(t)
        cur = self.conn.execute(f"INSERT INTO trades ({cols}) VALUES ({','.join('?' * len(t))})", list(t.values()))
        self.conn.commit()
        return cur.lastrowid

    def trades(self, setup: str | None = None, mode: str | None = None) -> list[dict]:
        q, args = "SELECT * FROM trades WHERE 1=1", []
        if setup:
            q, args = q + " AND setup=?", args + [setup]
        if mode:
            q, args = q + " AND mode=?", args + [mode]
        rows = [dict(r) for r in self.conn.execute(q + " ORDER BY id", args)]
        for r in rows:
            for k in ("path", "components", "decision"):
                r[k] = json.loads(r.pop(f"{k}_json") or "null")
        return rows

    def stats(self) -> dict:
        """Per-setup performance in R multiples."""
        out: dict = {}
        for r in self.trades():
            out.setdefault(r["setup"], []).append(r["r_multiple"])
        res = {}
        for setup, rs in out.items():
            wins = [x for x in rs if x > 0]
            losses = [x for x in rs if x <= 0]
            gross_loss = -sum(losses)
            res[setup] = {
                "trades": len(rs),
                "win_rate": round(len(wins) / len(rs), 3),
                "avg_r": round(sum(rs) / len(rs), 3),
                "expectancy_r": round(sum(rs) / len(rs), 3),
                "profit_factor": round(sum(wins) / gross_loss, 2) if gross_loss > 0 else None,
                "total_r": round(sum(rs), 2),
            }
        return res
