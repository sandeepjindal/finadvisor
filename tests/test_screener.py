from agent.knowledge import load_rules
from agent.screener import rank_universe, score_ticker


def test_good_beats_bad():
    rules = load_rules()
    good = score_ticker(
        "A", trend="up", rsi=55, pe=12, profit_margin=0.3, sentiment=0.6, rules=rules
    )
    bad = score_ticker(
        "B",
        trend="down",
        rsi=82,
        pe=90,
        profit_margin=-0.1,
        sentiment=-0.6,
        rules=rules,
    )
    assert good.composite > bad.composite
    assert set(good.breakdown) == {
        "fundamental",
        "technical",
        "sentiment",
        "macro",
        "catalyst",
    }


def test_rank_orders_desc():
    rules = load_rules()
    a = score_ticker(
        "A", trend="up", rsi=50, pe=12, profit_margin=0.3, sentiment=0.5, rules=rules
    )
    b = score_ticker(
        "B", trend="down", rsi=80, pe=80, profit_margin=0.0, sentiment=-0.5, rules=rules
    )
    ranked = rank_universe([b, a])
    assert ranked[0].ticker == "A"


def test_composite_in_range():
    rules = load_rules()
    s = score_ticker(
        "X",
        trend="sideways",
        rsi=None,
        pe=None,
        profit_margin=None,
        sentiment=None,
        rules=rules,
    )
    assert 0.0 <= s.composite <= 1.0


# --- Work-stream A: graded technical score ---------------------------------------


def _tech(rules, **kw):
    base = dict(
        trend="sideways",
        rsi=None,
        pe=None,
        profit_margin=None,
        sentiment=None,
        rules=rules,
    )
    base.update(kw)
    return score_ticker("T", **base).breakdown["technical"]


def test_technical_score_monotonic_in_strength():
    rules = load_rules()
    weak = _tech(rules, trend_strength=-0.9)
    mid = _tech(rules, trend_strength=0.0)
    strong = _tech(rules, trend_strength=0.9)
    assert weak < mid < strong


def test_bullish_macd_and_golden_cross_add_bonus():
    rules = load_rules()
    plain = _tech(rules, trend_strength=0.2)
    boosted = _tech(rules, trend_strength=0.2, macd_cross="bullish", cross_signal="golden")
    bearish = _tech(rules, trend_strength=0.2, macd_cross="bearish", cross_signal="death")
    assert boosted > plain > bearish


def test_technical_score_falls_back_to_buckets_without_strength():
    rules = load_rules()
    up = _tech(rules, trend="up")
    down = _tech(rules, trend="down")
    assert up > down  # old {up:0.8, down:0.2} behavior preserved


def test_overbought_penalizes_graded_score():
    rules = load_rules()
    overbought = rules.alert_thresholds.get("rsi_overbought", 70)
    calm = _tech(rules, trend_strength=0.8, rsi=50)
    hot = _tech(rules, trend_strength=0.8, rsi=overbought + 10)
    assert hot < calm
