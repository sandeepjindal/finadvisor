import pandas as pd
from data.technicals import compute_indicators


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
