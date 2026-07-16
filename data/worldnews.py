"""World / topic news ingestion (free, no-key): Google News RSS by query and the
GDELT 2.0 DOC API. Both use injectable fetch/client callables so tests run offline with
canned data. Returned text is plain data — the tool layer wraps it via
``agent.prompts.wrap_untrusted`` before it reaches an LLM. Work-stream B, Step B1.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote_plus


@dataclass
class Headline:
    title: str
    url: str
    source: str
    published_at: str
    summary: str


def _google_news_url(query: str) -> str:
    return (
        "https://news.google.com/rss/search?q="
        f"{quote_plus(query)}&hl=en-US&gl=US&ceid=US:en"
    )


def _entry_source(entry) -> str:
    """Google News RSS puts the outlet in a <source> element; be robust to feedparser
    representing it as an object, a dict, or a bare string."""
    src = getattr(entry, "source", None)
    if src is None:
        return "google_news"
    title = getattr(src, "title", None)
    if title:
        return title
    if isinstance(src, dict):
        return src.get("title") or src.get("value") or "google_news"
    return str(src) or "google_news"


def google_news(query: str, limit: int = 10, *, fetch=None) -> list[Headline]:
    """Topical world/event headlines for ``query`` via Google News RSS.

    ``fetch(url) -> str`` returns the feed XML/text; defaults to
    ``http_client.get_text`` for the live path. Degrades to ``[]`` on any error.
    """
    if fetch is None:
        from http_client import get_text as fetch  # live path

    try:
        raw = fetch(_google_news_url(query))
    except Exception:  # noqa: BLE001 - best-effort source
        return []

    try:
        import feedparser

        feed = feedparser.parse(raw)
    except Exception:  # noqa: BLE001
        return []

    out: list[Headline] = []
    for e in getattr(feed, "entries", [])[:limit]:
        out.append(
            Headline(
                title=getattr(e, "title", "") or "",
                url=getattr(e, "link", "") or "",
                source=_entry_source(e),
                published_at=getattr(e, "published", "") or "",
                summary=getattr(e, "summary", "") or "",
            )
        )
    return out


def _gdelt_url(query: str) -> str:
    return (
        "https://api.gdeltproject.org/api/v2/doc/doc?query="
        f"{quote_plus(query)}&mode=artlist&format=json&maxrecords=25"
    )


def gdelt_events(query: str, *, client=None) -> list[Headline]:
    """Global-event articles for ``query`` via the GDELT 2.0 DOC API.

    ``client(url) -> dict`` returns parsed JSON; defaults to ``http_client.get_json``
    for the live path. Degrades to ``[]`` on any error.
    """
    if client is None:
        from http_client import get_json as client  # live path

    try:
        data = client(_gdelt_url(query))
    except Exception:  # noqa: BLE001 - best-effort source
        return []

    if not isinstance(data, dict):
        return []
    articles = data.get("articles")
    if not isinstance(articles, list):
        return []

    out: list[Headline] = []
    for a in articles:
        if not isinstance(a, dict):
            continue
        out.append(
            Headline(
                title=a.get("title", "") or "",
                url=a.get("url", "") or "",
                source=a.get("domain", "") or "gdelt",
                published_at=a.get("seendate", "") or "",
                summary=a.get("title", "") or "",
            )
        )
    return out
