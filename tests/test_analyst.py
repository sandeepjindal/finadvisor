"""Offline tests for data/analyst.py — all data is canned/injected, no network."""

from __future__ import annotations

from datetime import date

from data.analyst import (
    AnalystRatings,
    Catalysts,
    GrowthEstimates,
    format_analyst,
    get_analyst_ratings,
    get_catalysts,
    get_growth_estimates,
)
from data.market import Quote, Unavailable


# --------------------------------------------------------------------------- analyst ratings


def _analyst_fetch(ticker):
    return {
        # yfinance-style recommendations: current period "0m" plus older rows.
        "recommendations": [
            {"period": "0m", "strongBuy": 20, "buy": 6, "hold": 2, "sell": 1, "strongSell": 0},
            {"period": "-1m", "strongBuy": 18, "buy": 8, "hold": 3, "sell": 1, "strongSell": 0},
        ],
        "analyst_price_targets": {
            "current": 100.0,
            "low": 90.0,
            "high": 160.0,
            "mean": 120.0,
            "median": 118.0,
        },
    }


def test_consensus_strong_buy_from_counts():
    r = get_analyst_ratings("AAPL", fetch=_analyst_fetch)
    assert isinstance(r, AnalystRatings)
    assert r.consensus == "Strong Buy"
    assert r.strong_buy == 20 and r.buy == 6 and r.hold == 2
    assert r.source == "yfinance"


def test_implied_upside_math():
    r = get_analyst_ratings("AAPL", fetch=_analyst_fetch)
    assert isinstance(r, AnalystRatings)
    assert r.mean_target == 120.0
    assert r.current_price == 100.0
    # target 120 vs price 100 -> +20%
    assert abs(r.implied_upside_pct - 20.0) < 1e-9


def test_consensus_hold_from_counts():
    def fetch(t):
        return {
            "recommendations": [
                {"period": "0m", "strongBuy": 1, "buy": 2, "hold": 12, "sell": 2, "strongSell": 1}
            ]
        }

    r = get_analyst_ratings("XYZ", fetch=fetch)
    assert isinstance(r, AnalystRatings)
    assert r.consensus == "Hold"


def test_current_price_fallback_via_market():
    class _Market:
        def get_quote(self, ticker):
            return Quote(
                ticker=ticker,
                price=200.0,
                previous_close=None,
                change=None,
                change_pct=None,
                volume=None,
                currency="USD",
                as_of="2026-07-16T00:00:00+00:00",
                source="test",
            )

    def fetch(t):
        return {
            "recommendations": [
                {"period": "0m", "strongBuy": 5, "buy": 5, "hold": 5, "sell": 0, "strongSell": 0}
            ],
            # No current in the price targets -> should fall back to market quote.
            "analyst_price_targets": {"mean": 240.0},
        }

    r = get_analyst_ratings("MSFT", _Market(), fetch=fetch)
    assert isinstance(r, AnalystRatings)
    assert r.current_price == 200.0
    assert r.mean_target == 240.0
    assert abs(r.implied_upside_pct - 20.0) < 1e-9


def test_analyst_version_tolerance_missing_keys():
    # recommendations present but NO price targets -> counts parsed, targets None, no crash.
    def fetch(t):
        return {
            "recommendations": [
                {"period": "0m", "strongBuy": 10, "buy": 3, "hold": 1, "sell": 0, "strongSell": 0}
            ]
        }

    r = get_analyst_ratings("NVDA", fetch=fetch)
    assert isinstance(r, AnalystRatings)
    assert r.consensus == "Strong Buy"
    assert r.mean_target is None
    assert r.current_price is None
    assert r.implied_upside_pct is None


def test_analyst_empty_summary_key_tolerated():
    # Uses recommendations_summary alias with snake_case keys; still parses.
    def fetch(t):
        return {
            "recommendations_summary": [
                {"period": "0m", "strong_buy": 2, "buy": 3, "hold": 10, "sell": 4, "strong_sell": 2}
            ]
        }

    r = get_analyst_ratings("GE", fetch=fetch)
    assert isinstance(r, AnalystRatings)
    assert r.strong_buy == 2 and r.strong_sell == 2
    assert r.consensus in ("Hold", "Sell")


def test_analyst_unavailable_on_fetch_error():
    def boom(t):
        raise RuntimeError("network down")

    r = get_analyst_ratings("AAPL", fetch=boom)
    assert isinstance(r, Unavailable)
    assert r.field == "analyst_ratings"
    assert "network down" in r.reason


def test_analyst_unavailable_on_bad_ticker():
    r = get_analyst_ratings("not a ticker!", fetch=_analyst_fetch)
    assert isinstance(r, Unavailable)


def test_analyst_no_data_is_unavailable():
    r = get_analyst_ratings("AAPL", fetch=lambda t: {})
    assert isinstance(r, Unavailable)
    assert r.reason == "no analyst data"


def test_format_analyst_disclaimer():
    r = get_analyst_ratings("AAPL", fetch=_analyst_fetch)
    assert isinstance(r, AnalystRatings)
    out = format_analyst(r)
    assert "AAPL" in out
    assert "Strong Buy" in out
    assert "+20.0%" in out
    assert out.strip().endswith("Not financial advice.")


# --------------------------------------------------------------------------- growth estimates


def test_growth_estimates_parsed_from_map():
    def fetch(t):
        return {
            "growth_estimates": {"0q": 0.05, "+1q": 0.08, "0y": 0.12, "+1y": 0.18, "+5y": 0.14},
            "revenue_estimate": {"+1q": 0.06, "+1y": 0.10},
        }

    g = get_growth_estimates("AAPL", fetch=fetch)
    assert isinstance(g, GrowthEstimates)
    assert g.eps_growth_next_year == 0.18
    assert g.long_term_growth == 0.14
    assert g.revenue_growth_next_year == 0.10
    assert g.source == "yfinance"


def test_growth_estimates_from_list_of_dicts():
    def fetch(t):
        return {
            "growth_estimates": [
                {"period": "+1y", "growth": 0.20},
                {"period": "+5y", "growth": 0.11},
            ],
            "revenue_estimate": [{"period": "+1y", "growth": 0.09}],
        }

    g = get_growth_estimates("AAPL", fetch=fetch)
    assert isinstance(g, GrowthEstimates)
    assert g.eps_growth_next_year == 0.20
    assert g.long_term_growth == 0.11
    assert g.revenue_growth_next_year == 0.09


def test_growth_eps_fallback_to_earnings_estimate():
    def fetch(t):
        return {
            "growth_estimates": {"+5y": 0.13},  # no +1y here
            "earnings_estimate": {"+1y": 0.16},
        }

    g = get_growth_estimates("AAPL", fetch=fetch)
    assert isinstance(g, GrowthEstimates)
    assert g.eps_growth_next_year == 0.16
    assert g.long_term_growth == 0.13


def test_growth_version_tolerance_missing_keys():
    g = get_growth_estimates("AAPL", fetch=lambda t: {})
    assert isinstance(g, GrowthEstimates)
    assert g.eps_growth_next_year is None
    assert g.revenue_growth_next_year is None
    assert g.long_term_growth is None


def test_growth_unavailable_on_fetch_error():
    def boom(t):
        raise RuntimeError("boom")

    g = get_growth_estimates("AAPL", fetch=boom)
    assert isinstance(g, Unavailable)
    assert g.field == "growth_estimates"


# --------------------------------------------------------------------------------- catalysts


def test_catalysts_next_earnings_parsed_from_date():
    def fetch(t):
        return {"calendar": {"Earnings Date": [date(2026, 8, 1), date(2026, 8, 5)]}}

    c = get_catalysts("AAPL", fetch=fetch)
    assert isinstance(c, Catalysts)
    assert c.next_earnings_date == "2026-08-01"
    assert c.recent_forms == []
    assert c.source == "yfinance"


def test_catalysts_next_earnings_from_string():
    def fetch(t):
        return {"calendar": {"Earnings Date": "2026-09-15T00:00:00"}}

    c = get_catalysts("AAPL", fetch=fetch)
    assert isinstance(c, Catalysts)
    assert c.next_earnings_date == "2026-09-15"


def test_catalysts_recent_forms_hook():
    def fetch(t):
        return {
            "calendar": {"Earnings Date": [date(2026, 8, 1)]},
            "recent_forms": ["8-K", "10-Q"],
        }

    c = get_catalysts("AAPL", fetch=fetch)
    assert isinstance(c, Catalysts)
    assert c.recent_forms == ["8-K", "10-Q"]


def test_catalysts_version_tolerance_no_calendar():
    c = get_catalysts("AAPL", fetch=lambda t: {})
    assert isinstance(c, Catalysts)
    assert c.next_earnings_date is None
    assert c.recent_forms == []


def test_catalysts_unavailable_on_fetch_error():
    def boom(t):
        raise RuntimeError("kaboom")

    c = get_catalysts("AAPL", fetch=boom)
    assert isinstance(c, Unavailable)
    assert c.field == "catalysts"
