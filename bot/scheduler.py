"""Scheduler for daily digest and the core digest pipeline."""

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

DIGEST_JOB_ID = "daily_digest"


def _get_fetcher(source_type: str):
    """Get the appropriate fetcher for a source type."""
    if source_type in ("rss", "wechat"):
        return _rss_fetcher
    elif source_type == "web":
        return _web_fetcher
    else:
        return _rss_fetcher  # default fallback


async def run_digest() -> str | None:
    """Run the full digest pipeline: fetch → summarize → return text.
    
    Returns:
        The summary text, or None if no content was available.
    """
    sources = models.get_enabled_sources()
    if not sources:
        logger.warning("No enabled sources found for digest.")
        return None

    logger.info(f"Starting digest for {len(sources)} sources...")

    # Fetch from all sources concurrently
    async def fetch_source(source: dict) -> tuple[str, list[Article]]:
        fetcher = _get_fetcher(source["source_type"])
        articles = await fetcher.fetch(source["url"], source["name"])
        return source["name"], articles

    results = await asyncio.gather(
        *[fetch_source(s) for s in sources],
        return_exceptions=True,
    )

    # Group articles by source
    articles_by_source: dict[str, list[Article]] = {}
    for result in results:
        if isinstance(result, Exception):
            logger.error(f"Fetch error: {result}")
            continue
        name, articles = result
        if articles:
            articles_by_source[name] = articles

    if not articles_by_source:
        logger.warning("No articles fetched from any source.")
        return None

    total = sum(len(a) for a in articles_by_source.values())
    logger.info(f"Fetched {total} articles from {len(articles_by_source)} sources. Summarizing...")

    # Generate summary via LLM
    summary = await summarize_articles(articles_by_source)
    return summary


async def _scheduled_digest(app) -> None:
    """Called by scheduler — runs digest and sends to admin."""
    logger.info("Scheduled digest triggered.")
    summary = await run_digest()

    if summary:
        try:
            # Send to admin, handle long messages
            if len(summary) > 4000:
                for i in range(0, len(summary), 4000):
                    await app.bot.send_message(
                        chat_id=config.ADMIN_USER_ID,
                        text=summary[i : i + 4000],
                        parse_mode="Markdown",
                    )
            else:
                await app.bot.send_message(
                    chat_id=config.ADMIN_USER_ID,
                    text=summary,
                    parse_mode="Markdown",
                )
            logger.info("Digest sent to admin successfully.")
        except Exception as e:
            logger.error(f"Failed to send digest to admin: {e}")
    else:
        logger.warning("No digest content generated, skipping notification.")


def _get_digest_time() -> tuple[int, int]:
    """Get digest time from DB settings, with fallback to config defaults."""
    time_str = models.get_setting("digest_time", "")
    if time_str:
        try:
            parts = time_str.split(":")
            return int(parts[0]), int(parts[1])
        except (ValueError, IndexError):
            pass
    return config.DEFAULT_DIGEST_HOUR, config.DEFAULT_DIGEST_MINUTE


def setup_scheduler(app) -> AsyncIOScheduler:
    """Set up the APScheduler for daily digest."""
    global _scheduler

    hour, minute = _get_digest_time()
    tz = ZoneInfo(config.TIMEZONE)

    _scheduler = AsyncIOScheduler(timezone=tz)
    _scheduler.add_job(
        _scheduled_digest,
        trigger=CronTrigger(hour=hour, minute=minute, timezone=tz),
        id=DIGEST_JOB_ID,
        args=[app],
        replace_existing=True,
    )
    _scheduler.start()

    logger.info(f"Scheduler started — daily digest at {hour:02d}:{minute:02d} ({config.TIMEZONE})")
    return _scheduler


async def reschedule_digest(app) -> None:
    """Reschedule the digest job (called when user changes time via /settime)."""
    global _scheduler

    if _scheduler is None:
        logger.warning("Scheduler not initialized, cannot reschedule.")
        return

    hour, minute = _get_digest_time()
    tz = ZoneInfo(config.TIMEZONE)

    _scheduler.reschedule_job(
        DIGEST_JOB_ID,
        trigger=CronTrigger(hour=hour, minute=minute, timezone=tz),
    )

    logger.info(f"Digest rescheduled to {hour:02d}:{minute:02d} ({config.TIMEZONE})")
