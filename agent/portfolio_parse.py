"""Parse natural-language holdings like "I own 30 NVDA at $450, 50 VOO at 400". Step 3.2."""

from __future__ import annotations

import re

from security.guards import validate_ticker

# <shares> <TICKER> [shares] (at|@) [$]<price>
_PATTERN = re.compile(
    r"(\d+(?:\.\d+)?)\s+([A-Za-z][A-Za-z.\-]{0,5})\s*(?:shares?\s*)?(?:at|@)\s*\$?(\d+(?:\.\d+)?)",
    re.IGNORECASE,
)


def parse_holdings_nl(text: str) -> list[tuple[str, float, float]]:
    out: list[tuple[str, float, float]] = []
    for m in _PATTERN.finditer(text or ""):
        shares, raw_ticker, price = m.group(1), m.group(2), m.group(3)
        try:
            ticker = validate_ticker(raw_ticker)
        except ValueError:
            continue
        out.append((ticker, float(shares), float(price)))
    return out
