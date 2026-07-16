"""Option-chain data behind one interface (Work-stream F2). Mirrors ``data/market.py``:
yfinance is the default provider (LAZY-imported only in the default fetch path), fetch is
INJECTABLE so tests run fully OFFLINE, and a typed ``Unavailable`` marker is returned on
error rather than a fabricated value.

Educational/conservative posture: the numbers here (break-even, probability-ITM, IV rank,
unusual activity) are inputs the advisor uses to explain risk — probability-ITM is a
lognormal approximation with a stdlib normal-CDF (no scipy), flagged as approximate.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime

from data.market import Unavailable
from security.guards import validate_ticker


@dataclass
class OptionQuote:
    ticker: str
    expiry: str  # YYYY-MM-DD
    type: str  # "call" | "put"
    strike: float
    bid: float | None
    ask: float | None
    last: float | None
    implied_volatility: float | None  # decimal, e.g. 0.35 == 35%
    volume: float | None
    open_interest: float | None


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
    """Normalize a yfinance-style ``.calls``/``.puts`` DataFrame OR a plain list[dict]
    (what tests inject) into a list of plain dicts. No pandas import required for tests."""
    if frame is None:
        return []
    # pandas DataFrame duck-typing: has ``to_dict`` returning records.
    to_dict = getattr(frame, "to_dict", None)
    if to_dict is not None and not isinstance(frame, (list, tuple, dict)):
        try:
            return list(frame.to_dict("records"))
        except TypeError:
            return list(frame.to_dict(orient="records"))
    if isinstance(frame, dict):
        return [frame]
    return list(frame)


def _parse_side(ticker: str, expiry: str, opt_type: str, frame) -> list[OptionQuote]:
    out: list[OptionQuote] = []
    for r in _rows(frame):
        strike = _to_float(r.get("strike"))
        if strike is None:
            continue
        out.append(
            OptionQuote(
                ticker=ticker,
                expiry=expiry,
                type=opt_type,
                strike=strike,
                bid=_to_float(r.get("bid")),
                ask=_to_float(r.get("ask")),
                last=_to_float(r.get("last") if "last" in r else r.get("lastPrice")),
                implied_volatility=_to_float(r.get("implied_volatility"))
                if "implied_volatility" in r
                else _to_float(r.get("impliedVolatility")),
                volume=_to_float(r.get("volume")),
                open_interest=_to_float(r.get("open_interest"))
                if "open_interest" in r
                else _to_float(r.get("openInterest")),
            )
        )
    return out


def _default_fetch(ticker: str, expiry: str | None):
    """Lazy yfinance path — imported here so tests never need the dependency/network."""
    import yfinance as yf  # noqa: PLC0415 - intentional lazy import

    tk = yf.Ticker(ticker)
    if expiry is None:
        options = getattr(tk, "options", None) or []
        if not options:
            raise ValueError(f"no expiries for {ticker}")
        expiry = options[0]
    chain = tk.option_chain(expiry)
    # Attach resolved expiry so the caller can label rows.
    return expiry, chain


def get_option_chain(
    ticker: str, expiry: str | None = None, *, fetch=None
) -> list[OptionQuote] | Unavailable:
    """Return the full option chain (calls + puts) for ``ticker`` at ``expiry``.

    ``fetch`` is injectable for offline tests. It is called as ``fetch(ticker, expiry)``
    and must return an object exposing ``.calls`` and ``.puts`` (yfinance-style DataFrames
    or plain list[dict]); it may optionally also expose ``.expiry`` to report the chosen
    expiry when ``expiry`` was None. The default path lazily uses yfinance and picks the
    nearest expiry when none is given. Returns ``Unavailable`` on any error.
    """
    try:
        t = validate_ticker(ticker)
    except ValueError as e:
        return Unavailable(field="option_chain", ticker=ticker, reason=str(e))

    try:
        if fetch is None:
            resolved_expiry, chain = _default_fetch(t, expiry)
        else:
            chain = fetch(t, expiry)
            resolved_expiry = expiry or getattr(chain, "expiry", None) or "unknown"
        calls = getattr(chain, "calls", None)
        puts = getattr(chain, "puts", None)
        if calls is None and puts is None:
            raise ValueError("fetch returned no calls/puts")
    except Exception as e:  # noqa: BLE001 - any provider failure -> Unavailable
        return Unavailable(field="option_chain", ticker=t, reason=str(e))

    quotes = _parse_side(t, resolved_expiry, "call", calls)
    quotes += _parse_side(t, resolved_expiry, "put", puts)
    if not quotes:
        return Unavailable(field="option_chain", ticker=t, reason="empty chain")
    return quotes


def iv_rank(current_iv: float | None, iv_history: list[float]) -> float | None:
    """Percentile rank of ``current_iv`` within ``iv_history`` in [0, 1]. Returns the
    fraction of historical observations at or below the current IV. None if inputs are
    insufficient (missing current IV or fewer than 2 clean history points)."""
    if current_iv is None:
        return None
    clean = [float(x) for x in (iv_history or []) if x is not None]
    if len(clean) < 2:
        return None
    at_or_below = sum(1 for x in clean if x <= current_iv)
    return at_or_below / len(clean)


def _mid(option: OptionQuote) -> float | None:
    if option.bid is not None and option.ask is not None:
        return (option.bid + option.ask) / 2.0
    return None


def premium(option: OptionQuote) -> float | None:
    """Best available premium estimate: last trade, else bid/ask midpoint."""
    if option.last is not None:
        return option.last
    return _mid(option)


def break_even(option: OptionQuote, spot: float) -> float | None:
    """Break-even underlying price at expiry for a long option.
    Call: strike + premium. Put: strike - premium. None if premium unknown."""
    prem = premium(option)
    if prem is None:
        return None
    if option.type == "call":
        return option.strike + prem
    if option.type == "put":
        return option.strike - prem
    return None


def _norm_cdf(x: float) -> float:
    """Standard-normal CDF using the stdlib error function (no scipy)."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def prob_itm(
    spot: float | None,
    strike: float | None,
    iv: float | None,
    days_to_exp: float | None,
    is_call: bool,
) -> float | None:
    """Approximate probability the option finishes in-the-money, using a risk-neutral
    lognormal model (zero drift) for the underlying:

        d2 = [ln(S/K) - (sigma^2 / 2) * T] / (sigma * sqrt(T))
        P(ITM call) = N(d2),  P(ITM put) = N(-d2)

    This is the standard delta-adjacent POP approximation — it is APPROXIMATE (ignores
    drift, dividends, skew). Returns None if any input is missing/invalid."""
    s = _to_float(spot)
    k = _to_float(strike)
    sigma = _to_float(iv)
    d = _to_float(days_to_exp)
    if s is None or k is None or sigma is None or d is None:
        return None
    if s <= 0 or k <= 0 or sigma <= 0 or d <= 0:
        return None
    t = d / 365.0
    denom = sigma * math.sqrt(t)
    if denom <= 0:
        return None
    d2 = (math.log(s / k) - 0.5 * sigma * sigma * t) / denom
    return _norm_cdf(d2) if is_call else _norm_cdf(-d2)


def unusual_activity(option: OptionQuote) -> bool:
    """True when today's volume exceeds open interest (a common unusual-activity screen).
    Requires both present and open interest > 0."""
    v = option.volume
    oi = option.open_interest
    if v is None or oi is None or oi <= 0:
        return False
    return v > oi


def days_to_expiry(expiry: str, *, now: date | None = None) -> float | None:
    """Whole days from ``now`` (default today) to an ``YYYY-MM-DD`` expiry; None if unparsable."""
    try:
        exp = datetime.strptime(expiry, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None
    today = now or date.today()
    return float((exp - today).days)
