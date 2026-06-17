from bot.commands import handle_command
from brain.db import init_db
from brain.holdings import list_holdings


def _db(tmp_path):
    return init_db(str(tmp_path / "brain.db"))


def test_portfolio_add_list_remove(tmp_path):
    conn = _db(tmp_path)
    assert "NVDA" in handle_command(conn, "/portfolio add NVDA 30 450")
    assert "NVDA" in handle_command(conn, "/portfolio list")
    assert "Removed" in handle_command(conn, "/portfolio remove NVDA")


def test_nl_holdings_ingested(tmp_path):
    conn = _db(tmp_path)
    reply = handle_command(conn, "I own 30 NVDA at $450 and 50 VOO at 400")
    assert reply is not None and "Recorded" in reply
    assert {h.ticker for h in list_holdings(conn)} == {"NVDA", "VOO"}


def test_question_not_treated_as_holding(tmp_path):
    conn = _db(tmp_path)
    assert handle_command(conn, "should I buy 30 NVDA at 450?") is None
