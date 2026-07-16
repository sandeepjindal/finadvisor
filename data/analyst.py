"""Analyst intelligence, growth estimates, and catalysts behind one interface
(Work-stream E1). Mirrors ``data/market.py`` / ``data/options.py``: yfinance is the default
provider (LAZY-imported only in the default fetch path), ``fetch`` is INJECTABLE so tests run
fully OFFLINE with canned dicts, and a typed ``Unavailable`` marker is returned on error
rather than a fabricated value.

Educational/conservative posture: analyst consensus, price targets, growth estimates, and
earnings catalysts are inputs the advisor uses to *explain* a stock — they are third-party
opinions/estimates, never a recommendation. Every parse is version-tolerant: yfinance
attribute shapes vary across releases, so every access is guarded and degrades to
None/Unavailable instead of crashing.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from data.market import Unavailable
from security.guards import validate_ticker


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_float(v) -> float | None:
    try:
        if v is None:
            return None
        f = float(v)
        if math.isnan(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


def _rows(frame) -> list[dict]:
    """Normalize a yfinance-style DataFrame OR a plain list[dict]/dict (what tests inject)
    into a list of plain dicts. No pandas import required for tests."""
    if frame is None:
        return []
    to_dict = getattr(frame, "to_dict", None)
    if to_dict is not None and not isinstance(frame, (list, tuple, dict)):
        try:
            return list(frame.to_dict("records"))
        except TypeError:
            try:
                return list(frame.to_dict(orient="records"))
            except Exception:  # noqa: BLE001
                return []
    if isinstance(frame, dict):
        return [frame]
    return list(frame)


def _period_map(obj, value_keys=("growth", "stockTrend", "value")) -> dict[str, float | None]:
    """Normalize a period-indexed estimate (yfinance DataFrame, dict, or list[dict]) into a
    plain ``{period: value}`` map. Tolerant of every shape yfinance has shipped."""
    if obj is None:
        return {}
    # pandas DataFrame: ``to_dict()`` (no args) -> {column: {period: value}}.
    to_dict = getattr(obj, "to_dict", None)
    if to_dict is not None and not isinstance(obj, (list, tuple, dict)):
        try:
            d = obj.to_dict()
        except Exception:  # noqa: BLE001
            return {}
        for key in value_keys:
            if key in d and isinstance(d[key], dict):
                return {str(k): _to_float(v) for k, v in d[key].items()}
        if d:
            first = next(iter(d.values()))
            if isinstance(first, dict):
                return {str(k): _to_float(v) for k, v in first.items()}
        return {}
    if isinstance(obj, dict):
        out: dict[str, float | None] = {}
        for k, v in obj.items():
            if isinstance(v, dict):
                val = None
                for vk in value_keys:
                    if vk in v:
                        val = _to_float(v[vk])
                        break
                out[str(k)] = val
            else:
                out[str(k)] = _to_float(v)
        return out
    if isinstance(obj, (list, tuple)):
        out2: dict[str, float | None] = {}
        for r in obj:
            if not isinstance(r, dict):
                continue
            period = r.get("period") if "period" in r else r.get("index")
            if period is None:
                continue
            val = None
            for vk in value_keys:
                if vk in r:
                    val = _to_float(r[vk])
                    break
            out2[str(period)] = val
        return out2
    return {}


# --------------------------------------------------------------------------- analyst ratings


@dataclass
class AnalystRatings:
    ticker: str
    strong_buy: int
    buy: int
    hold: int
    sell: int
    strong_sell: int
    consensus: str  # "Strong Buy" | "Buy" | "Hold" | "Sell" | "Strong Sell" | "Unknown"
    mean_target: float | None
    current_price: float | None
    implied_upside_pct: float | None
    source: str
    as_of: str


def _consensus(sb: int, b: int, h: int, s: int, ss: int) -> str:
    """Derive a consensus label from rating counts via the standard 1..5 weighted mean
    (1=Strong Buy .. 5=Strong Sell)."""
    total = sb + b + h + s + ss
    if total <= 0:
        return "Unknown"
    score = (1 * sb + 2 * b + 3 * h + 4 * s + 5 * ss) / total
    if score <= 1.5:
        return "Strong Buy"
    if score <= 2.5:
        return "Buy"
    if score <= 3.5:
        return "Hold"
    if score <= 4.5:
        return "Sell"
    return "Strong Sell"


def _extract_counts(rec) -> dict[str, int] | None:
    """Pull the current-period ("0m") rating counts out of a yfinance ``recommendations``/
    ``recommendations_summary`` frame (DataFrame or list[dict]). None if unparsable."""
    rows = _rows(rec)
    if not rows:
        return None
    row = None
    for r in rows:
        p = r.get("period") if isinstance(r, dict) and "period" in r else (
            r.get("Period") if isinstance(r, dict) else None
        )
        if p in ("0m", "0M", "0", 0):
            row = r
            break
    if row is None:
        row = rows[0]
    if not isinstance(row, dict):
        return None

    def g(*keys) -> int:
        for k in keys:
            if k in row:
                v = _to_float(row[k])
                if v is not None:
                    return int(v)
        return 0

    return {
        "strong_buy": g("strongBuy", "strong_buy", "StrongBuy"),
        "buy": g("buy", "Buy"),
        "hold": g("hold", "Hold"),
        "sell": g("sell", "Sell"),
        "strong_sell": g("strongSell", "strong_sell", "StrongSell"),
    }


def _extract_targets(pt) -> tuple[float | None, float | None]:
    """(mean_target, current_price) from a yfinance ``analyst_price_targets`` mapping."""
    if not isinstance(pt, dict):
        return (None, None)
    mean = _to_float(pt.get("mean")) if "mean" in pt else _to_float(pt.get("targetMeanPrice"))
    current = (
        _to_float(pt.get("current"))
        if "current" in pt
        else _to_float(pt.get("currentPrice"))
    )
    return (mean, current)


def _default_analyst_fetch(ticker: str) -> dict:
    """Lazy yfinance path — imported here so tests never need the dependency/network."""
    import yfinance as yf  # noqa: PLC0415 - intentional lazy import

    tk = yf.Ticker(ticker)
    return {
        "recommendations": getattr(tk, "recommendations", None),
        "recommendations_summary": getattr(tk, "recommendations_summary", None),
        "analyst_price_targets": getattr(tk, "analyst_price_targets", None),
    }


def get_analyst_ratings(
    ticker: str, market=None, *, fetch=None
) -> AnalystRatings | Unavailable:
    """Return analyst rating counts, consensus, and price-target upside for ``ticker``.

    ``fetch`` is injectable for offline tests: ``fetch(ticker) -> dict`` returning any of
    ``recommendations`` / ``recommendations_summary`` (rating counts) and
    ``analyst_price_targets`` (mean/current). The default path lazily uses yfinance.
    ``market`` (optional) supplies a current-price fallback via ``get_quote`` when the price
    targets omit it. Returns ``Unavailable`` on any error / no usable data.
    """
    try:
        t = validate_ticker(ticker)
    except ValueError as e:
        return Unavailable(field="analyst_ratings", ticker=ticker, reason=str(e))

    try:
        data = _default_analyst_fetch(t) if fetch is None else fetch(t)
        if not isinstance(data, dict):
            raise ValueError("fetch did not return a dict")
        counts = _extract_counts(data.get("recommendations")) or _extract_counts(
            data.get("recommendations_summary")
        )
        mean_target, current_price = _extract_targets(data.get("analyst_price_targets"))
    except Exception as e:  # noqa: BLE001 - any provider failure -> Unavailable
        return Unavailable(field="analyst_ratings", ticker=t, reason=str(e))

    # Current-price fallback via the market facade (best-effort, never fatal).
    if current_price is None and market is not None:
        try:
            q = market.get_quote(t)
            price = getattr(q, "price", None)
            if not isinstance(q, Unavailable) and price is not None:
                current_price = _to_float(price)
        except Exception:  # noqa: BLE001
            current_price = None

    if counts is None and mean_target is None and current_price is None:
        return Unavailable(field="analyst_ratings", ticker=t, reason="no analyst data")

    c = counts or {"strong_buy": 0, "buy": 0, "hold": 0, "sell": 0, "strong_sell": 0}
    consensus = _consensus(
        c["strong_buy"], c["buy"], c["hold"], c["sell"], c["strong_sell"]
    )

    implied = None
    if mean_target is not None and current_price is not None and current_price != 0:
        implied = (mean_target - current_price) / current_price * 100.0

    return AnalystRatings(
        ticker=t,
        strong_buy=c["strong_buy"],
        buy=c["buy"],
        hold=c["hold"],
        sell=c["sell"],
        strong_sell=c["strong_sell"],
        consensus=consensus,
        mean_target=mean_target,
        current_price=current_price,
        implied_upside_pct=implied,
        source="yfinance",
        as_of=_now(),
    )


# --------------------------------------------------------------------------- growth estimates


@dataclass
class GrowthEstimates:
    ticker: str
    eps_growth_next_year: float | None
    revenue_growth_next_year: float | None
    long_term_growth: float | None
    source: str
    as_of: str


def _default_growth_fetch(ticker: str) -> dict:
    import yfinance as yf  # noqa: PLC0415 - intentional lazy import

    tk = yf.Ticker(ticker)
    return {
        "growth_estimates": getattr(tk, "growth_estimates", None),
        "earnings_estimate": getattr(tk, "earnings_estimate", None),
        "revenue_estimate": getattr(tk, "revenue_estimate", None),
    }


def get_growth_estimates(ticker: str, *, fetch=None) -> GrowthEstimates | Unavailable:
    """Return next-year EPS/revenue growth and long-term (5y) growth for ``ticker``.

    ``fetch`` is injectable for offline tests: ``fetch(ticker) -> dict`` returning any of
    ``growth_estimates`` (period -> EPS growth, incl. "+1y" and "+5y"), ``earnings_estimate``
    (fallback for EPS "+1y"), and ``revenue_estimate`` (period -> revenue growth). The default
    path lazily uses yfinance. Missing periods degrade to None; ``Unavailable`` on error.
    """
    try:
        t = validate_ticker(ticker)
    except ValueError as e:
        return Unavailable(field="growth_estimates", ticker=ticker, reason=str(e))

    try:
        data = _default_growth_fetch(t) if fetch is None else fetch(t)
        if not isinstance(data, dict):
            raise ValueError("fetch did not return a dict")
        growth = _period_map(data.get("growth_estimates"))
        earnings = _period_map(data.get("earnings_estimate"))
        revenue = _period_map(data.get("revenue_estimate"))
    except Exception as e:  # noqa: BLE001
        return Unavailable(field="growth_estimates", ticker=t, reason=str(e))

    eps_next = growth.get("+1y")
    if eps_next is None:
        eps_next = earnings.get("+1y")
    long_term = growth.get("+5y")
    rev_next = revenue.get("+1y")

    return GrowthEstimates(
        ticker=t,
        eps_growth_next_year=eps_next,
        revenue_growth_next_year=rev_next,
        long_term_growth=long_term,
        source="yfinance",
        as_of=_now(),
    )


# --------------------------------------------------------------------------------- catalysts


@dataclass
class Catalysts:
    ticker: str
    next_earnings_date: str | None
    recent_forms: list[str] = field(default_factory=list)
    source: str = "yfinance"
    as_of: str = ""


def _fmt_date(v) -> str | None:
    """Coerce a date/datetime/ISO-string into a ``YYYY-MM-DD`` string; None if unparsable."""
    if v is None:
        return None
    if isinstance(v, (date, datetime)):
        return v.strftime("%Y-%m-%d")
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None
        # Accept full ISO timestamps too; take the date portion.
        return s[:10]
    return None


def _next_earnings(calendar) -> str | None:
    """Extract the next earnings date from a yfinance ``calendar`` (dict or DataFrame)."""
    if calendar is None:
        return None
    val = None
    if isinstance(calendar, dict):
        val = calendar.get("Earnings Date")
        if val is None:
            val = calendar.get("earnings_date")
    else:
        # DataFrame-ish: try to locate an "Earnings Date" row/column tolerantly.
        to_dict = getattr(calendar, "to_dict", None)
        if to_dict is not None:
            try:
                d = calendar.to_dict()
            except Exception:  # noqa: BLE001
                d = {}
            for k, v in d.items():
                if "earnings" in str(k).lower() and "date" in str(k).lower():
                    val = v
                    break
                if isinstance(v, dict):
                    for kk, vv in v.items():
                        if "earnings" in str(kk).lower() and "date" in str(kk).lower():
                            val = vv
                            break
    if isinstance(val, (list, tuple)):
        val = val[0] if val else None
    return _fmt_date(val)


def _default_catalyst_fetch(ticker: str) -> dict:
    import yfinance as yf  # noqa: PLC0415 - intentional lazy import

    tk = yf.Ticker(ticker)
    return {"calendar": getattr(tk, "calendar", None)}


def get_catalysts(ticker: str, *, fetch=None) -> Catalysts | Unavailable:
    """Return upcoming catalysts (next earnings date, recent SEC forms) for ``ticker``.

    ``fetch`` is injectable for offline tests: ``fetch(ticker) -> dict`` returning ``calendar``
    (next earnings date) and, optionally, ``recent_forms`` (a list of form types). The default
    path lazily uses yfinance for the earnings date; ``recent_forms`` is a deliberate HOOK left
    empty here — the agent's ``data/filings.py`` (8-Ks) can populate it upstream and pass it in.
    Returns ``Unavailable`` on error.
    """
    try:
        t = validate_ticker(ticker)
    except ValueError as e:
        return Unavailable(field="catalysts", ticker=ticker, reason=str(e))

    try:
        data = _default_catalyst_fetch(t) if fetch is None else fetch(t)
        if not isinstance(data, dict):
            raise ValueError("fetch did not return a dict")
        next_earnings = _next_earnings(data.get("calendar"))
        forms_raw = data.get("recent_forms") or []
        recent_forms = [str(x) for x in forms_raw if x is not None]
    except Exception as e:  # noqa: BLE001
        return Unavailable(field="catalysts", ticker=t, reason=str(e))

    return Catalysts(
        ticker=t,
        next_earnings_date=next_earnings,
        recent_forms=recent_forms,
        source="yfinance",
        as_of=_now(),
    )


# ------------------------------------------------------------------------------- formatting


def format_analyst(r: AnalystRatings) -> str:
    """Readable analyst-consensus summary. Ends with the standard disclaimer."""
    lines = [f"📈 **{r.ticker} — Analyst Consensus: {r.consensus}**"]
    total = r.strong_buy + r.buy + r.hold + r.sell + r.strong_sell
    if total > 0:
        lines.append(
            f"• Ratings ({total} analysts): {r.strong_buy} strong buy / {r.buy} buy / "
            f"{r.hold} hold / {r.sell} sell / {r.strong_sell} strong sell"
        )
    if r.mean_target is not None:
        lines.append(f"• Mean price target: {r.mean_target:.2f}")
    if r.current_price is not None:
        lines.append(f"• Current price: {r.current_price:.2f}")
    if r.implied_upside_pct is not None:
        lines.append(f"• Implied upside: {r.implied_upside_pct:+.1f}%")
    lines.append(f"_source: {r.source}, as of {r.as_of[:10]}_")
    lines.append("\n⚠️ Not financial advice.")
    return "\n".join(lines)
