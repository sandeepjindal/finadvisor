"""Application configuration loaded from environment variables.

`load_config()` reads the environment fresh on each call, validates required keys per the
selected LLM provider, registers secrets with the logging redactor, and returns a frozen
`Config`. Step 0.2.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from logging_setup import register_secret


class ConfigError(Exception):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True)
class Config:
    bot_platform: str
    llm_provider: str
    groq_api_key: str | None
    groq_model: str
    ollama_model: str
    anthropic_api_key: str | None
    claude_model: str
    discord_token: str | None
    discord_allowed_ids: frozenset[int]
    discord_digest_channel_id: int | None
    whatsapp_verify_token: str | None
    whatsapp_access_token: str | None
    whatsapp_phone_number_id: str | None
    whatsapp_allowed_numbers: frozenset[str]
    whatsapp_app_secret: str | None
    whatsapp_api_version: str
    whatsapp_host: str
    whatsapp_port: int
    whatsapp_webhook_path: str
    db_path: str
    article_retention_days: int
    max_tool_iters: int
    market_tz: str
    digest_time: str
    web_search_backend: str
    tavily_api_key: str | None
    mcp_search_command: str | None
    mcp_search_url: str | None
    mcp_search_tool: str
    log_level: str
    privacy_mode: str


def _clean(raw: str | None) -> str | None:
    """Strip surrounding whitespace and any inline `# comment` (a common .env mistake;
    none of our values legitimately contain '#'). Returns None for empty results."""
    if raw is None:
        return None
    value = raw.split("#", 1)[0].strip()
    return value or None


def _parse_ids(raw: str | None) -> frozenset[int]:
    raw = _clean(raw)
    if not raw:
        return frozenset()
    ids = set()
    for part in raw.split(","):
        part = part.strip()
        if part:
            try:
                ids.add(int(part))
            except ValueError as e:
                raise ConfigError(f"Invalid Discord id: {part!r}") from e
    return frozenset(ids)


def _normalize_whatsapp_identity(raw: str) -> str:
    return raw.strip().removeprefix("+").replace(" ", "").replace("-", "")


def _parse_whatsapp_allowed(raw: str | None) -> frozenset[str]:
    raw = _clean(raw)
    if not raw:
        return frozenset()
    return frozenset(
        normalized
        for part in raw.split(",")
        if (normalized := _normalize_whatsapp_identity(part))
    )


def _parse_int(raw: str | None, default: int, name: str) -> int:
    raw = _clean(raw)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as e:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from e


def _opt_int(raw: str | None) -> int | None:
    raw = _clean(raw)
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError as e:
        raise ConfigError(f"Expected integer, got {raw!r}") from e


def _validate_discord_token(token: str) -> None:
    lowered = token.lower()
    if lowered in {"your_token_here", "discord_token", "token"} or "your_" in lowered:
        raise ConfigError(
            "DISCORD_TOKEN is still a placeholder; paste the bot token from the Discord Developer Portal"
        )
    if lowered.startswith("bot "):
        raise ConfigError("DISCORD_TOKEN should be the raw token only, without 'Bot '")


_VALID_PROVIDERS = {"groq", "ollama", "gemini", "claude", "openai"}
_VALID_BOT_PLATFORMS = {"discord", "whatsapp"}


def load_config(env: dict[str, str] | None = None) -> Config:
    env = os.environ if env is None else env

    provider = (_clean(env.get("LLM_PROVIDER")) or "groq").lower()
    if provider not in _VALID_PROVIDERS:
        raise ConfigError(
            f"LLM_PROVIDER must be one of {sorted(_VALID_PROVIDERS)}, got {provider!r}"
        )

    bot_platform = (_clean(env.get("BOT_PLATFORM")) or "discord").lower()
    if bot_platform not in _VALID_BOT_PLATFORMS:
        raise ConfigError(
            f"BOT_PLATFORM must be one of {sorted(_VALID_BOT_PLATFORMS)}, got {bot_platform!r}"
        )

    discord_token = _clean(env.get("DISCORD_TOKEN"))
    if bot_platform == "discord" and not discord_token:
        raise ConfigError("DISCORD_TOKEN is required")
    if discord_token:
        _validate_discord_token(discord_token)

    whatsapp_verify_token = _clean(env.get("WHATSAPP_VERIFY_TOKEN"))
    whatsapp_access_token = _clean(env.get("WHATSAPP_ACCESS_TOKEN"))
    whatsapp_phone_number_id = _clean(env.get("WHATSAPP_PHONE_NUMBER_ID"))
    if bot_platform == "whatsapp":
        if not whatsapp_verify_token:
            raise ConfigError("WHATSAPP_VERIFY_TOKEN is required when BOT_PLATFORM=whatsapp")
        if not whatsapp_access_token:
            raise ConfigError("WHATSAPP_ACCESS_TOKEN is required when BOT_PLATFORM=whatsapp")
        if not whatsapp_phone_number_id:
            raise ConfigError("WHATSAPP_PHONE_NUMBER_ID is required when BOT_PLATFORM=whatsapp")

    groq_api_key = _clean(env.get("GROQ_API_KEY"))
    tavily_api_key = _clean(env.get("TAVILY_API_KEY"))
    anthropic_api_key = _clean(env.get("ANTHROPIC_API_KEY"))

    if provider == "groq" and not groq_api_key:
        raise ConfigError("GROQ_API_KEY is required when LLM_PROVIDER=groq")
    # LLM_PROVIDER=claude does NOT require ANTHROPIC_API_KEY: the Anthropic SDK falls back to
    # an `ant auth login` OAuth profile / ANTHROPIC_AUTH_TOKEN when no key is set.

    web_search_backend = (_clean(env.get("WEB_SEARCH_BACKEND")) or "ddgs").lower()
    if web_search_backend == "tavily" and not tavily_api_key:
        raise ConfigError("TAVILY_API_KEY is required when WEB_SEARCH_BACKEND=tavily")

    mcp_search_command = _clean(env.get("MCP_SEARCH_COMMAND"))
    mcp_search_url = _clean(env.get("MCP_SEARCH_URL"))
    if web_search_backend == "mcp" and not (mcp_search_command or mcp_search_url):
        raise ConfigError(
            "WEB_SEARCH_BACKEND=mcp requires MCP_SEARCH_COMMAND or MCP_SEARCH_URL"
        )

    privacy_mode = (_clean(env.get("PRIVACY_MODE")) or "off").lower()
    if privacy_mode not in {"off", "local"}:
        raise ConfigError("PRIVACY_MODE must be 'off' or 'local'")

    cfg = Config(
        bot_platform=bot_platform,
        llm_provider=provider,
        groq_api_key=groq_api_key,
        groq_model=_clean(env.get("GROQ_MODEL")) or "llama-3.3-70b-versatile",
        ollama_model=_clean(env.get("OLLAMA_MODEL")) or "llama3.1",
        anthropic_api_key=anthropic_api_key,
        claude_model=_clean(env.get("CLAUDE_MODEL")) or "claude-opus-4-8",
        discord_token=discord_token,
        discord_allowed_ids=_parse_ids(env.get("DISCORD_ALLOWED_IDS")),
        discord_digest_channel_id=_opt_int(env.get("DISCORD_DIGEST_CHANNEL_ID")),
        whatsapp_verify_token=whatsapp_verify_token,
        whatsapp_access_token=whatsapp_access_token,
        whatsapp_phone_number_id=whatsapp_phone_number_id,
        whatsapp_allowed_numbers=_parse_whatsapp_allowed(env.get("WHATSAPP_ALLOWED_NUMBERS")),
        whatsapp_app_secret=_clean(env.get("WHATSAPP_APP_SECRET")),
        whatsapp_api_version=_clean(env.get("WHATSAPP_API_VERSION")) or "v25.0",
        whatsapp_host=_clean(env.get("WHATSAPP_HOST")) or "0.0.0.0",
        whatsapp_port=_parse_int(env.get("WHATSAPP_PORT"), 8080, "WHATSAPP_PORT"),
        whatsapp_webhook_path=_clean(env.get("WHATSAPP_WEBHOOK_PATH")) or "/whatsapp/webhook",
        db_path=_clean(env.get("DB_PATH")) or "./brain.db",
        article_retention_days=_parse_int(
            env.get("ARTICLE_RETENTION_DAYS"), 90, "ARTICLE_RETENTION_DAYS"
        ),
        max_tool_iters=_parse_int(env.get("MAX_TOOL_ITERS"), 6, "MAX_TOOL_ITERS"),
        market_tz=_clean(env.get("MARKET_TZ")) or "America/New_York",
        digest_time=_clean(env.get("DIGEST_TIME")) or "08:30",
        web_search_backend=web_search_backend,
        tavily_api_key=tavily_api_key,
        mcp_search_command=mcp_search_command,
        mcp_search_url=mcp_search_url,
        mcp_search_tool=_clean(env.get("MCP_SEARCH_TOOL")) or "search",
        log_level=(_clean(env.get("LOG_LEVEL")) or "INFO").upper(),
        privacy_mode=privacy_mode,
    )

    # Make secrets unloggable.
    for secret in (
        cfg.groq_api_key,
        cfg.discord_token,
        cfg.whatsapp_access_token,
        cfg.whatsapp_app_secret,
        cfg.whatsapp_verify_token,
        cfg.tavily_api_key,
        cfg.anthropic_api_key,
    ):
        register_secret(secret)

    return cfg
