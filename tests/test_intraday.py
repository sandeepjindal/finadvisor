import pandas as pd
from data.intraday import IntradayMetrics, compute_intraday, get_intraday
from data.market import Unavailable


def _ohlcv():
    # 3 bars, hand-computable VWAP.
    return pd.DataFrame(
        {
            "Open": [9.0, 10.0, 12.0],
            "High": [10.0, 12.0, 14.0],
            "Low": [8.0, 10.0, 12.0],
            "Close": [9.0, 11.0, 13.0],
            "Volume": [100.0, 200.0, 300.0],
        }
    )


def test_vwap_math():
    m = compute_intraday(_ohlcv())
    # typical = (H+L+C)/3 = [9, 11, 13]; sum(tp*vol)=900+2200+3900=7000; sum(vol)=600.
    assert m.vwap is not None
    assert abs(m.vwap - 7000.0 / 600.0) < 1e-9


def test_opening_range_uses_first_n_bars():
    m = compute_intraday(_ohlcv(), opening_range_bars=2)
    assert m.opening_range_high == 12.0  # max(High[:2]) = max(10,12)
    assert m.opening_range_low == 8.0  # min(Low[:2]) = min(8,10)


def test_rel_volume_last_over_average():
    m = compute_intraday(_ohlcv())
    # last vol 300 / mean(100,200,300)=200 => 1.5
    assert m.rel_volume is not None
    assert abs(m.rel_volume - 1.5) < 1e-9


def test_gap_pct_from_prior_close():
    m = compute_intraday(_ohlcv(), prior_close=8.0)
    # today's first open = 9 vs prior close 8 => +12.5%
    assert m.gap_pct is not None
    assert abs(m.gap_pct - 12.5) < 1e-9


def test_gap_none_without_prior_close_or_dates():
    # No prior_close and no DatetimeIndex to derive one => gap unknown.
    m = compute_intraday(_ohlcv())
    assert m.gap_pct is None


def test_close_only_frame_degrades_gracefully():
    df = pd.DataFrame({"Close": [float(i) for i in range(1, 21)]})
    m = compute_intraday(df, prior_close=10.0)
    assert m.vwap is None
    assert m.opening_range_high is None and m.opening_range_low is None
    assert m.rel_volume is None
    assert m.gap_pct is None  # no Open column
    assert m.last == 20.0
    assert m.intraday_rsi is not None  # RSI only needs Close


def test_no_price_column_all_none():
    m = compute_intraday(pd.DataFrame({"foo": [1, 2, 3]}))
    assert m == IntradayMetrics(None, None, None, None, None, None, None)


def test_get_intraday_injected_fetch_offline():
    calls = {}

    def fake_fetch(ticker, interval, period):
        calls["args"] = (ticker, interval, period)
        return _ohlcv()

    df = get_intraday("aapl", interval="5m", period="5d", fetch=fake_fetch)
    assert isinstance(df, pd.DataFrame)
    assert calls["args"] == ("AAPL", "5m", "5d")  # ticker validated + upper-cased


def test_get_intraday_empty_is_unavailable():
    out = get_intraday("AAPL", fetch=lambda t, i, p: pd.DataFrame())
    assert isinstance(out, Unavailable)


def test_get_intraday_invalid_ticker_is_unavailable():
    out = get_intraday("not a ticker", fetch=lambda t, i, p: _ohlcv())
    assert isinstance(out, Unavailable)


def test_get_intraday_fetch_error_is_unavailable():
    def boom(t, i, p):
        raise RuntimeError("network down")

    out = get_intraday("AAPL", fetch=boom)
    assert isinstance(out, Unavailable)
