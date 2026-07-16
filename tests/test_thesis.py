"""build_thesis synthesis — confirmation-required verdict + probabilistic range, composed
from the E pillars. Offline: the data pillars are patched with canned stances."""

from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

from agent.thesis import build_thesis
from brain.db import init_db
from data.market import Quote, Unavailable


class _FakeMarket:
    def get_quote(self, t):
        return Quote(t.upper(), 100.0, 99.0, 1.0, 1.0, 1000.0, "USD", "now", "test")

    def get_history(self, t, period="1y"):
        return Unavailable("history", t.upper(), "n/a")  # technical pillar skipped


def _patch(val=None, fin=None, ana=None, growth=None, own=None):
    return mock.patch.multiple(
        "data.valuation",
        get_valuation_context=mock.Mock(return_value=val),
    ), mock.patch.multiple(
        "data.financials",
        get_financial_trends=mock.Mock(return_value=fin),
    ), mock.patch.multiple(
        "data.analyst",
        get_analyst_ratings=mock.Mock(return_value=ana),
        get_growth_estimates=mock.Mock(return_value=growth),
    ), mock.patch.multiple(
        "data.ownership",
        get_ownership=mock.Mock(return_value=own),
    )


def test_thesis_all_bullish_is_strong_buy(tmp_path):
    conn = init_db(str(tmp_path / "brain.db"))
    patches = _patch(
        val=SimpleNamespace(verdict="cheap"),
        fin=SimpleNamespace(
            revenue_cagr=0.2, margin_direction="improving", fcf_positive=True,
            debt_direction="improving",
        ),
        ana=SimpleNamespace(
            consensus="Buy", implied_upside_pct=20.0, mean_target=120.0, current_price=100.0
        ),
        growth=SimpleNamespace(eps_growth_next_year=0.2, revenue_growth_next_year=0.15),
        own=SimpleNamespace(insider_activity="net buying"),
    )
    for p in patches:
        p.start()
    try:
        r = build_thesis("NVDA", _FakeMarket(), conn)
    finally:
        for p in patches:
            p.stop()

    assert r.verdict == "STRONG BUY"
    assert r.bullish >= 4 and r.bearish == 0
    assert r.scenarios["bear"] < r.scenarios["base"] < r.scenarios["bull"]
    assert r.confidence is not None


def test_thesis_conflicting_pillars_is_mixed_watch(tmp_path):
    conn = init_db(str(tmp_path / "brain.db"))
    patches = _patch(
        val=SimpleNamespace(verdict="rich"),  # bearish
        fin=SimpleNamespace(
            revenue_cagr=-0.1, margin_direction="deteriorating", fcf_positive=False,
            debt_direction="deteriorating",
        ),  # bearish
        ana=SimpleNamespace(
            consensus="Buy", implied_upside_pct=15.0, mean_target=110.0, current_price=100.0
        ),  # bullish
        growth=SimpleNamespace(eps_growth_next_year=0.2, revenue_growth_next_year=0.2),  # bullish
        own=SimpleNamespace(insider_activity="neutral"),  # neutral
    )
    for p in patches:
        p.start()
    try:
        r = build_thesis("NVDA", _FakeMarket(), conn)
    finally:
        for p in patches:
            p.stop()

    assert r.mixed is True
    assert r.verdict == "WATCH"
    assert any("mixed signals" in why.lower() for why in r.reasons)


def test_thesis_no_data_is_insufficient(tmp_path):
    conn = init_db(str(tmp_path / "brain.db"))
    un = Unavailable("x", "NVDA", "n/a")
    patches = _patch(val=un, fin=un, ana=un, growth=un, own=un)
    for p in patches:
        p.start()
    try:
        r = build_thesis("NVDA", _FakeMarket(), conn)
    finally:
        for p in patches:
            p.stop()
    assert r.verdict == "INSUFFICIENT DATA"
