from types import SimpleNamespace
from unittest import mock

import pytest

import data.search as search
from data.search import DDGSearch, MCPSearch, SearchHit, TavilySearch, get_search


def test_ddg_search_maps_hits():
    fake = mock.MagicMock()
    fake.text.return_value = [
        {"title": "NVDA soars", "href": "https://x.test/a", "body": "demand"}
    ]
    with mock.patch.object(search, "DDGS", return_value=fake):
        hits = DDGSearch().search("nvidia news")
    assert hits == [SearchHit("NVDA soars", "https://x.test/a", "demand")]


def test_tavily_search_maps_hits():
    resp = SimpleNamespace(
        json=lambda: {
            "results": [{"title": "T", "url": "https://y.test", "content": "c"}]
        }
    )
    with mock.patch.object(search.httpx, "post", return_value=resp):
        hits = TavilySearch("key").search("q")
    assert hits[0].url == "https://y.test"


def test_get_search_selects_backend():
    assert isinstance(get_search(SimpleNamespace(web_search_backend="ddgs")), DDGSearch)
    assert isinstance(
        get_search(SimpleNamespace(web_search_backend="tavily", tavily_api_key="k")),
        TavilySearch,
    )


def test_mcp_search_uses_injected_client_and_maps_hits():
    def fake_client(tool, args):
        assert tool == "search"
        return {"results": [{"title": "T", "url": "https://z.test", "snippet": "s"}]}

    hits = MCPSearch(command="x", tool="search", client=fake_client).search("q")
    assert hits[0].url == "https://z.test" and hits[0].snippet == "s"


def test_mcp_search_refuses_non_readonly_tool():
    # A mutating/unknown tool name must be rejected even if a server offers it.
    with pytest.raises(ValueError):
        MCPSearch(command="x", tool="delete_index", client=lambda *_: []).search("q")


def test_mcp_search_selected_with_command():
    m = get_search(
        SimpleNamespace(
            web_search_backend="mcp",
            mcp_search_command="npx server",
            mcp_search_url=None,
            mcp_search_tool="search",
        )
    )
    assert isinstance(m, MCPSearch)


def test_mcp_default_client_raises_without_config():
    # No command/url configured -> clear error, never a silent bad call.
    with pytest.raises(RuntimeError):
        MCPSearch().search("q")
