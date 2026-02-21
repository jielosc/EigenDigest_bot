"""Generic web page content fetcher."""

import logging
import re
from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup

from fetchers.base import Article, BaseFetcher

logger = logging.getLogger(__name__)

# Common headers to mimic a browser
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


class WebFetcher(BaseFetcher):
    """Fetches and extracts main content from web pages."""

    async def fetch(self, url: str, source_name: str = "") -> list[Article]:
        """Fetch a web page and extract its main content."""
        try:
            async with httpx.AsyncClient(
                timeout=30, follow_redirects=True, headers=HEADERS
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "html.parser")

            # Remove script, style, nav, footer, header tags
            for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                tag.decompose()

            # Try to find main content area
            content_el = (
                soup.find("article")
                or soup.find("main")
                or soup.find("div", class_=re.compile(r"content|article|post|entry", re.I))
                or soup.find("div", id=re.compile(r"content|article|post|entry", re.I))
            )

            if content_el:
                text = content_el.get_text(separator="\n", strip=True)
            else:
                # Fallback: use body text
                body = soup.find("body")
                text = body.get_text(separator="\n", strip=True) if body else ""

            # Clean up excessive whitespace
            text = re.sub(r"\n{3,}", "\n\n", text)
            text = text[:5000]  # Limit length

            title = ""
            title_tag = soup.find("title")
            if title_tag:
                title = title_tag.get_text(strip=True)

            if not text.strip():
                logger.warning(f"No content extracted from: {url}")
                return []

            article = Article(
                title=title or source_name or url,
                content=text,
                url=url,
                source_name=source_name,
                published_at=datetime.now(timezone.utc),
            )

            logger.info(f"Fetched web page: {source_name} ({url}) — {len(text)} chars")
            return [article]

        except Exception as e:
            logger.error(f"Error fetching web page {url}: {e}")
            return []
