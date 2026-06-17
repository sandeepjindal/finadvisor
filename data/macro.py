"""Macro indicators (FRED) + commodity prices (yfinance futures). Clients are injectable
so tests run offline and `fredapi` need not be installed. Step 4.2.
"""

from __future__ import annotations

import os

_DEFAULT_SERIES = {
    "fed_funds": "FEDFUNDS",
    "cpi": "CPIAUCSL",
    "unemployment": "UNRATE",
    "gdp": "GDP",
}


def get_macro(
    series: dict[str, str] | None = None, api_key: str | None = None, client=None
) -> dict:
    if client is None:
        from fredapi import Fred  # [macro] extra

        client = Fred(api_key=api_key or os.environ.get("FRED_API_KEY"))
    series = series or _DEFAULT_SERIES
    out: dict[str, float | None] = {}
    for name, code in series.items():
        try:
            s = client.get_series(code)
            out[name] = float(s.iloc[-1])
        except Exception:  # noqa: BLE001
            out[name] = None
    return out


def get_commodity(ticker: str, fetch=None) -> float | None:
    """Latest price for a commodity future (e.g. CL=F crude, GC=F gold)."""
    if fetch is None:
        import yfinance as yf

        def fetch(t):  # pragma: no cover - live path
            info = yf.Ticker(t).info
            return info.get("regularMarketPrice") or info.get("currentPrice")

    try:
        return fetch(ticker)
    except Exception:  # noqa: BLE001
        return None
