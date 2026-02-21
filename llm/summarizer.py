"""LLM-based content summarizer using OpenAI-compatible API."""

import logging
from typing import Optional

from openai import AsyncOpenAI

import config
from fetchers.base import Article

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一个专业的信息摘要助手。你的任务是将多个信息源的内容整理成一份结构清晰、重点突出的每日简报。

要求：
1. 按信息源分组展示
2. 每个信息源下列出关键要点（bullet points）
3. 突出重要新闻和事件
4. 使用简洁明了的中文
5. 如果内容是英文，翻译为中文摘要
6. 在末尾给出一句话总结今日要闻

格式模板：
📰 **每日信息摘要**
━━━━━━━━━━━━━━━

**📌 [信息源名称]**
• 要点1
• 要点2
...

**📌 [信息源名称]**
• 要点1
• 要点2
...

━━━━━━━━━━━━━━━
💡 **今日一句话**: [一句话概括今天最重要的信息]
"""


async def summarize_articles(
    articles_by_source: dict[str, list[Article]],
) -> Optional[str]:
    """Summarize articles grouped by source using LLM.
    
    Args:
        articles_by_source: Dict mapping source names to lists of articles.
        
    Returns:
        Formatted summary string, or None on failure.
    """
    if not articles_by_source:
        return None

    # Build the user prompt with all articles
    parts = []
    total_articles = 0
    for source_name, articles in articles_by_source.items():
        parts.append(f"\n=== 信息源: {source_name} ===")
        for i, article in enumerate(articles, 1):
            parts.append(f"\n--- 文章 {i} ---")
            parts.append(article.summary_text())
            total_articles += 1

    if total_articles == 0:
        return None

    user_content = (
        f"以下是今天从 {len(articles_by_source)} 个信息源获取的 "
        f"{total_articles} 篇内容，请生成每日摘要：\n"
        + "\n".join(parts)
    )

    # Truncate if too long (keep under ~12k chars for most models)
    if len(user_content) > 12000:
        user_content = user_content[:12000] + "\n\n[内容过长，已截断...]"

    try:
        client = AsyncOpenAI(
            api_key=config.OPENAI_API_KEY,
            base_url=config.OPENAI_BASE_URL,
        )

        response = await client.chat.completions.create(
            model=config.LLM_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.3,
            max_tokens=2000,
        )

        summary = response.choices[0].message.content
        logger.info(f"Generated summary for {total_articles} articles from {len(articles_by_source)} sources")
        return summary

    except Exception as e:
        logger.error(f"LLM summarization failed: {e}")
        return None
