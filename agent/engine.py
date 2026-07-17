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
from brain.analyses import recall_analyses, save_analysis
from brain.audit import log_audit
from llm.base import Message
from logging_setup import get_logger

_log = get_logger("engine")


def _memory_context(conn, ticker: str | None) -> str | None:
    """Build a 'what I already know / how right I've been' block so the agent LEARNS from
    its own history. Best-effort: any failure returns None and the answer proceeds."""
    if not ticker:
        return None
    try:
        prior = recall_analyses(conn, ticker.upper(), limit=3)
    except Exception:  # noqa: BLE001 - memory is best-effort
        return None
    lines: list[str] = []
    if prior:
        lines.append(f"Your prior analyses of {ticker.upper()} (most recent first):")
        for a in prior:
            px = f" @ {a.price_at_time}" if a.price_at_time is not None else ""
            lines.append(f"- {a.created_at[:10]}: {a.verdict}{px} — {a.reasoning[:160]}")
    try:
        from brain.signals import track_record

        tr = track_record(conn, ticker.upper())
        if tr.get("total"):
            lines.append(
                f"Your track record on {ticker.upper()}: {tr['correct']}/{tr['total']} "
                f"past calls correct ({tr['accuracy']:.0%}). Calibrate confidence accordingly."
            )
    except Exception:  # noqa: BLE001
        pass
    return "\n".join(lines) if lines else None


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
    system = SYSTEM_PROMPT + "\n\n" + principles_summary()
    memory = _memory_context(conn, ticker)
    if memory:
        system += "\n\n## Your memory (learn from it)\n" + memory
    messages = [
        Message("system", system),
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

    # Never return an empty/no-op answer: nudge once, then fall back to a helpful default.
    if not (final_text or "").strip():
        messages.append(
            Message(
                "user",
                "Give a concise, useful answer now from the data gathered. If the question "
                "was broad, suggest 2-3 specific tickers or headlines with a one-line reason "
                "each. Do not reply with only a disclaimer.",
            )
        )
        try:
            final_text = llm.ask(messages) or ""
        except Exception:  # noqa: BLE001
            final_text = ""
    if not (final_text or "").strip():
        final_text = (
            "I couldn't gather enough live data to answer that just now. Try: a specific "
            "ticker (e.g. \"How's NVDA?\"), \"what's moving markets today?\", or "
            "\"find me cheap profitable stocks in an uptrend.\""
        )

    grounding = validate_grounding(final_text, citations)
    if not grounding.ok:
        flagged = ", ".join(str(u) for u in grounding.unsupported)
        final_text += f"\n\n⚠️ Unverified figure(s) not traced to data: {flagged}"

    text = _ensure_disclaimer(final_text)
    verdict = _detect_verdict(text)
    confidence = None

    # The enriched signal blob = every cited figure the agent gathered (technical trend,
    # events, social, macro, fundamentals). Price is pulled out so the learning loop can
    # later score this decision against realised price.
    signals_blob = {c.metric: c.value for c in citations}
    price = signals_blob.get("price")
    tkr = (ticker or "?").upper()

    save_analysis(
        conn,
        tkr,
        question,
        verdict,
        text,
        confidence,
        {**signals_blob, "grounded": grounding.ok, "unsupported": grounding.unsupported},
        price,
    )
    try:  # historical brain (Work-stream D) — never break the answer
        from brain.signals import save_signal_snapshot

        save_signal_snapshot(conn, tkr, signals_blob, price, source="agent")
    except Exception as e:  # noqa: BLE001
        _log.warning("signal snapshot save failed: %s", e)
    _audit(conn, "recommendation", tkr, question[:200], verdict)
    return AgentAnswer(
        text=text,
        verdict=verdict,
        confidence=confidence,
        citations=citations,
        grounded=grounding.ok,
        unsupported=grounding.unsupported,
    )
