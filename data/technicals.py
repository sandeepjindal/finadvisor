"""Technical indicators from price history, computed locally with the `ta` library
(NumPy-2-safe — unlike pandas-ta). RSI, MACD, 50/200-day SMA, trend. Step 1.3.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import MACD, SMAIndicator


@dataclass
class Technicals:
    rsi: float | None
    macd: float | None
    macd_signal: float | None
    sma50: float | None
    sma200: float | None
    trend: str  # "up" | "down" | "sideways"
    above_200ma: bool | None
    last_close: float | None


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


def compute_indicators(history_df: pd.DataFrame) -> Technicals:
    close = _close_col(history_df)
    rsi = _last(RSIIndicator(close, window=14).rsi()) if len(close) >= 15 else None
    macd_obj = MACD(close)
    macd = _last(macd_obj.macd()) if len(close) >= 26 else None
    macd_signal = _last(macd_obj.macd_signal()) if len(close) >= 35 else None
    sma50 = (
        _last(SMAIndicator(close, window=50).sma_indicator())
        if len(close) >= 50
        else None
    )
    sma200 = (
        _last(SMAIndicator(close, window=200).sma_indicator())
        if len(close) >= 200
        else None
    )
    last_close = _last(close)

    above_200ma = None
    if last_close is not None and sma200 is not None:
        above_200ma = last_close > sma200

    trend = "sideways"
    if last_close is not None and sma50 is not None and sma200 is not None:
        if last_close > sma50 > sma200:
            trend = "up"
        elif last_close < sma50 < sma200:
            trend = "down"

    return Technicals(
        rsi=rsi,
        macd=macd,
        macd_signal=macd_signal,
        sma50=sma50,
        sma200=sma200,
        trend=trend,
        above_200ma=above_200ma,
        last_close=last_close,
    )
