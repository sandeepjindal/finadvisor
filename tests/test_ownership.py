"""Offline tests for data/ownership.py — all data is canned/injected, no network."""

from __future__ import annotations

from data.market import Unavailable
from data.ownership import (
    Holder,
    OwnershipSummary,
    format_ownership,
    get_ownership,
)


def _fetch_new(_ticker):
    """New-yfinance shapes: major_holders as a label->fraction dict, holders/transactions
    as list[dict]. Buys exceed sells => net buying."""
    return {
        "major_holders": {
            "insidersPercentHeld": 0.02,  # -> 2.0%
            "institutionsPercentHeld": 0.71,  # -> 71.0%
        },
        "institutional_holders": [
            {"Holder": "Vanguard Group", "Shares": 1_000_000, "% Out": 0.083},
            {"Holder": "BlackRock", "Shares": 800_000, "% Out": 0.066},
        ],
        "insider_transactions": [
            {"Shares": 5000, "Transaction": "Purchase"},
            {"Shares": 3000, "Transaction": "Buy"},
            {"Shares": 1000, "Transaction": "Sale"},
        ],
        "source": "test",
        "as_of": "2026-07-15T00:00:00+00:00",
    }


def test_percentages_parsed_and_holders_built():
    o = get_ownership("AAPL", fetch=_fetch_new)
    assert isinstance(o, OwnershipSummary)
    assert o.ticker == "AAPL"
    assert o.insider_pct == 2.0
    assert o.institutional_pct == 71.0
    assert len(o.top_holders) == 2
    assert isinstance(o.top_holders[0], Holder)
    assert o.top_holders[0].name == "Vanguard Group"
    assert o.top_holders[0].shares == 1_000_000
    assert abs(o.top_holders[0].pct - 8.3) < 1e-9


def test_net_buying():
    o = get_ownership("AAPL", fetch=_fetch_new)
    assert o.insider_activity == "net buying"
    assert o.insider_net_shares == 5000 + 3000 - 1000  # 7000


def test_net_selling():
    def fetch(_t):
        return {
            "insider_transactions": [
                {"Shares": 10_000, "Transaction": "Sale"},
                {"Shares": 2_000, "Transaction": "Sell at loss"},
                {"Shares": 1_000, "Transaction": "Purchase"},
            ],
        }

    o = get_ownership("MSFT", fetch=fetch)
    assert o.insider_activity == "net selling"
    assert o.insider_net_shares == 1_000 - 12_000  # -11000


def test_neutral_when_no_transactions():
    o = get_ownership("MSFT", fetch=lambda _t: {})
    assert o.insider_activity == "neutral"
    assert o.insider_net_shares is None


def test_old_yfinance_major_holders_list_format():
    """Old yfinance returns [value, label] rows with percent strings."""

    def fetch(_t):
        return {
            "major_holders": [
                ["0.14%", "% of Shares Held by All Insider"],
                ["72.30%", "% of Shares Held by Institutions"],
            ],
        }

    o = get_ownership("IBM", fetch=fetch)
    assert o.insider_pct == 0.14
    assert o.institutional_pct == 72.30


def test_missing_fields_degrade_to_none_without_crashing():
    o = get_ownership("AAPL", fetch=lambda _t: {})
    assert isinstance(o, OwnershipSummary)
    assert o.institutional_pct is None
    assert o.insider_pct is None
    assert o.top_holders == []
    assert o.insider_net_shares is None
    assert o.insider_activity == "neutral"
    assert o.source == "yfinance"  # default when fetch omits it
    assert o.as_of  # falls back to _now()


def test_unavailable_on_fetch_error():
    def boom(_t):
        raise RuntimeError("provider down")

    res = get_ownership("AAPL", fetch=boom)
    assert isinstance(res, Unavailable)
    assert res.field == "ownership"
    assert res.ticker == "AAPL"
    assert "provider down" in res.reason


def test_invalid_ticker_unavailable():
    res = get_ownership("not a ticker!", fetch=_fetch_new)
    assert isinstance(res, Unavailable)


def test_format_ends_with_disclaimer_and_reflects_nuance():
    o = get_ownership("AAPL", fetch=_fetch_new)
    text = format_ownership(o)
    assert text.rstrip().endswith("Not financial advice.")
    assert "net BUYING" in text
    assert "Vanguard Group" in text
    assert "71.0%" in text


def test_format_selling_nuance_notes_benign_reasons():
    def fetch(_t):
        return {"insider_transactions": [{"Shares": 9999, "Transaction": "Sale"}]}

    o = get_ownership("X", fetch=fetch)
    text = format_ownership(o)
    assert "net SELLING" in text
    assert "benign" in text  # caution framed conservatively
    assert text.rstrip().endswith("Not financial advice.")
