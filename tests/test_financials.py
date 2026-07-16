"""Offline tests for data/financials.py — all data is canned/injected, no network."""

from __future__ import annotations

from data.financials import (
    FinancialTrend,
    format_financials,
    get_financial_trends,
)
from data.market import Unavailable


def _canned(**overrides):
    data = {
        "periods": ["2020", "2021", "2022", "2023", "2024"],
        # 100 -> 200 over 4 intervals -> CAGR = 2 ** (1/4) - 1 ~= 0.1892
        "revenue": [100.0, 119.0, 141.0, 168.0, 200.0],
        "gross_margin": [0.40, 0.41, 0.43, 0.44, 0.45],
        "eps": [1.0, 1.5, 2.0, 2.5, 3.0],
        "free_cash_flow": [10.0, 12.0, 15.0, 18.0, 20.0],
        "total_debt": [500.0, 480.0, 450.0, 420.0, 400.0],
    }
    data.update(overrides)

    def fetch(ticker):
        return data

    return fetch


def test_revenue_cagr_100_to_200_over_4_years():
    t = get_financial_trends("AAA", fetch=_canned())
    assert isinstance(t, FinancialTrend)
    assert t.revenue_cagr is not None
    assert abs(t.revenue_cagr - (2 ** 0.25 - 1)) < 1e-9  # ~= 0.18921


def test_margin_direction_improving():
    t = get_financial_trends("AAA", fetch=_canned())
    assert t.margin_direction == "improving"


def test_margin_direction_deteriorating():
    fetch = _canned(gross_margin=[0.45, 0.44, 0.42, 0.41, 0.30])
    t = get_financial_trends("AAA", fetch=fetch)
    assert t.margin_direction == "deteriorating"


def test_margin_direction_flat():
    fetch = _canned(gross_margin=[0.400, 0.401, 0.399, 0.4005, 0.4003])
    t = get_financial_trends("AAA", fetch=fetch)
    assert t.margin_direction == "flat"


def test_debt_direction_improving_when_debt_falls():
    # default canned debt falls 500 -> 400 -> improving
    t = get_financial_trends("AAA", fetch=_canned())
    assert t.debt_direction == "improving"


def test_debt_direction_deteriorating_when_debt_rises():
    fetch = _canned(total_debt=[400.0, 450.0, 500.0, 600.0, 700.0])
    t = get_financial_trends("AAA", fetch=fetch)
    assert t.debt_direction == "deteriorating"


def test_fcf_positive_true_and_false():
    assert get_financial_trends("AAA", fetch=_canned()).fcf_positive is True
    fetch = _canned(free_cash_flow=[10.0, 5.0, -3.0, -8.0, -12.0])
    assert get_financial_trends("AAA", fetch=fetch).fcf_positive is False


def test_gross_margin_derived_from_gross_profit():
    fetch = _canned(gross_margin=None, gross_profit=[40.0, 60.0, 70.0, 84.0, 100.0])
    t = get_financial_trends("AAA", fetch=fetch)
    # last: 100 / 200 = 0.50, first: 40 / 100 = 0.40 -> improving
    assert abs(t.gross_margin[-1] - 0.5) < 1e-9
    assert t.margin_direction == "improving"


def test_eps_falls_back_to_net_income():
    fetch = _canned(eps=None, net_income=[50.0, 60.0, 70.0])
    t = get_financial_trends("AAA", fetch=fetch)
    assert t.eps == [50.0, 60.0, 70.0]


def test_missing_fields_degrade_to_empty_and_none():
    def fetch(ticker):
        return {"revenue": [100.0, 200.0], "periods": ["2023", "2024"]}

    t = get_financial_trends("AAA", fetch=fetch)
    assert isinstance(t, FinancialTrend)
    assert t.eps == []
    assert t.gross_margin == []
    assert t.fcf_positive is None
    assert t.margin_direction == "flat"
    assert t.debt_direction == "flat"


def test_unavailable_on_fetch_error():
    def boom(ticker):
        raise RuntimeError("network down")

    res = get_financial_trends("AAA", fetch=boom)
    assert isinstance(res, Unavailable)
    assert res.field == "financials"


def test_unavailable_on_bad_ticker():
    res = get_financial_trends("!!!", fetch=_canned())
    assert isinstance(res, Unavailable)


def test_unavailable_when_no_series():
    def fetch(ticker):
        return {"periods": ["2024"]}

    assert isinstance(get_financial_trends("AAA", fetch=fetch), Unavailable)


def test_format_ends_with_disclaimer():
    t = get_financial_trends("AAA", fetch=_canned())
    text = format_financials(t)
    assert text.strip().endswith("Not financial advice.")
    assert "Revenue" in text
