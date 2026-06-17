"""Capital-redeployment ideas — a curated set of low-cost index/ETF options by risk
posture. Advisory only. Step 3.4.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FundIdea:
    ticker: str
    name: str
    avg_annual_return: float  # rough long-run, decimal
    expense_ratio: float
    note: str


_FUNDS = {
    "VOO": FundIdea("VOO", "Vanguard S&P 500", 0.13, 0.0003, "broad US large-cap core"),
    "VTI": FundIdea(
        "VTI", "Vanguard Total US Market", 0.12, 0.0003, "total-market core"
    ),
    "QQQ": FundIdea("QQQ", "Invesco Nasdaq-100", 0.17, 0.0020, "growth/tech tilt"),
    "SCHD": FundIdea("SCHD", "Schwab US Dividend", 0.11, 0.0006, "dividend/defensive"),
}


def suggest_redeploy(
    amount: float | None = None, risk: str = "balanced"
) -> list[FundIdea]:
    risk = (risk or "balanced").lower()
    if risk == "growth":
        picks = ["QQQ", "VTI"]
    elif risk == "defensive":
        picks = ["SCHD", "VOO"]
    else:
        picks = ["VOO", "VTI"]
    return [_FUNDS[p] for p in picks]
