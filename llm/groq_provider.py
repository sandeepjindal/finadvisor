"""Groq provider — free, fast, open models (Llama/Qwen). OpenAI-style tool calling.

The client is created lazily so importing this module (and unit tests) needs no API key
or network. Step 0.4.
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


# Matches Groq/Llama's malformed tool syntax, e.g.
#   <function=assess_exit[]{"ticker": "NVDA"}</function>
_FAILED_FN_RE = re.compile(
    r"<function=([A-Za-z_][\w-]*)[^{>]*?(\{.*?\})\s*</function>", re.DOTALL
)


def _error_text(e) -> str:
    parts = [str(e)]
    body = getattr(e, "body", None)
    if isinstance(body, dict):
        fg = body.get("error", {}).get("failed_generation")
        if fg:
            parts.append(fg)
    return "\n".join(p for p in parts if p)


def _recover_tool_calls_from_error(e) -> list[ToolCall]:
    """Best-effort: pull the intended tool call(s) out of a Groq `tool_use_failed` error."""
    text = _error_text(e)
    calls: list[ToolCall] = []
    for i, m in enumerate(_FAILED_FN_RE.finditer(text)):
        name = m.group(1)
        try:
            args = json.loads(m.group(2))
        except ValueError:
            args = {}
        calls.append(ToolCall(id=f"recovered_{i}", name=name, arguments=args))
    return calls


class GroqProvider(LLMProvider):
    def __init__(self, api_key: str | None, model: str = "llama-3.3-70b-versatile"):
        self._api_key = api_key
        self._model = model
        self._client = None

    @property
    def client(self):
        if self._client is None:
            from groq import Groq

            self._client = Groq(api_key=self._api_key)
        return self._client

    # --- message translation ---
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
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.name,
                                    "arguments": json.dumps(tc.arguments),
                                },
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

    # --- interface ---
    def ask(self, messages: list[Message]) -> str:
        resp = self.client.chat.completions.create(
            model=self._model, messages=self._to_messages(messages)
        )
        return resp.choices[0].message.content or ""

    def ask_with_tools(
        self, messages: list[Message], tools: list[ToolSpec]
    ) -> ToolCallResult:
        try:
            resp = self.client.chat.completions.create(
                model=self._model,
                messages=self._to_messages(messages),
                tools=self._to_tools(tools),
                tool_choice="auto",
            )
        except Exception as e:  # noqa: BLE001
            # Groq/Llama sometimes emits a malformed tool call and the API 400s with
            # `tool_use_failed`. Recover the intended call from the error; else fall back
            # to a plain (tool-less) answer so the user is never blocked.
            recovered = _recover_tool_calls_from_error(e)
            if recovered:
                return ToolCallResult(text=None, tool_calls=recovered)
            return ToolCallResult(text=self.ask(messages), tool_calls=[])
        calls = self.parse_tool_calls(resp)
        text = resp.choices[0].message.content
        return ToolCallResult(text=text, tool_calls=calls)

    def to_provider_tool_result(self, msg: ToolResultMessage) -> dict:
        return {
            "role": "tool",
            "tool_call_id": msg.tool_call_id,
            "name": msg.name,
            "content": msg.content,
        }

    def parse_tool_calls(self, raw_response) -> list[ToolCall]:
        message = raw_response.choices[0].message
        raw_calls = getattr(message, "tool_calls", None) or []
        calls: list[ToolCall] = []
        for tc in raw_calls:
            args = tc.function.arguments
            if isinstance(args, str):
                args = json.loads(args or "{}")
            calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))
        return calls
