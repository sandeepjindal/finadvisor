from agent.portfolio_parse import parse_holdings_nl


def test_single_holding():
    assert parse_holdings_nl("I own 30 NVDA at $450") == [("NVDA", 30.0, 450.0)]


def test_multiple_holdings():
    out = parse_holdings_nl("I own 30 NVDA at $450, 50 VOO at 400")
    assert ("NVDA", 30.0, 450.0) in out
    assert ("VOO", 50.0, 400.0) in out


def test_variants():
    assert parse_holdings_nl("bought 10 AAPL @ 150.5") == [("AAPL", 10.0, 150.5)]
    assert parse_holdings_nl("100 brk.b shares at 350") == [("BRK.B", 100.0, 350.0)]


def test_no_match():
    assert parse_holdings_nl("what about nvidia?") == []
