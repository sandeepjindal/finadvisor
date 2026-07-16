"""Market data behind one interface. yfinance is the Phase-1 PRIMARY provider; the facade
takes an ordered provider list and does per-method fallback, returning a typed
``Unavailable`` marker (never a fabricated value) when data can't be fetched.
Steps 1.1, 1.2 (+ cache wiring in 1.2b).
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone

import yfinance as yf
from brain import cache as _cache
from logging_setup import get_logger
from security.guards import validate_ticker

log = get_logger(__name__)


class MarketDataError(Exception):
    """A provider failed to fetch a requested datum."""


@dataclass
class Quote:
    ticker: str
    price: float
    previous_close: float | None
    change: float | None
    change_pct: float | None
    volume: float | None
    currency: str
    as_of: str
    source: str


@dataclass
class Fundamentals:
    ticker: str
    pe: float | None
    pb: float | None
    market_cap: float | None
    profit_margin: float | None
    debt_to_equity: float | None
    as_of: str
    source: str
    raw: dict = field(default_factory=dict)


@dataclass
class Unavailable:
    """Returned when no provider could supply a datum — engine must disclose, not fake."""

    field: str
    ticker: str
    reason: str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class MarketDataProvider(ABC):
    @abstractmethod
    def get_quote(self, ticker: str) -> Quote: ...

    @abstractmethod
    def get_history(self, ticker: str, period: str = "1y"): ...

    @abstractmethod
    def get_fundamentals(self, ticker: str) -> Fundamentals: ...


class YFinanceProvider(MarketDataProvider):
    name = "yfinance"

    def _quote_from_info(self, symbol: str, info: dict) -> Quote:
        price = info.get("currentPrice") or info.get("regularMarketPrice")
        if price is None:
            raise MarketDataError(f"no price for {symbol}")
        prev = info.get("previousClose")
        change = (price - prev) if prev else None
        change_pct = (change / prev * 100) if (prev and change is not None) else None
        return Quote(
            ticker=symbol,
            price=float(price),
            previous_close=float(prev) if prev else None,
            change=change,
            change_pct=change_pct,
            volume=info.get("volume") or info.get("regularMarketVolume"),
            currency=info.get("currency", "USD"),
            as_of=_now(),
            source=self.name,
        )

    def get_quote(self, ticker: str) -> Quote:
        t = validate_ticker(ticker)
        try:
            info = yf.Ticker(t).info
        except Exception as e:  # noqa: BLE001
            raise MarketDataError(f"yfinance quote failed for {t}: {e}") from e
        return self._quote_from_info(t, info)

    def get_sector(self, ticker: str) -> str | None:
        """GICS-style sector via yfinance ``.info['sector']``; None on any failure."""
        try:
            t = validate_ticker(ticker)
            return yf.Ticker(t).info.get("sector")
        except Exception:  # noqa: BLE001
            return None

    def get_futures(self, symbol: str) -> Quote:
        """Quote for a commodity/index future (e.g. CL=F crude, GC=F gold). These symbols
        contain '=' and so bypass the equity ticker validator; reuses quote logic."""
        sym = (symbol or "").strip().upper()
        if not sym:
            raise MarketDataError("empty futures symbol")
        try:
            info = yf.Ticker(sym).info
        except Exception as e:  # noqa: BLE001
            raise MarketDataError(f"yfinance futures failed for {sym}: {e}") from e
        return self._quote_from_info(sym, info)

    def get_history(self, ticker: str, period: str = "1y"):
        t = validate_ticker(ticker)
        try:
            df = yf.Ticker(t).history(period=period)
        except Exception as e:  # noqa: BLE001
            raise MarketDataError(f"yfinance history failed for {t}: {e}") from e
        if df is None or len(df) == 0:
            raise MarketDataError(f"no history for {t}")
        return df

    def get_fundamentals(self, ticker: str) -> Fundamentals:
        t = validate_ticker(ticker)
        try:
            info = yf.Ticker(t).info
        except Exception as e:  # noqa: BLE001
            raise MarketDataError(f"yfinance fundamentals failed for {t}: {e}") from e
        return Fundamentals(
            ticker=t,
            pe=info.get("trailingPE"),
            pb=info.get("priceToBook"),
            market_cap=info.get("marketCap"),
            profit_margin=info.get("profitMargins"),
            debt_to_equity=info.get("debtToEquity"),
            as_of=_now(),
            source=self.name,
            raw=info,
        )


class MarketData:
    """Facade over an ordered list of providers with per-method fallback."""

    def __init__(
        self,
        providers: list[MarketDataProvider] | None = None,
        cache_conn=None,
        fundamentals_ttl: float = 86400.0,
    ):
        self.providers = providers or [YFinanceProvider()]
        self.cache_conn = cache_conn
        self.fundamentals_ttl = fundamentals_ttl

    def _try(self, method: str, field_name: str, ticker: str, *args):
        last: Exception | None = None
        for p in self.providers:
            try:
                result = getattr(p, method)(ticker, *args)
                if last is not None:
                    log.info("%s served by fallback %s", field_name, type(p).__name__)
                return result
            except Exception as e:  # noqa: BLE001
                last = e
                log.warning("%s via %s failed: %s", field_name, type(p).__name__, e)
        return Unavailable(field=field_name, ticker=ticker, reason=str(last))

    def get_quote(self, ticker: str):
        return self._try("get_quote", "quote", ticker)

    def get_fundamentals(self, ticker: str):
        t = ticker.strip().upper()
        if self.cache_conn is not None:
            row = _cache.get_fundamentals(self.cache_conn, t, self.fundamentals_ttl)
            if row is not None:
                return Fundamentals(
                    ticker=t,
                    pe=row["pe"],
                    pb=row["pb"],
                    market_cap=None,
                    profit_margin=row["margins"],
                    debt_to_equity=row["debt"],
                    as_of=row["as_of"],
                    source="cache",
                    raw=json.loads(row["raw_json"] or "{}"),
                )
        result = self._try("get_fundamentals", "fundamentals", ticker)
        if self.cache_conn is not None and isinstance(result, Fundamentals):
            _cache.put_fundamentals(
                self.cache_conn,
                result.ticker,
                result.as_of,
                result.pe,
                result.pb,
                result.debt_to_equity,
                result.profit_margin,
                json.dumps(result.raw or {}),
            )
        return result

    def get_history(self, ticker: str, period: str = "1y"):
        return self._try("get_history", "history", ticker, period)

    def get_sector(self, ticker: str) -> str | None:
        """First provider that can resolve a sector wins; None if none can."""
        for p in self.providers:
            fn = getattr(p, "get_sector", None)
            if fn is None:
                continue
            try:
                sector = fn(ticker)
            except Exception:  # noqa: BLE001
                continue
            if sector:
                return sector
        return None

    def get_futures(self, symbol: str):
        return self._try("get_futures", "futures", symbol)
