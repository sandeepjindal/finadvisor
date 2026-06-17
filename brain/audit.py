"""Audit trail: every tool call and recommendation logged with secret-redacted args.
Lets you always answer "why did it say that?". Step 3.6.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from logging_setup import _redact


def log_audit(
    conn: sqlite3.Connection,
    actor: str,
    action: str,
    tool: str,
    args: str,
    result_summary: str,
) -> None:
    conn.execute(
        """INSERT INTO audit_log (ts, actor, action, tool, args, result_summary)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            datetime.now(timezone.utc).isoformat(),
            actor,
            action,
            tool,
            _redact(args or ""),
            _redact(result_summary or ""),
        ),
    )
    conn.commit()
