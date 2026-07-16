import numpy as np
import pandas as pd
from data.technicals import compute_indicators, compute_multiframe


def _frame(values):
    return pd.DataFrame({"Close": values})


def test_rising_series_is_uptrend():
    t = compute_indicators(_frame([float(i) for i in range(1, 261)]))
    assert t.trend == "up"
    assert t.above_200ma is True
    assert t.rsi is not None and t.rsi > 50


def test_falling_series_is_downtrend():
    t = compute_indicators(_frame([float(i) for i in range(260, 0, -1)]))
    assert t.trend == "down"
    assert t.above_200ma is False
    assert t.rsi is not None and t.rsi < 50


def test_short_series_has_no_sma200():
    t = compute_indicators(_frame([10.0, 11.0, 12.0]))
    assert t.sma200 is None
    assert t.trend == "sideways"


# --- Work-stream A: graded strength, crosses, ATR, volume, multi-timeframe --------


def test_rising_series_has_positive_strength():
    t = compute_indicators(_frame([float(i) for i in range(1, 261)]))
    assert t.trend_strength is not None and t.trend_strength > 0.5
    assert t.trend == "up"


def test_falling_series_has_negative_strength():
    t = compute_indicators(_frame([float(i) for i in range(260, 0, -1)]))
    assert t.trend_strength is not None and t.trend_strength < -0.5
    assert t.trend == "down"


def test_choppy_series_is_sideways_near_zero_strength():
    choppy = [100 + 3 * np.sin(i / 3.0) for i in range(260)]
    t = compute_indicators(_frame([float(v) for v in choppy]))
    assert t.trend == "sideways"
    assert t.trend_strength is not None and abs(t.trend_strength) < 0.15


def test_short_series_has_no_strength():
    t = compute_indicators(_frame([10.0, 11.0, 12.0]))
    assert t.trend_strength is None


def test_golden_cross_detected():
    down = np.linspace(300, 150, 215)
    up = np.linspace(151, 300, 260 - 215)
    vals = [float(v) for v in np.concatenate([down, up])]
    t = compute_indicators(_frame(vals))
    assert t.cross_signal == "golden"


def test_death_cross_detected():
    up = np.linspace(150, 300, 215)
    down = np.linspace(299, 150, 260 - 215)
    vals = [float(v) for v in np.concatenate([up, down])]
    t = compute_indicators(_frame(vals))
    assert t.cross_signal == "death"


def test_macd_bullish_cross():
    vals = [100 + 10 * np.sin(i * 2 * np.pi / 8) for i in range(202)]
    t = compute_indicators(_frame([float(v) for v in vals]))
    assert t.macd_cross == "bullish"


def test_macd_bearish_cross():
    vals = [100 + 10 * np.sin(i * 2 * np.pi / 8) for i in range(206)]
    t = compute_indicators(_frame([float(v) for v in vals]))
    assert t.macd_cross == "bearish"


def test_atr_and_volume_ratio_present_with_ohlcv():
    n = 60
    close = [100 + i * 0.5 for i in range(n)]
    df = pd.DataFrame(
        {
            "High": [c + 2 for c in close],
            "Low": [c - 2 for c in close],
            "Close": close,
            "Volume": [1000.0] * (n - 1) + [3000.0],
        }
    )
    t = compute_indicators(df)
    assert t.atr is not None and t.atr > 0
    assert t.volume_ratio is not None and t.volume_ratio > 2.0  # last spike vs 20d avg


def test_atr_and_volume_none_on_close_only():
    t = compute_indicators(_frame([float(i) for i in range(1, 61)]))
    assert t.atr is None
    assert t.volume_ratio is None


def test_compute_multiframe_returns_both_windows():
    long_vals = [float(i) for i in range(1, 261)]
    short_vals = long_vals[-63:]
    mf = compute_multiframe(_frame(short_vals), _frame(long_vals))
    assert mf.short.trend == "up" and mf.long.trend == "up"
    assert mf.long.sma200 is not None
    assert mf.short.sma200 is None  # short window too small for a 200-day SMA
