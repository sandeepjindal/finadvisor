import pandas as pd
from agent.daytrade import (
    DayTradeSetup,
    enrich_daytrade,
    format_daytrade,
    suggest_daytrade,
)
from data.market import Quote, Unavailable


class FakeMarket:
    """Daily-data facade stand-in. History is Unavailable so tests exercise the intraday
    path independently of daily technicals unless a setup needs them."""

    def __init__(self, prev_close=None):
        self._prev = prev_close

    def get_quote(self, t):
        return Quote(t.upper(), 105.0, self._prev, None, None, None, "USD", "t", "yf")

    def get_history(self, t, period="1y"):
        return Unavailable("history", t.upper(), "n/a")


def _breakout_df():
    # First 6 bars form the opening range (high 101, low 99); last bar breaks out on volume.
    close = [100.0, 100.5, 99.5, 100.0, 101.0, 100.5, 103.0, 105.0]
    high = [100.5, 101.0, 100.0, 100.5, 101.0, 101.0, 103.5, 105.5]
    low = [99.5, 100.0, 99.0, 99.5, 100.0, 100.0, 102.5, 104.0]
    volume = [1000.0] * 7 + [5000.0]
    return pd.DataFrame({"High": high, "Low": low, "Close": close, "Volume": volume})


def _chop_df():
    # Price chops inside a tight opening range on flat volume => no clean setup.
    close = [100.0, 100.1, 99.9, 100.0, 100.05, 99.95, 100.02, 100.01]
    high = [c + 0.2 for c in close]
    low = [c - 0.2 for c in close]
    volume = [1000.0] * 8
    return pd.DataFrame({"High": high, "Low": low, "Close": close, "Volume": volume})


def test_breakout_produces_full_plan_with_min_rr():
    s = suggest_daytrade("AAPL", FakeMarket(), intraday_df=_breakout_df(), min_rr=1.5)
    assert s.setup == "breakout"
    assert s.bias == "long"
    assert s.entry is not None and s.stop is not None and s.target is not None
    assert s.risk_reward is not None and s.risk_reward >= 1.5
    # entry 101, stop 99, target 101 + 2*(101-99) = 105 => rr = 4/2 = 2.0
    assert s.entry == 101.0 and s.stop == 99.0 and s.target == 105.0
    assert s.risk_reward == 2.0
    assert s.position_size_hint is not None
    assert any(c.metric == "entry" for c in s.citations)


def test_risk_reward_math_is_consistent():
    s = suggest_daytrade("AAPL", FakeMarket(), intraday_df=_breakout_df())
    risk = abs(s.entry - s.stop)
    reward = abs(s.target - s.entry)
    assert abs(s.risk_reward - reward / risk) < 1e-9


def test_no_setup_stands_aside():
    s = suggest_daytrade("AAPL", FakeMarket(), intraday_df=_chop_df())
    assert s.setup == "none"
    assert s.bias == "none"
    assert s.entry is None and s.stop is None and s.target is None
    assert any("stand aside" in r.lower() for r in s.reasons)


def test_min_rr_gate_forces_stand_aside():
    # A high min_rr the 2.0 breakout can't clear => stand aside despite a real pattern.
    s = suggest_daytrade("AAPL", FakeMarket(), intraday_df=_breakout_df(), min_rr=5.0)
    assert s.setup == "none"
    assert any("risk:reward" in r.lower() for r in s.reasons)


def test_unavailable_intraday_stands_aside():
    s = suggest_daytrade(
        "AAPL", FakeMarket(), intraday_df=Unavailable("intraday", "AAPL", "down")
    )
    assert s.setup == "none"


def test_position_size_hint_uses_account_size():
    s = suggest_daytrade(
        "AAPL", FakeMarket(), intraday_df=_breakout_df(), account_size=100_000.0
    )
    # 1% of 100k = $1000 risk; $2 risk/share => ~500 shares.
    assert s.position_size_hint is not None
    assert "500" in s.position_size_hint


def test_format_has_disclaimer_and_risk_line():
    s = suggest_daytrade("AAPL", FakeMarket(), intraday_df=_breakout_df())
    out = format_daytrade(s)
    assert "Not financial advice." in out
    assert "high-risk" in out
    assert "Risk line" in out
    assert str(s.entry) in out


def test_format_stand_aside_has_disclaimer():
    s = suggest_daytrade("AAPL", FakeMarket(), intraday_df=_chop_df())
    out = format_daytrade(s)
    assert "STAND ASIDE" in out
    assert "Not financial advice." in out


def test_enrich_none_llm_is_noop():
    s = suggest_daytrade("AAPL", FakeMarket(), intraday_df=_breakout_df())
    before = (s.setup, s.entry, s.stop, s.target, s.risk_reward)
    out = enrich_daytrade(s, "some untrusted context", None)
    assert out.llm_rationale is None
    assert (out.setup, out.entry, out.stop, out.target, out.risk_reward) == before


class _FakeLLM:
    def __init__(self, resp):
        self.resp = resp

    def ask(self, messages):
        return self.resp


def test_enrich_adds_rationale_without_changing_levels():
    s = DayTradeSetup(
        "AAPL", "breakout", "long", 101.0, 99.0, 105.0, 2.0, "risk 1%", ["broke out"]
    )
    out = enrich_daytrade(
        s, "volume confirms", _FakeLLM("rationale: breakout looks clean while above VWAP")
    )
    assert "breakout" in (out.llm_rationale or "").lower()
    assert out.entry == 101.0 and out.risk_reward == 2.0  # levels untouched


def test_enrich_llm_error_is_safe():
    class Boom:
        def ask(self, messages):
            raise RuntimeError("llm down")

    s = DayTradeSetup(
        "AAPL", "breakout", "long", 101.0, 99.0, 105.0, 2.0, "risk 1%", []
    )
    out = enrich_daytrade(s, "ctx", Boom())
    assert out.entry == 101.0 and out.llm_rationale is None
