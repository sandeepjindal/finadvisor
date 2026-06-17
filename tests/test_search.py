from types import SimpleNamespace
from unittest import mock

import data.search as search
from data.search import DDGSearch, SearchHit, TavilySearch, get_search


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
