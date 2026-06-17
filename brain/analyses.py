"""Persist and recall the agent's own analyses — the memory that informs future calls.

Every write is parameterized (no SQL injection). Step 0.8.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class Analysis:
    id: int
    ticker: str
    created_at: str
    question: str
    verdict: str
    reasoning: str
    confidence: float | None
    signals: dict
    price_at_time: float | None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def save_analysis(
    conn: sqlite3.Connection,
    ticker: str,
    question: str,
    verdict: str,
    reasoning: str,
    confidence: float | None,
    signals: dict | None,
    price_at_time: float | None,
) -> int:
    cur = conn.execute(
        """INSERT INTO analyses
           (ticker, created_at, question, verdict, reasoning, confidence,
            signals_json, price_at_time)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            ticker,
            _now(),
            question,
            verdict,
            reasoning,
            confidence,
            json.dumps(signals or {}),
            price_at_time,
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def recall_analyses(
    conn: sqlite3.Connection, ticker: str, limit: int = 5
) -> list[Analysis]:
    rows = conn.execute(
        """SELECT * FROM analyses WHERE ticker = ?
           ORDER BY created_at DESC, id DESC LIMIT ?""",
        (ticker, limit),
    ).fetchall()
    return [
        Analysis(
            id=r["id"],
            ticker=r["ticker"],
            created_at=r["created_at"],
            question=r["question"],
            verdict=r["verdict"],
            reasoning=r["reasoning"],
            confidence=r["confidence"],
            signals=json.loads(r["signals_json"] or "{}"),
            price_at_time=r["price_at_time"],
        )
        for r in rows
    ]
