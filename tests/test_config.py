import pytest
from config import ConfigError, load_config

BASE_ENV = {
    "LLM_PROVIDER": "groq",
    "GROQ_API_KEY": "gsk_test",
    "DISCORD_TOKEN": "discord_test",
    "DISCORD_ALLOWED_IDS": "123, 456",
    "MARKET_TZ": "America/New_York",
}


def test_config_reads_env():
    cfg = load_config(dict(BASE_ENV))
    assert cfg.llm_provider == "groq"
    assert cfg.discord_allowed_ids == frozenset({123, 456})
    assert cfg.market_tz == "America/New_York"
    assert cfg.max_tool_iters == 6  # default
    assert cfg.article_retention_days == 90  # default


def test_config_missing_token_raises():
    env = dict(BASE_ENV)
    del env["DISCORD_TOKEN"]
    with pytest.raises(ConfigError):
        load_config(env)


def test_config_groq_requires_key():
    env = dict(BASE_ENV)
    del env["GROQ_API_KEY"]
    with pytest.raises(ConfigError):
        load_config(env)


def test_config_unknown_provider_raises():
    env = dict(BASE_ENV)
    env["LLM_PROVIDER"] = "bogus"
    with pytest.raises(ConfigError):
        load_config(env)


def test_config_tavily_backend_requires_key():
    env = dict(BASE_ENV)
    env["WEB_SEARCH_BACKEND"] = "tavily"
    with pytest.raises(ConfigError):
        load_config(env)


def test_config_bad_int_raises():
    env = dict(BASE_ENV)
    env["MAX_TOOL_ITERS"] = "notanint"
    with pytest.raises(ConfigError):
        load_config(env)
