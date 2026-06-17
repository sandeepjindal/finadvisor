"""Ollama provider — local, private, offline models. Tool calling + JSON-mode fallback.

Differs from Groq: Ollama tool results carry no `tool_call_id`, and tool-call arguments
arrive as dicts (not JSON strings). For models without native tool support we fall back
to parsing a JSON blob from the message content. Client is lazy. Step 0.5.
"""

from __future__ import annotations

import json
import re

from llm.base import (
    LLMProvider,
    Message,
    ToolCall,
    ToolCallResult,
    ToolResultMessage,
    ToolSpec,
)

_JSON_BLOB = re.compile(r"\{.*\}", re.DOTALL)


class OllamaProvider(LLMProvider):
    def __init__(self, model: str = "llama3.1"):
        self._model = model
        self._client = None

    @property
    def client(self):
        if self._client is None:
            import ollama

            self._client = ollama.Client()
        return self._client

    def _to_messages(self, messages: list[Message]) -> list[dict]:
        out: list[dict] = []
        for m in messages:
            if m.role == "tool":
                out.append(
                    self.to_provider_tool_result(
                        ToolResultMessage(m.tool_call_id or "", m.name or "", m.content)
                    )
                )
            elif m.role == "assistant" and m.tool_calls:
                out.append(
                    {
                        "role": "assistant",
                        "content": m.content or "",
                        "tool_calls": [
                            {
                                "function": {
                                    "name": tc.name,
                                    "arguments": tc.arguments,
                                }
                            }
                            for tc in m.tool_calls
                        ],
                    }
                )
            else:
                out.append({"role": m.role, "content": m.content})
        return out

    @staticmethod
    def _to_tools(tools: list[ToolSpec]) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in tools
        ]

    @staticmethod
    def _content(resp) -> str:
        # ollama returns a ChatResponse (subscriptable) or a dict.
        try:
            return resp["message"]["content"] or ""
        except (TypeError, KeyError):
            return getattr(resp.message, "content", "") or ""

    @staticmethod
    def _raw_tool_calls(resp):
        try:
            return resp["message"].get("tool_calls")
        except (TypeError, KeyError, AttributeError):
            return getattr(getattr(resp, "message", None), "tool_calls", None)

    def ask(self, messages: list[Message]) -> str:
        resp = self.client.chat(model=self._model, messages=self._to_messages(messages))
        return self._content(resp)

    def ask_with_tools(
        self, messages: list[Message], tools: list[ToolSpec]
    ) -> ToolCallResult:
        resp = self.client.chat(
            model=self._model,
            messages=self._to_messages(messages),
            tools=self._to_tools(tools),
        )
        calls = self.parse_tool_calls(resp)
        return ToolCallResult(text=self._content(resp), tool_calls=calls)

    def to_provider_tool_result(self, msg: ToolResultMessage) -> dict:
        # Older Ollama has no tool_call_id; include name for traceability.
        return {"role": "tool", "name": msg.name, "content": msg.content}

    def parse_tool_calls(self, raw_response) -> list[ToolCall]:
        raw_calls = self._raw_tool_calls(raw_response)
        calls: list[ToolCall] = []
        if raw_calls:
            for i, tc in enumerate(raw_calls):
                fn = tc["function"] if isinstance(tc, dict) else tc.function
                name = fn["name"] if isinstance(fn, dict) else fn.name
                args = fn["arguments"] if isinstance(fn, dict) else fn.arguments
                if isinstance(args, str):
                    args = json.loads(args or "{}")
                calls.append(ToolCall(id=f"call_{i}", name=name, arguments=args or {}))
            return calls
        # JSON-mode fallback: recover {"tool"/"name": ..., "arguments": {...}} from text.
        return self._fallback_from_text(self._content(raw_response))

    @staticmethod
    def _fallback_from_text(text: str) -> list[ToolCall]:
        if not text:
            return []
        match = _JSON_BLOB.search(text)
        if not match:
            return []
        try:
            blob = json.loads(match.group(0))
        except ValueError:
            return []
        name = blob.get("tool") or blob.get("name")
        if not name:
            return []
        args = blob.get("arguments") or blob.get("args") or {}
        return [ToolCall(id="call_0", name=name, arguments=args)]
