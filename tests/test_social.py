"""Offline tests for Work-stream C (data/social.py).

All network + optional deps (pytrends/praw) are bypassed via injected fetch/client
callables and canned JSON. No keys, no network.
"""

from agent.prompts import Citation
from data.market import Unavailable
from data.social import (
    AttentionSignal,
    SocialSignal,
    combined_social,
    google_trends_attention,
    reddit_mentions,
    stocktwits_sentiment,
)


def _stocktwits_canned(bullish: int, bearish: int, neutral: int = 0):
    msgs = []
    for _ in range(bullish):
        msgs.append({"entities": {"sentiment": {"basic": "Bullish"}}})
    for _ in range(bearish):
        msgs.append({"entities": {"sentiment": {"basic": "Bearish"}}})
    for _ in range(neutral):
        msgs.append({"entities": {"sentiment": None}})
    data = {"messages": msgs}
    return lambda url: data


def _reddit_canned(titles):
    children = [{"data": {"title": t}} for t in titles]
    data = {"data": {"children": children}}
    return lambda url: data


def test_stocktwits_bullish_ratio_math():
    sig = stocktwits_sentiment("NVDA", fetch=_stocktwits_canned(6, 2, neutral=2))
    assert isinstance(sig, SocialSignal)
    assert sig.ticker == "NVDA"
    assert sig.bullish_ratio == 6 / 8  # neutral excluded from ratio
    assert sig.message_volume == 10  # total messages incl. neutral
    assert sig.source == "stocktwits"


def test_stocktwits_no_graded_messages_ratio_none():
    sig = stocktwits_sentiment("AAPL", fetch=_stocktwits_canned(0, 0, neutral=3))
    assert isinstance(sig, SocialSignal)
    assert sig.bullish_ratio is None
    assert sig.message_volume == 3


def test_stocktwits_invalid_ticker_unavailable():
    sig = stocktwits_sentiment("not a ticker", fetch=_stocktwits_canned(1, 1))
    assert isinstance(sig, Unavailable)


def test_stocktwits_fetch_raises_unavailable():
    def boom(url):
        raise RuntimeError("network down")

    sig = stocktwits_sentiment("NVDA", fetch=boom)
    assert isinstance(sig, Unavailable)
    assert sig.field == "social"


def test_reddit_mentions_count_and_sentiment():
    titles = [
        "NVDA soars on incredible record profits, amazing outlook",
        "NVDA great beat, investors thrilled",
    ]
    sig = reddit_mentions("NVDA", subreddits=("stocks",), fetch=_reddit_canned(titles))
    assert isinstance(sig, SocialSignal)
    assert sig.message_volume == 2
    assert sig.bullish_ratio is None
    assert sig.sentiment is not None
    assert sig.sentiment > 0  # positive titles -> positive VADER


def test_reddit_empty_sentiment_none():
    sig = reddit_mentions("NVDA", subreddits=("stocks",), fetch=_reddit_canned([]))
    assert isinstance(sig, SocialSignal)
    assert sig.message_volume == 0
    assert sig.sentiment is None


def test_reddit_fetch_raises_unavailable():
    def boom(url):
        raise RuntimeError("429")

    sig = reddit_mentions("NVDA", fetch=boom)
    assert isinstance(sig, Unavailable)


def test_google_trends_spike_true():
    sig = google_trends_attention("NVDA", client=lambda q: [10, 10, 10, 30])
    assert isinstance(sig, AttentionSignal)
    assert sig.attention == 30
    assert sig.baseline == 10
    assert sig.attention_spike is True


def test_google_trends_spike_false_flat():
    sig = google_trends_attention("NVDA", client=lambda q: [20, 20, 20, 21])
    assert isinstance(sig, AttentionSignal)
    assert sig.attention_spike is False


def test_google_trends_empty_unavailable():
    sig = google_trends_attention("NVDA", client=lambda q: [])
    assert isinstance(sig, Unavailable)


def test_google_trends_client_raises_unavailable():
    def boom(q):
        raise RuntimeError("pytrends blew up")

    sig = google_trends_attention("NVDA", client=boom)
    assert isinstance(sig, Unavailable)


def test_combined_social_risk_flag_true_on_extreme_plus_spike():
    out = combined_social(
        "NVDA",
        stocktwits_fetch=_stocktwits_canned(9, 1),  # ratio 0.9 -> extreme
        reddit_fetch=_reddit_canned(["NVDA to the moon, unbelievable gains, buy buy"]),
        trends_client=lambda q: [10, 10, 10, 40],  # spike
    )
    assert out["risk_flag"] is True
    assert out["bullish_ratio"] == 0.9
    assert out["attention_spike"] is True
    assert "<untrusted>" in out["note"]
    assert "risk" in out["note"].lower()
    assert out["citations"]
    assert all(isinstance(c, Citation) for c in out["citations"])


def test_combined_social_risk_flag_false_without_spike():
    out = combined_social(
        "NVDA",
        stocktwits_fetch=_stocktwits_canned(9, 1),  # extreme sentiment
        reddit_fetch=_reddit_canned(["NVDA news"]),
        trends_client=lambda q: [20, 20, 20, 20],  # flat, no spike
    )
    assert out["attention_spike"] is False
    assert out["risk_flag"] is False


def test_combined_social_risk_flag_false_spike_without_extreme():
    out = combined_social(
        "NVDA",
        stocktwits_fetch=_stocktwits_canned(5, 5),  # ratio 0.5, not extreme
        reddit_fetch=_reddit_canned(["NVDA quarterly filing released today"]),
        trends_client=lambda q: [10, 10, 10, 50],  # spike
    )
    assert out["attention_spike"] is True
    assert out["risk_flag"] is False


def test_combined_social_skips_unavailable_components():
    def boom(url):
        raise RuntimeError("down")

    out = combined_social(
        "NVDA",
        stocktwits_fetch=boom,  # -> Unavailable, skipped
        reddit_fetch=boom,  # -> Unavailable, skipped
        trends_client=lambda q: [10, 10, 10, 40],
    )
    assert out["bullish_ratio"] is None
    assert out["sentiment"] is None
    assert out["attention"] == 40
    assert out["risk_flag"] is False  # no extreme sentiment available
