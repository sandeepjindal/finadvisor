import pandas as pd
from agent.discovery import (
    DEFAULT_UNIVERSE,
    discover_stocks,
    format_discovery,
    parse_criteria,
)
from data.market import Fundamentals, Unavailable


def _rising():
    # Oscillating uptrend: net up (so trend=="up", trend_strength>0) but RSI stays
    # moderate (avg gain > avg loss, RS~2 => RSI~66) so it isn't flagged overbought.
    close = [100.0]
    for i in range(1, 260):
        close.append(close[-1] + (2.0 if i % 2 else -1.0))
    return pd.DataFrame({"Close": close})


def _falling():
    return pd.DataFrame({"Close": [float(i) for i in range(260, 0, -1)]})


class FakeMarket:
    def __init__(self, data):
        self._data = data

    def get_quote(self, t):
        return Unavailable("quote", t.upper(), "n/a")  # unused by discovery

    def get_fundamentals(self, t):
        t = t.upper()
        d = self._data.get(t)
        if d is None or d.get("pe") is None:
            return Unavailable("fundamentals", t, "n/a")
        return Fundamentals(
            t, d["pe"], None, None, d.get("margin"), None, "t", "yfinance"
        )

    def get_history(self, t, period="1y"):
        t = t.upper()
        d = self._data.get(t)
        if d is None or d.get("hist") is None:
            return Unavailable("history", t, "n/a")
        return d["hist"]


def _market():
    return FakeMarket(
        {
            # Cheap + uptrend + profitable.
            "GOODUP": {"pe": 12.0, "margin": 0.25, "hist": _rising()},
            # Expensive but uptrend.
            "PRICEY": {"pe": 90.0, "margin": 0.20, "hist": _rising()},
            # Cheap but downtrend.
            "CHEAPD": {"pe": 10.0, "margin": 0.05, "hist": _falling()},
        }
    )


_UNIVERSE = ["GOODUP", "PRICEY", "CHEAPD"]


def test_default_universe_is_reasonable():
    assert "AAPL" in DEFAULT_UNIVERSE
    assert 5 <= len(DEFAULT_UNIVERSE) <= 30


def test_max_pe_filters_out_expensive_name():
    result = discover_stocks(
        {"max_pe": 20.0}, _market(), universe=_UNIVERSE
    )
    tickers = [m["ticker"] for m in result["matches"]]
    assert "PRICEY" not in tickers  # P/E 90 filtered
    assert "GOODUP" in tickers and "CHEAPD" in tickers


def test_trend_up_requirement_includes_uptrend_name():
    result = discover_stocks(
        {"trend": "up", "min_trend_strength": 0.0}, _market(), universe=_UNIVERSE
    )
    tickers = [m["ticker"] for m in result["matches"]]
    assert "GOODUP" in tickers and "PRICEY" in tickers
    assert "CHEAPD" not in tickers  # downtrend excluded


def test_combined_criteria_and_ranking():
    result = discover_stocks(
        {"max_pe": 20.0, "trend": "up", "min_profit_margin": 0.0},
        _market(),
        universe=_UNIVERSE,
    )
    tickers = [m["ticker"] for m in result["matches"]]
    assert tickers == ["GOODUP"]  # only one satisfies all three
    assert result["matches"][0]["why"]


def test_unavailable_universe_member_is_skipped():
    result = discover_stocks(
        {"max_pe": 20.0}, _market(), universe=_UNIVERSE + ["NOPE"]
    )
    tickers = [m["ticker"] for m in result["matches"]]
    assert "NOPE" not in tickers  # everything Unavailable => no real P/E => filtered


def test_parse_criteria_maps_phrases():
    c = parse_criteria("find me cheap profitable semis in an uptrend")
    assert c["max_pe"] == 20.0
    assert c["trend"] == "up"
    assert c["min_trend_strength"] == 0.0
    assert c["min_profit_margin"] == 0.0


def test_parse_criteria_empty():
    assert parse_criteria("just some random words") == {}


def test_format_discovery_has_disclaimer():
    result = discover_stocks({"max_pe": 20.0}, _market(), universe=_UNIVERSE)
    out = format_discovery(result)
    assert "GOODUP" in out
    assert "⚠️ Not financial advice." in out
