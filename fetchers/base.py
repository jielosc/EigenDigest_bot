"""Base classes for content fetchers."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from abc import ABC, abstractmethod


@dataclass
class Article:
    """Represents a fetched article/content piece."""
    title: str
    content: str
    url: str
    source_name: str = ""
    published_at: Optional[datetime] = None

    def summary_text(self) -> str:
        """Return a compact representation for LLM input."""
        parts = [f"标题: {self.title}"]
        if self.published_at:
            parts.append(f"时间: {self.published_at.strftime('%Y-%m-%d %H:%M')}")
        parts.append(f"内容: {self.content[:2000]}")
        return "\n".join(parts)


class BaseFetcher(ABC):
    """Abstract base class for all fetchers."""

    @abstractmethod
    async def fetch(self, url: str, source_name: str = "") -> list[Article]:
        """Fetch articles from the given URL.
        
        Args:
            url: The source URL to fetch from.
            source_name: Human-readable name for the source.
            
        Returns:
            List of Article objects.
        """
        ...
