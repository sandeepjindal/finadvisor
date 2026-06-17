import pandas as pd
from backtest.exit_rules import backtest_trailing_stop, max_drawdown


def test_rising_series_no_stop():
    res = backtest_trailing_stop([float(i) for i in range(1, 101)], stop_pct=12)
    assert res.exited_early is False
    assert abs(res.total_return - res.buy_hold_return) < 1e-9


def test_crash_triggers_stop_and_beats_buyhold():
    prices = [float(i) for i in range(1, 101)] + [50.0, 10.0, 5.0]  # rise then crash
    res = backtest_trailing_stop(prices, stop_pct=12)
    assert res.exited_early is True
    assert res.total_return > res.buy_hold_return


def test_max_drawdown():
    eq = pd.Series([100.0, 120.0, 60.0, 90.0])
    assert max_drawdown(eq) == (60.0 - 120.0) / 120.0
