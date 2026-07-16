"""Offline tests for agent/options_advisor.py — canned chain + fake market, no network."""

from __future__ import annotations

from agent.options_advisor import (
    OptionAssessment,
    assess_option,
    enrich_option,
    format_option,
    suggest_conservative_strategy,
)
from data.market import Quote, Unavailable


class FakeMarket:
    def __init__(self, price=100.0, ticker="AAPL"):
        self._price = price
        self._ticker = ticker

    def get_quote(self, t):
        return Quote(
            t.upper(), self._price, None, None, None, None, "USD", "t", "yfinance"
        )


class DeadMarket:
    def get_quote(self, t):
        return Unavailable("quote", t, "down")


class _Chain:
    def __init__(self, calls, puts, expiry="2026-08-21"):
        self.calls = calls
        self.puts = puts
        self.expiry = expiry


def _fetch(ticker, expiry):
    calls = [
        {
            "strike": 100.0,
            "bid": 5.0,
            "ask": 5.4,
            "lastPrice": 5.2,
            "impliedVolatility": 0.45,
            "volume": 1200,
            "openInterest": 800,
        },
        {
            "strike": 110.0,
            "bid": 1.0,
            "ask": 1.2,
            "lastPrice": 1.1,
            "impliedVolatility": 0.50,
            "volume": 50,
            "openInterest": 5000,
        },
    ]
    puts = [
        {
            "strike": 90.0,
            "bid": 2.0,
            "ask": 2.4,
            "lastPrice": 2.2,
            "impliedVolatility": 0.42,
            "volume": 300,
            "openInterest": 300,
        },
    ]
    return _Chain(calls, puts)


# IV history where 0.45 sits near the top => rich (high IV rank).
_RICH_HISTORY = [0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.38, 0.40, 0.42, 0.44]
# IV history where 0.45 sits near the bottom => cheap (low IV rank).
_CHEAP_HISTORY = [0.44, 0.50, 0.55, 0.60, 0.65, 0.70, 0.72, 0.75, 0.80, 0.90]


def test_assess_option_returns_break_even_prob_and_verdict():
    a = assess_option(
        "AAPL", FakeMarket(price=100.0), strike=100.0, expiry="2026-08-21",
        opt_type="call", chain_fetch=_fetch, iv_history=_RICH_HISTORY,
    )
    assert isinstance(a, OptionAssessment)
    assert a.ticker == "AAPL" and a.type == "call" and a.strike == 100.0
    assert a.premium == 5.2
    assert a.break_even == 105.2  # 100 + 5.2
    assert a.prob_itm is not None and 0.0 <= a.prob_itm <= 1.0
    assert a.verdict
    assert a.citations  # numbers are cited
    assert any(c.metric == "break_even" for c in a.citations)
    assert any(c.metric == "prob_itm" for c in a.citations)


def test_iv_rich_verdict_favours_selling_premium():
    a = assess_option(
        "AAPL", FakeMarket(price=100.0), strike=100.0, expiry="2026-08-21",
        opt_type="call", chain_fetch=_fetch, iv_history=_RICH_HISTORY,
    )
    assert isinstance(a, OptionAssessment)
    assert a.iv_rank is not None and a.iv_rank >= 0.7
    low = a.verdict.lower()
    assert "rich" in low
    assert "covered call" in low or "cash-secured put" in low or "sell" in low


def test_iv_cheap_verdict_notes_cheap_but_warns():
    a = assess_option(
        "AAPL", FakeMarket(price=100.0), strike=100.0, expiry="2026-08-21",
        opt_type="call", chain_fetch=_fetch, iv_history=_CHEAP_HISTORY,
    )
    assert isinstance(a, OptionAssessment)
    assert a.iv_rank is not None and a.iv_rank <= 0.3
    assert "cheap" in a.verdict.lower()


def test_disclaimer_present_in_format_option():
    a = assess_option(
        "AAPL", FakeMarket(), strike=100.0, expiry="2026-08-21",
        opt_type="call", chain_fetch=_fetch, iv_history=_RICH_HISTORY,
    )
    text = format_option(a)
    assert "Options can lose 100% of premium" in text
    assert "Not financial advice." in text


def test_enrich_noops_with_llm_none():
    a = assess_option(
        "AAPL", FakeMarket(), strike=100.0, expiry="2026-08-21",
        opt_type="call", chain_fetch=_fetch,
    )
    out = enrich_option(a, None)
    assert out.llm_rationale is None


def test_enrich_llm_error_is_safe():
    class Boom:
        def ask(self, messages):
            raise RuntimeError("llm down")

    a = assess_option(
        "AAPL", FakeMarket(), strike=100.0, expiry="2026-08-21",
        opt_type="call", chain_fetch=_fetch,
    )
    out = enrich_option(a, Boom())
    assert out.llm_rationale is None  # unchanged, no crash


def test_enrich_adds_rationale():
    class FakeLLM:
        def ask(self, messages):
            return "Prefer a covered call here since IV is rich."

    a = assess_option(
        "AAPL", FakeMarket(), strike=100.0, expiry="2026-08-21",
        opt_type="call", chain_fetch=_fetch,
    )
    out = enrich_option(a, FakeLLM())
    assert out.llm_rationale and "covered call" in out.llm_rationale.lower()


def test_unavailable_when_strike_not_found():
    out = assess_option(
        "AAPL", FakeMarket(), strike=999.0, expiry="2026-08-21",
        opt_type="call", chain_fetch=_fetch,
    )
    assert isinstance(out, Unavailable)


def test_unavailable_when_spot_missing():
    out = assess_option(
        "AAPL", DeadMarket(), strike=100.0, expiry="2026-08-21",
        opt_type="call", chain_fetch=_fetch,
    )
    assert isinstance(out, Unavailable)


def test_unusual_activity_flagged_in_assessment():
    a = assess_option(
        "AAPL", FakeMarket(), strike=100.0, expiry="2026-08-21",
        opt_type="call", chain_fetch=_fetch,
    )
    # strike 100 call has volume 1200 > OI 800 => unusual
    assert a.unusual is True


def test_suggest_conservative_strategy_is_educational():
    text = suggest_conservative_strategy("AAPL", FakeMarket(price=100.0), chain_fetch=_fetch)
    low = text.lower()
    assert "covered call" in low and "cash-secured put" in low
    assert "naked long call" in low
    assert "Not financial advice." in text


def test_suggest_conservative_strategy_handles_missing_spot():
    text = suggest_conservative_strategy("AAPL", DeadMarket(), chain_fetch=_fetch)
    assert "unavailable" in text.lower()
    assert "Not financial advice." in text
