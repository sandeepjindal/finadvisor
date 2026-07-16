"""Ownership & insider activity behind one interface (Work-stream E2). Mirrors
``data/market.py`` / ``data/options.py``: yfinance is the default provider (LAZY-imported
only in the default fetch path), ``fetch`` is INJECTABLE so tests run fully OFFLINE, and a
typed ``Unavailable`` marker is returned on error rather than a fabricated value.

Educational/conservative posture on the insider signal: insider BUYING is treated as a
mild positive (insiders buy when they see value); heavy insider SELLING is surfaced as a
caution only — selling has many benign reasons (diversification, taxes, scheduled 10b5-1
plans) and is a weaker signal than buying. This nuance is reflected in ``insider_activity``
and in ``format_ownership``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone

from data.market import Unavailable
from security.guards import validate_ticker


@dataclass
class Holder:
    name: str
    pct: float | None  # percent of shares outstanding, 0-100 scale
    shares: float | None


@dataclass
class OwnershipSummary:
    ticker: str
    institutional_pct: float | None
    insider_pct: float | None
    top_holders: list[Holder]
    insider_net_shares: float | None  # buys - sells over recent transactions
    insider_activity: str  # "net buying" | "net selling" | "neutral"
    source: str
    as_of: str


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


def _parse_pct(v) -> float | None:
    """Normalize a percentage to a 0-100 float, tolerating both yfinance formats.

    Old yfinance gives strings like ``"0.14%"`` (already a percent). New yfinance gives
    fractions like ``0.0014`` (== 0.14%). Both map to ``0.14`` here."""
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip().rstrip("%").strip()
        try:
            return float(s)
        except ValueError:
            return None
    f = _to_float(v)
    if f is None:
        return None
    if 0.0 <= f <= 1.0:
        return f * 100.0
    return f


def _rows(frame) -> list[dict]:
    """Normalize a yfinance-style DataFrame OR a plain list[dict] (what tests inject) into
    a list of plain dicts. No pandas import required for tests."""
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


def _pairs(mh) -> list[tuple[str, object]]:
    """Normalize ``major_holders`` (many shapes across yfinance versions) into
    ``(label, value)`` pairs so we can scan for the insider/institution rows."""
    pairs: list[tuple[str, object]] = []
    if mh is None:
        return pairs
    if isinstance(mh, dict):
        return [(str(k), v) for k, v in mh.items()]
    to_dict = getattr(mh, "to_dict", None)
    if to_dict is not None and not isinstance(mh, (list, tuple)):
        try:
            d = to_dict()  # DataFrame -> {col: {index: value}}
        except Exception:  # noqa: BLE001
            d = {}
        for col, inner in d.items():
            if isinstance(inner, dict):
                for idx, val in inner.items():
                    pairs.append((str(idx), val))
            else:
                pairs.append((str(col), inner))
        return pairs
    # list-like of rows
    for row in mh:
        if isinstance(row, dict):
            label = row.get("label", row.get("Breakdown", row.get(1)))
            val = row.get("value") if "value" in row else row.get(0)
            if label is not None:
                pairs.append((str(label), val))
        elif isinstance(row, (list, tuple)) and len(row) >= 2:
            # old yfinance rows are [value, label]
            pairs.append((str(row[1]), row[0]))
    return pairs


def _parse_major_holders(mh) -> tuple[float | None, float | None]:
    """Return ``(insider_pct, institutional_pct)`` on a 0-100 scale, or None where absent."""
    insider: float | None = None
    institutional: float | None = None
    for label, val in _pairs(mh):
        low = label.lower()
        if "insider" in low and insider is None:
            insider = _parse_pct(val)
        elif "institution" in low and institutional is None:
            institutional = _parse_pct(val)
    return insider, institutional


def _parse_holders(ih) -> list[Holder]:
    out: list[Holder] = []
    for r in _rows(ih):
        name = r.get("Holder", r.get("holder", r.get("name")))
        if name is None:
            continue
        if "% Out" in r:
            pct = _parse_pct(r.get("% Out"))
        elif "pctHeld" in r:
            pct = _parse_pct(r.get("pctHeld"))
        else:
            pct = _parse_pct(r.get("pct"))
        shares = _to_float(r.get("Shares") if "Shares" in r else r.get("shares"))
        out.append(Holder(name=str(name), pct=pct, shares=shares))
    return out


_BUY_WORDS = ("buy", "purchase", "acqui")
_SELL_WORDS = ("sale", "sell", "dispos")


def _parse_insider(it) -> tuple[float | None, str]:
    """Sum recent insider buy vs sell shares. Returns ``(net_shares, activity)`` where
    ``activity`` is "net buying"/"net selling"/"neutral". ``net_shares`` is buys minus
    sells (None when no classifiable transactions were found)."""
    buys = 0.0
    sells = 0.0
    seen = False
    for r in _rows(it):
        text = str(
            r.get("Transaction")
            or r.get("Text")
            or r.get("transaction")
            or r.get("text")
            or ""
        ).lower()
        shares = _to_float(r.get("Shares") if "Shares" in r else r.get("shares"))
        if shares is None:
            continue
        shares = abs(shares)
        if any(w in text for w in _BUY_WORDS):
            buys += shares
            seen = True
        elif any(w in text for w in _SELL_WORDS):
            sells += shares
            seen = True
    if not seen:
        return None, "neutral"
    net = buys - sells
    if buys > sells:
        activity = "net buying"
    elif sells > buys:
        activity = "net selling"
    else:
        activity = "neutral"
    return net, activity


def _default_fetch(ticker: str) -> dict:
    """Lazy yfinance path — imported here so tests never need the dependency/network."""
    import yfinance as yf  # noqa: PLC0415 - intentional lazy import

    tk = yf.Ticker(ticker)
    return {
        "major_holders": getattr(tk, "major_holders", None),
        "institutional_holders": getattr(tk, "institutional_holders", None),
        "insider_transactions": getattr(tk, "insider_transactions", None),
        "source": "yfinance",
        "as_of": _now(),
    }


def get_ownership(ticker: str, *, fetch=None) -> OwnershipSummary | Unavailable:
    """Summarize institutional/insider ownership and recent insider activity for ``ticker``.

    ``fetch`` is injectable for offline tests and is called as ``fetch(ticker) -> dict`` with
    keys ``major_holders`` (insider %, institutional %), ``institutional_holders`` (top
    holders) and ``insider_transactions`` (recent buys/sells); each value may be a
    yfinance DataFrame or a plain list[dict]. The default path lazily uses yfinance.
    Returns ``Unavailable`` on any error."""
    try:
        t = validate_ticker(ticker)
    except ValueError as e:
        return Unavailable(field="ownership", ticker=ticker, reason=str(e))

    try:
        data = _default_fetch(t) if fetch is None else fetch(t)
        if data is None:
            raise ValueError("fetch returned no data")
        insider_pct, institutional_pct = _parse_major_holders(data.get("major_holders"))
        top_holders = _parse_holders(data.get("institutional_holders"))
        net, activity = _parse_insider(data.get("insider_transactions"))
        source = data.get("source") or "yfinance"
        as_of = data.get("as_of") or _now()
    except Exception as e:  # noqa: BLE001 - any provider failure -> Unavailable
        return Unavailable(field="ownership", ticker=t, reason=str(e))

    return OwnershipSummary(
        ticker=t,
        institutional_pct=institutional_pct,
        insider_pct=insider_pct,
        top_holders=top_holders,
        insider_net_shares=net,
        insider_activity=activity,
        source=source,
        as_of=as_of,
    )


def _fmt_pct(v: float | None) -> str:
    return f"{v:.1f}%" if v is not None else "n/a"


def _fmt_shares(v: float | None) -> str:
    return f"{v:,.0f}" if v is not None else "n/a"


def format_ownership(o: OwnershipSummary) -> str:
    """Readable, conservative summary. Ends with the standard disclaimer."""
    lines = [f"Ownership & insider activity — {o.ticker}"]
    lines.append(f"Institutional ownership: {_fmt_pct(o.institutional_pct)}")
    lines.append(f"Insider ownership: {_fmt_pct(o.insider_pct)}")

    if o.top_holders:
        lines.append("Top institutional holders:")
        for h in o.top_holders[:5]:
            lines.append(f"  - {h.name}: {_fmt_pct(h.pct)} ({_fmt_shares(h.shares)} shares)")
    else:
        lines.append("Top institutional holders: n/a")

    net = o.insider_net_shares
    if o.insider_activity == "net buying":
        note = (
            "Recent insider activity: net BUYING"
            + (f" ({_fmt_shares(net)} net shares)" if net is not None else "")
            + " — a mild positive signal (insiders often buy when they see value)."
        )
    elif o.insider_activity == "net selling":
        note = (
            "Recent insider activity: net SELLING"
            + (f" ({_fmt_shares(net)} net shares)" if net is not None else "")
            + " — worth noting as a caution, but insider selling has many benign reasons "
            "(diversification, taxes, scheduled 10b5-1 plans) and is a weaker signal than buying."
        )
    else:
        note = "Recent insider activity: no clear net buying or selling."
    lines.append(note)

    lines.append(f"Source: {o.source} (as of {o.as_of})")
    lines.append("Not financial advice.")
    return "\n".join(lines)
