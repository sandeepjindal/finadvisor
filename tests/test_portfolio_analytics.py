"""OFFLINE tests for portfolio-level analytics (Work-stream G1). Uses a fake market
(canned quotes, sectors, synthetic history frames) + in-memory sqlite. No network."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from agent.portfolio_analytics import (
    PortfolioReport,
    analyze_portfolio,
    format_portfolio,
)
from brain.db import init_db
from brain.holdings import add_holding
from data.market import Quote, Unavailable


def _quote(ticker: str, price: float) -> Quote:
    return Quote(
        ticker=ticker,
        price=price,
        previous_close=price,
        change=0.0,
        change_pct=0.0,
        volume=1000,
        currency="USD",
        as_of="2026-07-15T00:00:00Z",
        source="fake",
    )


def _history(seed: int | None = None, series: np.ndarray | None = None) -> pd.DataFrame:
    """A 200-row daily Close frame. Deterministic per seed (independent series), or a
    caller-supplied returns/price series for identical-history correlation tests."""
    idx = pd.date_range("2025-01-01", periods=200, freq="D")
    if series is not None:
        close = series
    else:
        rng = np.random.default_rng(seed)
        rets = rng.normal(0.0005, 0.02, size=200)
        close = 100.0 * np.cumprod(1.0 + rets)
    return pd.DataFrame({"Close": close}, index=idx)


class FakeMarket:
    def __init__(self, quotes=None, sectors=None, histories=None):
        self._quotes = quotes or {}
        self._sectors = sectors or {}
        self._histories = histories or {}

    def get_quote(self, ticker):
        t = ticker.upper()
        q = self._quotes.get(t)
        if q is None:
            return Unavailable("quote", t, "no canned quote")
        return q

    def get_sector(self, ticker):
        return self._sectors.get(ticker.upper())

    def get_history(self, ticker, period="1y"):
        t = ticker.upper()
        h = self._histories.get(t)
        if h is None:
            return Unavailable("history", t, "no canned history")
        return h


# A pinned identical close series for the correlation-flag test.
_IDENTICAL = 100.0 * np.cumprod(
    1.0 + np.random.default_rng(7).normal(0.0005, 0.02, size=200)
)


class StubRules:
    max_position_weight = 0.25


def test_total_value_and_weights(tmp_path):
    conn = init_db(str(tmp_path / "brain.db"))
    add_holding(conn, "AAA", 10, 5.0)
    add_holding(conn, "BBB", 20, 5.0)
    market = FakeMarket(
        quotes={"AAA": _quote("AAA", 10.0), "BBB": _quote("BBB", 20.0)},
        sectors={"AAA": "Tech", "BBB": "Energy"},
    )
    report = analyze_portfolio(conn, market, rules=StubRules())
    assert isinstance(report, PortfolioReport)
    # AAA: 10*10=100, BBB: 20*20=400 -> 500 total
    assert report.total_value == 500.0
    weights = {p["ticker"]: p["weight"] for p in report.positions}
    assert abs(weights["AAA"] - 0.2) < 1e-9
    assert abs(weights["BBB"] - 0.8) < 1e-9
    assert any(c.metric == "total_value" and c.value == 500.0 for c in report.citations)


def test_concentration_flag(tmp_path):
    conn = init_db(str(tmp_path / "brain.db"))
    add_holding(conn, "BIG", 100, 1.0)   # 100*90 = 9000 (huge)
    add_holding(conn, "SML", 10, 1.0)    # 10*10 = 100
    market = FakeMarket(
        quotes={"BIG": _quote("BIG", 90.0), "SML": _quote("SML", 10.0)},
    )
    report = analyze_portfolio(conn, market, rules=StubRules())
    assert report.concentration["flagged"] is True
    assert "BIG" in report.concentration["over_limit"]
    assert report.concentration["max_weight_ticker"] == "BIG"
    assert report.concentration["max_weight"] > 0.25


def test_sector_exposure_grouping(tmp_path):
    conn = init_db(str(tmp_path / "brain.db"))
    add_holding(conn, "AAA", 10, 1.0)  # 100, Tech
    add_holding(conn, "BBB", 10, 1.0)  # 100, Tech
    add_holding(conn, "CCC", 10, 1.0)  # 100, Energy
    market = FakeMarket(
        quotes={
            "AAA": _quote("AAA", 10.0),
            "BBB": _quote("BBB", 10.0),
            "CCC": _quote("CCC", 10.0),
        },
        sectors={"AAA": "Tech", "BBB": "Tech", "CCC": "Energy"},
    )
    report = analyze_portfolio(conn, market, rules=StubRules())
    assert report.sector_exposure["Tech"] == 200.0
    assert report.sector_exposure["Energy"] == 100.0


def test_high_correlation_flag_for_identical_series(tmp_path):
    conn = init_db(str(tmp_path / "brain.db"))
    add_holding(conn, "AAA", 10, 1.0)
    add_holding(conn, "BBB", 10, 1.0)
    market = FakeMarket(
        quotes={"AAA": _quote("AAA", 10.0), "BBB": _quote("BBB", 10.0)},
        histories={
            "AAA": _history(series=_IDENTICAL),
            "BBB": _history(series=_IDENTICAL),
        },
    )
    report = analyze_portfolio(conn, market, rules=StubRules())
    assert any("AAA~BBB" in f for f in report.correlation_flags)
    assert any(c.metric == "corr:AAA~BBB" for c in report.citations)


def test_diversification_score_higher_when_diversified(tmp_path):
    # Diversified: 4 equal-weight names, distinct sectors, independent histories.
    div_conn = init_db(str(tmp_path / "div.db"))
    for t in ("AAA", "BBB", "CCC", "DDD"):
        add_holding(div_conn, t, 10, 1.0)
    div_market = FakeMarket(
        quotes={t: _quote(t, 10.0) for t in ("AAA", "BBB", "CCC", "DDD")},
        sectors={"AAA": "Tech", "BBB": "Energy", "CCC": "Health", "DDD": "Finance"},
        histories={
            "AAA": _history(seed=1),
            "BBB": _history(seed=2),
            "CCC": _history(seed=3),
            "DDD": _history(seed=4),
        },
    )
    div_report = analyze_portfolio(div_conn, div_market, rules=StubRules())

    # Concentrated: one dominant name + a sliver, same sector, identical histories.
    con_conn = init_db(str(tmp_path / "con.db"))
    add_holding(con_conn, "EEE", 1000, 1.0)  # 10000
    add_holding(con_conn, "FFF", 10, 1.0)    # 100
    con_market = FakeMarket(
        quotes={"EEE": _quote("EEE", 10.0), "FFF": _quote("FFF", 10.0)},
        sectors={"EEE": "Tech", "FFF": "Tech"},
        histories={
            "EEE": _history(series=_IDENTICAL),
            "FFF": _history(series=_IDENTICAL),
        },
    )
    con_report = analyze_portfolio(con_conn, con_market, rules=StubRules())

    assert div_report.diversification_score is not None
    assert con_report.diversification_score is not None
    assert div_report.diversification_score > con_report.diversification_score


def test_portfolio_beta_is_float_or_none(tmp_path):
    conn = init_db(str(tmp_path / "brain.db"))
    add_holding(conn, "AAA", 10, 1.0)
    add_holding(conn, "BBB", 10, 1.0)
    market = FakeMarket(
        quotes={"AAA": _quote("AAA", 10.0), "BBB": _quote("BBB", 10.0)},
        histories={
            "AAA": _history(seed=11),
            "BBB": _history(seed=12),
            "SPY": _history(seed=13),
        },
    )
    report = analyze_portfolio(conn, market, rules=StubRules(), benchmark="SPY")
    assert report.portfolio_beta is None or isinstance(report.portfolio_beta, float)


def test_graceful_when_quote_unavailable(tmp_path):
    conn = init_db(str(tmp_path / "brain.db"))
    add_holding(conn, "AAA", 10, 1.0)
    add_holding(conn, "GONE", 10, 1.0)  # no canned quote -> Unavailable
    market = FakeMarket(quotes={"AAA": _quote("AAA", 10.0)})
    report = analyze_portfolio(conn, market, rules=StubRules())
    tickers = {p["ticker"] for p in report.positions}
    assert tickers == {"AAA"}
    assert report.total_value == 100.0
    assert any("GONE" in r for r in report.reasons)


def test_no_holdings_returns_empty_report(tmp_path):
    conn = init_db(str(tmp_path / "brain.db"))
    market = FakeMarket()
    report = analyze_portfolio(conn, market, rules=StubRules())
    assert report.total_value == 0.0
    assert report.positions == []
    assert report.reasons and "No holdings" in report.reasons[0]


def test_format_portfolio_ends_with_disclaimer(tmp_path):
    conn = init_db(str(tmp_path / "brain.db"))
    add_holding(conn, "AAA", 10, 1.0)
    market = FakeMarket(quotes={"AAA": _quote("AAA", 10.0)}, sectors={"AAA": "Tech"})
    report = analyze_portfolio(conn, market, rules=StubRules())
    text = format_portfolio(report)
    assert text.strip().endswith("⚠️ Not financial advice.")
    assert "AAA" in text
