from agent.redeploy import suggest_redeploy


def test_balanced_default():
    out = suggest_redeploy()
    assert out and all(f.expense_ratio < 0.01 for f in out)


def test_growth_includes_qqq():
    assert any(f.ticker == "QQQ" for f in suggest_redeploy(risk="growth"))


def test_defensive_includes_schd():
    assert any(f.ticker == "SCHD" for f in suggest_redeploy(risk="defensive"))
