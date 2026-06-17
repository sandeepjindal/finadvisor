import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from llm.base import Message, ToolResultMessage, ToolSpec
from llm.groq_provider import GroqProvider


def _resp(content=None, tool_calls=None):
    msg = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


def _fake_tc(id_, name, args):
    return SimpleNamespace(
        id=id_, function=SimpleNamespace(name=name, arguments=json.dumps(args))
    )


def test_ask_returns_content():
    p = GroqProvider(api_key="k", model="m")
    p._client = MagicMock()
    p._client.chat.completions.create.return_value = _resp(content="hello")
    assert p.ask([Message("user", "hi")]) == "hello"
    kwargs = p._client.chat.completions.create.call_args.kwargs
    assert kwargs["model"] == "m"
    assert kwargs["messages"] == [{"role": "user", "content": "hi"}]


def test_ask_with_tools_parses_tool_calls():
    p = GroqProvider(api_key="k", model="m")
    p._client = MagicMock()
    p._client.chat.completions.create.return_value = _resp(
        tool_calls=[_fake_tc("c1", "get_quote", {"ticker": "NVDA"})]
    )
    spec = ToolSpec("get_quote", "quote", {"type": "object"})
    res = p.ask_with_tools([Message("user", "nvda?")], [spec])
    assert len(res.tool_calls) == 1
    assert res.tool_calls[0].name == "get_quote"
    assert res.tool_calls[0].arguments == {"ticker": "NVDA"}


def test_to_provider_tool_result_shape():
    p = GroqProvider(api_key="k")
    d = p.to_provider_tool_result(ToolResultMessage("c1", "get_quote", "$123"))
    assert d["role"] == "tool"
    assert d["tool_call_id"] == "c1"
    assert d["content"] == "$123"


class _FakeBadRequest(Exception):
    """Mimics Groq's tool_use_failed 400 (carries .body with failed_generation)."""

    def __init__(self, failed_generation=None, msg="400"):
        super().__init__(msg)
        self.body = (
            {"error": {"failed_generation": failed_generation}}
            if failed_generation
            else None
        )


def test_recovers_tool_call_from_malformed_groq_generation():
    p = GroqProvider(api_key="k")
    p._client = MagicMock()
    p._client.chat.completions.create.side_effect = _FakeBadRequest(
        '<function=assess_exit[]{"ticker": "NVDA"}</function>'
    )
    res = p.ask_with_tools(
        [Message("user", "sell nvda?")], [ToolSpec("assess_exit", "x", {})]
    )
    assert len(res.tool_calls) == 1
    assert res.tool_calls[0].name == "assess_exit"
    assert res.tool_calls[0].arguments == {"ticker": "NVDA"}


def test_falls_back_to_plain_answer_when_unrecoverable():
    p = GroqProvider(api_key="k")
    p._client = MagicMock()
    # first call (with tools) errors with no recoverable function; second call (ask) answers
    p._client.chat.completions.create.side_effect = [
        _FakeBadRequest(None, "boom"),
        _resp(content="plain answer"),
    ]
    res = p.ask_with_tools([Message("user", "hi")], [ToolSpec("get_quote", "x", {})])
    assert res.tool_calls == []
    assert res.text == "plain answer"
