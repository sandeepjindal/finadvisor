"""Entrypoint: load env FIRST, then config, logging, brain, LLM, and the Discord bot.

`.env` must load before `load_config()` reads the environment. `bootstrap()` performs all
wiring except starting the client, so it is unit-testable. Steps 0.11 + Phase 1-3 wiring.
"""

from __future__ import annotations

from types import SimpleNamespace

from agent import engine
from agent.knowledge import load_rules
from agent.tools import ToolRegistry
from bot.commands import handle_command
from bot.discord_bot import build_bot
from bot.formatting import chunk_message, format_answer
from brain.db import init_db
from brain.watchlist import list_watch
from config import load_config
from data.documents import ingest_file, scan_inbox
from data.market import MarketData
from data.news import RSSProvider
from data.search import get_search
from dotenv import load_dotenv
from llm.factory import get_llm
from logging_setup import configure_logging, get_logger
from scheduler.jobs import (
    build_digest_scores,
    build_scheduler,
    daily_crawl_job,
    format_digest,
    maintenance_job,
    world_scan_job,
)
from security.guards import sanitize_user_text


def _ingest_documents(conn, log) -> None:
    try:
        for path in scan_inbox("documents"):
            try:
                ingest_file(conn, path)
            except Exception as e:  # noqa: BLE001
                log.warning("doc ingest failed for %s: %s", path, e)
    except Exception as e:  # noqa: BLE001
        log.warning("document scan failed: %s", e)


def bootstrap() -> SimpleNamespace:
    load_dotenv()  # MUST be first so config sees the env
    cfg = load_config()
    configure_logging(cfg.log_level)
    log = get_logger("app")
    conn = init_db(cfg.db_path)
    llm = get_llm(cfg)
    market = MarketData(cache_conn=conn)
    tools = ToolRegistry(market=market, conn=conn, search=get_search(cfg), llm=llm)
    _ingest_documents(conn, log)

    async def handle_message(text: str) -> str:
        clean = sanitize_user_text(text)
        # Slash commands (e.g. /watchlist) are handled before the agent engine.
        cmd_reply = handle_command(conn, clean)
        if cmd_reply is not None:
            return cmd_reply
        ans = engine.answer(clean, conn, llm, tools, cfg.max_tool_iters)
        return format_answer(ans)

    bot = build_bot(cfg, handle_message)
    log.info("fin-advisor bootstrapped (provider=%s)", cfg.llm_provider)
    return SimpleNamespace(
        cfg=cfg, conn=conn, llm=llm, market=market, tools=tools, bot=bot
    )


def _start_scheduler(ctx):  # pragma: no cover - background timers
    cfg, conn, market = ctx.cfg, ctx.conn, ctx.market
    rss = RSSProvider()
    rules = load_rules()
    log = get_logger("scheduler")

    def _tickers():
        return [w.ticker for w in list_watch(conn)]

    def crawl():
        log.info(
            "daily crawl: added %d articles", daily_crawl_job(conn, rss, _tickers())
        )

    def digest():
        try:
            backdrop = world_scan_job(market)  # trending macro/geopolitical themes
        except Exception as e:  # noqa: BLE001 - backdrop is best-effort
            log.warning("world scan failed: %s", e)
            backdrop = []
        # Feed the backdrop into scoring so macro/catalyst are real, not placebos.
        scores = build_digest_scores(market, rss, conn, rules, _tickers(), events=backdrop)
        post = format_digest(scores, backdrop=backdrop)
        if cfg.discord_digest_channel_id:
            ctx.bot.loop.create_task(_send_digest(ctx, post))

    def maintenance():
        maintenance_job(conn, cfg.article_retention_days)

    sched = build_scheduler(
        cfg, digest_cb=digest, crawl_cb=crawl, maintenance_cb=maintenance
    )
    sched.start()
    return sched


async def _send_digest(ctx, text):  # pragma: no cover
    channel = ctx.bot.get_channel(int(ctx.cfg.discord_digest_channel_id))
    if channel:
        for chunk in chunk_message(text):
            await channel.send(chunk)


def main() -> None:  # pragma: no cover - runs the live client
    ctx = bootstrap()
    _start_scheduler(ctx)
    ctx.bot.run(ctx.cfg.discord_token)


if __name__ == "__main__":  # pragma: no cover
    main()
