"""Offline tests for data/options.py — all data is canned/injected, no network."""

from __future__ import annotations

from data.market import Unavailable
from data.options import (
    OptionQuote,
    break_even,
    get_option_chain,
    iv_rank,
    prob_itm,
    unusual_activity,
)


class _Chain:
    """Stand-in for a yfinance ``option_chain`` result: has .calls/.puts (list[dict])."""

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
            "impliedVolatility": 0.35,
            "volume": 1200,
            "openInterest": 800,
        },
        {
            "strike": 110.0,
            "bid": 1.0,
            "ask": 1.2,
            "lastPrice": 1.1,
            "impliedVolatility": 0.40,
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
            "impliedVolatility": 0.38,
            "volume": 300,
            "openInterest": 300,
        },
    ]
    return _Chain(calls, puts)


def test_chain_parses_from_injected_fetch():
    chain = get_option_chain("AAPL", "2026-08-21", fetch=_fetch)
    assert not isinstance(chain, Unavailable)
    assert len(chain) == 3
    calls = [o for o in chain if o.type == "call"]
    puts = [o for o in chain if o.type == "put"]
    assert len(calls) == 2 and len(puts) == 1
    c = next(o for o in calls if o.strike == 100.0)
    assert c.ticker == "AAPL"
    assert c.expiry == "2026-08-21"
    assert c.bid == 5.0 and c.ask == 5.4 and c.last == 5.2
    assert c.implied_volatility == 0.35
    assert c.volume == 1200 and c.open_interest == 800


def test_chain_picks_expiry_from_fetch_when_none():
    chain = get_option_chain("AAPL", None, fetch=_fetch)
    assert not isinstance(chain, Unavailable)
    assert chain[0].expiry == "2026-08-21"


def test_invalid_ticker_is_unavailable():
    out = get_option_chain("not a ticker!", "2026-08-21", fetch=_fetch)
    assert isinstance(out, Unavailable)


def test_fetch_error_is_unavailable():
    def boom(t, e):
        raise RuntimeError("provider down")

    out = get_option_chain("AAPL", "2026-08-21", fetch=boom)
    assert isinstance(out, Unavailable)


def test_break_even_call_and_put_math():
    call = OptionQuote("X", "2026-08-21", "call", 100.0, 5.0, 5.4, 5.2, 0.3, 1, 1)
    put = OptionQuote("X", "2026-08-21", "put", 90.0, 2.0, 2.4, 2.2, 0.3, 1, 1)
    # premium falls back to last (5.2 / 2.2)
    assert break_even(call, spot=101.0) == 105.2
    assert break_even(put, spot=95.0) == 87.8


def test_break_even_uses_mid_when_no_last():
    call = OptionQuote("X", "2026-08-21", "call", 100.0, 4.0, 6.0, None, 0.3, 1, 1)
    assert break_even(call, spot=101.0) == 105.0  # strike + mid(4,6)=5


def test_break_even_none_without_premium():
    call = OptionQuote("X", "2026-08-21", "call", 100.0, None, None, None, 0.3, 1, 1)
    assert break_even(call, spot=101.0) is None


def test_prob_itm_in_unit_interval_and_monotonic():
    # Deep ITM call (spot >> strike) should have high POP; deep OTM low POP.
    deep_itm = prob_itm(150.0, 100.0, 0.3, 30, is_call=True)
    atm = prob_itm(100.0, 100.0, 0.3, 30, is_call=True)
    deep_otm = prob_itm(60.0, 100.0, 0.3, 30, is_call=True)
    for p in (deep_itm, atm, deep_otm):
        assert p is not None and 0.0 <= p <= 1.0
    assert deep_itm > atm > deep_otm
    assert deep_itm > 0.9 and deep_otm < 0.1


def test_prob_itm_call_put_complementary():
    call = prob_itm(105.0, 100.0, 0.3, 30, is_call=True)
    put = prob_itm(105.0, 100.0, 0.3, 30, is_call=False)
    assert call is not None and put is not None
    assert abs((call + put) - 1.0) < 1e-9


def test_prob_itm_none_on_bad_inputs():
    assert prob_itm(None, 100.0, 0.3, 30, True) is None
    assert prob_itm(100.0, 100.0, 0.0, 30, True) is None  # zero IV invalid
    assert prob_itm(100.0, 100.0, 0.3, 0, True) is None  # zero DTE invalid
    assert prob_itm(-1.0, 100.0, 0.3, 30, True) is None


def test_iv_rank_percentile():
    hist = [0.20, 0.25, 0.30, 0.35, 0.40]
    assert iv_rank(0.30, hist) == 0.6  # three of five <= 0.30
    assert iv_rank(0.45, hist) == 1.0  # above all
    assert iv_rank(0.10, hist) == 0.0  # below all


def test_iv_rank_insufficient_data():
    assert iv_rank(0.30, []) is None
    assert iv_rank(0.30, [0.25]) is None
    assert iv_rank(None, [0.2, 0.3, 0.4]) is None


def test_unusual_activity_volume_gt_oi():
    hot = OptionQuote("X", "e", "call", 100.0, 1, 1, 1, 0.3, volume=1500, open_interest=800)
    cold = OptionQuote("X", "e", "call", 100.0, 1, 1, 1, 0.3, volume=50, open_interest=5000)
    assert unusual_activity(hot) is True
    assert unusual_activity(cold) is False


def test_unusual_activity_requires_both_and_positive_oi():
    no_vol = OptionQuote("X", "e", "call", 100.0, 1, 1, 1, 0.3, None, 800)
    no_oi = OptionQuote("X", "e", "call", 100.0, 1, 1, 1, 0.3, 1500, None)
    zero_oi = OptionQuote("X", "e", "call", 100.0, 1, 1, 1, 0.3, 1500, 0)
    assert unusual_activity(no_vol) is False
    assert unusual_activity(no_oi) is False
    assert unusual_activity(zero_oi) is False
