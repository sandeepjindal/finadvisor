"""Cross-provider parity for the tool-result feedback contract (Step 0.3b).

Capability restriction (no write tools) is the real safety backstop; this verifies the
*correctness* of the tool-calling loop's wire translation for both providers.
"""

import json
from types import SimpleNamespace

from llm.base import ToolResultMessage
from llm.groq_provider import GroqProvider
from llm.ollama_provider import OllamaProvider


def test_groq_tool_result_includes_id():
    p = GroqProvider(api_key="k")
    d = p.to_provider_tool_result(ToolResultMessage("call_1", "get_quote", "x"))
    assert d == {
        "role": "tool",
        "tool_call_id": "call_1",
        "name": "get_quote",
        "content": "x",
    }


def test_ollama_tool_result_omits_id():
    p = OllamaProvider()
    d = p.to_provider_tool_result(ToolResultMessage("call_1", "get_quote", "x"))
    assert "tool_call_id" not in d
    assert d["role"] == "tool" and d["content"] == "x"


def test_groq_parse_tool_calls():
    p = GroqProvider(api_key="k")
    raw = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=None,
                    tool_calls=[
                        SimpleNamespace(
                            id="c1",
                            function=SimpleNamespace(
                                name="get_quote",
                                arguments=json.dumps({"ticker": "AAPL"}),
                            ),
                        )
                    ],
                )
            )
        ]
    )
    calls = p.parse_tool_calls(raw)
    assert calls[0].id == "c1" and calls[0].arguments == {"ticker": "AAPL"}


def test_ollama_parse_tool_calls_native_and_fallback():
    p = OllamaProvider()
    native = {
        "message": {
            "content": "",
            "tool_calls": [
                {"function": {"name": "get_quote", "arguments": {"ticker": "AAPL"}}}
            ],
        }
    }
    assert p.parse_tool_calls(native)[0].name == "get_quote"

    fallback = {
        "message": {
            "content": '{"name": "get_quote", "arguments": {"ticker": "AAPL"}}',
            "tool_calls": None,
        }
    }
    calls = p.parse_tool_calls(fallback)
    assert calls[0].name == "get_quote" and calls[0].arguments == {"ticker": "AAPL"}
