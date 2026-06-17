import pytest
from brain.db import init_db
from brain.watchlist import add_watch, list_watch, remove_watch


def _db(tmp_path):
    return init_db(str(tmp_path / "brain.db"))


def test_add_list_remove(tmp_path):
    conn = _db(tmp_path)
    add_watch(conn, "nvda", "ai leader")
    add_watch(conn, "aapl", "")
    items = list_watch(conn)
    assert {i.ticker for i in items} == {"NVDA", "AAPL"}
    assert remove_watch(conn, "NVDA") is True
    assert {i.ticker for i in list_watch(conn)} == {"AAPL"}


def test_dedupe_updates_reason(tmp_path):
    conn = _db(tmp_path)
    add_watch(conn, "NVDA", "first")
    add_watch(conn, "NVDA", "second")
    items = list_watch(conn)
    assert len(items) == 1
    assert items[0].reason == "second"


def test_invalid_ticker_raises(tmp_path):
    conn = _db(tmp_path)
    with pytest.raises(ValueError):
        add_watch(conn, "12345")
