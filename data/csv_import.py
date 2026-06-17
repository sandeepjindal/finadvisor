"""Import holdings from a broker CSV export (read-only file, never credentials). Tolerant
of common column-name variants; skips malformed rows. Step 3.2b.
"""

from __future__ import annotations

import csv
import io

from security.guards import validate_ticker

_TICKER_KEYS = ("ticker", "symbol", "stock")
_SHARES_KEYS = ("shares", "quantity", "qty", "units")
_COST_KEYS = ("avg_cost", "cost", "average cost", "avg price", "price", "cost basis")


def _pick(row: dict, keys) -> str | None:
    lower = {k.lower().strip(): v for k, v in row.items() if k}
    for k in keys:
        if k in lower and lower[k] not in (None, ""):
            return lower[k]
    return None


def import_holdings_csv(content: str) -> list[tuple[str, float, float]]:
    out: list[tuple[str, float, float]] = []
    reader = csv.DictReader(io.StringIO(content))
    for row in reader:
        raw_ticker = _pick(row, _TICKER_KEYS)
        raw_shares = _pick(row, _SHARES_KEYS)
        raw_cost = _pick(row, _COST_KEYS)
        if not (raw_ticker and raw_shares and raw_cost):
            continue
        try:
            ticker = validate_ticker(raw_ticker)
            shares = float(str(raw_shares).replace(",", ""))
            cost = float(str(raw_cost).replace("$", "").replace(",", ""))
        except ValueError:
            continue
        out.append((ticker, shares, cost))
    return out
