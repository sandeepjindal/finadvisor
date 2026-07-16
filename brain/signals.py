"""Historical brain: signal snapshots + a learning loop over past decisions.

The canonical decision log is the existing ``analyses`` table (see ``brain/db.py`` and
``brain/analyses.py``): a saved analysis IS a decision — ``verdict`` is the action,
``confidence`` the confidence, ``price_at_time`` the price when the call was made, and the
enriched signal blob lives in ``signals_json`` (JSON). This module does NOT duplicate that.

What it adds is the *learning loop*:

* ``signal_snapshots`` — an optional richer, standalone history of the signal blobs the
  agent observed over time (technical / event / social), independent of any single verdict.
* ``decision_outcomes`` — links back to ``analyses.id`` and records how each past decision
  actually played out vs realised price, so the agent can recall a track record / hit-rate.

Every write is parameterized (no SQL injection). Structured blobs are JSON-encoded with the
stdlib ``json``. The new DDL is exported as ``SIGNALS_TABLES`` / ``SIGNALS_INDEXES`` so the
canonical schema in ``brain/db.py`` can register it in one place. Work-stream D.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

# Verdict (action) buckets we can score against realised price. Everything else
# (WATCH, INFO, ...) is non-directional -> recorded but judged "correct = None".
_BEARISH = {"SELL", "TRIM", "AVOID"}
_BULLISH = {"BUY", "STRONG BUY", "HOLD"}


@dataclass
class SignalSnapshot:
    id: int
    ticker: str
    created_at: str
    price: float | None
    signals: dict
    source: str


@dataclass
class DecisionOutcome:
    id: int
    analysis_id: int
    evaluated_at: str
    price_then: float | None
    price_now: float | None
    horizon_days: int | None
    correct: int | None
    note: str


# --- schema (exported so brain/db.py can own the canonical registration) ---
SIGNALS_TABLES = [
    """CREATE TABLE IF NOT EXISTS signal_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker TEXT, created_at TEXT, price REAL, signals TEXT, source TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS decision_outcomes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        analysis_id INTEGER, evaluated_at TEXT, price_then REAL, price_now REAL,
        horizon_days INTEGER, correct INTEGER, note TEXT
    )""",
]

SIGNALS_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_signal_snapshots_ticker_time ON signal_snapshots(ticker, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_decision_outcomes_analysis ON decision_outcomes(analysis_id)",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_signals_schema(conn: sqlite3.Connection) -> None:
    """Idempotent create of the historical-brain tables + indexes.

    Safe to call repeatedly and safe on an existing brain.db — every statement is
    ``IF NOT EXISTS`` and touches only ``signal_snapshots`` / ``decision_outcomes``.
    Does not touch ``analyses`` (the canonical decision log lives there already).
    """
    for ddl in SIGNALS_TABLES:
        conn.execute(ddl)
    for ddl in SIGNALS_INDEXES:
        conn.execute(ddl)
    conn.commit()


def save_signal_snapshot(
    conn: sqlite3.Connection,
    ticker: str,
    signals: dict,
    price: float | None,
    source: str = "agent",
) -> int:
    cur = conn.execute(
        """INSERT INTO signal_snapshots (ticker, created_at, price, signals, source)
           VALUES (?, ?, ?, ?, ?)""",
        (ticker, _now(), price, json.dumps(signals or {}), source),
    )
    conn.commit()
    return int(cur.lastrowid)


def recall_signal_history(
    conn: sqlite3.Connection, ticker: str, limit: int = 10
) -> list[SignalSnapshot]:
    """Most recent signal snapshots for a ticker, newest first."""
    rows = conn.execute(
        """SELECT id, ticker, created_at, price, signals, source
           FROM signal_snapshots WHERE ticker = ?
           ORDER BY created_at DESC, id DESC LIMIT ?""",
        (ticker, limit),
    ).fetchall()
    return [
        SignalSnapshot(
            id=r["id"],
            ticker=r["ticker"],
            created_at=r["created_at"],
            price=r["price"],
            signals=json.loads(r["signals"] or "{}"),
            source=r["source"],
        )
        for r in rows
    ]


def recall_decisions(conn: sqlite3.Connection, ticker: str, limit: int = 20):
    """Recall past decisions for a ticker — thin delegate to the canonical decision log.

    Decisions live in the ``analyses`` table; this returns ``brain.analyses.Analysis``
    records (newest first), so callers get one consistent decision type.
    """
    from brain.analyses import recall_analyses

    return recall_analyses(conn, ticker, limit=limit)


def _horizon_days(created_at: str | None, now: str) -> int | None:
    """Whole days between a decision's creation and the evaluation time."""
    if not created_at:
        return None
    try:
        then = datetime.fromisoformat(created_at)
        current = datetime.fromisoformat(now)
    except (TypeError, ValueError):
        return None
    return max((current - then).days, 0)


def _judge(verdict: str, price_then: float | None, price_now: float) -> int | None:
    """1 if the decision was borne out by price, 0 if not, None if unscorable.

    * SELL / TRIM / AVOID    -> correct when price fell   (price_now < price_then)
    * BUY / STRONG BUY / HOLD -> correct when price rose or held (price_now >= price_then)
    * anything else (WATCH, INFO, ...) is non-directional -> None.
    """
    if price_then is None:
        return None
    act = (verdict or "").upper()
    if act in _BEARISH:
        return 1 if price_now < price_then else 0
    if act in _BULLISH:
        return 1 if price_now >= price_then else 0
    return None


def evaluate_decisions(
    conn: sqlite3.Connection,
    ticker: str,
    current_price: float,
    *,
    now: str | None = None,
) -> list[DecisionOutcome]:
    """Score every not-yet-evaluated ``analyses`` decision for ``ticker`` vs ``current_price``.

    Iterates the canonical ``analyses`` table (left-joined to ``decision_outcomes`` to find
    rows without an outcome), judges each ``verdict`` against realised price, and writes one
    ``decision_outcomes`` row per newly evaluated decision (idempotent across repeat calls).
    """
    now = now or _now()
    rows = conn.execute(
        """SELECT a.id AS analysis_id, a.verdict AS verdict,
                  a.created_at AS created_at, a.price_at_time AS price_then
           FROM analyses a
           LEFT JOIN decision_outcomes o ON o.analysis_id = a.id
           WHERE a.ticker = ? AND o.id IS NULL
           ORDER BY a.created_at ASC, a.id ASC""",
        (ticker,),
    ).fetchall()

    outcomes: list[DecisionOutcome] = []
    for r in rows:
        price_then = r["price_then"]
        correct = _judge(r["verdict"], price_then, current_price)
        horizon = _horizon_days(r["created_at"], now)
        note = f"{(r['verdict'] or '').upper()} evaluated @ {current_price}"
        cur = conn.execute(
            """INSERT INTO decision_outcomes
               (analysis_id, evaluated_at, price_then, price_now, horizon_days, correct, note)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (r["analysis_id"], now, price_then, current_price, horizon, correct, note),
        )
        outcomes.append(
            DecisionOutcome(
                id=int(cur.lastrowid),
                analysis_id=r["analysis_id"],
                evaluated_at=now,
                price_then=price_then,
                price_now=current_price,
                horizon_days=horizon,
                correct=correct,
                note=note,
            )
        )
    conn.commit()
    return outcomes


def track_record(conn: sqlite3.Connection, ticker: str | None = None) -> dict:
    """Aggregate hit-rate — the agent's learning summary.

    Joins ``decision_outcomes`` to ``analyses`` and returns total scored decisions, correct
    count, overall accuracy, and a per-verdict breakdown. Only outcomes with a non-null
    ``correct`` (directional calls) are scored. If ``ticker`` is None, aggregates across all
    tickers.
    """
    params: tuple = ()
    where = "WHERE o.correct IS NOT NULL"
    if ticker is not None:
        where += " AND a.ticker = ?"
        params = (ticker,)

    rows = conn.execute(
        f"""SELECT a.verdict AS verdict, o.correct AS correct
            FROM decision_outcomes o
            JOIN analyses a ON a.id = o.analysis_id
            {where}""",
        params,
    ).fetchall()

    total = len(rows)
    correct = sum(1 for r in rows if r["correct"] == 1)
    by_action: dict[str, dict] = {}
    for r in rows:
        act = (r["verdict"] or "").upper()
        bucket = by_action.setdefault(act, {"total": 0, "correct": 0, "accuracy": 0.0})
        bucket["total"] += 1
        if r["correct"] == 1:
            bucket["correct"] += 1
    for bucket in by_action.values():
        bucket["accuracy"] = (
            bucket["correct"] / bucket["total"] if bucket["total"] else 0.0
        )

    return {
        "ticker": ticker,
        "total": total,
        "correct": correct,
        "accuracy": (correct / total) if total else 0.0,
        "by_action": by_action,
    }
