"""Multi-year financial trends (Work-stream E3). Mirrors ``data/market.py`` /
``data/options.py`` conventions: yfinance is LAZY-imported only in the default fetch
path, ``fetch`` is INJECTABLE so tests run fully OFFLINE, and a typed ``Unavailable``
marker (never a fabricated value) is returned on error.

The advisor uses these numbers to explain the direction a business is trending over
several annual periods — revenue growth (CAGR), gross-margin direction, free-cash-flow
generation, and debt trajectory — as context, not as a recommendation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from data.market import Unavailable
from security.guards import validate_ticker


@dataclass
class FinancialTrend:
    ticker: str
    revenue: list[float]  # oldest -> newest, annual
    eps: list[float]
    gross_margin: list[float]  # fractions, e.g. 0.42 == 42%
    free_cash_flow: list[float]
    total_debt: list[float]
    periods: list[str]  # labels aligned oldest -> newest
    revenue_cagr: float | None  # compound annual growth over the window (fraction)
    margin_direction: str  # "improving" | "deteriorating" | "flat"
    fcf_positive: bool | None  # most-recent FCF > 0
    debt_direction: str  # "improving" (falling) | "deteriorating" (rising) | "flat"
    source: str
    as_of: str
    raw: dict = field(default_factory=dict)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _floats(values) -> list[float]:
    """Coerce an iterable to a clean list of floats, dropping None/NaN/garbage."""
    out: list[float] = []
    for v in values or []:
        try:
            if v is None:
                continue
            f = float(v)
        except (TypeError, ValueError):
            continue
        if f != f:  # NaN
            continue
        out.append(f)
    return out


def _cagr(values: list[float]) -> float | None:
    """Compound annual growth over the window. ``years`` = number of intervals
    (``len - 1``). None when there aren't at least two points or the base is non-positive."""
    if len(values) < 2:
        return None
    first, last = values[0], values[-1]
    years = len(values) - 1
    if first <= 0 or last <= 0 or years <= 0:
        return None
    return (last / first) ** (1.0 / years) - 1.0


def _direction(values: list[float], *, higher_is_better: bool, rel_threshold: float = 0.02) -> str:
    """First-vs-last read: "improving" / "deteriorating" / "flat".

    A change smaller (in magnitude) than ``rel_threshold`` (relative to the first value)
    counts as "flat". ``higher_is_better`` flips the polarity so falling debt reads as
    "improving" while falling margin reads as "deteriorating"."""
    if len(values) < 2:
        return "flat"
    first, last = values[0], values[-1]
    if first != 0:
        change = (last - first) / abs(first)
    else:
        change = last - first
    if abs(change) < rel_threshold:
        return "flat"
    improved = (last > first) if higher_is_better else (last < first)
    return "improving" if improved else "deteriorating"


def _extract(data: dict, *keys) -> list[float]:
    """First present key wins; returns a clean float list (oldest -> newest as given)."""
    for k in keys:
        if k in data and data[k] is not None:
            return _floats(data[k])
    return []


def _row(frame, *labels) -> list | None:
    """Pull a row (by any of ``labels``) from a yfinance statement DataFrame, returned
    OLDEST -> NEWEST. yfinance orders columns newest-first, so we reverse. Returns None
    if the frame or the row is absent."""
    if frame is None:
        return None
    index = getattr(frame, "index", None)
    loc = getattr(frame, "loc", None)
    if index is None or loc is None:
        return None
    try:
        available = list(index)
    except TypeError:
        return None
    for label in labels:
        if label in available:
            try:
                series = loc[label]
            except Exception:  # noqa: BLE001
                continue
            values = list(getattr(series, "values", series))
            return list(reversed(values))
    return None


def _default_fetch(ticker: str) -> dict:
    """Lazy yfinance path — imported here so tests never need the dependency/network.

    Returns a dict-of-lists (oldest -> newest) with keys the normalizer understands:
    ``revenue``, ``gross_profit``, ``net_income``, ``eps``, ``total_debt``,
    ``free_cash_flow`` and ``periods``."""
    import yfinance as yf  # noqa: PLC0415 - intentional lazy import

    tk = yf.Ticker(ticker)
    income = getattr(tk, "income_stmt", None)
    if income is None or getattr(income, "empty", False):
        income = getattr(tk, "financials", None)
    balance = getattr(tk, "balance_sheet", None)
    cash = getattr(tk, "cashflow", None)

    periods: list[str] = []
    cols = getattr(income, "columns", None)
    if cols is not None:
        try:
            periods = [str(getattr(c, "year", None) or c) for c in reversed(list(cols))]
        except TypeError:
            periods = []

    return {
        "periods": periods,
        "revenue": _row(income, "Total Revenue", "TotalRevenue", "Revenue"),
        "gross_profit": _row(income, "Gross Profit", "GrossProfit"),
        "net_income": _row(income, "Net Income", "NetIncome", "Net Income Common Stockholders"),
        "eps": _row(income, "Diluted EPS", "Basic EPS"),
        "total_debt": _row(balance, "Total Debt", "TotalDebt"),
        "free_cash_flow": _row(cash, "Free Cash Flow", "FreeCashFlow"),
    }


def get_financial_trends(ticker: str, *, fetch=None) -> FinancialTrend | Unavailable:
    """Multi-year annual financial trends for ``ticker``.

    ``fetch`` is injectable for offline tests. It is called as ``fetch(ticker)`` and must
    return a dict-of-lists ordered OLDEST -> NEWEST. Recognized keys: ``revenue``,
    ``gross_margin`` (or ``gross_profit`` to derive it against revenue), ``eps`` (or
    ``net_income`` as a proxy), ``free_cash_flow``, ``total_debt`` and ``periods``. The
    default path lazily uses yfinance's ``income_stmt``/``financials``, ``balance_sheet``
    and ``cashflow``. Returns ``Unavailable`` on any error."""
    try:
        t = validate_ticker(ticker)
    except ValueError as e:
        return Unavailable(field="financials", ticker=ticker, reason=str(e))

    try:
        source = "yfinance" if fetch is None else "injected"
        data = _default_fetch(t) if fetch is None else fetch(t)
        if not isinstance(data, dict):
            raise ValueError("fetch must return a dict-of-lists")

        revenue = _extract(data, "revenue")
        gross_profit = _extract(data, "gross_profit")
        eps = _extract(data, "eps")
        if not eps:
            eps = _extract(data, "net_income")
        free_cash_flow = _extract(data, "free_cash_flow")
        total_debt = _extract(data, "total_debt")

        gross_margin = _extract(data, "gross_margin")
        if not gross_margin and gross_profit and revenue:
            n = min(len(gross_profit), len(revenue))
            gross_margin = [
                gross_profit[i] / revenue[i] for i in range(n) if revenue[i]
            ]

        periods = [str(p) for p in (data.get("periods") or [])]

        if not any((revenue, eps, gross_margin, free_cash_flow, total_debt)):
            raise ValueError("no financial series available")
    except Exception as e:  # noqa: BLE001 - any provider failure -> Unavailable
        return Unavailable(field="financials", ticker=ticker, reason=str(e))

    return FinancialTrend(
        ticker=t,
        revenue=revenue,
        eps=eps,
        gross_margin=gross_margin,
        free_cash_flow=free_cash_flow,
        total_debt=total_debt,
        periods=periods,
        revenue_cagr=_cagr(revenue),
        margin_direction=_direction(gross_margin, higher_is_better=True),
        fcf_positive=(free_cash_flow[-1] > 0) if free_cash_flow else None,
        debt_direction=_direction(total_debt, higher_is_better=False),
        source=source,
        as_of=_now(),
        raw=data if isinstance(data, dict) else {},
    )


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:.1f}%"


def _money(x: float | None) -> str:
    if x is None:
        return "n/a"
    a = abs(x)
    if a >= 1e12:
        return f"${x / 1e12:.2f}T"
    if a >= 1e9:
        return f"${x / 1e9:.2f}B"
    if a >= 1e6:
        return f"${x / 1e6:.2f}M"
    return f"${x:,.0f}"


def format_financials(t: FinancialTrend) -> str:
    """Readable multi-year summary. Numbers are attributed to their source/as-of."""
    span = f" ({t.periods[0]} -> {t.periods[-1]})" if t.periods else ""
    lines = [f"Financial trends for {t.ticker}{span}:"]

    if t.revenue:
        lines.append(
            f"- Revenue: {_money(t.revenue[0])} -> {_money(t.revenue[-1])} "
            f"(CAGR {_pct(t.revenue_cagr)} over {max(len(t.revenue) - 1, 0)}y)"
        )
    if t.gross_margin:
        lines.append(
            f"- Gross margin: {_pct(t.gross_margin[0])} -> {_pct(t.gross_margin[-1])} "
            f"({t.margin_direction})"
        )
    if t.eps:
        lines.append(f"- EPS: {t.eps[0]:.2f} -> {t.eps[-1]:.2f}")
    if t.free_cash_flow:
        state = (
            "positive" if t.fcf_positive else "negative" if t.fcf_positive is False else "n/a"
        )
        lines.append(
            f"- Free cash flow: {_money(t.free_cash_flow[0])} -> "
            f"{_money(t.free_cash_flow[-1])} (latest {state})"
        )
    if t.total_debt:
        lines.append(
            f"- Total debt: {_money(t.total_debt[0])} -> {_money(t.total_debt[-1])} "
            f"({t.debt_direction})"
        )

    lines.append(f"(source: {t.source}, as of {t.as_of})")
    lines.append("Not financial advice.")
    return "\n".join(lines)
