"""Store and search ingested documents (the `documents` table). Step 3.7.

Keyword search uses LIKE for reliable Document-row mapping; a semantic upgrade lands in
Phase 4 (sqlite-vec).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class Document:
    id: int
    kind: str
    path: str
    title: str
    ingested_at: str
    clean_text: str


def _row(r) -> Document:
    return Document(
        r["id"], r["kind"], r["path"], r["title"], r["ingested_at"], r["clean_text"]
    )


def save_document(
    conn: sqlite3.Connection, kind: str, path: str, title: str, clean_text: str
) -> int:
    cur = conn.execute(
        """INSERT INTO documents (kind, path, title, ingested_at, clean_text)
           VALUES (?, ?, ?, ?, ?)""",
        (kind, path, title, datetime.now(timezone.utc).isoformat(), clean_text),
    )
    conn.commit()
    try:
        conn.execute(
            "INSERT INTO documents_fts (title, clean_text) VALUES (?, ?)",
            (title, clean_text),
        )
        conn.commit()
    except Exception:  # noqa: BLE001 - FTS optional
        pass
    return int(cur.lastrowid)


def list_documents(conn: sqlite3.Connection) -> list[Document]:
    rows = conn.execute("SELECT * FROM documents ORDER BY ingested_at DESC").fetchall()
    return [_row(r) for r in rows]


def get_document(conn: sqlite3.Connection, name: str) -> Document | None:
    row = conn.execute(
        "SELECT * FROM documents WHERE title = ? OR path = ? ORDER BY ingested_at DESC LIMIT 1",
        (name, name),
    ).fetchone()
    return _row(row) if row else None


def search_documents(
    conn: sqlite3.Connection, query: str, limit: int = 5
) -> list[Document]:
    rows = conn.execute(
        """SELECT * FROM documents WHERE clean_text LIKE ? OR title LIKE ?
           ORDER BY ingested_at DESC LIMIT ?""",
        (f"%{query}%", f"%{query}%", limit),
    ).fetchall()
    return [_row(r) for r in rows]
