from types import SimpleNamespace
from unittest import mock

import data.market as market
from data.market import MarketData, Quote, Unavailable

INFO = {
    "currentPrice": 120.0,
    "previousClose": 100.0,
    "regularMarketVolume": 1000,
    "currency": "USD",
    "trailingPE": 30.0,
    "priceToBook": 12.0,
    "marketCap": 3e12,
    "profitMargins": 0.25,
    "debtToEquity": 40.0,
}


def _ticker(info):
    return lambda t: SimpleNamespace(info=info)


def test_get_quote_maps_fields():
    with mock.patch.object(market.yf, "Ticker", _ticker(INFO)):
        q = MarketData().get_quote("nvda")
    assert isinstance(q, Quote)
    assert q.ticker == "NVDA"
    assert q.price == 120.0
    assert round(q.change, 2) == 20.0
    assert round(q.change_pct, 1) == 20.0
    assert q.source == "yfinance"


def test_get_fundamentals_maps_fields():
    with mock.patch.object(market.yf, "Ticker", _ticker(INFO)):
        f = MarketData().get_fundamentals("nvda")
    assert f.pe == 30.0
    assert f.market_cap == 3e12


def test_exception_yields_unavailable_not_fabricated():
    def boom(_):
        raise RuntimeError("network down")

    with mock.patch.object(market.yf, "Ticker", boom):
        q = MarketData().get_quote("NVDA")
    assert isinstance(q, Unavailable)
    assert q.field == "quote"
