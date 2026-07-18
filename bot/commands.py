"""Slash-style command handlers (pure functions). `handle_command` returns a reply for a
recognized command or natural-language portfolio statement, or None so the caller routes
the text to the agent engine. Steps 2.4 + 3.2.
"""

from __future__ import annotations

import re

from agent.portfolio_parse import parse_holdings_nl
from brain.holdings import add_holding, list_holdings, remove_holding
from brain.watchlist import add_watch, list_watch, remove_watch

_OWN_RE = re.compile(r"^\s*i\s+(own|hold|have|bought)\b", re.IGNORECASE)


def handle_watchlist(conn, tokens: list[str]) -> str:
    sub = tokens[0].lower() if tokens else "list"
    if sub == "add":
        if len(tokens) < 2:
            return "Usage: /watchlist add TICKER [reason]"
        try:
            t = add_watch(conn, tokens[1], " ".join(tokens[2:]))
        except ValueError as e:
            return f"⚠️ {e}"
        return f"✅ Added {t} to watchlist."
    if sub == "remove":
        if len(tokens) < 2:
            return "Usage: /watchlist remove TICKER"
        try:
            ok = remove_watch(conn, tokens[1])
        except ValueError as e:
            return f"⚠️ {e}"
        return (
            f"🗑️ Removed {tokens[1].upper()}."
            if ok
            else f"{tokens[1].upper()} not on watchlist."
        )
    items = list_watch(conn)
    if not items:
        return "Watchlist is empty. Add one with `/watchlist add NVDA`."
    return "👀 **Watchlist**\n" + "\n".join(
        f"• {it.ticker}" + (f" — {it.reason}" if it.reason else "") for it in items
    )


def handle_portfolio(conn, tokens: list[str]) -> str:
    sub = tokens[0].lower() if tokens else "list"
    if sub == "add":
        if len(tokens) < 4:
            return "Usage: /portfolio add TICKER SHARES AVG_COST"
        # A leading '$' marks the price, so shares/cost may be given in either order
        # ("NVDA 30 $450" or "NVDA $450 30"). Without a '$', order is shares-then-cost.
        a, b = tokens[2], tokens[3]
        if a.startswith("$") and not b.startswith("$"):
            shares_tok, cost_tok = b, a
        else:
            shares_tok, cost_tok = a, b
        try:
            shares = float(shares_tok.lstrip("$"))
            cost = float(cost_tok.lstrip("$"))
        except ValueError:
            return (
                "⚠️ SHARES and AVG_COST must be numbers "
                "(mark the price with '$', e.g. /portfolio add NVDA 30 $450)."
            )
        try:
            add_holding(conn, tokens[1], shares, cost, " ".join(tokens[4:]))
        except ValueError as e:
            return f"⚠️ {e}"
        return f"✅ Added {tokens[1].upper()}: {shares:g} @ {cost:g}."
    if sub == "remove":
        if len(tokens) < 2:
            return "Usage: /portfolio remove TICKER"
        try:
            n = remove_holding(conn, tokens[1])
        except ValueError as e:
            return f"⚠️ {e}"
        return (
            f"🗑️ Removed {tokens[1].upper()}." if n else f"{tokens[1].upper()} not held."
        )
    items = list_holdings(conn)
    if not items:
        return "No holdings yet. Add with `/portfolio add NVDA 30 450` or say 'I own 30 NVDA at 450'."
    return "💼 **Portfolio**\n" + "\n".join(
        f"• {h.ticker}: {h.shares} @ {h.avg_cost}" for h in items
    )


def _ingest_nl_holdings(conn, text: str) -> str | None:
    if not _OWN_RE.match(text):
        return None
    parsed = parse_holdings_nl(text)
    if not parsed:
        return None
    for ticker, shares, cost in parsed:
        add_holding(conn, ticker, shares, cost)
    summary = ", ".join(f"{t} {s:g}@{c:g}" for t, s, c in parsed)
    return f"✅ Recorded holdings: {summary}."


def handle_command(conn, text: str) -> str | None:
    stripped = (text or "").strip()
    if stripped.startswith("/watchlist"):
        return handle_watchlist(conn, stripped.split()[1:])
    if stripped.startswith("/portfolio"):
        return handle_portfolio(conn, stripped.split()[1:])
    return _ingest_nl_holdings(conn, stripped)
