from brain.audit import log_audit
from brain.db import init_db
from logging_setup import register_secret


def test_audit_row_written(tmp_path):
    conn = init_db(str(tmp_path / "brain.db"))
    log_audit(
        conn, "agent", "tool_call", "get_quote", '{"ticker": "NVDA"}', "price 120"
    )
    rows = conn.execute("SELECT actor, action, tool FROM audit_log").fetchall()
    assert rows[0]["tool"] == "get_quote"
    assert rows[0]["action"] == "tool_call"


def test_audit_redacts_secrets(tmp_path):
    conn = init_db(str(tmp_path / "brain.db"))
    register_secret("supersecretvalue123")
    log_audit(conn, "agent", "tool_call", "x", "key=supersecretvalue123", "ok")
    args = conn.execute("SELECT args FROM audit_log").fetchone()["args"]
    assert "supersecretvalue123" not in args
