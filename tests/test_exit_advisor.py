import numpy as np
import pandas as pd
from agent.exit_advisor import (
    enrich_exit_verdict,
    evaluate_exit,
    ExitVerdict,
    format_exit_verdict,
)
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


class _FakeLLM:
    def __init__(self, resp):
        self.resp = resp

    def ask(self, messages):
        return self.resp


def test_enrich_sets_classification_and_rationale():
    base = ExitVerdict("NVDA", "TRIM", "transient", 10.0, ["RSI 74 overbought"])
    out = enrich_exit_verdict(
        base,
        "guidance cut; demand falling",
        _FakeLLM(
            "classification: structural\nrationale: guidance was cut, demand weakening"
        ),
    )
    assert out.classification == "structural"
    assert out.action == "TRIM"  # deterministic action is never flipped
    assert "guidance" in (out.llm_rationale or "").lower()


def test_enrich_none_llm_is_noop():
    base = ExitVerdict("NVDA", "HOLD", "transient", 5.0, [])
    out = enrich_exit_verdict(base, "ctx", None)
    assert out.llm_rationale is None and out.classification == "transient"


def test_enrich_llm_error_is_safe():
    class Boom:
        def ask(self, messages):
            raise RuntimeError("llm down")

    base = ExitVerdict("NVDA", "SELL", "structural", -5.0, [])
    out = enrich_exit_verdict(base, "ctx", Boom())
    assert out.action == "SELL"  # unchanged, no crash


# --- Work-stream A: multi-timeframe, crosses, ATR-sized stop ----------------------


def _transient_pullback():
    """Long-term uptrend with a recent, shallow pullback in the last ~3 months.
    Full-frame trend stays up; the tail(63) short window reads down => transient.
    """
    rise = np.linspace(100, 400, 230)
    pull = np.linspace(400, 370, 30)
    return pd.DataFrame({"Close": [float(v) for v in np.concatenate([rise, pull])]})


def _death_cross_frame():
    up = np.linspace(150, 300, 215)
    down = np.linspace(299, 150, 260 - 215)
    return pd.DataFrame({"Close": [float(v) for v in np.concatenate([up, down])]})


def _ohlcv_rising():
    n = 60
    close = [100.0 + i * 0.5 for i in range(n)]
    return pd.DataFrame(
        {
            "High": [c + 2 for c in close],
            "Low": [c - 2 for c in close],
            "Close": close,
            "Volume": [1000.0] * n,
        }
    )


def test_transient_pullback_within_uptrend(tmp_path):
    conn, h = _holding(tmp_path)
    market = FakeMarket(price=370.0, hist=_transient_pullback(), pe=20)
    v = evaluate_exit(h, market, conn, load_rules())
    assert v.classification == "transient"
    assert any("pullback" in r.lower() for r in v.reasons)


def test_structural_when_both_timeframes_down(tmp_path):
    conn, h = _holding(tmp_path)
    market = FakeMarket(price=50.0, hist=_falling(), pe=20)
    v = evaluate_exit(h, market, conn, load_rules())
    assert v.classification == "structural"
    assert any("both short- and long-term" in r.lower() for r in v.reasons)


def test_death_cross_flags_structural(tmp_path):
    conn, h = _holding(tmp_path)
    market = FakeMarket(price=150.0, hist=_death_cross_frame(), pe=20)
    v = evaluate_exit(h, market, conn, load_rules())
    assert v.classification == "structural"
    assert any("death cross" in r.lower() for r in v.reasons)


def test_atr_sized_stop_when_volatility_available(tmp_path):
    conn, h = _holding(tmp_path)
    market = FakeMarket(price=130.0, hist=_ohlcv_rising(), pe=20)
    v = evaluate_exit(h, market, conn, load_rules())
    assert v.suggested_rule is not None and "ATR" in v.suggested_rule
    assert any(c.metric == "atr" for c in v.citations)


def test_flat_stop_fallback_without_ohlc(tmp_path):
    conn, h = _holding(tmp_path)
    market = FakeMarket(price=260.0, hist=_rising(), pe=20)
    v = evaluate_exit(h, market, conn, load_rules())
    # Close-only frame => no ATR => flat trailing-stop percentage fallback.
    assert v.suggested_rule is not None and "%" in v.suggested_rule
    assert not any(c.metric == "atr" for c in v.citations)
