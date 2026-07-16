"""SQLite "brain" schema: tables, indexes, FTS5, WAL, POSIX file hardening. Step 0.7.

SQLite is embedded (a single file) — no server. Indexes are created up front so reads
stay fast as the brain grows; FTS5 virtual tables back fast keyword search (with a
graceful fallback if FTS5 isn't compiled in).
"""

from __future__ import annotations

import os
import sqlite3

from brain.signals import SIGNALS_INDEXES, SIGNALS_TABLES
from logging_setup import get_logger

log = get_logger(__name__)

_TABLES = [
    """CREATE TABLE IF NOT EXISTS articles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker TEXT, url TEXT UNIQUE, title TEXT, source TEXT,
        published_at TEXT, clean_text TEXT, sentiment REAL, fetched_at TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS quotes_daily (
        ticker TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL,
        volume REAL, PRIMARY KEY (ticker, date)
    )""",
    """CREATE TABLE IF NOT EXISTS fundamentals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker TEXT, as_of TEXT, pe REAL, pb REAL, debt REAL, margins REAL,
        raw_json TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS analyses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker TEXT, created_at TEXT, question TEXT, verdict TEXT, reasoning TEXT,
        confidence REAL, signals_json TEXT, price_at_time REAL
    )""",
    """CREATE TABLE IF NOT EXISTS holdings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker TEXT, shares REAL, avg_cost REAL, added_at TEXT, notes TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS watchlist (
        ticker TEXT PRIMARY KEY, added_at TEXT, reason TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS alerts_sent (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker TEXT, type TEXT, created_at TEXT, payload TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT, actor TEXT, action TEXT, tool TEXT, args TEXT, result_summary TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS documents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kind TEXT, path TEXT, title TEXT, ingested_at TEXT, clean_text TEXT
    )""",
    # Historical brain / learning loop (Work-stream D) — registered here so the whole
    # schema is created and maintained in one place. See brain/signals.py.
    *SIGNALS_TABLES,
]

_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_analyses_ticker_time ON analyses(ticker, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_articles_ticker_time ON articles(ticker, published_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_fundamentals_ticker ON fundamentals(ticker, as_of DESC)",
    "CREATE INDEX IF NOT EXISTS idx_alerts_ticker_type ON alerts_sent(ticker, type, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_documents_kind ON documents(kind)",
    *SIGNALS_INDEXES,
]

# Standalone (contentless) FTS5 tables; app code inserts mirrored rows on ingest.
_FTS = [
    "CREATE VIRTUAL TABLE IF NOT EXISTS articles_fts USING fts5(title, clean_text)",
    "CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(title, clean_text)",
]


def fts5_available(conn: sqlite3.Connection) -> bool:
    try:
        conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS _fts_probe USING fts5(x)")
        conn.execute("DROP TABLE IF EXISTS _fts_probe")
        return True
    except sqlite3.OperationalError:
        return False


def init_db(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    for ddl in _TABLES:
        conn.execute(ddl)
    for ddl in _INDEXES:
        conn.execute(ddl)
    if fts5_available(conn):
        for ddl in _FTS:
            conn.execute(ddl)
    else:  # pragma: no cover - depends on build
        log.warning("FTS5 unavailable; keyword search will fall back to LIKE")
    conn.commit()

    # POSIX-only file hardening; Windows has no equivalent mode bits.
    if os.name == "posix" and path != ":memory:" and os.path.exists(path):
        os.chmod(path, 0o600)
    return conn


def open_encrypted_db(path: str, key: str):  # pragma: no cover - requires pysqlcipher3
    """Open an encrypted SQLite DB via SQLCipher ([encryption] extra). NOTE: the stdlib
    `sqlite3` module CANNOT open an encrypted DB — this is a separate driver, not a PRAGMA
    on a stdlib connection. Step 4.5."""
    try:
        from pysqlcipher3 import dbapi2 as sqlcipher
    except ImportError as e:
        raise RuntimeError(
            "encryption requires pysqlcipher3; run: uv sync --extra encryption"
        ) from e
    conn = sqlcipher.connect(path)
    conn.execute(f"PRAGMA key = '{key}'")
    conn.row_factory = sqlcipher.Row
    return conn
