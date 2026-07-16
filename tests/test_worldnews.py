from data.worldnews import Headline, gdelt_events, google_news

_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Google News</title>
    <item>
      <title>Iran strikes near Strait of Hormuz, oil jumps</title>
      <link>https://example.com/a</link>
      <pubDate>Mon, 14 Jul 2026 10:00:00 GMT</pubDate>
      <description>Crude prices surge on supply fears</description>
      <source url="https://reuters.com">Reuters</source>
    </item>
    <item>
      <title>Markets react to escalation</title>
      <link>https://example.com/b</link>
      <pubDate>Mon, 14 Jul 2026 11:00:00 GMT</pubDate>
      <description>Defense stocks rise</description>
      <source url="https://apnews.com">AP News</source>
    </item>
  </channel>
</rss>
"""

_GDELT = {
    "articles": [
        {
            "url": "https://example.com/g1",
            "title": "OPEC signals production cut",
            "domain": "reuters.com",
            "seendate": "20260714T100000Z",
        },
        {
            "url": "https://example.com/g2",
            "title": "Crude spikes on embargo talk",
            "domain": "bloomberg.com",
            "seendate": "20260714T110000Z",
        },
    ]
}


def test_google_news_parses_canned_rss():
    out = google_news("iran oil", fetch=lambda url: _RSS)
    assert len(out) == 2
    assert isinstance(out[0], Headline)
    assert out[0].title.startswith("Iran strikes")
    assert out[0].url == "https://example.com/a"
    assert out[0].source == "Reuters"
    assert "Crude" in out[0].summary


def test_google_news_respects_limit():
    out = google_news("iran", limit=1, fetch=lambda url: _RSS)
    assert len(out) == 1


def test_google_news_degrades_on_error():
    def boom(url):
        raise RuntimeError("network down")

    assert google_news("iran", fetch=boom) == []


def test_gdelt_parses_canned_json():
    out = gdelt_events("opec", client=lambda url: _GDELT)
    assert len(out) == 2
    assert out[0].source == "reuters.com"
    assert out[0].title == "OPEC signals production cut"
    assert out[1].url == "https://example.com/g2"


def test_gdelt_degrades_on_error():
    def boom(url):
        raise RuntimeError("boom")

    assert gdelt_events("opec", client=boom) == []


def test_gdelt_degrades_on_bad_shape():
    assert gdelt_events("opec", client=lambda url: {"unexpected": 1}) == []
    assert gdelt_events("opec", client=lambda url: "not json") == []
