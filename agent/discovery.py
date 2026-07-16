"""Natural-language stock screener / discovery over a small liquid universe (Work-stream G3).

Given simple criteria (either a parsed dict or free text), screen the universe by
fundamentals + technicals, filter out the misses, rank survivors by composite score,
and explain why each matched. Deterministic and network-free — the ``market`` facade
fetches (a fake in tests). Every read is ``Unavailable``-aware.

Supported criteria keys:
  - ``max_pe``: float           — keep only P/E <= max_pe (needs a real P/E)
  - ``min_trend_strength``: float — keep only graded trend_strength >= threshold
  - ``trend``: "up"             — require the coarse trend label to match
  - ``min_profit_margin``: float — keep only profit_margin >= threshold
  - ``overbought_ok``: bool     — if False (default), drop names with RSI > overbought
"""

from __future__ import annotations

from agent.knowledge import load_rules
from agent.screener import score_ticker
from data.market import Fundamentals, Unavailable
from data.technicals import compute_indicators
from security.guards import validate_ticker

_DISCLAIMER = "⚠️ Not financial advice."

# A small, liquid, well-known default universe (kept short so tests/offline runs are cheap).
DEFAULT_UNIVERSE = [
    "AAPL",
    "MSFT",
    "NVDA",
    "GOOGL",
    "AMZN",
    "META",
    "JPM",
    "XOM",
    "JNJ",
    "WMT",
]

_CHEAP_PE = 20.0


def _num(x):
    return x if isinstance(x, (int, float)) else None


def parse_criteria(text: str) -> dict:
    """Light, deterministic NL -> criteria mapping. Unknown words are ignored.

    "cheap"/"undervalued"      -> max_pe ~ 20
    "uptrend"/"trending up"    -> trend="up" & min_trend_strength > 0
    "profitable"               -> min_profit_margin > 0
    """
    t = (text or "").lower()
    criteria: dict = {}

    if any(w in t for w in ("cheap", "undervalued", "value", "low p/e", "low pe")):
        criteria["max_pe"] = _CHEAP_PE

    if any(
        w in t
        for w in ("uptrend", "up trend", "trending up", "trend up", "momentum", "bullish")
    ):
        criteria["trend"] = "up"
        criteria["min_trend_strength"] = 0.0

    if any(w in t for w in ("profitable", "profit", "high margin", "margins")):
        criteria["min_profit_margin"] = 0.0

    return criteria


def _evaluate(ticker: str, market, rules) -> dict | None:
    """Fetch fundamentals + technicals for one validated ticker; None if nothing usable."""
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
        except Exception:  # noqa: BLE001
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
        "pe": pe,
        "profit_margin": profit_margin,
        "trend": trend,
        "trend_strength": trend_strength,
        "rsi": rsi,
        "composite": score.composite,
    }


def _matches(data: dict, criteria: dict, overbought: float) -> tuple[bool, list[str]]:
    """Apply criteria; return (passed, reasons). A missing datum required by a filter
    fails that filter (we don't fabricate)."""
    reasons: list[str] = []

    if "max_pe" in criteria:
        pe = data["pe"]
        if pe is None or pe > criteria["max_pe"]:
            return False, reasons
        reasons.append(f"P/E {pe:.1f} <= {criteria['max_pe']:g}")

    if "trend" in criteria:
        if data["trend"] != criteria["trend"]:
            return False, reasons
        reasons.append(f"trend {data['trend']}")

    if "min_trend_strength" in criteria:
        ts = data["trend_strength"]
        if ts is None or ts < criteria["min_trend_strength"]:
            return False, reasons
        reasons.append(f"trend_strength {ts:+.2f} >= {criteria['min_trend_strength']:g}")

    if "min_profit_margin" in criteria:
        pm = data["profit_margin"]
        if pm is None or pm < criteria["min_profit_margin"]:
            return False, reasons
        reasons.append(f"margin {pm:.0%} >= {criteria['min_profit_margin']:g}")

    if not criteria.get("overbought_ok", False):
        rsi = data["rsi"]
        if isinstance(rsi, (int, float)) and rsi > overbought:
            return False, reasons

    return True, reasons


def discover_stocks(
    criteria: dict,
    market,
    *,
    universe=None,
    rules=None,
    limit: int = 5,
) -> dict:
    """Screen ``universe`` by ``criteria``, rank matches by composite, return top ``limit``."""
    rules = rules or load_rules()
    overbought = rules.alert_thresholds.get("rsi_overbought", 70)
    criteria = dict(criteria or {})

    tickers = universe if universe is not None else DEFAULT_UNIVERSE

    matches: list[dict] = []
    for raw in tickers:
        try:
            t = validate_ticker(raw)
        except ValueError:
            continue
        data = _evaluate(t, market, rules)
        if data is None:
            continue
        ok, reasons = _matches(data, criteria, overbought)
        if not ok:
            continue
        matches.append(
            {
                "ticker": t,
                "pe": data["pe"],
                "trend": data["trend"],
                "composite": data["composite"],
                "why": "; ".join(reasons) if reasons else "meets all criteria",
            }
        )

    matches.sort(key=lambda m: m["composite"], reverse=True)
    return {
        "matches": matches[: max(0, limit)],
        "criteria_used": criteria,
    }


def format_discovery(result: dict) -> str:
    """Ranked list with each match's reason + disclaimer."""
    matches = result.get("matches", [])
    criteria = result.get("criteria_used", {})
    lines = []
    if criteria:
        crit = ", ".join(f"{k}={v}" for k, v in criteria.items())
        lines.append(f"Discovery (criteria: {crit}):")
    else:
        lines.append("Discovery (no criteria — ranked by composite):")

    if not matches:
        lines.append("(no matches)")
    else:
        for i, m in enumerate(matches, 1):
            pe = f"{m['pe']:.1f}" if isinstance(m["pe"], (int, float)) else "n/a"
            lines.append(
                f"{i}. {m['ticker']} — score {m['composite']:.2f}, P/E {pe}, "
                f"trend {m['trend']} ({m['why']})"
            )

    lines.append("")
    lines.append(_DISCLAIMER)
    return "\n".join(lines)
