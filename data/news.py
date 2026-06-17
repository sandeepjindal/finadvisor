"""News: per-ticker RSS headlines, safe article extraction, VADER sentiment.
Steps 1.4 + 1.4b (+ optional finBERT 4.9). (Web *search* lives in data/search.py.)
"""

from __future__ import annotations

from dataclasses import dataclass

import feedparser
import trafilatura
from http_client import get_text
from security.guards import is_safe_url, validate_ticker

_analyzer = None  # lazy VADER


@dataclass
class Article:
    ticker: str
    url: str
    title: str
    source: str
    published_at: str
    summary: str
    sentiment: float | None = None


def _yahoo_feed(ticker: str) -> str:
    return (
        "https://feeds.finance.yahoo.com/rss/2.0/headline?"
        f"s={ticker}&region=US&lang=en-US"
    )


class RSSProvider:
    def latest(self, ticker: str, limit: int = 10) -> list[Article]:
        t = validate_ticker(ticker)
        feed = feedparser.parse(_yahoo_feed(t))
        out: list[Article] = []
        for e in feed.entries[:limit]:
            out.append(
                Article(
                    ticker=t,
                    url=getattr(e, "link", "") or "",
                    title=getattr(e, "title", "") or "",
                    source="yahoo_rss",
                    published_at=getattr(e, "published", "") or "",
                    summary=getattr(e, "summary", "") or "",
                )
            )
        return out


def extract_article(url: str) -> str:
    """Fetch and extract clean text. Raises ValueError on an unsafe (SSRF) URL."""
    if not is_safe_url(url):
        raise ValueError(f"refusing to fetch unsafe url: {url!r}")
    html = get_text(url)
    return trafilatura.extract(html) or ""


def news_sentiment(text: str) -> float:
    """VADER compound sentiment in [-1, 1]."""
    global _analyzer
    if _analyzer is None:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

        _analyzer = SentimentIntensityAnalyzer()
    return _analyzer.polarity_scores(text or "")["compound"]


_finbert = None


def finbert_sentiment(text: str) -> float:
    """Optional finance-tuned sentiment ([finbert] extra). Returns [-1, 1]. VADER stays
    the default; this is an opt-in upgrade. Step 4.9."""
    global _finbert
    if _finbert is None:
        try:
            from transformers import pipeline
        except ImportError as e:
            raise RuntimeError(
                "finBERT not installed; run: uv sync --extra finbert"
            ) from e
        _finbert = pipeline("sentiment-analysis", model="ProsusAI/finbert")
    res = _finbert(text or "")[0]  # pragma: no cover - requires model
    label = res["label"].lower()  # pragma: no cover
    score = float(res["score"])  # pragma: no cover
    if label == "positive":  # pragma: no cover
        return score
    if label == "negative":  # pragma: no cover
        return -score
    return 0.0  # pragma: no cover
