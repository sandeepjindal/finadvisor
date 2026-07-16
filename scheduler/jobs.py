"""Scheduled jobs + scheduler builder. Steps 2.0 (tz) + 2.3 (jobs) + 3.5 (monitoring).

Jobs are pure functions returning payloads/counts; `build_scheduler` wires them to cron
triggers in the configured market timezone (it does not start the scheduler).
"""

from __future__ import annotations

import statistics
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from agent.exit_advisor import evaluate_exit, format_exit_verdict
from agent.screener import ScreenScore, rank_universe, score_ticker
from brain.holdings import list_holdings, record_alert, was_alerted
from data.market import Unavailable
from data.news import news_sentiment
from data.technicals import compute_indicators
from logging_setup import get_logger

log = get_logger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_digest_time(s: str) -> tuple[int, int]:
    h, m = s.split(":")
    return int(h), int(m)


def build_scheduler(
    cfg, digest_cb=None, crawl_cb=None, maintenance_cb=None
) -> BackgroundScheduler:
    tz = ZoneInfo(cfg.market_tz)
    sched = BackgroundScheduler(timezone=tz)
    h, m = parse_digest_time(cfg.digest_time)
    if crawl_cb is not None:
        # crawl an hour before the digest
        sched.add_job(
            crawl_cb, CronTrigger(hour=(h - 1) % 24, minute=m, timezone=tz), id="crawl"
        )
    if digest_cb is not None:
        sched.add_job(
            digest_cb, CronTrigger(hour=h, minute=m, timezone=tz), id="digest"
        )
    if maintenance_cb is not None:
        sched.add_job(
            maintenance_cb,
            CronTrigger(day_of_week="sun", hour=3, minute=0, timezone=tz),
            id="maintenance",
        )
    return sched


def daily_crawl_job(conn, rss, tickers, sentiment_fn=news_sentiment) -> int:
    """Fetch RSS headlines per ticker into `articles` (+ FTS). Returns rows added."""
    added = 0
    for t in tickers:
        try:
            arts = rss.latest(t)
        except Exception as e:  # noqa: BLE001
            log.warning("crawl failed for %s: %s", t, e)
            continue
        for a in arts:
            try:
                sent = sentiment_fn(a.summary or a.title or "")
                cur = conn.execute(
                    """INSERT OR IGNORE INTO articles
                       (ticker, url, title, source, published_at, clean_text, sentiment, fetched_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        a.ticker,
                        a.url,
                        a.title,
                        a.source,
                        a.published_at,
                        a.summary,
                        sent,
                        _now(),
                    ),
                )
                if cur.rowcount > 0:
                    added += 1
                    try:
                        conn.execute(
                            "INSERT INTO articles_fts (title, clean_text) VALUES (?, ?)",
                            (a.title, a.summary),
                        )
                    except Exception:  # noqa: BLE001 - FTS optional
                        pass
            except Exception as e:  # noqa: BLE001
                log.warning("insert article failed: %s", e)
        conn.commit()
    return added


def build_digest_scores(market, rss, conn, rules, tickers, events=None) -> list[ScreenScore]:
    from agent.screener import catalyst_score, macro_score_from_events

    macro = macro_score_from_events(events)  # market-wide tone from the world scan
    scores: list[ScreenScore] = []
    for t in tickers:
        f = market.get_fundamentals(t)
        h = market.get_history(t)
        trend, rsi = "sideways", None
        trend_strength = macd_cross = cross_signal = None
        if not isinstance(h, Unavailable):
            tech = compute_indicators(h)
            trend, rsi = tech.trend, tech.rsi
            trend_strength = tech.trend_strength
            macd_cross, cross_signal = tech.macd_cross, tech.cross_signal
        pe = None if isinstance(f, Unavailable) else f.pe
        margin = None if isinstance(f, Unavailable) else f.profit_margin
        sent = None
        try:
            arts = rss.latest(t)
            if arts:
                sent = statistics.mean(
                    news_sentiment(a.summary or a.title or "") for a in arts[:3]
                )
        except Exception as e:  # noqa: BLE001
            log.warning("sentiment fetch failed for %s: %s", t, e)
        # Catalyst from active confirmed themes hitting this ticker's sector (only when the
        # world scan supplied events; sector lookup guarded for markets without get_sector).
        catalyst = 0.5
        if events:
            sector = None
            try:
                sector = market.get_sector(t)
            except Exception:  # noqa: BLE001
                sector = None
            catalyst = catalyst_score(sector, events)
        scores.append(
            score_ticker(
                t,
                trend=trend,
                rsi=rsi,
                pe=pe,
                profit_margin=margin,
                sentiment=sent,
                rules=rules,
                macro=macro,
                catalyst=catalyst,
                trend_strength=trend_strength,
                macd_cross=macd_cross,
                cross_signal=cross_signal,
            )
        )
    return scores


def format_digest(
    scores: list[ScreenScore], limit: int = 5, backdrop: list | None = None
) -> str:
    """Format the morning push: an optional macro backdrop (trending themes + sectors from
    world_scan_job) followed by the top ranked ideas, each with its strongest driver."""
    lines = ["📈 **Morning digest**"]

    # Macro backdrop — what's moving markets today and which sectors it favours.
    active = [e for e in (backdrop or []) if getattr(e, "impacts", None)]
    if active:
        lines.append("\n🌍 **Market backdrop**")
        for e in active[:3]:
            ups = [i["sector"] for i in e.impacts if i.get("direction") == "up"]
            downs = [i["sector"] for i in e.impacts if i.get("direction") == "down"]
            bits = []
            if ups:
                bits.append("↑ " + ", ".join(ups))
            if downs:
                bits.append("↓ " + ", ".join(downs))
            lines.append(f"• {e.theme.replace('_', ' ')}: {' | '.join(bits)}")

    lines.append("\n💡 **Top ideas** (screened by trend + fundamentals + sentiment)")
    ranked = rank_universe(scores)[:limit]
    for s in ranked:
        driver = max(s.breakdown, key=s.breakdown.get) if s.breakdown else None
        why = f" — strongest: {driver}" if driver else ""
        lines.append(f"• {s.ticker} — score {s.composite:.2f}{why}")
    if not ranked:
        lines.append("(no candidates)")
    lines.append("\n⚠️ Not financial advice.")
    return "\n".join(lines)


def monitor_holdings_job(
    conn, market, rules, evaluate_fn=evaluate_exit, cooldown_hours: float | None = None
) -> list[str]:
    """Run the Exit Advisor over each holding; emit one alert per fresh TRIM/SELL
    trigger (cooldown-deduped). Returns the alert messages to push."""
    cooldown = cooldown_hours if cooldown_hours is not None else rules.cooldown_hours
    alerts: list[str] = []
    for h in list_holdings(conn):
        try:
            verdict = evaluate_fn(h, market, conn, rules)
        except Exception as e:  # noqa: BLE001
            log.warning("exit eval failed for %s: %s", h.ticker, e)
            continue
        # Learning loop (Work-stream D): score matured past calls against fresh price so
        # the track record accrues over time. Best-effort — never blocks alerting.
        try:
            from brain.signals import evaluate_decisions

            q = market.get_quote(h.ticker)
            if not isinstance(q, Unavailable) and getattr(q, "price", None) is not None:
                evaluate_decisions(conn, h.ticker, q.price)
        except Exception as e:  # noqa: BLE001
            log.warning("decision-outcome eval failed for %s: %s", h.ticker, e)
        if verdict.action in ("TRIM", "SELL"):
            if not was_alerted(conn, h.ticker, verdict.action, cooldown):
                msg = format_exit_verdict(verdict)
                record_alert(conn, h.ticker, verdict.action, msg[:500])
                alerts.append(msg)
    return alerts


def world_scan_job(market, *, news_fn=None, sector_map=None, queries=None) -> list:
    """Sweep world/macro news for market-moving themes and confirm each against the sector
    ETF's real price move. Returns the confirmed DetectedEvents (the macro backdrop the
    digest/monitoring can reference). Pure + injectable for offline tests. Work-stream B."""
    from agent.events import confirm_with_price, detect_events
    from data.worldnews import google_news

    if news_fn is None:
        news_fn = lambda q: google_news(q, limit=8)  # noqa: E731
    if queries is None:
        queries = (
            "geopolitical conflict markets",
            "oil supply prices",
            "federal reserve interest rates inflation",
            "semiconductor export restrictions",
        )
    if sector_map is None:
        from agent.knowledge import load_sector_map

        try:
            sector_map = load_sector_map()
        except Exception as e:  # noqa: BLE001
            log.warning("sector map load failed: %s", e)
            return []

    headlines: list = []
    for qy in queries:
        try:
            headlines.extend(news_fn(qy))
        except Exception as e:  # noqa: BLE001
            log.warning("world news fetch failed for %r: %s", qy, e)
    events = detect_events(headlines, sector_map)
    return [confirm_with_price(e, market) for e in events]


def maintenance_job(conn, retention_days: int) -> dict:
    """Prune bulky article text past retention, then VACUUM to reclaim space."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()
    cur = conn.execute(
        "UPDATE articles SET clean_text = NULL WHERE fetched_at < ? AND clean_text IS NOT NULL",
        (cutoff,),
    )
    pruned = cur.rowcount
    conn.commit()
    conn.execute("VACUUM")
    return {"pruned": pruned}
