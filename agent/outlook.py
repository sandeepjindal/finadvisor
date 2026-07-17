"""Industry / sector outlook — which industries are leading *right now*, ranked by the graded
trend of their sector/commodity ETF proxies (incl. AI/semis and commodities). Lets the
advisor answer "which industries can grow in this market?" with data, then overlay external
factors from scan_market_context. Reuses the Work-stream A graded trend.
"""

from __future__ import annotations

from dataclasses import dataclass

from agent.prompts import Citation
from data.market import Unavailable
from data.technicals import compute_indicators

# Curated industry / theme -> liquid ETF proxy. Covers the AI trend and commodities the user
# cares about; editable like the rest of the "skills" config.
INDUSTRY_ETFS = {
    "AI & Semiconductors": "SOXX",
    "Technology": "XLK",
    "Communication / Internet": "XLC",
    "Energy": "XLE",
    "Financials": "XLF",
    "Healthcare": "XLV",
    "Industrials": "XLI",
    "Consumer Discretionary": "XLY",
    "Utilities": "XLU",
    "Gold (commodity)": "GLD",
    "Oil (commodity)": "USO",
}


@dataclass
class IndustryRead:
    industry: str
    etf: str
    trend: str
    trend_strength: float | None
    above_200ma: bool | None


def industry_outlook(market, *, universe: dict | None = None) -> list[IndustryRead]:
    """Graded trend for each industry/commodity ETF, ranked strongest-first. Robust to
    missing data (an ETF with no history sinks to the bottom, never crashes)."""
    reads: list[IndustryRead] = []
    for industry, etf in (universe or INDUSTRY_ETFS).items():
        strength: float | None = None
        trend, above = "unknown", None
        try:
            hist = market.get_history(etf)
            if not isinstance(hist, Unavailable) and hist is not None:
                tech = compute_indicators(hist)
                strength, trend, above = (
                    tech.trend_strength,
                    tech.trend,
                    tech.above_200ma,
                )
        except Exception:  # noqa: BLE001 - each ETF is best-effort
            pass
        reads.append(IndustryRead(industry, etf, trend, strength, above))
    reads.sort(
        key=lambda r: r.trend_strength if r.trend_strength is not None else -9.0,
        reverse=True,
    )
    return reads


def outlook_citations(reads: list[IndustryRead]) -> list[Citation]:
    cites: list[Citation] = []
    for r in reads:
        if isinstance(r.trend_strength, (int, float)):
            cites.append(
                Citation(f"trend_strength:{r.etf}", round(r.trend_strength, 2), "computed", "now")
            )
    return cites


def format_outlook(reads: list[IndustryRead]) -> str:
    lines = ["🏭 **Industry outlook — trend leaders now** (ranked by sector/commodity ETF trend)"]
    for r in reads:
        st = r.trend_strength if isinstance(r.trend_strength, (int, float)) else None
        s = f"{st:+.2f}" if st is not None else "n/a"
        tag = "▲" if (st or 0) > 0.15 else ("▼" if (st or 0) < -0.15 else "→")
        lines.append(f"{tag} {r.industry} ({r.etf}): trend {r.trend}, strength {s}")
    lines.append("\n⚠️ Not financial advice.")
    return "\n".join(lines)
