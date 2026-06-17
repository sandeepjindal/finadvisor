import pytest

from llm.base import (
    LLMProvider,
    Message,
    ToolCall,
    ToolCallResult,
    ToolResultMessage,
    ToolSpec,
)


def test_cannot_instantiate_abstract():
    with pytest.raises(TypeError):
        LLMProvider()  # type: ignore[abstract]


def test_dataclasses_roundtrip():
    tc = ToolCall(id="c1", name="get_quote", arguments={"ticker": "NVDA"})
    assert tc.arguments["ticker"] == "NVDA"
    res = ToolCallResult(text=None, tool_calls=[tc])
    assert res.tool_calls[0].name == "get_quote"
    trm = ToolResultMessage(tool_call_id="c1", name="get_quote", content="$123")
    assert trm.content == "$123"
    spec = ToolSpec(
        name="get_quote", description="quote", parameters={"type": "object"}
    )
    assert spec.parameters["type"] == "object"
    m = Message(role="assistant", content="", tool_calls=[tc])
    assert m.tool_calls[0].id == "c1"


def test_dummy_provider_implements_interface():
    class DummyProvider(LLMProvider):
        def ask(self, messages):
            return "ok"

        def ask_with_tools(self, messages, tools):
            return ToolCallResult(text="ok")

        def to_provider_tool_result(self, msg):
            return {"role": "tool", "content": msg.content}

        def parse_tool_calls(self, raw_response):
            return []

    p = DummyProvider()
    assert p.ask([Message("user", "hi")]) == "ok"
    assert p.ask_with_tools([], []).text == "ok"
