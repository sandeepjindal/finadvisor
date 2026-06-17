from types import SimpleNamespace
from unittest import mock

import data.news as news
from data.news import Article, extract_article, RSSProvider


def test_rss_latest_maps_entries():
    fake_feed = SimpleNamespace(
        entries=[
            SimpleNamespace(
                link="https://x.test/a",
                title="NVDA up",
                published="2026-06-16",
                summary="datacenter demand",
            )
        ]
    )
    with mock.patch.object(news.feedparser, "parse", return_value=fake_feed):
        arts = RSSProvider().latest("nvda")
    assert len(arts) == 1
    assert isinstance(arts[0], Article)
    assert arts[0].ticker == "NVDA"
    assert arts[0].url == "https://x.test/a"


def test_extract_article_rejects_unsafe_url():
    with mock.patch.object(news, "is_safe_url", return_value=False):
        try:
            extract_article("http://169.254.169.254/")
            assert False, "should have raised"
        except ValueError:
            pass


def test_extract_article_safe_path():
    with (
        mock.patch.object(news, "is_safe_url", return_value=True),
        mock.patch.object(news, "get_text", return_value="<html>...</html>"),
        mock.patch.object(news.trafilatura, "extract", return_value="clean text"),
    ):
        assert extract_article("https://good.test/article") == "clean text"
