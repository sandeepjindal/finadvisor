import os

import pytest
from brain.db import fts5_available, init_db

EXPECTED_TABLES = {
    "articles",
    "quotes_daily",
    "fundamentals",
    "analyses",
    "holdings",
    "watchlist",
    "alerts_sent",
    "audit_log",
    "documents",
}


def test_all_tables_created(tmp_path):
    conn = init_db(str(tmp_path / "brain.db"))
    names = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert EXPECTED_TABLES <= names


def test_indexes_created(tmp_path):
    conn = init_db(str(tmp_path / "brain.db"))
    idx = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
    }
    assert "idx_analyses_ticker_time" in idx
    assert "idx_articles_ticker_time" in idx


@pytest.mark.skipif(os.name != "posix", reason="POSIX file mode only")
def test_db_file_mode_600(tmp_path):
    path = str(tmp_path / "brain.db")
    init_db(path)
    assert (os.stat(path).st_mode & 0o777) == 0o600


def test_fts_search(tmp_path):
    conn = init_db(str(tmp_path / "brain.db"))
    if not fts5_available(conn):
        pytest.skip("FTS5 not compiled in")
    conn.execute(
        "INSERT INTO articles_fts (title, clean_text) VALUES (?, ?)",
        ("Nvidia soars", "NVDA reported strong datacenter demand"),
    )
    conn.commit()
    rows = conn.execute(
        "SELECT title FROM articles_fts WHERE articles_fts MATCH 'datacenter'"
    ).fetchall()
    assert len(rows) == 1
