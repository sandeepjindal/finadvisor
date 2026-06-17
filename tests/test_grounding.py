from agent.grounding import extract_numeric_tokens, validate_grounding
from agent.prompts import Citation


def _cites(*vals):
    return [Citation("m", v, "src", "t") for v in vals]


def test_extract_numbers():
    assert extract_numeric_tokens("P/E is 28.4, up 3.2%") == {28.4, 3.2}


def test_grounded_passes():
    res = validate_grounding("P/E 28.4 moved 3.2%", _cites(28.4, 3.2, 123.45))
    assert res.ok
    assert res.unsupported == []


def test_ungrounded_decimal_flagged():
    res = validate_grounding("P/E is 99.9 actually", _cites(28.4))
    assert not res.ok
    assert 99.9 in res.unsupported


def test_tolerance_match_and_far_off():
    res = validate_grounding("price 123.45 not 999.99", _cites(123.4500001))
    assert 123.45 in res.supported
    assert 999.99 in res.unsupported


def test_structural_integers_whitelisted():
    res = validate_grounding(
        "In 2026 the 200-day MA and 50-day with 70% confidence, point 1.", _cites()
    )
    assert res.ok
