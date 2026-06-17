from datetime import datetime, timedelta, timezone

from agent.knowledge import load_rules
from agent.screener import score_ticker
from brain.db import init_db
from data.market import Unavailable
from data.news import Article
from scheduler.jobs import (
    build_digest_scores,
    daily_crawl_job,
    format_digest,
    maintenance_job,
)


class FakeRSS:
    def __init__(self, arts):
        self.arts = arts

    def latest(self, ticker, limit=10):
        return [a for a in self.arts if a.ticker == ticker]


class FakeMarket:
    def get_quote(self, t):
        return Unavailable("quote", t, "n/a")

    def get_fundamentals(self, t):
        return Unavailable("fundamentals", t, "n/a")

    def get_history(self, t, period="1y"):
        return Unavailable("history", t, "n/a")


def _arts():
    return [
        Article(
            "NVDA", "https://x.test/1", "NVDA up", "rss", "2026-06-16", "good demand"
        ),
        Article(
            "NVDA", "https://x.test/2", "NVDA chips", "rss", "2026-06-16", "more demand"
        ),
    ]


def test_daily_crawl_inserts_and_dedupes(tmp_path):
    conn = init_db(str(tmp_path / "brain.db"))
    rss = FakeRSS(_arts())
    added = daily_crawl_job(conn, rss, ["NVDA"], sentiment_fn=lambda s: 0.0)
    assert added == 2
    assert conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM articles_fts").fetchone()[0] == 2
    assert daily_crawl_job(conn, rss, ["NVDA"], sentiment_fn=lambda s: 0.0) == 0


def test_crawl_skips_failing_feed(tmp_path):
    conn = init_db(str(tmp_path / "brain.db"))

    class BoomRSS:
        def latest(self, t, limit=10):
            raise RuntimeError("feed down")

    assert daily_crawl_job(conn, BoomRSS(), ["NVDA"], sentiment_fn=lambda s: 0.0) == 0


def test_maintenance_prunes_old_text(tmp_path):
    conn = init_db(str(tmp_path / "brain.db"))
    old = (datetime.now(timezone.utc) - timedelta(days=200)).isoformat()
    new = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO articles (ticker,url,title,clean_text,fetched_at) VALUES (?,?,?,?,?)",
        ("NVDA", "u1", "old", "bulky old text", old),
    )
    conn.execute(
        "INSERT INTO articles (ticker,url,title,clean_text,fetched_at) VALUES (?,?,?,?,?)",
        ("NVDA", "u2", "new", "fresh text", new),
    )
    conn.commit()
    res = maintenance_job(conn, retention_days=30)
    assert res["pruned"] == 1
    rows = dict(conn.execute("SELECT url, clean_text FROM articles").fetchall())
    assert rows["u1"] is None
    assert rows["u2"] == "fresh text"


def test_format_digest():
    rules = load_rules()
    scores = [
        score_ticker(
            "A",
            trend="up",
            rsi=50,
            pe=12,
            profit_margin=0.3,
            sentiment=0.5,
            rules=rules,
        ),
        score_ticker(
            "B",
            trend="down",
            rsi=80,
            pe=80,
            profit_margin=0.0,
            sentiment=-0.5,
            rules=rules,
        ),
    ]
    out = format_digest(scores)
    assert "A" in out and "B" in out
    assert "Not financial advice" in out


def test_build_digest_scores_handles_unavailable(tmp_path):
    conn = init_db(str(tmp_path / "brain.db"))
    rules = load_rules()
    scores = build_digest_scores(
        FakeMarket(), FakeRSS([]), conn, rules, ["NVDA", "AAPL"]
    )
    assert len(scores) == 2
