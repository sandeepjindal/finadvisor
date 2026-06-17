"""Privacy-mode routing (deterministic, pre-LLM): when PRIVACY_MODE=local, portfolio-
related prompts go to the local Ollama provider so holdings never leave the machine —
decided BEFORE any provider is called. Step 4.6.
"""

from __future__ import annotations

import re

_PORTFOLIO_RE = re.compile(
    r"\b(my portfolio|my holdings|i own|i hold|i bought|should i (sell|hold|trim)|/portfolio)\b",
    re.IGNORECASE,
)


def is_portfolio_related(text: str, held_tickers) -> bool:
    if _PORTFOLIO_RE.search(text or ""):
        return True
    up = (text or "").upper()
    return any(t and t in up for t in held_tickers)


def select_provider(text, held_tickers, privacy_mode, default_llm, local_llm):
    if privacy_mode == "local" and is_portfolio_related(text, held_tickers):
        return local_llm
    return default_llm
