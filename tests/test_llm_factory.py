import pytest
from config import ConfigError, load_config
from llm.factory import get_llm
from llm.groq_provider import GroqProvider
from llm.ollama_provider import OllamaProvider

BASE = {"DISCORD_TOKEN": "t"}


def _cfg(**over):
    env = dict(BASE)
    env.update(over)
    if env.get("LLM_PROVIDER", "groq") == "groq":
        env.setdefault("GROQ_API_KEY", "k")
    return load_config(env)


def test_factory_groq():
    assert isinstance(get_llm(_cfg(LLM_PROVIDER="groq")), GroqProvider)


def test_factory_ollama():
    assert isinstance(get_llm(_cfg(LLM_PROVIDER="ollama")), OllamaProvider)


@pytest.mark.parametrize("provider", ["gemini", "openai"])
def test_factory_stubs_raise_not_implemented(provider):
    with pytest.raises(NotImplementedError):
        get_llm(_cfg(LLM_PROVIDER=provider))


def test_factory_claude_implemented():
    from llm.claude_provider import ClaudeProvider

    llm = get_llm(_cfg(LLM_PROVIDER="claude", ANTHROPIC_API_KEY="sk-ant-test"))
    assert isinstance(llm, ClaudeProvider)


def test_factory_claude_works_without_key():
    # No ANTHROPIC_API_KEY needed — the SDK uses an `ant auth login` profile at runtime.
    from llm.claude_provider import ClaudeProvider

    llm = get_llm(_cfg(LLM_PROVIDER="claude"))
    assert isinstance(llm, ClaudeProvider) and llm._api_key is None


def test_factory_unknown_provider_rejected_at_config():
    # Unknown providers are rejected by config validation before reaching the factory.
    with pytest.raises(ConfigError):
        _cfg(LLM_PROVIDER="bogus")
