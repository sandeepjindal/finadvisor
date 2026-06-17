"""Exit Advisor — the core differentiator. Given a holding, weigh position, trend, RSI,
valuation, and the saved thesis to recommend HOLD / TRIM / SELL, classify the situation as
transient vs structural, suggest a concrete rule, and (on exit) a redeploy idea. Step 3.3.

Deterministic baseline (testable, no LLM required); an LLM layer can enrich later.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agent.prompts import Citation
from agent.redeploy import FundIdea, suggest_redeploy
from brain.analyses import recall_analyses
from data.market import Fundamentals, Quote, Unavailable
from data.technicals import compute_indicators


@dataclass
class ExitVerdict:
    ticker: str
    action: str  # HOLD | TRIM | SELL
    classification: str  # transient | structural | unknown
    gain_pct: float | None
    reasons: list[str] = field(default_factory=list)
    suggested_rule: str | None = None
    redeploy: list[FundIdea] = field(default_factory=list)
    confidence: float | None = None
    citations: list[Citation] = field(default_factory=list)


def evaluate_exit(holding, market, conn, rules) -> ExitVerdict:
    ticker = holding.ticker
    quote = market.get_quote(ticker)
    if isinstance(quote, Unavailable):
        return ExitVerdict(
            ticker,
            "HOLD",
            "unknown",
            None,
            reasons=["price data unavailable — cannot evaluate"],
        )
    assert isinstance(quote, Quote)
    price = quote.price
    gain_pct = (
        (price - holding.avg_cost) / holding.avg_cost * 100
        if holding.avg_cost
        else None
    )

    thresholds = rules.alert_thresholds
    overbought = thresholds.get("rsi_overbought", 70)
    trailing_pct = thresholds.get("trailing_stop_pct", 12.0)

    hist = market.get_history(ticker)
    trend, rsi, above_200 = "sideways", None, None
    if not isinstance(hist, Unavailable):
        tech = compute_indicators(hist)
        trend, rsi, above_200 = tech.trend, tech.rsi, tech.above_200ma

    f = market.get_fundamentals(ticker)
    pe = None if isinstance(f, Unavailable) else f.pe

    reasons: list[str] = []
    citations = [Citation("price", price, quote.source, quote.as_of)]
    score = 0  # higher => more exit pressure

    if above_200 is False:
        reasons.append("price below the 200-day MA (trend break)")
        score += 2
    if isinstance(rsi, (int, float)):
        citations.append(Citation("rsi", round(rsi, 1), "computed", "now"))
        if rsi > overbought:
            reasons.append(f"RSI {rsi:.0f} overbought")
            score += 1
    stretched = isinstance(pe, (int, float)) and pe > 40
    if stretched:
        citations.append(Citation("pe", pe, "yfinance", "now"))
        reasons.append(f"valuation stretched (P/E {pe:.0f})")
        score += 1

    # Thesis check from saved analyses (informational).
    past = recall_analyses(conn, ticker, limit=1)
    if past:
        reasons.append(f"prior view: {past[0].verdict} on {past[0].created_at[:10]}")

    if score >= 3:
        action = "SELL"
    elif score >= 1:
        action = "TRIM"
    else:
        action = "HOLD"
        reasons.append("trend intact, no exit trigger")

    classification = "structural" if above_200 is False else "transient"
    if action == "HOLD":
        classification = "transient"

    suggested_rule = f"set a trailing stop at {price * (1 - trailing_pct / 100):.2f} (-{trailing_pct:.0f}%)"
    redeploy = suggest_redeploy() if action in ("TRIM", "SELL") else []

    return ExitVerdict(
        ticker=ticker,
        action=action,
        classification=classification,
        gain_pct=gain_pct,
        reasons=reasons,
        suggested_rule=suggested_rule,
        redeploy=redeploy,
        confidence=None,
        citations=citations,
    )


def format_exit_verdict(v: ExitVerdict) -> str:
    gain = f"{v.gain_pct:+.1f}%" if v.gain_pct is not None else "n/a"
    lines = [f"📊 **{v.ticker} — {v.action}** ({v.classification}); P/L {gain}"]
    for r in v.reasons:
        lines.append(f"• {r}")
    if v.suggested_rule:
        lines.append(f"➡️ {v.suggested_rule}")
    if v.redeploy:
        ideas = ", ".join(f"{f.ticker} ({f.name})" for f in v.redeploy)
        lines.append(f"💡 Redeploy idea: {ideas}")
    lines.append("\n⚠️ Not financial advice.")
    return "\n".join(lines)
