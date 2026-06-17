"""Pluggable LLM provider interface + provider-neutral tool-calling contract.

The agent engine speaks only this interface, so swapping models (Groq -> Ollama ->
Claude -> ...) is a config change. Tool-calling is normalized here: providers translate
our neutral `ToolResultMessage`/`ToolCall` to/from their own wire shapes (the shapes
differ between Groq's OpenAI-style API and Ollama). Steps 0.3 + 0.3b.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class Message:
    """A chat message. `tool_calls` is set on assistant messages that requested tools;
    `tool_call_id`/`name` are set on tool-result messages."""

    role: str  # "system" | "user" | "assistant" | "tool"
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str | None = None
    name: str | None = None


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict  # JSON Schema


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class ToolCallResult:
    """Result of one `ask_with_tools` turn: either free text or a set of tool calls."""

    text: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)


@dataclass
class ToolResultMessage:
    """Neutral representation of a tool's output fed back to the model."""

    tool_call_id: str
    name: str
    content: str


class LLMProvider(ABC):
    @abstractmethod
    def ask(self, messages: list[Message]) -> str:
        """Return a plain-text completion."""

    @abstractmethod
    def ask_with_tools(
        self, messages: list[Message], tools: list[ToolSpec]
    ) -> ToolCallResult:
        """Return either text or tool calls for one turn."""

    @abstractmethod
    def to_provider_tool_result(self, msg: ToolResultMessage) -> dict:
        """Translate a neutral tool-result into this provider's message dict."""

    @abstractmethod
    def parse_tool_calls(self, raw_response) -> list[ToolCall]:
        """Parse this provider's raw response into neutral ToolCalls."""
