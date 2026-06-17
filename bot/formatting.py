"""Render an AgentAnswer for Discord and split long replies under the 2000-char limit.
Steps 1.9a + 1.9b.
"""

from __future__ import annotations

DISCORD_LIMIT = 2000


def format_answer(ans) -> str:
    parts = [f"**{ans.verdict}**", "", ans.text]
    if ans.citations:
        parts.append("")
        parts.append("_Sources:_")
        seen = set()
        for c in ans.citations:
            key = (c.metric, c.source)
            if key in seen:
                continue
            seen.add(key)
            parts.append(f"• {c.metric} = {c.value} [{c.source}]")
    return "\n".join(parts)


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
