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
    log_level: str
    privacy_mode: str


def _parse_ids(raw: str | None) -> frozenset[int]:
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
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError as e:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from e


def _opt_int(raw: str | None) -> int | None:
    if raw is None or raw.strip() == "":
        return None
    try:
        return int(raw)
    except ValueError as e:
        raise ConfigError(f"Expected integer, got {raw!r}") from e


_VALID_PROVIDERS = {"groq", "ollama", "gemini", "claude", "openai"}


def load_config(env: dict[str, str] | None = None) -> Config:
    env = os.environ if env is None else env

    provider = env.get("LLM_PROVIDER", "groq").strip().lower()
    if provider not in _VALID_PROVIDERS:
        raise ConfigError(
            f"LLM_PROVIDER must be one of {sorted(_VALID_PROVIDERS)}, got {provider!r}"
        )

    discord_token = env.get("DISCORD_TOKEN", "").strip()
    if not discord_token:
        raise ConfigError("DISCORD_TOKEN is required")

    groq_api_key = env.get("GROQ_API_KEY") or None
    tavily_api_key = env.get("TAVILY_API_KEY") or None

    if provider == "groq" and not groq_api_key:
        raise ConfigError("GROQ_API_KEY is required when LLM_PROVIDER=groq")

    web_search_backend = env.get("WEB_SEARCH_BACKEND", "ddgs").strip().lower()
    if web_search_backend == "tavily" and not tavily_api_key:
        raise ConfigError("TAVILY_API_KEY is required when WEB_SEARCH_BACKEND=tavily")

    privacy_mode = env.get("PRIVACY_MODE", "off").strip().lower()
    if privacy_mode not in {"off", "local"}:
        raise ConfigError("PRIVACY_MODE must be 'off' or 'local'")

    cfg = Config(
        llm_provider=provider,
        groq_api_key=groq_api_key,
        groq_model=env.get("GROQ_MODEL", "llama-3.3-70b-versatile").strip(),
        ollama_model=env.get("OLLAMA_MODEL", "llama3.1").strip(),
        discord_token=discord_token,
        discord_allowed_ids=_parse_ids(env.get("DISCORD_ALLOWED_IDS")),
        discord_digest_channel_id=_opt_int(env.get("DISCORD_DIGEST_CHANNEL_ID")),
        db_path=env.get("DB_PATH", "./brain.db").strip(),
        article_retention_days=_parse_int(
            env.get("ARTICLE_RETENTION_DAYS"), 90, "ARTICLE_RETENTION_DAYS"
        ),
        max_tool_iters=_parse_int(env.get("MAX_TOOL_ITERS"), 6, "MAX_TOOL_ITERS"),
        market_tz=env.get("MARKET_TZ", "America/New_York").strip(),
        digest_time=env.get("DIGEST_TIME", "08:30").strip(),
        web_search_backend=web_search_backend,
        tavily_api_key=tavily_api_key,
        log_level=env.get("LOG_LEVEL", "INFO").strip().upper(),
        privacy_mode=privacy_mode,
    )

    # Make secrets unloggable.
    for secret in (cfg.groq_api_key, cfg.discord_token, cfg.tavily_api_key):
        register_secret(secret)

    return cfg
