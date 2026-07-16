"""build_thesis — the full due-diligence synthesis (Work-stream E).

Composes the fundamental, analyst, ownership, valuation, growth, and technical pillars into
one grounded verdict. Two locked design choices (from review):

* **Confirmation-required verdict:** a confident BUY/SELL only when multiple independent
  pillars agree; when they conflict, we say "mixed signals" and lean HOLD/WATCH. One pillar
  never carries a strong call on its own.
* **Probabilistic range, not a point forecast:** we surface a bear/base/bull band (anchored
  on the analyst mean target when available) with calibrated confidence — never a single
  "price will be X" prediction.

Confidence is calibrated by the agent's own historical hit-rate on this ticker (Work-stream
D track record). Every pillar degrades gracefully to "unavailable" — the thesis is built
from whatever data is present and discloses what's missing, it never fabricates.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agent.prompts import Citation, wrap_untrusted
from data.market import Unavailable
from data.technicals import compute_indicators


@dataclass
class ThesisReport:
    ticker: str
    verdict: str  # STRONG BUY | BUY | HOLD | WATCH | SELL | STRONG SELL | INSUFFICIENT DATA
    confidence: float | None
    stance_by_pillar: dict = field(default_factory=dict)  # pillar -> +1/0/-1
    bullish: int = 0
    bearish: int = 0
    neutral: int = 0
    mixed: bool = False
    scenarios: dict = field(default_factory=dict)  # {bear, base, bull}
    reasons: list[str] = field(default_factory=list)
    unavailable: list[str] = field(default_factory=list)
    citations: list = field(default_factory=list)
    llm_rationale: str | None = None


def _stance_valuation(v) -> tuple[int, str]:
    verdict = getattr(v, "verdict", "unclear")
    if verdict == "cheap":
        return 1, "valuation looks cheap (PEG/PS/forward-P/E)"
    if verdict == "rich":
        return -1, "valuation looks rich"
    return 0, f"valuation {verdict}"


def _stance_financials(f) -> tuple[int, str]:
    cagr = getattr(f, "revenue_cagr", None)
    margin = getattr(f, "margin_direction", "flat")
    fcf_pos = getattr(f, "fcf_positive", None)
    if cagr is not None and cagr < 0 or margin == "deteriorating":
        return -1, "fundamentals weakening (falling revenue or margin compression)"
    if (cagr or 0) > 0.05 and margin != "deteriorating" and fcf_pos:
        return 1, "fundamentals improving (growing revenue, healthy margins/FCF)"
    return 0, "fundamentals mixed/flat"


def _stance_analyst(a) -> tuple[int, str]:
    consensus = getattr(a, "consensus", "Unknown")
    upside = getattr(a, "implied_upside_pct", None)
    up = f" ({upside:+.0f}% to mean target)" if isinstance(upside, (int, float)) else ""
    if consensus in ("Strong Buy", "Buy"):
        return 1, f"analysts lean {consensus}{up}"
    if consensus in ("Sell", "Strong Sell"):
        return -1, f"analysts lean {consensus}{up}"
    return 0, f"analyst consensus {consensus}{up}"


def _stance_growth(g) -> tuple[int, str]:
    eps = getattr(g, "eps_growth_next_year", None)
    rev = getattr(g, "revenue_growth_next_year", None)
    best = max([x for x in (eps, rev) if isinstance(x, (int, float))], default=None)
    if best is None:
        return 0, "forward growth unknown"
    if best > 0.10:
        return 1, f"forward growth solid (~{best*100:.0f}%)"
    if best < 0:
        return -1, "forward growth negative"
    return 0, f"forward growth modest (~{best*100:.0f}%)"


def _stance_ownership(o) -> tuple[int, str]:
    act = getattr(o, "insider_activity", "neutral")
    if act == "net buying":
        return 1, "insiders net buying (mild positive)"
    if act == "net selling":
        return -1, "insiders net selling (caution — note benign reasons exist)"
    return 0, "insider activity neutral"


def _stance_technical(strength, trend) -> tuple[int, str]:
    if trend == "up" or (isinstance(strength, (int, float)) and strength > 0.15):
        return 1, "price trend is up"
    if trend == "down" or (isinstance(strength, (int, float)) and strength < -0.15):
        return -1, "price trend is down"
    return 0, "price trend sideways"


def build_thesis(ticker, market, conn, *, llm=None) -> ThesisReport:
    from data.analyst import get_analyst_ratings, get_growth_estimates
    from data.financials import get_financial_trends
    from data.ownership import get_ownership
    from data.valuation import get_valuation_context
    from security.guards import validate_ticker

    t = validate_ticker(ticker)
    stance: dict[str, int] = {}
    reasons: list[str] = []
    unavailable: list[str] = []
    citations: list[Citation] = []

    def _run(pillar, fn, stance_fn):
        try:
            res = fn()
        except Exception:  # noqa: BLE001 - each pillar is best-effort
            res = None
        if res is None or isinstance(res, Unavailable):
            unavailable.append(pillar)
            return None
        s, why = stance_fn(res)
        stance[pillar] = s
        reasons.append(f"[{pillar}] {why}")
        return res

    val = _run("valuation", lambda: get_valuation_context(t), _stance_valuation)
    fin = _run("financials", lambda: get_financial_trends(t), _stance_financials)
    ana = _run("analyst", lambda: get_analyst_ratings(t, market), _stance_analyst)
    _run("growth", lambda: get_growth_estimates(t), _stance_growth)
    _run("ownership", lambda: get_ownership(t), _stance_ownership)

    # Technical pillar via the market facade + graded trend (Work-stream A).
    price = None
    try:
        q = market.get_quote(t)
        if not isinstance(q, Unavailable):
            price = q.price
            citations.append(Citation("price", price, q.source, q.as_of))
    except Exception:  # noqa: BLE001
        pass
    try:
        hist = market.get_history(t)
        if not isinstance(hist, Unavailable):
            tech = compute_indicators(hist)
            s, why = _stance_technical(tech.trend_strength, tech.trend)
            stance["technical"] = s
            reasons.append(f"[technical] {why}")
            if isinstance(tech.trend_strength, (int, float)):
                citations.append(
                    Citation("trend_strength", round(tech.trend_strength, 2), "computed", "now")
                )
        else:
            unavailable.append("technical")
    except Exception:  # noqa: BLE001
        unavailable.append("technical")

    # Analyst-target citation (feeds the base scenario).
    mean_target = getattr(ana, "mean_target", None) if ana else None
    if isinstance(mean_target, (int, float)):
        citations.append(Citation("mean_target", mean_target, "analyst", "now"))
    if ana is not None and isinstance(getattr(ana, "implied_upside_pct", None), (int, float)):
        citations.append(
            Citation("implied_upside_pct", round(ana.implied_upside_pct, 1), "analyst", "now")
        )

    bullish = sum(1 for s in stance.values() if s > 0)
    bearish = sum(1 for s in stance.values() if s < 0)
    neutral = sum(1 for s in stance.values() if s == 0)
    evaluated = len(stance)

    # --- Confirmation-required verdict -------------------------------------------------
    if evaluated < 2:
        verdict = "INSUFFICIENT DATA"
    elif bullish >= 4 and bearish == 0:
        verdict = "STRONG BUY"
    elif bullish >= 3 and bearish <= 1:
        verdict = "BUY"
    elif bearish >= 4 and bullish == 0:
        verdict = "STRONG SELL"
    elif bearish >= 3 and bullish <= 1:
        verdict = "SELL"
    elif bullish >= 2 and bearish >= 2:
        verdict = "WATCH"
    else:
        verdict = "HOLD"
    mixed = bullish >= 2 and bearish >= 2
    if mixed:
        reasons.insert(0, "⚠️ mixed signals — pillars disagree; leaning cautious")

    # --- Confidence, calibrated by the agent's own track record (Work-stream D) ---------
    confidence = None
    if evaluated:
        agreement = max(bullish, bearish) / evaluated  # 0..1
        calib = 0.7  # discount when we have no history to calibrate against
        try:
            from brain.signals import track_record

            tr = track_record(conn, t)
            if tr.get("total"):
                calib = 0.5 + 0.5 * tr["accuracy"]
                reasons.append(
                    f"[track record] {tr['correct']}/{tr['total']} past calls correct "
                    f"({tr['accuracy']:.0%}) — confidence calibrated to it"
                )
        except Exception:  # noqa: BLE001
            pass
        confidence = round(min(1.0, agreement * calib * (0.7 if mixed else 1.0)), 2)

    # --- Probabilistic bear / base / bull range (NOT a point forecast) ------------------
    scenarios: dict = {}
    anchor = mean_target if isinstance(mean_target, (int, float)) else price
    if isinstance(anchor, (int, float)) and anchor > 0:
        net = bullish - bearish
        base = anchor * (1 + 0.02 * net) if anchor is price else anchor
        spread = 0.20 if mixed else 0.13  # wider band when signals conflict
        scenarios = {
            "bear": round(base * (1 - spread), 2),
            "base": round(base, 2),
            "bull": round(base * (1 + spread), 2),
        }

    report = ThesisReport(
        ticker=t,
        verdict=verdict,
        confidence=confidence,
        stance_by_pillar=stance,
        bullish=bullish,
        bearish=bearish,
        neutral=neutral,
        mixed=mixed,
        scenarios=scenarios,
        reasons=reasons,
        unavailable=unavailable,
        citations=citations,
    )
    if llm is not None:
        report = enrich_thesis(report, llm)
    return report


_ENRICH_SYSTEM = (
    "You are an equity analyst. Given a deterministic multi-pillar verdict and its reasons, "
    "write ONE concise sentence summarizing the investment case and the single biggest risk. "
    "Do not invent numbers. Do not change the verdict."
)


def enrich_thesis(report: ThesisReport, llm) -> ThesisReport:
    """Best-effort one-sentence LLM synthesis over the deterministic thesis. No-op if llm is
    None or on any error; never changes the verdict (deterministic call is authoritative)."""
    if llm is None:
        return report
    try:
        from llm.base import Message

        body = (
            f"Ticker {report.ticker}: verdict {report.verdict} "
            f"(bullish {report.bullish}, bearish {report.bearish}).\n"
            + wrap_untrusted("\n".join(report.reasons))
        )
        resp = llm.ask([Message("system", _ENRICH_SYSTEM), Message("user", body)]) or ""
        report.llm_rationale = resp.strip() or None
    except Exception:  # noqa: BLE001 - enrichment is best-effort
        pass
    return report


def format_thesis(r: ThesisReport) -> str:
    conf = f"{r.confidence:.0%}" if r.confidence is not None else "n/a"
    lines = [f"🧭 **{r.ticker} — {r.verdict}** (confidence {conf})"]
    lines.append(f"pillars: {r.bullish} bullish / {r.bearish} bearish / {r.neutral} neutral")
    for why in r.reasons:
        lines.append(f"• {why}")
    if r.scenarios:
        s = r.scenarios
        lines.append(
            f"📊 12-mo range (not a forecast): bear {s['bear']} / base {s['base']} / bull {s['bull']}"
        )
    if r.unavailable:
        lines.append(f"(no data for: {', '.join(r.unavailable)})")
    if r.llm_rationale:
        lines.append(f"🧠 {r.llm_rationale}")
    lines.append("\n⚠️ Not financial advice.")
    return "\n".join(lines)
