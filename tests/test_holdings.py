from brain.db import init_db
from brain.holdings import (
    add_holding,
    list_holdings,
    record_alert,
    remove_holding,
    was_alerted,
)


def _db(tmp_path):
    return init_db(str(tmp_path / "brain.db"))


def test_add_list_remove(tmp_path):
    conn = _db(tmp_path)
    add_holding(conn, "nvda", 30, 450, "ai")
    add_holding(conn, "voo", 50, 400)
    items = list_holdings(conn)
    assert {h.ticker for h in items} == {"NVDA", "VOO"}
    assert remove_holding(conn, "NVDA") == 1
    assert {h.ticker for h in list_holdings(conn)} == {"VOO"}


def test_alert_cooldown(tmp_path):
    conn = _db(tmp_path)
    assert was_alerted(conn, "NVDA", "SELL", 24) is False
    record_alert(conn, "NVDA", "SELL", "payload")
    assert was_alerted(conn, "NVDA", "SELL", 24) is True
    assert was_alerted(conn, "NVDA", "TRIM", 24) is False
