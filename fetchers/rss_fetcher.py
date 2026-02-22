"""RSS/Atom feed fetcher."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import feedparser

from fetchers.base import Article, BaseFetcher

logger = logging.getLogger(__name__)


class RSSFetcher(BaseFetcher):
    """Fetches articles from RSS/Atom feeds."""

    async def fetch(self, url: str, source_name: str = "") -> list[Article]:
        """Parse RSS feed and return recent articles (last 24h)."""
        try:
            # feedparser.parse is blocking I/O; move it off the event loop.
            feed = await asyncio.to_thread(feedparser.parse, url)
            if feed.bozo and not feed.entries:
                logger.warning(f"Failed to parse RSS feed: {url} — {feed.bozo_exception}")
                return []

            articles = []
            cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

            for entry in feed.entries[:20]:  # Limit to 20 most recent
                # Parse published date
                published = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                    published = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)

                # Skip old articles if we have a date
                if published and published < cutoff:
                    continue

                # Extract content
                content = ""
                if hasattr(entry, "content") and entry.content:
                    content = entry.content[0].get("value", "")
                elif hasattr(entry, "summary"):
                    content = entry.summary or ""
                elif hasattr(entry, "description"):
                    content = entry.description or ""

                # Strip HTML tags (simple approach)
                content = self._strip_html(content)

                title = entry.get("title", "无标题")
                link = entry.get("link", url)

                articles.append(Article(
                    title=title,
                    content=content[:3000],  # Limit content length
                    url=link,
                    source_name=source_name,
                    published_at=published,
                ))

            logger.info(f"Fetched {len(articles)} articles from RSS: {source_name} ({url})")
            return articles

        except Exception as e:
            logger.error(f"Error fetching RSS {url}: {e}")
            return []

    @staticmethod
    def _strip_html(html: str) -> str:
        """Remove HTML tags from content."""
        import re
        text = re.sub(r"<[^>]+>", "", html)
        text = re.sub(r"\s+", " ", text).strip()
        # Decode common HTML entities
        text = text.replace("&amp;", "&")
        text = text.replace("&lt;", "<")
        text = text.replace("&gt;", ">")
        text = text.replace("&quot;", '"')
        text = text.replace("&#39;", "'")
        text = text.replace("&nbsp;", " ")
        return text
