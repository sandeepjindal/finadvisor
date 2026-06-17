import brain.cache as cache
from brain.db import init_db
from data.market import (
    Fundamentals,
    MarketData,
    MarketDataError,
    MarketDataProvider,
    Quote,
)


def _db(tmp_path):
    return init_db(str(tmp_path / "brain.db"))


def test_put_then_get_within_ttl(tmp_path):
    conn = _db(tmp_path)
    cache.put_fundamentals(
        conn, "NVDA", "2099-01-01T00:00:00+00:00", 30, 12, 40, 0.25, "{}"
    )
    row = cache.get_fundamentals(conn, "NVDA", max_age_seconds=10**9)
    assert row is not None and row["pe"] == 30


def test_stale_returns_none(tmp_path):
    conn = _db(tmp_path)
    cache.put_fundamentals(
        conn, "NVDA", "2000-01-01T00:00:00+00:00", 30, 12, 40, 0.25, "{}"
    )
    assert cache.get_fundamentals(conn, "NVDA", max_age_seconds=60) is None


def test_upsert_quote_roundtrip(tmp_path):
    conn = _db(tmp_path)
    cache.upsert_quote(conn, "NVDA", "2026-06-16", 1, 2, 0.5, 1.5, 1000)
    row = cache.get_quote_row(conn, "NVDA", "2026-06-16")
    assert row["close"] == 1.5


class CountingProvider(MarketDataProvider):
    def __init__(self):
        self.calls = 0

    def get_quote(self, ticker):
        raise MarketDataError("n/a")

    def get_history(self, ticker, period="1y"):
        raise MarketDataError("n/a")

    def get_fundamentals(self, ticker):
        self.calls += 1
        return Fundamentals(
            "NVDA", 30, 12, 1e9, 0.25, 40, "2099-01-01T00:00:00+00:00", "live"
        )


def test_facade_caches_fundamentals(tmp_path):
    conn = _db(tmp_path)
    prov = CountingProvider()
    md = MarketData(providers=[prov], cache_conn=conn)
    first = md.get_fundamentals("NVDA")
    second = md.get_fundamentals("NVDA")
    assert prov.calls == 1  # second served from cache
    assert first.source == "live"
    assert second.source == "cache"
