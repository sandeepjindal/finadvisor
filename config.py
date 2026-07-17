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
    llm_provider: str
    groq_api_key: str | None
    groq_model: str
    ollama_model: str
    anthropic_api_key: str | None
    claude_model: str
    discord_token: str
    discord_allowed_ids: frozenset[int]
    discord_digest_channel_id: int | None
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


_VALID_PROVIDERS = {"groq", "ollama", "gemini", "claude", "openai"}


def load_config(env: dict[str, str] | None = None) -> Config:
    env = os.environ if env is None else env

    provider = (_clean(env.get("LLM_PROVIDER")) or "groq").lower()
    if provider not in _VALID_PROVIDERS:
        raise ConfigError(
            f"LLM_PROVIDER must be one of {sorted(_VALID_PROVIDERS)}, got {provider!r}"
        )

    discord_token = _clean(env.get("DISCORD_TOKEN"))
    if not discord_token:
        raise ConfigError("DISCORD_TOKEN is required")

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
        llm_provider=provider,
        groq_api_key=groq_api_key,
        groq_model=_clean(env.get("GROQ_MODEL")) or "llama-3.3-70b-versatile",
        ollama_model=_clean(env.get("OLLAMA_MODEL")) or "llama3.1",
        anthropic_api_key=anthropic_api_key,
        claude_model=_clean(env.get("CLAUDE_MODEL")) or "claude-opus-4-8",
        discord_token=discord_token,
        discord_allowed_ids=_parse_ids(env.get("DISCORD_ALLOWED_IDS")),
        discord_digest_channel_id=_opt_int(env.get("DISCORD_DIGEST_CHANNEL_ID")),
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
        cfg.tavily_api_key,
        cfg.anthropic_api_key,
    ):
        register_secret(secret)

    return cfg
