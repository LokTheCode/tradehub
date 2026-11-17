"""SQLite storage (stdlib only, free, zero setup)."""
import os
import sqlite3
import threading
from contextlib import contextmanager

DB_PATH = os.getenv("TRADEHUB_DB", os.path.join(os.path.dirname(__file__), "..", "tradehub.db"))
_lock = threading.RLock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS account (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    cash REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS holdings (
    symbol TEXT PRIMARY KEY,
    qty INTEGER NOT NULL,
    avg_price REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    qty INTEGER NOT NULL,
    price REAL NOT NULL,
    status TEXT NOT NULL,
    broker TEXT NOT NULL,
    broker_order_id TEXT,
    message TEXT
);
CREATE TABLE IF NOT EXISTS watchlist (
    symbol TEXT PRIMARY KEY
);
"""


@contextmanager
def connect():
    """One transaction per `with` block; serialized by a lock (fine for a single-user app)."""
    with _lock:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def init_db(start_cash: float) -> None:
    with connect() as c:
        c.executescript(SCHEMA)
        c.execute("INSERT OR IGNORE INTO account (id, cash) VALUES (1, ?)", (start_cash,))
        if c.execute("SELECT COUNT(*) FROM watchlist").fetchone()[0] == 0:
            for s in ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "ITC", "SBIN", "WIPRO"]:
                c.execute("INSERT INTO watchlist (symbol) VALUES (?)", (s,))
