"""Plain web search behind one interface (ddgs default; Tavily optional). No MCP on the
critical path — MCP remains an optional later adapter (Step 4.8). Step 1.5.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx
from ddgs import DDGS

from logging_setup import get_logger

_log = get_logger(__name__)


@dataclass
class SearchHit:
    title: str
    url: str
    snippet: str


class NewsSearch(ABC):
    @abstractmethod
    def search(self, query: str, max_results: int = 5) -> list[SearchHit]: ...


class DDGSearch(NewsSearch):
    def search(self, query: str, max_results: int = 5) -> list[SearchHit]:
        results = DDGS().text(query, max_results=max_results)
        out: list[SearchHit] = []
        for r in results or []:
            out.append(
                SearchHit(
                    title=r.get("title", ""),
                    url=r.get("href") or r.get("url", ""),
                    snippet=r.get("body", ""),
                )
            )
        return out


class TavilySearch(NewsSearch):
    def __init__(self, api_key: str | None):
        self.api_key = api_key

    def search(self, query: str, max_results: int = 5) -> list[SearchHit]:
        resp = httpx.post(
            "https://api.tavily.com/search",
            json={
                "api_key": self.api_key,
                "query": query,
                "max_results": max_results,
            },
            timeout=15.0,
        )
        data = resp.json()
        return [
            SearchHit(
                title=r.get("title", ""),
                url=r.get("url", ""),
                snippet=r.get("content", ""),
            )
            for r in data.get("results", [])
        ]


class MCPSearch(NewsSearch):
    """MCP-server-backed web search / fetch (Work-stream G5).

    Guardrail model (unchanged philosophy): the agent may only ever CALL a **read-only,
    allowlisted** research tool (search / fetch) on a **configured, trusted** MCP server, and
    the results are treated as untrusted data (the caller wraps them via ``wrap_untrusted``).
    Any tool whose name looks mutating is refused — a compromised or misconfigured server can
    never make this agent write, trade, or exfiltrate.

    ``client`` is an injectable callable ``(tool_name, arguments) -> raw`` so the wrapping and
    guardrail logic are fully offline-testable without a live server. The default client
    lazy-imports the ``mcp`` SDK (``[mcp]`` extra) and needs a configured command/URL.
    """

    # Read-only research tools we permit calling on an MCP server.
    ALLOWED_TOOLS = frozenset(
        {"search", "web_search", "brave_web_search", "tavily_search", "exa_search", "fetch"}
    )
    _FORBIDDEN = re.compile(
        r"write|delete|exec|shell|trade|order|send|post|email|create|update|mutate",
        re.IGNORECASE,
    )

    def __init__(self, *, command=None, url=None, tool="search", client=None):
        self.command = command
        self.url = url
        self.tool = tool or "search"
        self._client = client

    def _guard_tool(self, name: str) -> None:
        if self._FORBIDDEN.search(name) or name not in self.ALLOWED_TOOLS:
            raise ValueError(f"refusing to call non-read-only MCP tool: {name!r}")

    @staticmethod
    def _to_hits(raw, max_results: int) -> list[SearchHit]:
        """Normalize common MCP result shapes into SearchHit."""
        rows = raw
        if isinstance(raw, dict):
            rows = raw.get("results") or raw.get("hits") or raw.get("content") or []
        out: list[SearchHit] = []
        for r in rows or []:
            if isinstance(r, dict):
                out.append(
                    SearchHit(
                        title=r.get("title", ""),
                        url=r.get("url") or r.get("href", ""),
                        snippet=r.get("snippet") or r.get("content") or r.get("body", ""),
                    )
                )
            elif isinstance(r, str):
                out.append(SearchHit(title="", url="", snippet=r))
        return out[:max_results]

    def search(self, query: str, max_results: int = 5) -> list[SearchHit]:
        self._guard_tool(self.tool)
        client = self._client or self._default_client
        raw = client(self.tool, {"query": query, "max_results": max_results})
        return self._to_hits(raw, max_results)

    def _default_client(self, tool: str, arguments: dict):  # pragma: no cover - needs server
        """Lazy MCP client over stdio (command) or SSE (url). Requires the `mcp` extra and a
        configured, trusted server."""
        if not self.command and not self.url:
            raise RuntimeError(
                "MCP search selected but no server configured; set MCP_SEARCH_COMMAND or "
                "MCP_SEARCH_URL (and install: uv sync --extra mcp)."
            )
        try:
            import mcp  # noqa: F401
        except ImportError as e:
            raise RuntimeError("MCP SDK not installed; run: uv sync --extra mcp") from e
        # Live wiring is deployment-specific (stdio/SSE session handshake). Kept as a clear
        # extension point rather than a half-working connection.
        raise RuntimeError(
            "MCP live transport not wired in this build; inject a client or use ddgs/tavily. "
            "See docs/plans (Work-stream G5)."
        )


def get_search(cfg) -> NewsSearch:
    if cfg.web_search_backend == "tavily":
        return TavilySearch(cfg.tavily_api_key)
    if cfg.web_search_backend == "mcp":
        try:
            return MCPSearch(
                command=getattr(cfg, "mcp_search_command", None),
                url=getattr(cfg, "mcp_search_url", None),
                tool=getattr(cfg, "mcp_search_tool", "search"),
            )
        except Exception as e:  # noqa: BLE001 - never fail bootstrap over search backend
            _log.warning("MCP search init failed (%s); falling back to ddgs", e)
    return DDGSearch()
