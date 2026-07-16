"""Side-by-side comparison of 2..5 tickers (Work-stream G2).

Gathers price, valuation, a graded trend read and a composite score for each ticker,
ranks them best->worst, and renders a compact table-ish summary. Every field is
``Unavailable``-aware (degrades to ``None``); no network here — the ``market`` facade
does the fetching (and in tests is a fake). Composite scoring reuses ``score_ticker``.
"""

from __future__ import annotations

from agent.knowledge import load_rules
from agent.screener import score_ticker
from data.market import Fundamentals, Quote, Unavailable
from data.technicals import compute_indicators
from security.guards import validate_ticker

MIN_TICKERS = 2
MAX_TICKERS = 5
_DISCLAIMER = "⚠️ Not financial advice."


def _num(x):
    return x if isinstance(x, (int, float)) else None


def _gather(ticker: str, market, rules) -> dict:
    """Fetch price/PE/trend for one already-validated ticker; None on Unavailable."""
    quote = market.get_quote(ticker)
    price = quote.price if isinstance(quote, Quote) else None

    fund = market.get_fundamentals(ticker)
    pe = _num(fund.pe) if isinstance(fund, Fundamentals) else None
    profit_margin = _num(fund.profit_margin) if isinstance(fund, Fundamentals) else None

    trend = "sideways"
    trend_strength = None
    rsi = None
    hist = market.get_history(ticker)
    if not isinstance(hist, Unavailable):
        try:
            tech = compute_indicators(hist)
            trend = tech.trend
            trend_strength = tech.trend_strength
            rsi = tech.rsi
        except Exception:  # noqa: BLE001 - a bad frame must not sink the whole compare
            pass

    score = score_ticker(
        ticker,
        trend=trend,
        rsi=rsi,
        pe=pe,
        profit_margin=profit_margin,
        sentiment=None,
        rules=rules,
        trend_strength=trend_strength,
    )
    return {
        "ticker": ticker,
        "price": price,
        "pe": pe,
        "trend": trend,
        "trend_strength": trend_strength,
        "composite": score.composite,
    }


def compare_tickers(tickers: list[str], market, *, rules=None) -> dict:
    """Compare 2..5 tickers. Returns rows, a best->worst ranking, a takeaway, citations."""
    validated: list[str] = []
    for t in tickers or []:
        validated.append(validate_ticker(t))
    # De-dupe while preserving order.
    seen: set[str] = set()
    validated = [t for t in validated if not (t in seen or seen.add(t))]

    if not (MIN_TICKERS <= len(validated) <= MAX_TICKERS):
        raise ValueError(
            f"compare_tickers expects {MIN_TICKERS}..{MAX_TICKERS} distinct tickers, "
            f"got {len(validated)}"
        )

    rules = rules or load_rules()
    rows = [_gather(t, market, rules) for t in validated]

    ranked_rows = sorted(rows, key=lambda r: r["composite"], reverse=True)
    ranked = [r["ticker"] for r in ranked_rows]

    if ranked:
        best = ranked_rows[0]
        takeaway = (
            f"{best['ticker']} ranks highest (composite {best['composite']:.2f}, "
            f"trend {best['trend']})"
        )
        if len(ranked) > 1:
            takeaway += f"; {ranked_rows[-1]['ticker']} ranks lowest."
    else:
        takeaway = "No tickers to compare."

    return {
        "rows": rows,
        "ranked": ranked,
        "takeaway": takeaway,
        "citations": [],
    }


def _fmt(x, kind: str = "num") -> str:
    if x is None:
        return "n/a"
    if kind == "price":
        return f"{x:,.2f}"
    if kind == "pe":
        return f"{x:.1f}"
    if kind == "strength":
        return f"{x:+.2f}"
    return f"{x:.2f}"


def format_compare(result: dict) -> str:
    """Compact table-ish summary + ranked takeaway + disclaimer."""
    rows = result.get("rows", [])
    header = f"{'TICKER':<8}{'PRICE':>12}{'P/E':>8}{'TREND':>10}{'SCORE':>8}"
    lines = ["Comparison:", header, "-" * len(header)]
    # Render in ranked order for readability.
    by_ticker = {r["ticker"]: r for r in rows}
    ordered = [by_ticker[t] for t in result.get("ranked", []) if t in by_ticker]
    for r in ordered:
        lines.append(
            f"{r['ticker']:<8}"
            f"{_fmt(r['price'], 'price'):>12}"
            f"{_fmt(r['pe'], 'pe'):>8}"
            f"{str(r['trend']):>10}"
            f"{_fmt(r['composite']):>8}"
        )
    ranked = result.get("ranked", [])
    if ranked:
        lines.append("")
        lines.append("Ranked (best->worst): " + " > ".join(ranked))
    lines.append(result.get("takeaway", ""))
    lines.append("")
    lines.append(_DISCLAIMER)
    return "\n".join(lines)
