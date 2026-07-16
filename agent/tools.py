"""Read-only tool registry with citation emission. The agent can ONLY read data and its
own brain — there is no trade/exec/exfil tool (capability restriction = the real injection
backstop). Each tool returns a ToolOutput carrying citations drawn from real values.
Steps 1.7 + 3.7 (doc tools) + 4.1 (filings tool).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from agent.prompts import Citation, wrap_untrusted
from data.market import Fundamentals, Quote, Unavailable
from data.news import RSSProvider
from data.technicals import compute_indicators

# Any tool whose name matches this is forbidden — asserted at registry build time.
FORBIDDEN_NAME = re.compile(
    r"buy|sell|trade|exec|shell|write|delete|send|post|order|withdraw|transfer",
    re.IGNORECASE,
)


@dataclass
class ToolOutput:
    text: str
    citations: list[Citation] = field(default_factory=list)


@dataclass
class _Tool:
    name: str
    description: str
    parameters: dict
    fn: object  # callable(args: dict) -> ToolOutput


def _ticker_param(desc: str) -> dict:
    return {
        "type": "object",
        "properties": {"ticker": {"type": "string", "description": desc}},
        "required": ["ticker"],
    }


class ToolRegistry:
    def __init__(self, market, conn, search=None, rss=None, llm=None):
        self.market = market
        self.conn = conn
        self.search = search
        self.rss = rss or RSSProvider()
        self.llm = llm  # optional; enables LLM-enriched assess_exit (Step 5B)
        self._tools: dict[str, _Tool] = {}
        self._register_all()
        self.assert_read_only()

    # --- registration ---
    def _register_all(self):
        self._add(
            "get_quote",
            "Live price and day change for a ticker.",
            _ticker_param("Stock ticker, e.g. NVDA"),
            self._get_quote,
        )
        self._add(
            "get_fundamentals",
            "Valuation and balance-sheet basics for a ticker.",
            _ticker_param("Stock ticker"),
            self._get_fundamentals,
        )
        self._add(
            "get_technicals",
            "RSI, MACD, 50/200-day MA and trend for a ticker.",
            _ticker_param("Stock ticker"),
            self._get_technicals,
        )
        self._add(
            "search_news",
            "Search recent news/headlines for a company or topic.",
            {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            self._search_news,
        )
        self._add(
            "recall_analysis",
            "Recall this agent's past analyses for a ticker.",
            _ticker_param("Stock ticker"),
            self._recall_analysis,
        )
        self._add(
            "read_playbook",
            "Read an internal investing playbook (e.g. exit_rules).",
            {
                "type": "object",
                "properties": {"topic": {"type": "string"}},
                "required": ["topic"],
            },
            self._read_playbook,
        )
        self._add(
            "get_macro",
            "Current macro indicators (interest rate, CPI, GDP, unemployment).",
            {"type": "object", "properties": {}},
            self._get_macro,
        )
        self._add(
            "assess_exit",
            "Run the Exit Advisor for a holding (HOLD/TRIM/SELL + transient/structural + "
            "redeploy). Uses your stored holding, or pass shares & avg_cost inline.",
            {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "shares": {"type": "number"},
                    "avg_cost": {"type": "number"},
                },
                "required": ["ticker"],
            },
            self._assess_exit,
        )
        self._add(
            "get_filings",
            "Recent SEC filings (10-K/10-Q/8-K) for a ticker.",
            _ticker_param("Stock ticker"),
            self._get_filings,
        )
        self._add(
            "list_documents",
            "List the user's ingested local documents.",
            {"type": "object", "properties": {}},
            self._list_documents,
        )
        self._add(
            "read_document",
            "Read an ingested local document by name.",
            {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
            self._read_document,
        )
        self._add(
            "search_documents",
            "Search the user's ingested documents for a query.",
            {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            self._search_documents,
        )
        self._add(
            "get_social_signal",
            "Social & search-attention read for a ticker (StockTwits bullish/bearish, "
            "Reddit chatter, Google Trends). An attention SPIKE is a RISK flag, not a buy.",
            _ticker_param("Stock ticker"),
            self._get_social_signal,
        )
        self._add(
            "scan_market_context",
            "Scan world/geopolitical news for market-moving themes and the sectors they "
            "help/hurt (confirmed against each sector ETF's real price move).",
            {"type": "object", "properties": {}},
            self._scan_market_context,
        )
        self._add(
            "get_sector_impact",
            "For a ticker: its sector and any active macro/geopolitical theme hitting that "
            "sector, with the sector ETF's confirming price move.",
            _ticker_param("Stock ticker"),
            self._get_sector_impact,
        )
        self._add(
            "recall_signal_history",
            "Recall the enriched signal snapshots this agent saved for a ticker over time.",
            _ticker_param("Stock ticker"),
            self._recall_signal_history,
        )
        self._add(
            "assess_track_record",
            "This agent's historical hit-rate on past calls (overall or for a ticker) — "
            "how often prior HOLD/SELL/TRIM/BUY calls were borne out by price.",
            {
                "type": "object",
                "properties": {"ticker": {"type": "string"}},
            },
            self._assess_track_record,
        )
        self._add(
            "get_intraday",
            "Intraday snapshot for a ticker (VWAP, opening range, relative volume, "
            "intraday RSI, gap) — for day-trading context. Data is delayed/limited.",
            _ticker_param("Stock ticker"),
            self._get_intraday,
        )
        self._add(
            "day_trading_plan",
            "Educational intraday plan for a ticker: momentum/breakout/mean-reversion "
            "with a concrete entry, stop, target and risk:reward — or 'stand aside'. "
            "Day trading is high-risk; risk-management first.",
            _ticker_param("Stock ticker"),
            self._suggest_daytrade,
        )
        self._add(
            "get_options_chain",
            "Option chain for a ticker (strikes, IV, volume, open interest) for the "
            "nearest or a given expiry.",
            {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "expiry": {"type": "string", "description": "YYYY-MM-DD, optional"},
                },
                "required": ["ticker"],
            },
            self._get_options_chain,
        )
        self._add(
            "assess_option",
            "Educational assessment of a specific option (IV rank, break-even, "
            "probability-ITM); favors conservative structures. Options can lose 100%.",
            {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "strike": {"type": "number"},
                    "expiry": {"type": "string", "description": "YYYY-MM-DD"},
                    "type": {"type": "string", "enum": ["call", "put"]},
                },
                "required": ["ticker", "strike", "expiry", "type"],
            },
            self._assess_option,
        )

    def _add(self, name, description, parameters, fn):
        self._tools[name] = _Tool(name, description, parameters, fn)

    def assert_read_only(self):
        for name in self._tools:
            if FORBIDDEN_NAME.search(name):
                raise RuntimeError(f"non-read-only tool registered: {name!r}")

    # --- access ---
    @property
    def names(self) -> list[str]:
        return list(self._tools)

    @property
    def specs(self):
        from llm.base import ToolSpec

        return [
            ToolSpec(t.name, t.description, t.parameters) for t in self._tools.values()
        ]

    def call(self, name: str, args: dict) -> ToolOutput:
        tool = self._tools.get(name)
        if tool is None:
            return ToolOutput(f"unknown tool: {name}", [])
        try:
            return tool.fn(args or {})
        except Exception as e:  # noqa: BLE001
            return ToolOutput(f"tool {name} error: {e}", [])

    # --- tool implementations ---
    def _get_quote(self, args) -> ToolOutput:
        q = self.market.get_quote(args["ticker"])
        if isinstance(q, Unavailable):
            return ToolOutput(f"quote unavailable for {q.ticker}: {q.reason}", [])
        assert isinstance(q, Quote)
        chg = f"{q.change_pct:.2f}%" if q.change_pct is not None else "n/a"
        text = f"{q.ticker} price {q.price} {q.currency} (chg {chg}) as of {q.as_of} [{q.source}]"
        cites = [Citation("price", q.price, q.source, q.as_of)]
        if q.change_pct is not None:
            cites.append(
                Citation("change_pct", round(q.change_pct, 2), q.source, q.as_of)
            )
        return ToolOutput(text, cites)

    def _get_fundamentals(self, args) -> ToolOutput:
        f = self.market.get_fundamentals(args["ticker"])
        if isinstance(f, Unavailable):
            return ToolOutput(
                f"fundamentals unavailable for {f.ticker}: {f.reason}", []
            )
        assert isinstance(f, Fundamentals)
        text = (
            f"{f.ticker} P/E {f.pe} P/B {f.pb} margin {f.profit_margin} "
            f"D/E {f.debt_to_equity} [{f.source} @ {f.as_of}]"
        )
        cites = []
        for metric, val in (
            ("pe", f.pe),
            ("pb", f.pb),
            ("profit_margin", f.profit_margin),
            ("debt_to_equity", f.debt_to_equity),
        ):
            if isinstance(val, (int, float)):
                cites.append(Citation(metric, val, f.source, f.as_of))
        return ToolOutput(text, cites)

    def _get_technicals(self, args) -> ToolOutput:
        hist = self.market.get_history(args["ticker"], "1y")
        if isinstance(hist, Unavailable):
            return ToolOutput(
                f"history unavailable for {hist.ticker}: {hist.reason}", []
            )
        t = compute_indicators(hist)
        ticker = args["ticker"].upper()
        text = (
            f"{ticker} RSI {t.rsi} trend {t.trend} SMA50 {t.sma50} SMA200 {t.sma200} "
            f"above_200ma {t.above_200ma}"
        )
        cites = []
        for metric, val in (("rsi", t.rsi), ("sma50", t.sma50), ("sma200", t.sma200)):
            if isinstance(val, (int, float)):
                cites.append(Citation(metric, val, "computed", "now"))
        return ToolOutput(text, cites)

    def _search_news(self, args) -> ToolOutput:
        query = args["query"]
        lines: list[str] = []
        if self.search is not None:
            for hit in self.search.search(query, max_results=5):
                lines.append(f"- {hit.title}: {hit.snippet} ({hit.url})")
        if not lines:
            lines.append("(no results)")
        # Untrusted: external content is DATA, never instructions.
        return ToolOutput(wrap_untrusted("\n".join(lines)), [])

    def _recall_analysis(self, args) -> ToolOutput:
        from brain.analyses import recall_analyses
        from security.guards import validate_ticker

        t = validate_ticker(args["ticker"])
        past = recall_analyses(self.conn, t, limit=5)
        if not past:
            return ToolOutput(f"no prior analyses for {t}", [])
        lines = [
            f"- {a.created_at}: {a.verdict} (conf {a.confidence}) @ {a.price_at_time}"
            for a in past
        ]
        return ToolOutput("Past analyses for " + t + ":\n" + "\n".join(lines), [])

    def _read_playbook(self, args) -> ToolOutput:
        from agent.knowledge import load_playbook

        try:
            return ToolOutput(load_playbook(args["topic"]), [])
        except ValueError as e:
            return ToolOutput(str(e), [])

    def _get_filings(self, args) -> ToolOutput:
        from data.filings import get_recent_filings

        fs = get_recent_filings(args["ticker"])
        if not fs:
            return ToolOutput("(no recent filings)", [])
        return ToolOutput("\n".join(f"- {f.form} {f.date}: {f.url}" for f in fs), [])

    def _get_macro(self, args) -> ToolOutput:
        from data.macro import get_macro

        try:
            m = get_macro()
        except Exception as e:  # noqa: BLE001 - fredapi/key optional
            return ToolOutput(f"macro data unavailable: {e}", [])
        parts, cites = [], []
        for k, v in m.items():
            parts.append(f"{k}={v}")
            if isinstance(v, (int, float)):
                cites.append(Citation(k, v, "fred", "now"))
        return ToolOutput("Macro: " + ", ".join(parts), cites)

    def _assess_exit(self, args) -> ToolOutput:
        from agent.exit_advisor import (
            enrich_exit_verdict,
            evaluate_exit,
            format_exit_verdict,
        )
        from agent.knowledge import load_rules
        from brain.holdings import Holding, list_holdings
        from security.guards import validate_ticker

        t = validate_ticker(args["ticker"])
        shares, avg_cost = args.get("shares"), args.get("avg_cost")
        holding = None
        if shares is not None and avg_cost is not None:
            holding = Holding(0, t, float(shares), float(avg_cost), "", "")
        else:
            holding = next((h for h in list_holdings(self.conn) if h.ticker == t), None)
        if holding is None:
            return ToolOutput(
                f"No holding for {t}. Provide shares & avg_cost, or add via /portfolio.",
                [],
            )
        verdict = evaluate_exit(holding, self.market, self.conn, load_rules())
        if self.llm is not None:
            context = ""
            try:
                arts = self.rss.latest(t)
                context = "\n".join(f"- {a.title}: {a.summary}" for a in arts[:5])
            except Exception:  # noqa: BLE001 - context is best-effort
                pass
            verdict = enrich_exit_verdict(verdict, context, self.llm)
        return ToolOutput(format_exit_verdict(verdict), verdict.citations)

    def _list_documents(self, args) -> ToolOutput:
        from brain.documents import list_documents

        docs = list_documents(self.conn)
        if not docs:
            return ToolOutput("(no documents ingested)", [])
        return ToolOutput(
            "Documents:\n" + "\n".join(f"- {d.title} ({d.kind})" for d in docs), []
        )

    def _read_document(self, args) -> ToolOutput:
        from brain.documents import get_document

        d = get_document(self.conn, args["name"])
        if not d:
            return ToolOutput(f"document not found: {args['name']}", [])
        return ToolOutput(d.clean_text[:4000], [])

    def _search_documents(self, args) -> ToolOutput:
        from brain.documents import search_documents

        res = search_documents(self.conn, args["query"])
        if not res:
            return ToolOutput("(no matching documents)", [])
        return ToolOutput(
            "\n".join(f"- {d.title}: {d.clean_text[:200]}" for d in res), []
        )

    def _get_social_signal(self, args) -> ToolOutput:
        from data.social import combined_social
        from security.guards import validate_ticker

        t = validate_ticker(args["ticker"])
        s = combined_social(t)
        parts = [f"{t} social:"]
        if s.get("bullish_ratio") is not None:
            parts.append(f"StockTwits bullish {s['bullish_ratio']:.0%}")
        if s.get("sentiment") is not None:
            parts.append(f"Reddit sentiment {s['sentiment']:+.2f}")
        if s.get("attention") is not None:
            parts.append(f"search attention {s['attention']:.0f}")
        if s.get("attention_spike"):
            parts.append("ATTENTION SPIKE")
        if s.get("risk_flag"):
            parts.append("⚠️ hype/crowding RISK")
        text = ", ".join(parts) + f"\n{s.get('note', '')}"
        return ToolOutput(text, s.get("citations", []))

    # Macro queries the world-scan sweeps for market-moving themes.
    _MACRO_QUERIES = (
        "geopolitical conflict markets",
        "oil supply prices",
        "federal reserve interest rates inflation",
        "semiconductor export restrictions",
    )

    def _active_events(self) -> list:
        """Detect + price-confirm active themes from world news. Shared by two tools."""
        from agent.events import confirm_with_price, detect_events
        from agent.knowledge import load_sector_map
        from data.worldnews import google_news

        headlines: list = []
        for q in self._MACRO_QUERIES:
            try:
                headlines.extend(google_news(q, limit=8))
            except Exception:  # noqa: BLE001 - best-effort
                continue
        try:
            sector_map = load_sector_map()
        except Exception:  # noqa: BLE001
            return []
        events = detect_events(headlines, sector_map)
        return [confirm_with_price(e, self.market) for e in events]

    def _scan_market_context(self, args) -> ToolOutput:
        events = self._active_events()
        if not events:
            return ToolOutput("(no active market-moving themes detected)", [])
        lines: list[str] = []
        cites: list[Citation] = []
        for e in events:
            lines.append(f"• **{e.theme}** ({e.headline_count} headlines, conf {e.confidence})")
            cites.append(Citation(f"theme:{e.theme}", e.headline_count, "worldnews", "now"))
            for im in e.impacts:
                mark = {True: "✓confirmed", False: "✗not-confirmed", None: "?unconfirmed"}[
                    im.get("confirmed")
                ]
                lines.append(
                    f"   - {im['sector']} {im['direction']} ({im['etf']}, {mark})"
                    + (f" — {im['why']}" if im.get("why") else "")
                )
        return ToolOutput(wrap_untrusted("\n".join(lines)), cites)

    def _get_sector_impact(self, args) -> ToolOutput:
        from agent.events import sector_for_ticker
        from security.guards import validate_ticker

        t = validate_ticker(args["ticker"])
        sector = sector_for_ticker(t, self.market)
        if not sector:
            return ToolOutput(f"sector unknown for {t}; no sector-impact read", [])
        hits: list[str] = []
        for e in self._active_events():
            for im in e.impacts:
                if str(im.get("sector", "")).lower() == sector.lower():
                    mark = {True: "confirmed", False: "not confirmed", None: "unconfirmed"}[
                        im.get("confirmed")
                    ]
                    hits.append(
                        f"• {e.theme}: {sector} expected {im['direction']} "
                        f"({im['etf']} move {mark})"
                    )
        if not hits:
            return ToolOutput(f"{t} sector={sector}: no active theme currently impacts it", [])
        return ToolOutput(f"{t} sector={sector}:\n" + "\n".join(hits), [])

    def _recall_signal_history(self, args) -> ToolOutput:
        from brain.signals import recall_signal_history
        from security.guards import validate_ticker

        t = validate_ticker(args["ticker"])
        snaps = recall_signal_history(self.conn, t, limit=5)
        if not snaps:
            return ToolOutput(f"no saved signal history for {t}", [])
        lines = [f"- {s.created_at[:10]} @ {s.price}: {s.signals}" for s in snaps]
        return ToolOutput(f"Signal history for {t}:\n" + "\n".join(lines), [])

    def _assess_track_record(self, args) -> ToolOutput:
        from brain.signals import track_record

        ticker = args.get("ticker")
        if ticker:
            from security.guards import validate_ticker

            ticker = validate_ticker(ticker)
        tr = track_record(self.conn, ticker)
        if not tr["total"]:
            scope = ticker or "overall"
            return ToolOutput(f"no scored past decisions yet ({scope})", [])
        scope = ticker or "overall"
        lines = [
            f"Track record ({scope}): {tr['correct']}/{tr['total']} correct "
            f"= {tr['accuracy']:.0%}"
        ]
        for act, b in tr["by_action"].items():
            lines.append(f"• {act}: {b['correct']}/{b['total']} ({b['accuracy']:.0%})")
        return ToolOutput("\n".join(lines), [])

    def _get_intraday(self, args) -> ToolOutput:
        from data.intraday import compute_intraday, get_intraday

        df = get_intraday(args["ticker"])
        if isinstance(df, Unavailable):
            return ToolOutput(f"intraday unavailable for {df.ticker}: {df.reason}", [])
        m = compute_intraday(df)
        t = args["ticker"].upper()
        text = (
            f"{t} intraday: VWAP {m.vwap} RSI {m.intraday_rsi} rel-vol {m.rel_volume} "
            f"OR[{m.opening_range_low}-{m.opening_range_high}] gap {m.gap_pct}"
        )
        cites = []
        for metric, val in (
            ("vwap", m.vwap),
            ("intraday_rsi", m.intraday_rsi),
            ("rel_volume", m.rel_volume),
        ):
            if isinstance(val, (int, float)):
                cites.append(Citation(metric, round(val, 2), "computed", "intraday"))
        return ToolOutput(text, cites)

    def _suggest_daytrade(self, args) -> ToolOutput:
        from agent.daytrade import (
            enrich_daytrade,
            format_daytrade,
            suggest_daytrade,
        )
        from agent.knowledge import load_rules
        from security.guards import validate_ticker

        t = validate_ticker(args["ticker"])
        dt = load_rules().raw.get("daytrade", {})
        setup = suggest_daytrade(
            t,
            self.market,
            max_risk_per_trade=dt.get("max_risk_per_trade", 0.01),
            min_rr=dt.get("min_rr", 1.5),
        )
        if self.llm is not None:
            try:
                setup = enrich_daytrade(setup, "", self.llm)
            except Exception:  # noqa: BLE001 - enrichment best-effort
                pass
        return ToolOutput(format_daytrade(setup), setup.citations)

    def _get_options_chain(self, args) -> ToolOutput:
        from data.options import get_option_chain

        chain = get_option_chain(args["ticker"], args.get("expiry"))
        if isinstance(chain, Unavailable):
            return ToolOutput(f"options unavailable for {chain.ticker}: {chain.reason}", [])
        if not chain:
            return ToolOutput("(no options found)", [])
        lines = [
            f"- {o.type} {o.strike} exp {o.expiry}: IV {o.implied_volatility} "
            f"vol {o.volume} OI {o.open_interest}"
            for o in chain[:20]
        ]
        return ToolOutput("\n".join(lines), [])

    def _assess_option(self, args) -> ToolOutput:
        from agent.options_advisor import assess_option, enrich_option, format_option
        from security.guards import validate_ticker

        t = validate_ticker(args["ticker"])
        a = assess_option(
            t, self.market, args["strike"], args["expiry"], args["type"]
        )
        if isinstance(a, Unavailable):
            return ToolOutput(f"option assessment unavailable for {t}: {a.reason}", [])
        if self.llm is not None:
            try:
                a = enrich_option(a, self.llm)
            except Exception:  # noqa: BLE001 - enrichment best-effort
                pass
        return ToolOutput(format_option(a), a.citations)
