import pytest

from data.market import MarketData, Quote, Unavailable, YFinanceProvider


class _FakeTicker:
    def __init__(self, symbol):
        self.symbol = symbol

    @property
    def info(self):
        if self.symbol == "BOOM":
            raise RuntimeError("info failed")
        return {
            "sector": "Energy",
            "currentPrice": 80.5,
            "previousClose": 79.0,
            "currency": "USD",
            "volume": 1234,
        }


class _FakeYF:
    Ticker = _FakeTicker


def test_get_sector_from_fake_yfinance(monkeypatch):
    monkeypatch.setattr("data.market.yf", _FakeYF)
    prov = YFinanceProvider()
    assert prov.get_sector("XLE") == "Energy"


def test_get_sector_returns_none_on_error(monkeypatch):
    monkeypatch.setattr("data.market.yf", _FakeYF)
    prov = YFinanceProvider()
    assert prov.get_sector("BOOM") is None


def test_get_futures_from_fake_yfinance(monkeypatch):
    monkeypatch.setattr("data.market.yf", _FakeYF)
    prov = YFinanceProvider()
    q = prov.get_futures("CL=F")  # '=' bypasses equity ticker validation
    assert isinstance(q, Quote)
    assert q.ticker == "CL=F"
    assert q.price == 80.5
    assert q.source == "yfinance"


class _FakeProvider:
    """Injected provider so the facade is tested without any yfinance."""

    def get_sector(self, ticker):
        return {"XOM": "Energy"}.get(ticker)

    def get_futures(self, symbol):
        return Quote(
            ticker=symbol,
            price=2000.0,
            previous_close=1990.0,
            change=10.0,
            change_pct=0.5,
            volume=10,
            currency="USD",
            as_of="now",
            source="fake",
        )


def test_facade_get_sector_and_futures():
    md = MarketData(providers=[_FakeProvider()])
    assert md.get_sector("XOM") == "Energy"
    assert md.get_sector("ZZZ") is None
    gold = md.get_futures("GC=F")
    assert isinstance(gold, Quote)
    assert gold.price == 2000.0


def test_facade_get_sector_none_when_provider_lacks_method():
    class _Bare:
        pass

    md = MarketData(providers=[_Bare()])
    assert md.get_sector("XOM") is None


def test_facade_get_futures_unavailable_on_failure():
    class _Failing:
        def get_futures(self, symbol):
            raise RuntimeError("nope")

    md = MarketData(providers=[_Failing()])
    assert isinstance(md.get_futures("CL=F"), Unavailable)
