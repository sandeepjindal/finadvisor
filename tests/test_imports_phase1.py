"""Smoke test: the Phase-1 data/news libs import cleanly in this environment.

Guards against regressing onto the broken pandas-ta/NumPy-2 combination (C2) and confirms
the [data]+[news] extras are present.
"""


def test_phase1_imports():
    import feedparser  # noqa: F401
    import ta  # noqa: F401
    import trafilatura  # noqa: F401
    import yfinance  # noqa: F401
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer  # noqa: F401


def test_ddgs_imports():
    import ddgs  # noqa: F401
