from brain.analyses import recall_analyses, save_analysis
from brain.db import init_db


def _db(tmp_path):
    return init_db(str(tmp_path / "brain.db"))


def test_save_and_recall_newest_first(tmp_path):
    conn = _db(tmp_path)
    save_analysis(conn, "NVDA", "q1", "HOLD", "r1", 0.6, {"rsi": 55}, 100.0)
    save_analysis(conn, "NVDA", "q2", "TRIM", "r2", 0.7, {"rsi": 74}, 120.0)
    out = recall_analyses(conn, "NVDA")
    assert len(out) == 2
    assert out[0].question == "q2"  # newest first
    assert out[0].signals == {"rsi": 74}
    assert out[1].verdict == "HOLD"


def test_recall_filters_by_ticker(tmp_path):
    conn = _db(tmp_path)
    save_analysis(conn, "NVDA", "q", "HOLD", "r", 0.5, {}, 1.0)
    save_analysis(conn, "AAPL", "q", "BUY", "r", 0.5, {}, 1.0)
    assert len(recall_analyses(conn, "NVDA")) == 1


def test_sql_injection_is_neutralized(tmp_path):
    conn = _db(tmp_path)
    evil = "x'); DROP TABLE analyses;--"
    save_analysis(conn, evil, "q", "HOLD", "r", 0.5, {}, 1.0)
    rows = conn.execute("SELECT ticker FROM analyses").fetchall()
    assert any(r[0] == evil for r in rows)
