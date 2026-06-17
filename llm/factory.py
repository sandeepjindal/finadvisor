"""Select an LLM provider from config. One env var swaps the model. Step 0.6."""

from __future__ import annotations

from config import Config, ConfigError
from llm.base import LLMProvider
from llm.groq_provider import GroqProvider
from llm.ollama_provider import OllamaProvider

_STUBS = {"gemini", "claude", "openai"}


def get_llm(cfg: Config) -> LLMProvider:
    provider = cfg.llm_provider
    if provider == "groq":
        return GroqProvider(cfg.groq_api_key, cfg.groq_model)
    if provider == "ollama":
        return OllamaProvider(cfg.ollama_model)
    if provider in _STUBS:
        raise NotImplementedError(
            f"LLM provider {provider!r} is a stub; install its extra and implement it."
        )
    raise ConfigError(f"Unknown LLM provider: {provider!r}")
