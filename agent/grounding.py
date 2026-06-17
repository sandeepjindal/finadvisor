"""Programmatic number-grounding (C1): every financial figure in the final answer must
trace to a tool-output Citation, else it is flagged. Prevents hallucinated prices/ratios.
Step 1.8.

Heuristic: structural integers (years, MA windows like 50/200, percentages, counts) are
ignored to keep the check precise; non-integer figures (prices, ratios) must match a
citation within tolerance. This is a v1 tradeoff — large fabricated integers can slip
through; Phase 4 can strengthen.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_NUM_RE = re.compile(r"[-+]?\$?\d[\d,]*(?:\.\d+)?%?")


@dataclass
class GroundingResult:
    ok: bool
    unsupported: list[float] = field(default_factory=list)
    supported: list[float] = field(default_factory=list)


def extract_numeric_tokens(text: str) -> set[float]:
    out: set[float] = set()
    for m in _NUM_RE.findall(text or ""):
        s = m.strip().lstrip("$").rstrip("%").replace(",", "")
        try:
            out.add(float(s))
        except ValueError:
            pass
    return out


def _is_integer(x: float) -> bool:
    return float(x).is_integer()


def validate_grounding(
    answer_text: str,
    citations,
    rel_tol: float = 1e-3,
    ignore=None,
) -> GroundingResult:
    ignore_set = {float(i) for i in (ignore or ())}
    cite_vals: list[float] = []
    for c in citations or []:
        try:
            cite_vals.append(float(c.value))
        except (TypeError, ValueError):
            pass

    unsupported: list[float] = []
    supported: list[float] = []
    for n in extract_numeric_tokens(answer_text):
        if n in ignore_set or _is_integer(n):
            supported.append(n)
            continue
        if any(abs(n - cv) <= rel_tol * max(abs(n), abs(cv), 1.0) for cv in cite_vals):
            supported.append(n)
        else:
            unsupported.append(n)
    return GroundingResult(
        ok=not unsupported, unsupported=unsupported, supported=supported
    )
