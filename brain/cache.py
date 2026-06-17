"""TTL-bounded caches for fundamentals and daily quotes (the `fundamentals` /
`quotes_daily` tables). Cache-first reads soften free-tier rate limits. Step 1.2b.

Deals only in primitives so there's no import cycle with ``data.market``.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone


def _age_seconds(as_of: str) -> float:
    try:
        dt = datetime.fromisoformat(as_of)
    except (ValueError, TypeError):
        return float("inf")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - dt).total_seconds()


def get_fundamentals(
    conn: sqlite3.Connection, ticker: str, max_age_seconds: float
) -> sqlite3.Row | None:
    row = conn.execute(
        "SELECT * FROM fundamentals WHERE ticker = ? ORDER BY as_of DESC LIMIT 1",
        (ticker,),
    ).fetchone()
    if row is None:
        return None
    if _age_seconds(row["as_of"]) > max_age_seconds:
        return None
    return row


def put_fundamentals(
    conn: sqlite3.Connection,
    ticker: str,
    as_of: str,
    pe: float | None,
    pb: float | None,
    debt: float | None,
    margins: float | None,
    raw_json: str,
) -> None:
    conn.execute(
        """INSERT INTO fundamentals (ticker, as_of, pe, pb, debt, margins, raw_json)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (ticker, as_of, pe, pb, debt, margins, raw_json),
    )
    conn.commit()


def upsert_quote(
    conn: sqlite3.Connection, ticker: str, date: str, o, h, low, c, v
) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO quotes_daily
           (ticker, date, open, high, low, close, volume) VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (ticker, date, o, h, low, c, v),
    )
    conn.commit()


def get_quote_row(
    conn: sqlite3.Connection, ticker: str, date: str
) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM quotes_daily WHERE ticker = ? AND date = ?", (ticker, date)
    ).fetchone()
