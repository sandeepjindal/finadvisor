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
