"""Offline tests for data/valuation.py — all data is canned/injected, no network."""

from __future__ import annotations

from data.market import Unavailable
from data.valuation import (
    ValuationContext,
    format_valuation,
    get_valuation_context,
)


def _fetch(**info):
    def fetch(ticker):
        return info

    return fetch


def test_verdict_cheap_when_peg_below_one():
    v = get_valuation_context("AAA", fetch=_fetch(pegRatio=0.5))
    assert isinstance(v, ValuationContext)
    assert v.peg == 0.5
    assert v.verdict == "cheap"


def test_verdict_rich_when_peg_above_two():
    v = get_valuation_context("AAA", fetch=_fetch(pegRatio=3.0))
    assert v.verdict == "rich"


def test_verdict_fair_when_peg_between():
    v = get_valuation_context("AAA", fetch=_fetch(pegRatio=1.5))
    assert v.verdict == "fair"


def test_all_multiples_parsed():
    v = get_valuation_context(
        "AAA",
        fetch=_fetch(
            trailingPE=25.0,
            forwardPE=20.0,
            pegRatio=1.2,
            priceToSalesTrailing12Months=5.0,
            enterpriseToEbitda=14.0,
        ),
    )
    assert v.pe == 25.0
    assert v.forward_pe == 20.0
    assert v.peg == 1.2
    assert v.ps == 5.0
    assert v.ev_ebitda == 14.0
    assert v.verdict == "fair"


def test_verdict_rich_from_multiple_signals():
    v = get_valuation_context(
        "AAA",
        fetch=_fetch(forwardPE=40.0, priceToSalesTrailing12Months=15.0, enterpriseToEbitda=25.0),
    )
    assert v.verdict == "rich"


def test_verdict_cheap_from_multiple_signals():
    v = get_valuation_context(
        "AAA",
        fetch=_fetch(forwardPE=10.0, priceToSalesTrailing12Months=0.5, enterpriseToEbitda=8.0),
    )
    assert v.verdict == "cheap"


def test_verdict_unclear_when_no_multiples():
    v = get_valuation_context("AAA", fetch=_fetch())
    assert v.verdict == "unclear"
    assert v.pe is None
    assert v.reasons


def test_missing_fields_degrade_to_none():
    v = get_valuation_context("AAA", fetch=_fetch(trailingPE=18.0))
    assert v.pe == 18.0
    assert v.forward_pe is None
    assert v.peg is None
    assert v.ps is None
    assert v.ev_ebitda is None


def test_nan_and_garbage_degrade_to_none():
    v = get_valuation_context(
        "AAA", fetch=_fetch(pegRatio=float("nan"), forwardPE="junk", trailingPE=None)
    )
    assert v.peg is None
    assert v.forward_pe is None
    assert v.verdict == "unclear"


def test_unavailable_on_fetch_error():
    def boom(ticker):
        raise RuntimeError("network down")

    res = get_valuation_context("AAA", fetch=boom)
    assert isinstance(res, Unavailable)
    assert res.field == "valuation"


def test_unavailable_on_bad_ticker():
    assert isinstance(get_valuation_context("!!!", fetch=_fetch(pegRatio=1.0)), Unavailable)


def test_format_ends_with_disclaimer():
    v = get_valuation_context("AAA", fetch=_fetch(pegRatio=0.5))
    text = format_valuation(v)
    assert text.strip().endswith("Not financial advice.")
    assert "verdict" in text
