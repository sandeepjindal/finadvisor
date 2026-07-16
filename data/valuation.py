"""Valuation context (Work-stream E3). Mirrors ``data/market.py`` / ``data/options.py``
conventions: yfinance is LAZY-imported only in the default fetch path, ``fetch`` is
INJECTABLE so tests run fully OFFLINE, and a typed ``Unavailable`` marker is returned on
error rather than a fabricated value.

The ``verdict`` is a plain-language read ("cheap" / "fair" / "rich" / "unclear") derived
from simple, disclosed heuristics over common multiples — it is context for a
conversation about price, not a recommendation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from data.market import Unavailable
from security.guards import validate_ticker


@dataclass
class ValuationContext:
    ticker: str
    pe: float | None  # trailing P/E
    forward_pe: float | None
    peg: float | None
    ps: float | None  # price / sales (TTM)
    ev_ebitda: float | None  # enterprise value / EBITDA
    verdict: str  # "cheap" | "fair" | "rich" | "unclear"
    reasons: list[str]
    source: str
    as_of: str
    raw: dict = field(default_factory=dict)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_float(v) -> float | None:
    try:
        if v is None:
            return None
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    return f


# Each metric votes "cheap" / "rich" / "fair" with a plain-language reason. Thresholds are
# deliberately conservative and disclosed in the reasons so nothing is a black box.
def _vote_peg(v: float | None) -> tuple[str, str] | None:
    if v is None:
        return None
    if v < 1.0:
        return "cheap", f"PEG {v:.2f} < 1 (growth-adjusted, looks cheap)"
    if v > 2.0:
        return "rich", f"PEG {v:.2f} > 2 (growth-adjusted, looks rich)"
    return "fair", f"PEG {v:.2f} between 1 and 2 (roughly fair)"


def _vote_forward_pe(v: float | None) -> tuple[str, str] | None:
    if v is None:
        return None
    if v < 15.0:
        return "cheap", f"forward P/E {v:.1f} < 15 (below-market multiple)"
    if v > 30.0:
        return "rich", f"forward P/E {v:.1f} > 30 (premium multiple)"
    return "fair", f"forward P/E {v:.1f} between 15 and 30"


def _vote_ps(v: float | None) -> tuple[str, str] | None:
    if v is None:
        return None
    if v < 1.0:
        return "cheap", f"P/S {v:.2f} < 1 (low sales multiple)"
    if v > 10.0:
        return "rich", f"P/S {v:.1f} > 10 (rich sales multiple)"
    return "fair", f"P/S {v:.2f} between 1 and 10"


def _vote_ev_ebitda(v: float | None) -> tuple[str, str] | None:
    if v is None:
        return None
    if v < 10.0:
        return "cheap", f"EV/EBITDA {v:.1f} < 10 (below typical)"
    if v > 20.0:
        return "rich", f"EV/EBITDA {v:.1f} > 20 (elevated)"
    return "fair", f"EV/EBITDA {v:.1f} between 10 and 20"


def _judge(
    peg: float | None,
    forward_pe: float | None,
    ps: float | None,
    ev_ebitda: float | None,
) -> tuple[str, list[str]]:
    votes = [
        _vote_peg(peg),
        _vote_forward_pe(forward_pe),
        _vote_ps(ps),
        _vote_ev_ebitda(ev_ebitda),
    ]
    votes = [v for v in votes if v is not None]
    if not votes:
        return "unclear", ["no valuation multiples available"]

    reasons = [reason for _, reason in votes]
    cheap = sum(1 for label, _ in votes if label == "cheap")
    rich = sum(1 for label, _ in votes if label == "rich")

    if cheap > rich:
        verdict = "cheap"
    elif rich > cheap:
        verdict = "rich"
    else:
        verdict = "fair"
    return verdict, reasons


def _default_fetch(ticker: str) -> dict:
    """Lazy yfinance path — imported here so tests never need the dependency/network."""
    import yfinance as yf  # noqa: PLC0415 - intentional lazy import

    return dict(yf.Ticker(ticker).info or {})


def get_valuation_context(ticker: str, *, fetch=None) -> ValuationContext | Unavailable:
    """Valuation multiples + a plain-language verdict for ``ticker``.

    ``fetch`` is injectable for offline tests. It is called as ``fetch(ticker)`` and must
    return a dict with (any of) the yfinance ``.info`` keys ``trailingPE``, ``forwardPE``,
    ``pegRatio``, ``priceToSalesTrailing12Months`` and ``enterpriseToEbitda``. Missing
    fields degrade to None. The default path lazily uses yfinance. Returns ``Unavailable``
    on any error."""
    try:
        t = validate_ticker(ticker)
    except ValueError as e:
        return Unavailable(field="valuation", ticker=ticker, reason=str(e))

    try:
        source = "yfinance" if fetch is None else "injected"
        info = _default_fetch(t) if fetch is None else fetch(t)
        if not isinstance(info, dict):
            raise ValueError("fetch must return a dict")
    except Exception as e:  # noqa: BLE001 - any provider failure -> Unavailable
        return Unavailable(field="valuation", ticker=ticker, reason=str(e))

    pe = _to_float(info.get("trailingPE"))
    forward_pe = _to_float(info.get("forwardPE"))
    peg = _to_float(info.get("pegRatio"))
    ps = _to_float(info.get("priceToSalesTrailing12Months"))
    ev_ebitda = _to_float(info.get("enterpriseToEbitda"))

    verdict, reasons = _judge(peg, forward_pe, ps, ev_ebitda)

    return ValuationContext(
        ticker=t,
        pe=pe,
        forward_pe=forward_pe,
        peg=peg,
        ps=ps,
        ev_ebitda=ev_ebitda,
        verdict=verdict,
        reasons=reasons,
        source=source,
        as_of=_now(),
        raw=info if isinstance(info, dict) else {},
    )


def _num(x: float | None, fmt: str = "{:.2f}") -> str:
    return "n/a" if x is None else fmt.format(x)


def format_valuation(v: ValuationContext) -> str:
    """Readable valuation summary. Numbers are attributed to their source/as-of."""
    lines = [f"Valuation context for {v.ticker} — verdict: {v.verdict}"]
    lines.append(
        f"- Trailing P/E {_num(v.pe, '{:.1f}')}, forward P/E {_num(v.forward_pe, '{:.1f}')}"
    )
    lines.append(
        f"- PEG {_num(v.peg)}, P/S {_num(v.ps)}, EV/EBITDA {_num(v.ev_ebitda, '{:.1f}')}"
    )
    if v.reasons:
        lines.append("- Why: " + "; ".join(v.reasons))
    lines.append(f"(source: {v.source}, as of {v.as_of})")
    lines.append("Not financial advice.")
    return "\n".join(lines)
