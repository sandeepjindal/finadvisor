"""Watchlist CRUD (parameterized, deduped by ticker). Step 2.1."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from security.guards import validate_ticker


@dataclass
class WatchItem:
    ticker: str
    added_at: str
    reason: str


def add_watch(conn: sqlite3.Connection, ticker: str, reason: str = "") -> str:
    t = validate_ticker(ticker)
    conn.execute(
        """INSERT INTO watchlist (ticker, added_at, reason) VALUES (?, ?, ?)
           ON CONFLICT(ticker) DO UPDATE SET reason=excluded.reason""",
        (t, datetime.now(timezone.utc).isoformat(), reason),
    )
    conn.commit()
    return t


def list_watch(conn: sqlite3.Connection) -> list[WatchItem]:
    rows = conn.execute(
        "SELECT ticker, added_at, reason FROM watchlist ORDER BY added_at"
    ).fetchall()
    return [WatchItem(r["ticker"], r["added_at"], r["reason"]) for r in rows]


def remove_watch(conn: sqlite3.Connection, ticker: str) -> bool:
    t = validate_ticker(ticker)
    cur = conn.execute("DELETE FROM watchlist WHERE ticker = ?", (t,))
    conn.commit()
    return cur.rowcount > 0
