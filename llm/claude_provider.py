"""Claude (Anthropic) provider — high quality, high limits (paid). Anthropic Messages API
tool-calling, normalized to our provider-neutral contract.

The client is created lazily so importing this module (and unit tests) needs no API key or
network, and the `anthropic` SDK ([claude] extra) is imported only when actually used.

Anthropic differs from the OpenAI/Groq wire shape in three ways this adapter handles:
  1. the system prompt is a top-level `system` param, not a message with role "system";
  2. tool calls/results are CONTENT BLOCKS (`tool_use` / `tool_result`), not a separate
     `tool_calls` field; and
  3. all tool results for one assistant turn must arrive in a SINGLE following user message.
Default model is `claude-opus-4-8` (override via CLAUDE_MODEL). Note: on Opus 4.8 the
`temperature`/`top_p`/`top_k` params are rejected, so we never send them.
"""

from __future__ import annotations

from llm.base import (
    LLMProvider,
    Message,
    ToolCall,
    ToolCallResult,
    ToolResultMessage,
    ToolSpec,
)

_DEFAULT_MODEL = "claude-opus-4-8"
_DEFAULT_MAX_TOKENS = 4096


class ClaudeProvider(LLMProvider):
    def __init__(
        self,
        api_key: str | None,
        model: str = _DEFAULT_MODEL,
        max_tokens: int = _DEFAULT_MAX_TOKENS,
    ):
        self._api_key = api_key
        self._model = model
        self._max_tokens = max_tokens
        self._client = None

    @property
    def client(self):
        if self._client is None:
            import anthropic

            # No explicit key → let the SDK resolve ambient credentials: ANTHROPIC_API_KEY,
            # ANTHROPIC_AUTH_TOKEN, or an `ant auth login` OAuth profile on the machine. A
            # bare Anthropic() works when the Claude CLI is already authenticated.
            self._client = (
                anthropic.Anthropic(api_key=self._api_key)
                if self._api_key
                else anthropic.Anthropic()
            )
        return self._client

    # --- message translation to the Anthropic Messages shape ---
    def _split(self, messages: list[Message]) -> tuple[str, list[dict]]:
        """Return (system_prompt, anthropic_messages). System messages are pulled out; a run
        of tool-result messages is merged into one user turn (Anthropic requires that)."""
        system_parts: list[str] = []
        out: list[dict] = []
        pending_tool_results: list[dict] = []

        def flush_tools():
            if pending_tool_results:
                out.append({"role": "user", "content": list(pending_tool_results)})
                pending_tool_results.clear()

        for m in messages:
            if m.role == "system":
                if m.content:
                    system_parts.append(m.content)
                continue
            if m.role == "tool":
                pending_tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": m.tool_call_id or "",
                        "content": m.content or "",
                    }
                )
                continue
            flush_tools()  # a non-tool turn closes any pending tool-result batch
            if m.role == "assistant" and m.tool_calls:
                content: list[dict] = []
                if m.content:
                    content.append({"type": "text", "text": m.content})
                for tc in m.tool_calls:
                    content.append(
                        {
                            "type": "tool_use",
                            "id": tc.id,
                            "name": tc.name,
                            "input": tc.arguments or {},
                        }
                    )
                out.append({"role": "assistant", "content": content})
            else:
                out.append({"role": m.role, "content": m.content or ""})
        flush_tools()
        return "\n\n".join(system_parts), out

    @staticmethod
    def _to_tools(tools: list[ToolSpec]) -> list[dict]:
        return [
            {"name": t.name, "description": t.description, "input_schema": t.parameters}
            for t in tools
        ]

    def _create(self, messages: list[Message], tools: list[ToolSpec] | None = None):
        system, msgs = self._split(messages)
        kwargs: dict = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "messages": msgs,
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = self._to_tools(tools)
        return self.client.messages.create(**kwargs)

    @staticmethod
    def _text(resp) -> str:
        return "".join(
            b.text for b in resp.content if getattr(b, "type", None) == "text"
        )

    # --- interface ---
    def ask(self, messages: list[Message]) -> str:
        return self._text(self._create(messages))

    def ask_with_tools(
        self, messages: list[Message], tools: list[ToolSpec]
    ) -> ToolCallResult:
        resp = self._create(messages, tools)
        calls = self.parse_tool_calls(resp)
        text = self._text(resp)
        return ToolCallResult(text=text or None, tool_calls=calls)

    def to_provider_tool_result(self, msg: ToolResultMessage) -> dict:
        return {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": msg.tool_call_id,
                    "content": msg.content,
                }
            ],
        }

    def parse_tool_calls(self, raw_response) -> list[ToolCall]:
        calls: list[ToolCall] = []
        for b in raw_response.content:
            if getattr(b, "type", None) == "tool_use":
                calls.append(ToolCall(id=b.id, name=b.name, arguments=b.input or {}))
        return calls
