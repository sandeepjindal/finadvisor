"""Intraday price bars + microstructure metrics for day-trading guidance. Work-stream F1.

yfinance is the default source for intraday bars (1m/5m/15m), but it is LAZY-imported only
in the default fetch path so the compute layer and its tests stay fully OFFLINE. The
``fetch`` callable is injectable for tests (synthetic pandas DataFrames — no network).

Design: docs/plans/2026-07-15-market-intelligence-enrichment-design.md §11 (F1). Posture is
educational + conservative: metrics feed a risk-managed setup engine, never a bare tip.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import pandas as pd
from ta.momentum import RSIIndicator

from data.market import Unavailable
from security.guards import validate_ticker


def _last(series: pd.Series | None) -> float | None:
    if series is None or len(series) == 0:
        return None
    val = series.iloc[-1]
    return None if pd.isna(val) else float(val)


def _col(df: pd.DataFrame, *names: str) -> pd.Series | None:
    for name in names:
        if name in df.columns:
            return df[name].astype(float)
    return None


def _default_fetch(ticker: str, interval: str, period: str) -> pd.DataFrame:
    """Lazy-import yfinance so tests never need the network or the dependency at import."""
    import yfinance as yf  # noqa: PLC0415 - intentional lazy import

    return yf.Ticker(ticker).history(period=period, interval=interval)


def get_intraday(
    ticker: str,
    interval: str = "5m",
    period: str = "5d",
    *,
    fetch: Callable[[str, str, str], pd.DataFrame] | None = None,
) -> pd.DataFrame | Unavailable:
    """Fetch intraday bars for ``ticker``. Validates the ticker first, then delegates to
    ``fetch(ticker, interval, period)`` (default lazily uses yfinance). Returns an
    ``Unavailable`` marker (never a fabricated frame) on any error or an empty result.
    """
    try:
        t = validate_ticker(ticker)
    except ValueError as e:
        return Unavailable(field="intraday", ticker=str(ticker), reason=str(e))

    fn = fetch or _default_fetch
    try:
        df = fn(t, interval, period)
    except Exception as e:  # noqa: BLE001 - any provider failure degrades to Unavailable
        return Unavailable(field="intraday", ticker=t, reason=str(e))
    if df is None or len(df) == 0:
        return Unavailable(field="intraday", ticker=t, reason="no intraday bars")
    return df


@dataclass
class IntradayMetrics:
    """Microstructure snapshot from intraday bars. Every field degrades to None when its
    inputs are missing (e.g. a Close-only frame has no VWAP, opening range, or rel-volume).
    """

    vwap: float | None
    opening_range_high: float | None
    opening_range_low: float | None
    rel_volume: float | None  # last-bar volume / average bar volume
    intraday_rsi: float | None  # RSI(14) on intraday closes
    gap_pct: float | None  # today's open vs prior close, in percent
    last: float | None  # last close


def _gap_pct(
    df: pd.DataFrame,
    open_series: pd.Series | None,
    close: pd.Series,
    prior_close: float | None,
) -> float | None:
    """Percent gap of today's first bar open vs the prior close. Uses ``prior_close`` when
    supplied; otherwise tries to derive it from a multi-session DatetimeIndex frame."""
    if open_series is None or len(open_series) == 0:
        return None

    ref = prior_close
    today_open: float | None = None
    if isinstance(df.index, pd.DatetimeIndex):
        dates = df.index.normalize()
        unique = pd.unique(dates)
        if len(unique) >= 1:
            last_day = unique[-1]
            today_mask = dates == last_day
            first_idx = today_mask.argmax()
            today_open = float(open_series.iloc[first_idx])
            if ref is None and len(unique) >= 2:
                prior_day = unique[-2]
                prior_bars = close[dates == prior_day]
                ref = _last(prior_bars)
    if today_open is None:
        today_open = float(open_series.iloc[0])

    if ref is None or ref == 0:
        return None
    return (today_open - ref) / ref * 100.0


def compute_intraday(
    df: pd.DataFrame,
    prior_close: float | None = None,
    *,
    opening_range_bars: int = 6,
) -> IntradayMetrics:
    """Compute intraday metrics from a bar frame. ``opening_range_bars`` is the number of
    leading bars that define the opening range (default 6 ≈ first 30 min on 5-minute bars).
    Handles Close-only frames gracefully: fields whose inputs are absent come back None.
    """
    close = _col(df, "Close", "close", "Adj Close")
    if close is None:
        # No usable price column at all — everything is unknown.
        return IntradayMetrics(None, None, None, None, None, None, None)

    high = _col(df, "High", "high")
    low = _col(df, "Low", "low")
    volume = _col(df, "Volume", "volume")
    open_series = _col(df, "Open", "open")

    # VWAP needs typical price (High/Low/Close) and Volume.
    vwap: float | None = None
    if high is not None and low is not None and volume is not None and len(close) > 0:
        typical = (high + low + close) / 3.0
        cum_vol = volume.cumsum()
        cum_pv = (typical * volume).cumsum()
        last_vol = _last(cum_vol)
        if last_vol not in (None, 0):
            vwap = float(cum_pv.iloc[-1] / cum_vol.iloc[-1])

    # Opening range = high/low over the first N bars.
    opening_range_high: float | None = None
    opening_range_low: float | None = None
    if high is not None and low is not None and len(high) > 0:
        n = min(opening_range_bars, len(high))
        opening_range_high = float(high.iloc[:n].max())
        opening_range_low = float(low.iloc[:n].min())

    # Relative volume = last bar volume / average bar volume.
    rel_volume: float | None = None
    if volume is not None and len(volume) > 0:
        avg = float(volume.mean())
        last_vol = _last(volume)
        if avg and last_vol is not None:
            rel_volume = last_vol / avg

    # Intraday RSI(14) on closes.
    intraday_rsi = (
        _last(RSIIndicator(close, window=14).rsi()) if len(close) >= 15 else None
    )

    gap_pct = _gap_pct(df, open_series, close, prior_close)
    last = _last(close)

    return IntradayMetrics(
        vwap=vwap,
        opening_range_high=opening_range_high,
        opening_range_low=opening_range_low,
        rel_volume=rel_volume,
        intraday_rsi=intraday_rsi,
        gap_pct=gap_pct,
        last=last,
    )
