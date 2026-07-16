"""Portfolio-level analytics (Work-stream G1): value/weights, concentration vs the
configured max position weight, sector exposure, pairwise-return correlation flags,
portfolio beta vs a benchmark, and a 0..1 diversification score.

Everything is ``Unavailable``-aware and degrades to ``None`` rather than crashing:
a missing quote drops that position from the book, a missing history drops that name
from the correlation/beta math, and a missing benchmark leaves ``portfolio_beta`` at
``None``. Only real, tool-returned numbers are cited. Reads holdings via
``brain.holdings.list_holdings`` and prices/sectors/history via the ``data.market`` facade.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field

import pandas as pd

from agent.prompts import Citation
from data.market import Quote, Unavailable

_CORR_FLAG = 0.8  # pairwise daily-return correlation above this is flagged as redundant
_MIN_RETURNS = 30  # minimum overlapping daily returns to trust a correlation/beta number


@dataclass
class PortfolioReport:
    total_value: float
    positions: list[dict]
    concentration: dict
    sector_exposure: dict
    correlation_flags: list[str]
    portfolio_beta: float | None
    diversification_score: float | None
    reasons: list[str]
    citations: list = field(default_factory=list)


def _close_series(hist) -> pd.Series | None:
    """Extract a float Close series from a history frame, or None if unusable."""
    if hist is None or isinstance(hist, Unavailable):
        return None
    try:
        for name in ("Close", "close", "Adj Close"):
            if name in hist.columns:
                s = hist[name].astype(float)
                return s if len(s) else None
    except Exception:  # noqa: BLE001 - anything non-frame-like -> unusable
        return None
    return None


def _daily_returns(hist) -> pd.Series | None:
    s = _close_series(hist)
    if s is None or len(s) < 2:
        return None
    r = s.pct_change().dropna()
    return r if len(r) else None


def _diversification_score(
    weights: list[float],
    sector_exposure: dict,
    avg_corr: float | None,
) -> float | None:
    """Blend three 0..1 signals — spread of position weights (Herfindahl), spread of
    sector weights, and (1 - average pairwise correlation) — into a single 0..1 score.
    More positions, more sectors, and lower correlation all push it up.
    """
    comps: list[float] = []
    if weights:
        # 1 - HHI: 0 for a single/dominant name, -> 1 for many equal weights.
        comps.append(1.0 - sum(w * w for w in weights))
    if sector_exposure:
        total = sum(sector_exposure.values())
        if total > 0:
            sw = [v / total for v in sector_exposure.values()]
            comps.append(1.0 - sum(w * w for w in sw))
    if avg_corr is not None:
        comps.append(max(0.0, min(1.0, 1.0 - avg_corr)))
    if not comps:
        return None
    return round(sum(comps) / len(comps), 3)


def analyze_portfolio(conn, market, *, rules=None, benchmark: str = "SPY") -> PortfolioReport:
    """Analyze the whole book held in ``conn`` using the ``market`` facade.

    Positions whose quote is ``Unavailable`` are skipped (with a reason). Correlation
    and beta use daily returns from ``get_history``; names without history are simply
    omitted from that math. Never raises on missing/partial data.
    """
    from brain.holdings import list_holdings

    max_weight = None
    if rules is not None:
        max_weight = getattr(rules, "max_position_weight", None)

    holdings = list_holdings(conn)
    reasons: list[str] = []
    citations: list[Citation] = []

    if not holdings:
        return PortfolioReport(
            total_value=0.0,
            positions=[],
            concentration={},
            sector_exposure={},
            correlation_flags=[],
            portfolio_beta=None,
            diversification_score=None,
            reasons=["No holdings in portfolio; nothing to analyze."],
            citations=[],
        )

    # --- values per position (skip Unavailable quotes) ---
    positions: list[dict] = []
    total_value = 0.0
    for h in holdings:
        q = market.get_quote(h.ticker)
        if isinstance(q, Unavailable):
            reasons.append(f"Skipped {h.ticker}: quote unavailable ({q.reason}).")
            continue
        if not isinstance(q, Quote):
            reasons.append(f"Skipped {h.ticker}: no usable quote.")
            continue
        value = float(h.shares) * float(q.price)
        sector = None
        try:
            sector = market.get_sector(h.ticker)
        except Exception:  # noqa: BLE001 - sector is best-effort
            sector = None
        positions.append(
            {
                "ticker": h.ticker,
                "shares": float(h.shares),
                "price": float(q.price),
                "value": value,
                "weight": None,  # filled once total is known
                "sector": sector,
                "source": q.source,
                "as_of": q.as_of,
            }
        )
        total_value += value

    if not positions:
        reasons.append("No priceable positions; total value unknown.")
        return PortfolioReport(
            total_value=0.0,
            positions=[],
            concentration={},
            sector_exposure={},
            correlation_flags=[],
            portfolio_beta=None,
            diversification_score=None,
            reasons=reasons,
            citations=[],
        )

    # --- weights ---
    for p in positions:
        p["weight"] = (p["value"] / total_value) if total_value > 0 else 0.0

    citations.append(Citation("total_value", round(total_value, 2), "computed", "now"))
    for p in positions:
        citations.append(
            Citation(f"weight:{p['ticker']}", round(p["weight"], 4), "computed", "now")
        )

    # --- concentration vs max position weight ---
    top = max(positions, key=lambda p: p["weight"])
    over = (
        [p["ticker"] for p in positions if max_weight is not None and p["weight"] > max_weight]
        if max_weight is not None
        else []
    )
    concentration = {
        "max_weight_ticker": top["ticker"],
        "max_weight": round(top["weight"], 4),
        "limit": max_weight,
        "flagged": bool(over),
        "over_limit": over,
    }
    if over:
        reasons.append(
            f"Concentration: {', '.join(over)} exceed the max position weight "
            f"of {max_weight:.0%}."
        )

    # --- sector exposure (value-weighted) ---
    sector_exposure: dict[str, float] = {}
    for p in positions:
        key = p["sector"] or "Unknown"
        sector_exposure[key] = sector_exposure.get(key, 0.0) + p["value"]
    sector_exposure = {k: round(v, 2) for k, v in sector_exposure.items()}

    # --- daily returns per position (for correlation + beta) ---
    returns: dict[str, pd.Series] = {}
    for p in positions:
        try:
            hist = market.get_history(p["ticker"], "1y")
        except Exception:  # noqa: BLE001
            hist = None
        r = _daily_returns(hist)
        if r is not None:
            returns[p["ticker"]] = r

    # --- pairwise correlation flags ---
    correlation_flags: list[str] = []
    corr_values: list[float] = []
    for a, b in itertools.combinations(sorted(returns), 2):
        joined = pd.concat([returns[a], returns[b]], axis=1, join="inner").dropna()
        if len(joined) < _MIN_RETURNS:
            continue
        corr = joined.iloc[:, 0].corr(joined.iloc[:, 1])
        if corr is None or (isinstance(corr, float) and math.isnan(corr)):
            continue
        corr = float(corr)
        corr_values.append(corr)
        if corr > _CORR_FLAG:
            correlation_flags.append(f"{a}~{b}: corr {corr:.2f}")
            citations.append(Citation(f"corr:{a}~{b}", round(corr, 2), "computed", "now"))
    avg_corr = (sum(corr_values) / len(corr_values)) if corr_values else None
    if correlation_flags:
        reasons.append(
            "High correlation (redundant risk): " + "; ".join(correlation_flags) + "."
        )

    # --- portfolio beta vs benchmark ---
    portfolio_beta = _portfolio_beta(market, positions, returns, benchmark)
    if portfolio_beta is not None:
        citations.append(
            Citation(f"beta_vs_{benchmark}", round(portfolio_beta, 3), "computed", "now")
        )
    else:
        reasons.append(f"Portfolio beta unavailable (insufficient data vs {benchmark}).")

    # --- diversification score ---
    diversification_score = _diversification_score(
        [p["weight"] for p in positions], sector_exposure, avg_corr
    )
    if diversification_score is not None:
        citations.append(
            Citation("diversification_score", diversification_score, "computed", "now")
        )

    return PortfolioReport(
        total_value=round(total_value, 2),
        positions=positions,
        concentration=concentration,
        sector_exposure=sector_exposure,
        correlation_flags=correlation_flags,
        portfolio_beta=portfolio_beta,
        diversification_score=diversification_score,
        reasons=reasons,
        citations=citations,
    )


def _portfolio_beta(market, positions, returns, benchmark) -> float | None:
    """Weighted-portfolio daily returns regressed on the benchmark's daily returns:
    beta = cov(port, bench) / var(bench). None if the benchmark or overlap is too thin.
    """
    if not returns:
        return None
    try:
        bench_hist = market.get_history(benchmark, "1y")
    except Exception:  # noqa: BLE001
        return None
    bench = _daily_returns(bench_hist)
    if bench is None:
        return None

    # Renormalize weights across only the names that have return history.
    weighted = {t: p["weight"] for p in positions for t in [p["ticker"]] if t in returns}
    total_w = sum(weighted.values())
    if total_w <= 0:
        return None

    frame = pd.DataFrame(returns).dropna(how="all")
    if frame.empty:
        return None
    w = pd.Series({t: weighted[t] / total_w for t in weighted})
    port = frame[list(w.index)].mul(w, axis=1).sum(axis=1, min_count=1)

    joined = pd.concat([port, bench], axis=1, join="inner").dropna()
    if len(joined) < _MIN_RETURNS:
        return None
    p_ret, b_ret = joined.iloc[:, 0], joined.iloc[:, 1]
    var_b = float(b_ret.var())
    if var_b == 0 or math.isnan(var_b):
        return None
    cov = float(p_ret.cov(b_ret))
    beta = cov / var_b
    if math.isnan(beta) or math.isinf(beta):
        return None
    return beta


def format_portfolio(report: PortfolioReport) -> str:
    """Readable multi-line summary of a PortfolioReport, ending with the standard note."""
    lines: list[str] = []
    if not report.positions:
        lines.append("Portfolio analysis: no priceable positions.")
        for r in report.reasons:
            lines.append(f"- {r}")
        lines.append("")
        lines.append("⚠️ Not financial advice.")
        return "\n".join(lines)

    lines.append(f"Portfolio value: ${report.total_value:,.2f} ({len(report.positions)} positions)")
    lines.append("")
    lines.append("Positions:")
    for p in sorted(report.positions, key=lambda x: x["weight"], reverse=True):
        sector = p.get("sector") or "Unknown"
        lines.append(
            f"  • {p['ticker']}: ${p['value']:,.2f} "
            f"({p['weight']:.1%}) — {sector}"
        )

    c = report.concentration
    if c:
        limit = f"{c['limit']:.0%}" if c.get("limit") is not None else "n/a"
        flag = " ⚠️ OVER LIMIT" if c.get("flagged") else ""
        lines.append("")
        lines.append(
            f"Concentration: top {c['max_weight_ticker']} at {c['max_weight']:.1%} "
            f"(limit {limit}){flag}"
        )
        if c.get("over_limit"):
            lines.append(f"  over limit: {', '.join(c['over_limit'])}")

    if report.sector_exposure:
        lines.append("")
        lines.append("Sector exposure:")
        total = sum(report.sector_exposure.values()) or 1.0
        for sec, val in sorted(
            report.sector_exposure.items(), key=lambda kv: kv[1], reverse=True
        ):
            lines.append(f"  • {sec}: ${val:,.2f} ({val / total:.1%})")

    if report.correlation_flags:
        lines.append("")
        lines.append("High-correlation pairs (redundant risk):")
        for f in report.correlation_flags:
            lines.append(f"  • {f}")

    lines.append("")
    beta = (
        f"{report.portfolio_beta:.2f}" if report.portfolio_beta is not None else "n/a"
    )
    div = (
        f"{report.diversification_score:.2f}"
        if report.diversification_score is not None
        else "n/a"
    )
    lines.append(f"Portfolio beta: {beta}")
    lines.append(f"Diversification score (0-1): {div}")

    if report.reasons:
        lines.append("")
        lines.append("Notes:")
        for r in report.reasons:
            lines.append(f"  - {r}")

    lines.append("")
    lines.append("⚠️ Not financial advice.")
    return "\n".join(lines)
