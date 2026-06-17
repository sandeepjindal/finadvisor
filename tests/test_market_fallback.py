from data.market import (
    Fundamentals,
    MarketData,
    MarketDataError,
    MarketDataProvider,
    Quote,
    Unavailable,
)


class QuoteOnlyProvider(MarketDataProvider):
    def get_quote(self, ticker):
        return Quote(ticker, 10.0, 9.0, 1.0, 11.1, 100, "USD", "t", "primary")

    def get_history(self, ticker, period="1y"):
        raise MarketDataError("no history")

    def get_fundamentals(self, ticker):
        raise MarketDataError("no fundamentals")


class FundamentalsProvider(MarketDataProvider):
    def get_quote(self, ticker):
        raise MarketDataError("no quote")

    def get_history(self, ticker, period="1y"):
        raise MarketDataError("no history")

    def get_fundamentals(self, ticker):
        return Fundamentals(ticker, 25.0, 5.0, 1e9, 0.2, 30.0, "t", "secondary")


def test_per_method_fallback():
    md = MarketData(providers=[QuoteOnlyProvider(), FundamentalsProvider()])
    q = md.get_quote("NVDA")
    assert isinstance(q, Quote) and q.source == "primary"
    f = md.get_fundamentals("NVDA")
    assert isinstance(f, Fundamentals) and f.source == "secondary"


def test_all_providers_fail_returns_unavailable():
    md = MarketData(providers=[QuoteOnlyProvider()])
    assert isinstance(md.get_history("NVDA"), Unavailable)
