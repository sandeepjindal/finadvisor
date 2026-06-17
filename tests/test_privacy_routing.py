from agent.privacy import is_portfolio_related, select_provider

DEFAULT = "DEFAULT_LLM"
LOCAL = "LOCAL_LLM"


def test_is_portfolio_related():
    assert is_portfolio_related("should I sell my position?", [])
    assert is_portfolio_related("how is NVDA?", ["NVDA"])
    assert not is_portfolio_related("how is the market?", ["NVDA"])


def test_select_provider_local_for_portfolio():
    assert select_provider("I own 30 NVDA", ["NVDA"], "local", DEFAULT, LOCAL) == LOCAL


def test_select_provider_default_for_generic():
    assert (
        select_provider("what is an index fund?", ["NVDA"], "local", DEFAULT, LOCAL)
        == DEFAULT
    )


def test_privacy_off_always_default():
    assert (
        select_provider("should I sell my NVDA?", ["NVDA"], "off", DEFAULT, LOCAL)
        == DEFAULT
    )
