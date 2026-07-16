"""Technical indicators from price history, computed locally with the `ta` library
(NumPy-2-safe — unlike pandas-ta). RSI, MACD, 50/200-day SMA, trend. Step 1.3.

Work-stream A (Enriched Trend Analysis) extends this with a graded ``trend_strength``,
MACD/golden-death crossovers, ATR volatility, and a volume ratio, plus a multi-timeframe
helper — while keeping every original field and the ``compute_indicators`` signature
intact for backward compatibility. Design: docs/plans/2026-07-15-market-intelligence-enrichment-design.md §1.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import MACD, SMAIndicator
from ta.volatility import AverageTrueRange


@dataclass
class Technicals:
    rsi: float | None
    macd: float | None
    macd_signal: float | None
    sma50: float | None
    sma200: float | None
    trend: str  # "up" | "down" | "sideways" (coarse label derived from trend_strength)
    above_200ma: bool | None
    last_close: float | None
    # Work-stream A enrichments (all degrade to None/"none" on insufficient data):
    trend_strength: float | None = None  # continuous ~ -1..+1
    macd_cross: str = "none"  # "bullish" | "bearish" | "none"
    cross_signal: str = "none"  # "golden" | "death" | "none"
    atr: float | None = None  # 14-period Average True Range
    volume_ratio: float | None = None  # last volume / 20-day avg volume


def _last(series) -> float | None:
    if series is None or len(series) == 0:
        return None
    val = series.iloc[-1]
    return None if pd.isna(val) else float(val)


def _close_col(df: pd.DataFrame) -> pd.Series:
    for name in ("Close", "close", "Adj Close"):
        if name in df.columns:
            return df[name].astype(float)
    raise ValueError("history frame has no Close column")


def _optional_col(df: pd.DataFrame, *names: str) -> pd.Series | None:
    for name in names:
        if name in df.columns:
            return df[name].astype(float)
    return None


def _trend_strength(
    close: pd.Series,
    sma50_series: pd.Series | None,
    sma200_series: pd.Series | None,
) -> float | None:
    """Blend SMA50 slope, price-vs-SMA50 distance, and SMA50-vs-SMA200 gap into a
    continuous score squashed to ~ -1..+1 via tanh. Returns None without an SMA50.
    """
    sma50 = _last(sma50_series) if sma50_series is not None else None
    last_close = _last(close)
    if sma50 is None or sma50 == 0 or last_close is None:
        return None

    # Price vs SMA50 distance (fractional).
    dist = (last_close - sma50) / sma50

    # SMA50 slope over ~10 bars (fractional change), if we have the history.
    slope = 0.0
    if sma50_series is not None and len(sma50_series) >= 11:
        prev = sma50_series.iloc[-11]
        if pd.notna(prev) and prev != 0:
            slope = (sma50 - float(prev)) / float(prev)

    # SMA50 vs SMA200 gap (fractional), if SMA200 is available.
    gap = 0.0
    sma200 = _last(sma200_series) if sma200_series is not None else None
    if sma200 is not None and sma200 != 0:
        gap = (sma50 - sma200) / sma200

    raw = 10.0 * slope + 5.0 * dist + 3.0 * gap
    return math.tanh(raw)


def _macd_cross(macd_line: pd.Series | None, signal_line: pd.Series | None) -> str:
    """Crossover of the MACD line vs its signal line over the last 2 bars."""
    if macd_line is None or signal_line is None:
        return "none"
    if len(macd_line) < 2 or len(signal_line) < 2:
        return "none"
    m_prev, m_now = macd_line.iloc[-2], macd_line.iloc[-1]
    s_prev, s_now = signal_line.iloc[-2], signal_line.iloc[-1]
    if any(pd.isna(v) for v in (m_prev, m_now, s_prev, s_now)):
        return "none"
    if m_prev <= s_prev and m_now > s_now:
        return "bullish"
    if m_prev >= s_prev and m_now < s_now:
        return "bearish"
    return "none"


def _cross_signal(
    sma50_series: pd.Series | None,
    sma200_series: pd.Series | None,
    window: int = 5,
) -> str:
    """Golden/death cross: SMA50 crossing SMA200 within the recent ``window`` bars."""
    if sma50_series is None or sma200_series is None:
        return "none"
    diff = (sma50_series - sma200_series).dropna()
    if len(diff) < 2:
        return "none"
    recent = diff.iloc[-(window + 1) :]
    if len(recent) < 2:
        return "none"
    start, end = recent.iloc[0], recent.iloc[-1]
    if start <= 0 and end > 0:
        return "golden"
    if start >= 0 and end < 0:
        return "death"
    return "none"


def compute_indicators(history_df: pd.DataFrame) -> Technicals:
    close = _close_col(history_df)
    rsi = _last(RSIIndicator(close, window=14).rsi()) if len(close) >= 15 else None
    macd_obj = MACD(close)
    macd_line = macd_obj.macd() if len(close) >= 26 else None
    signal_line = macd_obj.macd_signal() if len(close) >= 35 else None
    macd = _last(macd_line) if macd_line is not None else None
    macd_signal = _last(signal_line) if signal_line is not None else None

    sma50_series = (
        SMAIndicator(close, window=50).sma_indicator() if len(close) >= 50 else None
    )
    sma200_series = (
        SMAIndicator(close, window=200).sma_indicator() if len(close) >= 200 else None
    )
    sma50 = _last(sma50_series) if sma50_series is not None else None
    sma200 = _last(sma200_series) if sma200_series is not None else None
    last_close = _last(close)

    above_200ma = None
    if last_close is not None and sma200 is not None:
        above_200ma = last_close > sma200

    # Graded strength, then derive the coarse label from thresholds.
    trend_strength = _trend_strength(close, sma50_series, sma200_series)
    if trend_strength is None:
        trend = "sideways"
    elif trend_strength >= 0.15:
        trend = "up"
    elif trend_strength <= -0.15:
        trend = "down"
    else:
        trend = "sideways"

    macd_cross = _macd_cross(macd_line, signal_line)
    cross_signal = _cross_signal(sma50_series, sma200_series)

    # ATR needs High/Low/Close; degrade to None on Close-only frames.
    atr = None
    high = _optional_col(history_df, "High", "high")
    low = _optional_col(history_df, "Low", "low")
    if high is not None and low is not None and len(close) >= 15:
        atr = _last(
            AverageTrueRange(high=high, low=low, close=close, window=14).average_true_range()
        )

    # Volume ratio: last volume vs 20-day average (None without a Volume column).
    volume_ratio = None
    volume = _optional_col(history_df, "Volume", "volume")
    if volume is not None and len(volume) >= 20:
        avg20 = float(volume.iloc[-20:].mean())
        last_vol = _last(volume)
        if avg20 and last_vol is not None:
            volume_ratio = last_vol / avg20

    return Technicals(
        rsi=rsi,
        macd=macd,
        macd_signal=macd_signal,
        sma50=sma50,
        sma200=sma200,
        trend=trend,
        above_200ma=above_200ma,
        last_close=last_close,
        trend_strength=trend_strength,
        macd_cross=macd_cross,
        cross_signal=cross_signal,
        atr=atr,
        volume_ratio=volume_ratio,
    )


@dataclass
class MultiframeTechnicals:
    """Short (~3m) vs long (~1y) reads, so callers can compare timeframes to tell a
    transient pullback (short down inside long up) from a structural break (both down).
    Work-stream A §1.2.
    """

    short: Technicals
    long: Technicals


def compute_multiframe(
    short_df: pd.DataFrame, long_df: pd.DataFrame
) -> MultiframeTechnicals:
    """Compute indicators on a short (~3-month) and long (~1-year) window and return both.
    ``compute_indicators`` keeps its single-frame signature; this is a thin wrapper.
    """
    return MultiframeTechnicals(
        short=compute_indicators(short_df),
        long=compute_indicators(long_df),
    )
