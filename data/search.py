"""Plain web search behind one interface (ddgs default; Tavily optional). No MCP on the
critical path — MCP remains an optional later adapter (Step 4.8). Step 1.5.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx
from ddgs import DDGS


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
    """Optional MCP-server-backed search ([mcp] / Step 4.8). Off the critical path;
    requires an MCP search server to be configured/running."""

    def search(self, query: str, max_results: int = 5) -> list[SearchHit]:
        raise NotImplementedError(
            "MCP search backend not configured; use WEB_SEARCH_BACKEND=ddgs or tavily, "
            "or wire an MCP server (Step 4.8)."
        )


def get_search(cfg) -> NewsSearch:
    if cfg.web_search_backend == "tavily":
        return TavilySearch(cfg.tavily_api_key)
    if cfg.web_search_backend == "mcp":
        return MCPSearch()
    return DDGSearch()
