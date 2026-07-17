"""Render an AgentAnswer for Discord and split long replies under the 2000-char limit.
Steps 1.9a + 1.9b.
"""

from __future__ import annotations

DISCORD_LIMIT = 2000

# Verdicts worth badging at the top; everything else (INFO, guides, chit-chat) reads as a
# plain conversational reply. Citations still power grounding internally but are NOT shown.
_ACTIONABLE = {
    "STRONG BUY", "BUY", "SELL", "STRONG SELL", "TRIM", "HOLD", "WATCH", "AVOID",
}


def format_answer(ans) -> str:
    text = ans.text
    verdict = (getattr(ans, "verdict", "") or "").upper()
    if verdict in _ACTIONABLE:
        return f"**{verdict}**\n\n{text}"
    return text


def chunk_message(text: str, limit: int = DISCORD_LIMIT) -> list[str]:
    """Split text into <=limit chunks on line boundaries (no mid-word breaks)."""
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    current = ""
    for line in text.split("\n"):
        # A single over-long line is hard-split as a last resort.
        while len(line) > limit:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(line[:limit])
            line = line[limit:]
        candidate = line if not current else current + "\n" + line
        if len(candidate) > limit:
            chunks.append(current)
            current = line
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks
