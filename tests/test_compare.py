import pandas as pd
import pytest
from agent.compare import compare_tickers, format_compare
from data.market import Fundamentals, Quote, Unavailable


def _rising():
    return pd.DataFrame({"Close": [float(i) for i in range(1, 261)]})


def _falling():
    return pd.DataFrame({"Close": [float(i) for i in range(260, 0, -1)]})


class FakeMarket:
    """Canned per-ticker quotes/fundamentals/history; anything unknown => Unavailable."""

    def __init__(self, data):
        self._data = data  # ticker -> {price, pe, margin, hist}

    def get_quote(self, t):
        t = t.upper()
        d = self._data.get(t)
        if d is None or d.get("price") is None:
            return Unavailable("quote", t, "n/a")
        return Quote(t, d["price"], None, None, None, None, "USD", "t", "yfinance")

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
            # Strong: cheap P/E, high margin, rising trend.
            "AAA": {"price": 260.0, "pe": 12.0, "margin": 0.30, "hist": _rising()},
            # Weak: expensive P/E, falling trend.
            "BBB": {"price": 50.0, "pe": 90.0, "margin": 0.01, "hist": _falling()},
        }
    )


def test_compare_ranks_higher_composite_first():
    result = compare_tickers(["AAA", "BBB"], _market())
    assert result["ranked"][0] == "AAA"
    assert result["ranked"] == ["AAA", "BBB"]
    rows = {r["ticker"]: r for r in result["rows"]}
    assert rows["AAA"]["composite"] > rows["BBB"]["composite"]
    assert rows["AAA"]["price"] == 260.0
    assert rows["AAA"]["pe"] == 12.0
    assert rows["AAA"]["trend"] == "up"


def test_compare_tolerates_unavailable_ticker():
    # ZZZ is unknown => everything Unavailable, fields None, still ranked (last).
    result = compare_tickers(["AAA", "ZZZ"], _market())
    rows = {r["ticker"]: r for r in result["rows"]}
    assert rows["ZZZ"]["price"] is None
    assert rows["ZZZ"]["pe"] is None
    assert rows["ZZZ"]["trend_strength"] is None
    assert result["ranked"][0] == "AAA"
    assert set(result["ranked"]) == {"AAA", "ZZZ"}


def test_compare_validates_count():
    with pytest.raises(ValueError):
        compare_tickers(["AAA"], _market())  # too few
    with pytest.raises(ValueError):
        compare_tickers(["A", "B", "C", "D", "E", "F"], _market())  # too many


def test_format_compare_has_table_and_disclaimer():
    out = format_compare(compare_tickers(["AAA", "BBB"], _market()))
    assert "AAA" in out and "BBB" in out
    assert "Ranked" in out
    assert "⚠️ Not financial advice." in out
