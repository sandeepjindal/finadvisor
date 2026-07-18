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


def test_portfolio_add_accepts_dollar_sign_on_price(tmp_path):
    conn = _db(tmp_path)
    reply = handle_command(conn, "/portfolio add NVDA 30 $450")
    assert "NVDA" in reply
    (h,) = list_holdings(conn)
    assert h.shares == 30 and h.avg_cost == 450


def test_portfolio_add_dollar_sign_allows_price_first(tmp_path):
    conn = _db(tmp_path)
    reply = handle_command(conn, "/portfolio add NVDA $450 30")
    assert "NVDA" in reply
    (h,) = list_holdings(conn)
    assert h.shares == 30 and h.avg_cost == 450


def test_portfolio_add_price_first_with_notes(tmp_path):
    conn = _db(tmp_path)
    handle_command(conn, "/portfolio add NVDA $450 30 long term hold")
    (h,) = list_holdings(conn)
    assert h.shares == 30 and h.avg_cost == 450 and h.notes == "long term hold"


def test_portfolio_add_without_dollar_stays_positional(tmp_path):
    # No '$' → no guessing: first number is shares, second is cost (unchanged).
    conn = _db(tmp_path)
    handle_command(conn, "/portfolio add NVDA 450 30")
    (h,) = list_holdings(conn)
    assert h.shares == 450 and h.avg_cost == 30


def test_portfolio_add_non_numeric_gives_clear_error(tmp_path):
    conn = _db(tmp_path)
    reply = handle_command(conn, "/portfolio add NVDA abc 450")
    assert "must be numbers" in reply
    assert list_holdings(conn) == []
