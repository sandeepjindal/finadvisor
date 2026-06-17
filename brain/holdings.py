"""Portfolio holdings + alert dedupe/cooldown (alerts_sent). Parameterized. Step 3.1."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from security.guards import validate_ticker


@dataclass
class Holding:
    id: int
    ticker: str
    shares: float
    avg_cost: float
    added_at: str
    notes: str


def _now() -> datetime:
    return datetime.now(timezone.utc)


def add_holding(
    conn: sqlite3.Connection,
    ticker: str,
    shares: float,
    avg_cost: float,
    notes: str = "",
) -> int:
    t = validate_ticker(ticker)
    cur = conn.execute(
        """INSERT INTO holdings (ticker, shares, avg_cost, added_at, notes)
           VALUES (?, ?, ?, ?, ?)""",
        (t, float(shares), float(avg_cost), _now().isoformat(), notes),
    )
    conn.commit()
    return int(cur.lastrowid)


def list_holdings(conn: sqlite3.Connection) -> list[Holding]:
    rows = conn.execute(
        "SELECT id, ticker, shares, avg_cost, added_at, notes FROM holdings ORDER BY ticker"
    ).fetchall()
    return [
        Holding(
            r["id"], r["ticker"], r["shares"], r["avg_cost"], r["added_at"], r["notes"]
        )
        for r in rows
    ]


def remove_holding(conn: sqlite3.Connection, ticker: str) -> int:
    t = validate_ticker(ticker)
    cur = conn.execute("DELETE FROM holdings WHERE ticker = ?", (t,))
    conn.commit()
    return cur.rowcount


def was_alerted(
    conn: sqlite3.Connection, ticker: str, type_: str, cooldown_hours: float
) -> bool:
    cutoff = (_now() - timedelta(hours=cooldown_hours)).isoformat()
    row = conn.execute(
        """SELECT 1 FROM alerts_sent
           WHERE ticker = ? AND type = ? AND created_at >= ? LIMIT 1""",
        (ticker, type_, cutoff),
    ).fetchone()
    return row is not None


def record_alert(
    conn: sqlite3.Connection, ticker: str, type_: str, payload: str = ""
) -> None:
    conn.execute(
        "INSERT INTO alerts_sent (ticker, type, created_at, payload) VALUES (?, ?, ?, ?)",
        (ticker, type_, _now().isoformat(), payload),
    )
    conn.commit()
