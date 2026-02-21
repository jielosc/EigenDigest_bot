"""Preset source group templates for quick import."""

# Each template is a dict: name -> list of sources
# source: {name, url, source_type}

PRESET_GROUPS: dict[str, list[dict]] = {
    "科技": [
        {"name": "HackerNews", "url": "https://hnrss.org/newest?count=20", "source_type": "rss"},
        {"name": "TechCrunch", "url": "https://techcrunch.com/feed/", "source_type": "rss"},
        {"name": "TheVerge", "url": "https://www.theverge.com/rss/index.xml", "source_type": "rss"},
        {"name": "ArsTechnica", "url": "https://feeds.arstechnica.com/arstechnica/index", "source_type": "rss"},
    ],
    "AI": [
        {"name": "OpenAI博客", "url": "https://openai.com/blog/rss.xml", "source_type": "rss"},
        {"name": "HuggingFace博客", "url": "https://huggingface.co/blog/feed.xml", "source_type": "rss"},
        {"name": "AI新闻", "url": "https://www.artificialintelligence-news.com/feed/", "source_type": "rss"},
    ],
    "中文科技": [
        {"name": "36氪", "url": "https://36kr.com/feed", "source_type": "rss"},
        {"name": "少数派", "url": "https://sspai.com/feed", "source_type": "rss"},
        {"name": "虎嗅", "url": "https://www.huxiu.com/rss/0.xml", "source_type": "rss"},
    ],
    "财经": [
        {"name": "华尔街日报", "url": "https://feeds.a]@wsj.com/tag/rssfeeds/wsj/xml", "source_type": "rss"},
        {"name": "Bloomberg", "url": "https://feeds.bloomberg.com/markets/news.rss", "source_type": "rss"},
        {"name": "Reuters", "url": "https://www.reutersagency.com/feed/", "source_type": "rss"},
    ],
    "设计": [
        {"name": "Dribbble", "url": "https://dribbble.com/shots/popular.rss", "source_type": "rss"},
        {"name": "DesignMilk", "url": "https://design-milk.com/feed/", "source_type": "rss"},
    ],
    "开源": [
        {"name": "GitHub趋势", "url": "https://mshibanami.github.io/GitHubTrendingRSS/daily/all.xml", "source_type": "rss"},
        {"name": "开源中国", "url": "https://www.oschina.net/news/rss", "source_type": "rss"},
    ],
}


def get_preset_names() -> list[str]:
    """Return all preset group names."""
    return list(PRESET_GROUPS.keys())


def get_preset(name: str) -> list[dict] | None:
    """Get a preset group's sources by name (case-insensitive match)."""
    # Exact match first
    if name in PRESET_GROUPS:
        return PRESET_GROUPS[name]
    # Case-insensitive
    for key, val in PRESET_GROUPS.items():
        if key.lower() == name.lower():
            return val
    return None


def get_preset_key(name: str) -> str | None:
    """Get the canonical preset key name."""
    if name in PRESET_GROUPS:
        return name
    for key in PRESET_GROUPS:
        if key.lower() == name.lower():
            return key
    return None
