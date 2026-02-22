"""Scheduler for daily digest — multi-user version."""

import asyncio
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

import config
from db import models
from fetchers.rss_fetcher import RSSFetcher
from fetchers.web_fetcher import WebFetcher
from fetchers.base import Article
from llm.summarizer import summarize_articles

logger = logging.getLogger(__name__)

# Fetcher instances
_rss_fetcher = RSSFetcher()
_web_fetcher = WebFetcher()

# Global scheduler reference
_scheduler: AsyncIOScheduler | None = None

DIGEST_JOB_ID = "daily_digest_check"
MAX_CONCURRENT_DIGESTS = 5


def _get_fetcher(source_type: str):
    """Get the appropriate fetcher for a source type."""
    if source_type in ("rss", "wechat"):
        return _rss_fetcher
    elif source_type == "web":
        return _web_fetcher
    return _rss_fetcher


async def run_digest_for_user(user_id: int) -> str | None:
    """Run the digest pipeline for a specific user.
    
    Returns:
        Summary text, or None if no content.
    """
    sources = models.get_enabled_sources(user_id)
    if not sources:
        logger.info(f"User {user_id}: no enabled sources, skipping.")
        return None

    logger.info(f"User {user_id}: fetching from {len(sources)} sources...")

    async def fetch_source(source: dict) -> tuple[str, list[Article]]:
        fetcher = _get_fetcher(source["source_type"])
        articles = await fetcher.fetch(source["url"], source["name"])
        return source["name"], articles

    results = await asyncio.gather(
        *[fetch_source(s) for s in sources],
        return_exceptions=True,
    )

    articles_by_source: dict[str, list[Article]] = {}
    for result in results:
        if isinstance(result, Exception):
            logger.error(f"User {user_id} fetch error: {result}")
            continue
        name, articles = result
        if articles:
            articles_by_source[name] = articles

    if not articles_by_source:
        logger.info(f"User {user_id}: no articles fetched.")
        return None

    total = sum(len(a) for a in articles_by_source.values())
    logger.info(f"User {user_id}: {total} articles from {len(articles_by_source)} sources. Summarizing...")

    summary = await summarize_articles(articles_by_source)
    return summary


async def _send_digest(app, user_id: int, summary: str) -> None:
    """Send digest message to a user, splitting if too long."""
    try:
        if len(summary) > 4000:
            for i in range(0, len(summary), 4000):
                await app.bot.send_message(
                    chat_id=user_id,
                    text=summary[i:i+4000],
                    parse_mode="Markdown",
                )
        else:
            await app.bot.send_message(
                chat_id=user_id,
                text=summary,
                parse_mode="Markdown",
            )
    except Exception as e:
        logger.error(f"Failed to send digest to user {user_id}: {e}")


async def _scheduled_digest_check(app) -> None:
    """Called every minute by scheduler. Check which users need digest now."""
    tz = ZoneInfo(config.TIMEZONE)
    now = datetime.now(tz)
    current_time = f"{now.hour:02d}:{now.minute:02d}"

    user_ids = models.get_all_user_ids()
    due_user_ids = [
        uid
        for uid in user_ids
        if models.get_setting(uid, "digest_time", "08:00") == current_time
    ]
    if not due_user_ids:
        return

    logger.info(f"Scheduled digest triggered for {len(due_user_ids)} user(s) at {current_time}")
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_DIGESTS)

    async def run_for_due_user(uid: int) -> None:
        async with semaphore:
            try:
                summary = await run_digest_for_user(uid)
                if summary:
                    await _send_digest(app, uid, summary)
                    logger.info(f"Digest sent to user {uid}")
                else:
                    logger.info(f"No digest content for user {uid}")
            except Exception as e:
                logger.error(f"Digest failed for user {uid}: {e}")

    await asyncio.gather(*(run_for_due_user(uid) for uid in due_user_ids))


def setup_scheduler(app) -> AsyncIOScheduler:
    """Set up scheduler — runs every minute to check per-user digest times."""
    global _scheduler

    tz = ZoneInfo(config.TIMEZONE)

    _scheduler = AsyncIOScheduler(timezone=tz)
    _scheduler.add_job(
        _scheduled_digest_check,
        trigger=CronTrigger(minute="*", timezone=tz),  # Every minute
        id=DIGEST_JOB_ID,
        args=[app],
        replace_existing=True,
    )
    _scheduler.start()

    logger.info(f"Scheduler started — checking digest times every minute ({config.TIMEZONE})")
    return _scheduler
