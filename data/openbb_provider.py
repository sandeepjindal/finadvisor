"""Optional OpenBB enrichment provider ([openbb] extra). yfinance stays primary; this is
added to the facade's provider list for richer fundamentals when installed. Step 4.0.
"""

from __future__ import annotations

from datetime import datetime, timezone

from data.market import Fundamentals, MarketDataError, MarketDataProvider, Quote
from security.guards import validate_ticker


def openbb_available() -> bool:
    try:
        import openbb  # noqa: F401

        return True
    except ImportError:
        return False


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class OpenBBProvider(MarketDataProvider):
    name = "openbb"

    def __init__(self):
        if not openbb_available():
            raise RuntimeError("OpenBB not installed; run: uv sync --extra openbb")
        from openbb import obb  # pragma: no cover - requires openbb

        self._obb = obb

    def get_quote(self, ticker: str) -> Quote:  # pragma: no cover - requires openbb
        t = validate_ticker(ticker)
        try:
            data = self._obb.equity.price.quote(t).results[0]
        except Exception as e:  # noqa: BLE001
            raise MarketDataError(f"openbb quote failed for {t}: {e}") from e
        price = getattr(data, "last_price", None) or getattr(data, "close", None)
        return Quote(t, float(price), None, None, None, None, "USD", _now(), self.name)

    def get_history(self, ticker: str, period: str = "1y"):  # pragma: no cover
        raise MarketDataError(
            "openbb history mapping not implemented; yfinance handles it"
        )

    def get_fundamentals(self, ticker: str) -> Fundamentals:  # pragma: no cover
        t = validate_ticker(ticker)
        try:
            m = self._obb.equity.fundamental.metrics(t).results[0]
        except Exception as e:  # noqa: BLE001
            raise MarketDataError(f"openbb fundamentals failed for {t}: {e}") from e
        return Fundamentals(
            t,
            getattr(m, "pe_ratio", None),
            getattr(m, "pb_ratio", None),
            getattr(m, "market_cap", None),
            getattr(m, "net_profit_margin", None),
            getattr(m, "debt_to_equity", None),
            _now(),
            self.name,
            {},
        )
