"""Claude provider — message translation to the Anthropic Messages shape + tool-call
parsing, all offline with a fake client (no anthropic SDK, no network, no key)."""

from __future__ import annotations

from types import SimpleNamespace

from llm.base import Message, ToolCall, ToolResultMessage, ToolSpec
from llm.claude_provider import ClaudeProvider


def _block(type_, **kw):
    return SimpleNamespace(type=type_, **kw)


def test_split_extracts_system_and_merges_tool_results():
    p = ClaudeProvider(api_key=None)
    msgs = [
        Message("system", "you are helpful"),
        Message("user", "how is NVDA?"),
        Message("assistant", "", tool_calls=[ToolCall("c1", "get_quote", {"ticker": "NVDA"})]),
        Message("tool", "price 120", tool_call_id="c1", name="get_quote"),
        Message("tool", "rsi 60", tool_call_id="c2", name="get_technicals"),
    ]
    system, out = p._split(msgs)
    assert system == "you are helpful"
    # user, assistant(tool_use), then ONE merged user turn with both tool_results
    assert out[0] == {"role": "user", "content": "how is NVDA?"}
    assert out[1]["role"] == "assistant"
    assert out[1]["content"][0] == {"type": "tool_use", "id": "c1", "name": "get_quote", "input": {"ticker": "NVDA"}}
    assert out[2]["role"] == "user"
    assert [b["type"] for b in out[2]["content"]] == ["tool_result", "tool_result"]
    assert out[2]["content"][0]["tool_use_id"] == "c1"


def test_parse_tool_calls_from_content_blocks():
    p = ClaudeProvider(api_key=None)
    resp = SimpleNamespace(
        content=[
            _block("text", text="Let me check."),
            _block("tool_use", id="tu1", name="get_quote", input={"ticker": "AAPL"}),
        ]
    )
    calls = p.parse_tool_calls(resp)
    assert len(calls) == 1
    assert calls[0].id == "tu1" and calls[0].name == "get_quote"
    assert calls[0].arguments == {"ticker": "AAPL"}


def test_ask_with_tools_uses_fake_client():
    p = ClaudeProvider(api_key=None)

    class _FakeMessages:
        def create(self, **kwargs):
            # tools + system are passed through in Anthropic shape
            assert kwargs["tools"][0]["input_schema"] == {"type": "object", "properties": {}}
            assert kwargs["system"] == "sys"
            return SimpleNamespace(
                content=[
                    _block("text", text="calling a tool"),
                    _block("tool_use", id="x", name="get_macro", input={}),
                ]
            )

    p._client = SimpleNamespace(messages=_FakeMessages())
    res = p.ask_with_tools(
        [Message("system", "sys"), Message("user", "macro?")],
        [ToolSpec("get_macro", "macro", {"type": "object", "properties": {}})],
    )
    assert res.text == "calling a tool"
    assert res.tool_calls[0].name == "get_macro"


def test_to_provider_tool_result_shape():
    p = ClaudeProvider(api_key=None)
    d = p.to_provider_tool_result(ToolResultMessage("c1", "get_quote", "price 120"))
    assert d["role"] == "user"
    assert d["content"][0] == {"type": "tool_result", "tool_use_id": "c1", "content": "price 120"}
