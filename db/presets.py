"""Preset source group templates for quick import."""

# Each template is a dict: name -> list of sources
# source: {name, url, source_type}

PRESET_GROUPS: dict[str, list[dict]] = {
    "科技与AI": [
        {"name": "OpenAI 博客", "url": "https://openai.com/blog/rss.xml", "source_type": "rss"},
        {"name": "Hugging Face 博客", "url": "https://huggingface.co/blog/feed.xml", "source_type": "rss"},
        {"name": "AI News", "url": "https://www.artificialintelligence-news.com/feed/", "source_type": "rss"},
        {"name": "The Batch", "url": "https://www.deeplearning.ai/the-batch/feed/", "source_type": "rss"},
        {"name": "VentureBeat AI", "url": "https://venturebeat.com/ai/feed/", "source_type": "rss"},
        {"name": "Hacker News", "url": "https://news.ycombinator.com/rss", "source_type": "rss"},
        {"name": "TechCrunch", "url": "https://techcrunch.com/feed/", "source_type": "rss"},
        {"name": "The Verge", "url": "https://www.theverge.com/rss/index.xml", "source_type": "rss"},
        {"name": "Ars Technica", "url": "https://feeds.arstechnica.com/arstechnica/index", "source_type": "rss"},
        {"name": "WIRED", "url": "https://www.wired.com/feed/rss", "source_type": "rss"},
        {"name": "36氪", "url": "https://36kr.com/feed", "source_type": "rss"},
        {"name": "少数派", "url": "https://sspai.com/feed", "source_type": "rss"},
        {"name": "虎嗅", "url": "https://www.huxiu.com/rss/0.xml", "source_type": "rss"},
        {"name": "爱范儿", "url": "https://www.ifanr.com/feed", "source_type": "rss"},
        {"name": "InfoQ 中文", "url": "https://www.infoq.cn/feed", "source_type": "rss"},
    ],
    "开发与开源": [
        {"name": "GitHub Blog", "url": "https://github.blog/feed/", "source_type": "rss"},
        {"name": "InfoQ", "url": "https://feed.infoq.com/", "source_type": "rss"},
        {"name": "Stack Overflow Blog", "url": "https://stackoverflow.blog/feed/", "source_type": "rss"},
        {"name": "Smashing Magazine", "url": "https://www.smashingmagazine.com/feed/", "source_type": "rss"},
        {"name": "DZone", "url": "https://feeds.dzone.com/home", "source_type": "rss"},
        {"name": "GitHub 趋势", "url": "https://mshibanami.github.io/GitHubTrendingRSS/daily/all.xml", "source_type": "rss"},
        {"name": "开源中国", "url": "https://www.oschina.net/news/rss", "source_type": "rss"},
        {"name": "CNCF Blog", "url": "https://www.cncf.io/feed/", "source_type": "rss"},
        {"name": "Python Insider", "url": "https://feeds.feedburner.com/PythonInsider", "source_type": "rss"},
        {"name": "Rust Blog", "url": "https://blog.rust-lang.org/feed.xml", "source_type": "rss"},
    ],
    "商业财经": [
        {"name": "华尔街日报", "url": "https://feeds.a.dj.com/rss/RSSWSJD.xml", "source_type": "rss"},
        {"name": "Bloomberg Markets", "url": "https://feeds.bloomberg.com/markets/news.rss", "source_type": "rss"},
        {"name": "CNBC财经", "url": "https://www.cnbc.com/id/10000664/device/rss/rss.html", "source_type": "rss"},
        {"name": "Reuters Business", "url": "https://feeds.reuters.com/reuters/businessNews", "source_type": "rss"},
        {"name": "Financial Times", "url": "https://www.ft.com/rss/home", "source_type": "rss"},
    ],
    "设计产品": [
        {"name": "Dribbble Stories", "url": "https://dribbble.com/stories.rss", "source_type": "rss"},
        {"name": "Design Milk", "url": "https://design-milk.com/feed/", "source_type": "rss"},
        {"name": "A List Apart", "url": "https://alistapart.com/main/feed/", "source_type": "rss"},
        {"name": "UX Collective", "url": "https://uxdesign.cc/feed", "source_type": "rss"},
        {"name": "CSS-Tricks", "url": "https://css-tricks.com/feed/", "source_type": "rss"},
    ],
    "网络安全": [
        {"name": "The Hacker News", "url": "https://feeds.feedburner.com/TheHackersNews", "source_type": "rss"},
        {"name": "Krebs on Security", "url": "https://krebsonsecurity.com/feed/", "source_type": "rss"},
        {"name": "Schneier on Security", "url": "https://www.schneier.com/feed/atom/", "source_type": "rss"},
        {"name": "BleepingComputer", "url": "https://www.bleepingcomputer.com/feed/", "source_type": "rss"},
    ],
}

# New users import only core groups by default, then expand via /presets.
DEFAULT_ONBOARDING_GROUPS: list[str] = [
    "科技与AI",
]


def get_preset_names() -> list[str]:
    """Return all preset group names."""
    return list(PRESET_GROUPS.keys())


def get_onboarding_preset_names() -> list[str]:
    """Return the preset groups auto-imported for new users."""
    return [name for name in DEFAULT_ONBOARDING_GROUPS if name in PRESET_GROUPS]


def _normalize_preset_name(name: str) -> str:
    """Normalize preset name for tolerant matching."""
    return "".join(name.lower().split())


def get_preset(name: str) -> list[dict] | None:
    """Get a preset group's sources by name (case-insensitive match)."""
    # Exact match first
    if name in PRESET_GROUPS:
        return PRESET_GROUPS[name]
    target = _normalize_preset_name(name)
    # Case-insensitive + ignore spaces
    for key, val in PRESET_GROUPS.items():
        if _normalize_preset_name(key) == target:
            return val
    return None


def get_preset_key(name: str) -> str | None:
    """Get the canonical preset key name."""
    if name in PRESET_GROUPS:
        return name
    target = _normalize_preset_name(name)
    for key in PRESET_GROUPS:
        if _normalize_preset_name(key) == target:
            return key
    return None
