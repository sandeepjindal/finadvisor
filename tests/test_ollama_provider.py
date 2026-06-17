from unittest.mock import MagicMock

from llm.base import Message, ToolResultMessage, ToolSpec
from llm.ollama_provider import OllamaProvider


def test_ask_returns_content_dict_style():
    p = OllamaProvider(model="llama3.1")
    p._client = MagicMock()
    p._client.chat.return_value = {"message": {"content": "hello", "tool_calls": None}}
    assert p.ask([Message("user", "hi")]) == "hello"


def test_ask_with_tools_parses_native_tool_calls():
    p = OllamaProvider(model="llama3.1")
    p._client = MagicMock()
    p._client.chat.return_value = {
        "message": {
            "content": "",
            "tool_calls": [
                {"function": {"name": "get_quote", "arguments": {"ticker": "NVDA"}}}
            ],
        }
    }
    res = p.ask_with_tools([Message("user", "nvda?")], [ToolSpec("get_quote", "q", {})])
    assert len(res.tool_calls) == 1
    assert res.tool_calls[0].name == "get_quote"
    assert res.tool_calls[0].arguments == {"ticker": "NVDA"}


def test_json_mode_fallback():
    p = OllamaProvider(model="tiny")
    p._client = MagicMock()
    p._client.chat.return_value = {
        "message": {
            "content": 'I will call {"tool": "get_quote", "arguments": {"ticker": "META"}}',
            "tool_calls": None,
        }
    }
    res = p.ask_with_tools([Message("user", "meta?")], [ToolSpec("get_quote", "q", {})])
    assert len(res.tool_calls) == 1
    assert res.tool_calls[0].name == "get_quote"
    assert res.tool_calls[0].arguments == {"ticker": "META"}


def test_to_provider_tool_result_has_no_tool_call_id():
    p = OllamaProvider()
    d = p.to_provider_tool_result(ToolResultMessage("c1", "get_quote", "$123"))
    assert d["role"] == "tool"
    assert "tool_call_id" not in d
    assert d["content"] == "$123"
