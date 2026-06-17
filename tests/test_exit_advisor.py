import pandas as pd

from agent.exit_advisor import evaluate_exit, format_exit_verdict
from agent.knowledge import load_rules
from brain.db import init_db
from brain.holdings import Holding
from data.market import Fundamentals, Quote, Unavailable


class FakeMarket:
    def __init__(self, price, hist, pe):
        self._price = price
        self._hist = hist
        self._pe = pe

    def get_quote(self, t):
        return Quote(
            t.upper(), self._price, None, None, None, None, "USD", "t", "yfinance"
        )

    def get_history(self, t, period="1y"):
        return self._hist

    def get_fundamentals(self, t):
        if self._pe is None:
            return Unavailable("fundamentals", t.upper(), "n/a")
        return Fundamentals(
            t.upper(), self._pe, None, None, None, None, "t", "yfinance"
        )


def _rising():
    return pd.DataFrame({"Close": [float(i) for i in range(1, 261)]})


def _falling():
    return pd.DataFrame({"Close": [float(i) for i in range(260, 0, -1)]})


def _holding(tmp_path):
    conn = init_db(str(tmp_path / "brain.db"))
    return conn, Holding(1, "NVDA", 30, 100.0, "t", "")


def test_uptrend_not_a_structural_exit(tmp_path):
    conn, h = _holding(tmp_path)
    # Strictly rising series => above 200MA but RSI ~100 (overbought) => TRIM, not a
    # structural SELL. The point: an intact uptrend is never classified structural.
    market = FakeMarket(price=260.0, hist=_rising(), pe=20)
    v = evaluate_exit(h, market, conn, load_rules())
    assert v.action in ("HOLD", "TRIM")
    assert v.classification == "transient"
    assert v.gain_pct and v.gain_pct > 0


def test_downtrend_overbought_stretched_exits(tmp_path):
    conn, h = _holding(tmp_path)
    market = FakeMarket(price=50.0, hist=_falling(), pe=90)
    v = evaluate_exit(h, market, conn, load_rules())
    assert v.action in ("TRIM", "SELL")
    assert v.classification == "structural"
    assert v.redeploy
    assert "Not financial advice" in format_exit_verdict(v)


def test_unavailable_quote_holds(tmp_path):
    conn, h = _holding(tmp_path)

    class Dead:
        def get_quote(self, t):
            return Unavailable("quote", t, "down")

        def get_history(self, t, period="1y"):
            return Unavailable("history", t, "down")

        def get_fundamentals(self, t):
            return Unavailable("fundamentals", t, "down")

    v = evaluate_exit(h, Dead(), conn, load_rules())
    assert v.action == "HOLD"
