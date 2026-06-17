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
