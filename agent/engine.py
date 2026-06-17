"""The tool-calling agent loop with grounding enforcement. Step 1.9 (+ audit 3.6).

Loop: ask -> if tool calls, execute (collecting citations) and feed results back via the
provider-neutral contract -> repeat until a final answer or the iteration cap. Before
returning, every numeric figure is grounding-checked against collected citations; any
unsupported figure is flagged (never silently emitted). The result is saved to the brain.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from agent.grounding import validate_grounding
from agent.knowledge import principles_summary
from agent.prompts import SYSTEM_PROMPT
from brain.analyses import save_analysis
from brain.audit import log_audit
from llm.base import Message
from logging_setup import get_logger

_log = get_logger("engine")


def _audit(conn, action, tool, args, summary):
    try:
        log_audit(conn, "agent", action, tool, args, summary)
    except Exception as e:  # noqa: BLE001 - audit must never break the answer
        _log.warning("audit log failed: %s", e)


_DISCLAIMER = "⚠️ Not financial advice."
_VERDICT_RE = re.compile(
    r"\b(STRONG BUY|BUY|SELL|TRIM|HOLD|AVOID|WATCH)\b", re.IGNORECASE
)


@dataclass
class AgentAnswer:
    text: str
    verdict: str
    confidence: float | None
    citations: list = field(default_factory=list)
    grounded: bool = True
    unsupported: list = field(default_factory=list)


def _detect_verdict(text: str) -> str:
    m = _VERDICT_RE.search(text)
    return m.group(1).upper() if m else "INFO"


def _ensure_disclaimer(text: str) -> str:
    return (
        text if "not financial advice" in text.lower() else f"{text}\n\n{_DISCLAIMER}"
    )


def answer(
    question: str,
    conn,
    llm,
    tools,
    max_iters: int = 6,
    ticker: str | None = None,
) -> AgentAnswer:
    messages = [
        Message("system", SYSTEM_PROMPT + "\n\n" + principles_summary()),
        Message("user", question),
    ]
    citations: list = []
    final_text: str | None = None

    for _ in range(max_iters):
        res = llm.ask_with_tools(messages, tools.specs)
        if res.tool_calls:
            messages.append(
                Message("assistant", res.text or "", tool_calls=res.tool_calls)
            )
            for call in res.tool_calls:
                out = tools.call(call.name, call.arguments)
                citations.extend(out.citations)
                _audit(
                    conn,
                    "tool_call",
                    call.name,
                    json.dumps(call.arguments),
                    out.text[:200],
                )
                messages.append(
                    Message("tool", out.text, tool_call_id=call.id, name=call.name)
                )
            continue
        final_text = res.text or ""
        break

    if final_text is None:
        # Iteration cap hit — force a final answer without further tool calls.
        final_text = llm.ask(messages)

    grounding = validate_grounding(final_text, citations)
    if not grounding.ok:
        flagged = ", ".join(str(u) for u in grounding.unsupported)
        final_text += f"\n\n⚠️ Unverified figure(s) not traced to data: {flagged}"

    text = _ensure_disclaimer(final_text)
    verdict = _detect_verdict(text)
    confidence = None

    save_analysis(
        conn,
        (ticker or "?").upper(),
        question,
        verdict,
        text,
        confidence,
        {"grounded": grounding.ok, "unsupported": grounding.unsupported},
        None,
    )
    _audit(conn, "recommendation", (ticker or "?").upper(), question[:200], verdict)
    return AgentAnswer(
        text=text,
        verdict=verdict,
        confidence=confidence,
        citations=citations,
        grounded=grounding.ok,
        unsupported=grounding.unsupported,
    )
