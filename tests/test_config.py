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
    assert cfg.bot_platform == "discord"
    assert cfg.llm_provider == "groq"
    assert cfg.discord_allowed_ids == frozenset({123, 456})
    assert cfg.market_tz == "America/New_York"
    assert cfg.whatsapp_api_version == "v25.0"
    assert cfg.max_tool_iters == 6  # default
    assert cfg.article_retention_days == 90  # default


def test_config_missing_token_raises():
    env = dict(BASE_ENV)
    del env["DISCORD_TOKEN"]
    with pytest.raises(ConfigError):
        load_config(env)


def test_config_placeholder_token_raises():
    env = dict(BASE_ENV)
    env["DISCORD_TOKEN"] = "your_token_here"
    with pytest.raises(ConfigError, match="placeholder"):
        load_config(env)


def test_config_bot_prefix_token_raises():
    env = dict(BASE_ENV)
    env["DISCORD_TOKEN"] = "Bot abc123"
    with pytest.raises(ConfigError, match="raw token"):
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


def test_config_tolerates_inline_comments():
    # python-dotenv can keep inline "# ..." as the value; config must strip it.
    env = dict(BASE_ENV)
    env["LLM_PROVIDER"] = "groq   # the provider"
    env["DISCORD_ALLOWED_IDS"] = "123  # my id"
    env["DISCORD_DIGEST_CHANNEL_ID"] = "   # channel id for the morning digest"
    env["MAX_TOOL_ITERS"] = "6  # cap"
    cfg = load_config(env)
    assert cfg.llm_provider == "groq"
    assert cfg.discord_allowed_ids == frozenset({123})
    assert cfg.discord_digest_channel_id is None
    assert cfg.max_tool_iters == 6


def test_config_bad_int_raises():
    env = dict(BASE_ENV)
    env["MAX_TOOL_ITERS"] = "notanint"
    with pytest.raises(ConfigError):
        load_config(env)


def test_config_whatsapp_mode_does_not_require_discord_token():
    env = dict(BASE_ENV)
    env["BOT_PLATFORM"] = "whatsapp"
    del env["DISCORD_TOKEN"]
    env["WHATSAPP_VERIFY_TOKEN"] = "verify_me"
    env["WHATSAPP_ACCESS_TOKEN"] = "wa_token"
    env["WHATSAPP_PHONE_NUMBER_ID"] = "12345"
    env["WHATSAPP_ALLOWED_NUMBERS"] = "+1555-0100, sender-id"
    cfg = load_config(env)
    assert cfg.bot_platform == "whatsapp"
    assert cfg.discord_token is None
    assert cfg.whatsapp_verify_token == "verify_me"
    assert cfg.whatsapp_allowed_numbers == frozenset({"15550100", "senderid"})


@pytest.mark.parametrize(
    "missing",
    ["WHATSAPP_VERIFY_TOKEN", "WHATSAPP_ACCESS_TOKEN", "WHATSAPP_PHONE_NUMBER_ID"],
)
def test_config_whatsapp_mode_requires_cloud_api_settings(missing):
    env = dict(BASE_ENV)
    env["BOT_PLATFORM"] = "whatsapp"
    env["WHATSAPP_VERIFY_TOKEN"] = "verify_me"
    env["WHATSAPP_ACCESS_TOKEN"] = "wa_token"
    env["WHATSAPP_PHONE_NUMBER_ID"] = "12345"
    del env[missing]
    with pytest.raises(ConfigError, match=missing):
        load_config(env)
