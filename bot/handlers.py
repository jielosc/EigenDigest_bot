"""Telegram bot command handlers."""

import logging
import re

from telegram import Update
from telegram.ext import ContextTypes

import config
from db import models
from db.presets import PRESET_GROUPS, get_preset, get_preset_key, get_preset_names

logger = logging.getLogger(__name__)


def admin_only(func):
    """Decorator to restrict commands to the admin user."""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != config.ADMIN_USER_ID:
            await update.message.reply_text("⛔ 你没有权限使用此 Bot。")
            return
        return await func(update, context)
    return wrapper


# ─── Basic Commands ──────────────────────────────────────────────


@admin_only
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    current_time = models.get_setting("digest_time", "08:00")
    await update.message.reply_text(
        "🤖 **EigenDigest Bot**\n\n"
        "每天定时为你总结各信息源的内容。\n\n"
        "📋 **基础命令：**\n"
        "`/add <类型> <名称> <URL>` — 添加信息源\n"
        "`/remove <名称>` — 删除信息源\n"
        "`/list` — 查看所有信息源\n"
        "`/toggle <名称>` — 启用/禁用信息源\n"
        f"`/settime <HH:MM>` — 推送时间 (当前: {current_time})\n"
        "`/digest` — 立即生成摘要\n\n"
        "📂 **分组管理：**\n"
        "`/groups` — 查看所有分组\n"
        "`/import <分组名>` — 导入预设信息源\n"
        "`/presets` — 查看可导入的预设\n"
        "`/delgroup <分组名>` — 删除整组\n"
        "`/togglegroup <分组名>` — 启用/禁用整组\n\n"
        "`/help` — 查看详细帮助",
        parse_mode="Markdown",
    )


@admin_only
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command."""
    await update.message.reply_text(
        "📖 **使用指南**\n\n"
        "**1️⃣ 快速开始 — 导入预设**\n"
        "`/presets` — 查看可用预设\n"
        "`/import 科技` — 一键导入科技类源\n"
        "`/import AI` — 一键导入 AI 类源\n\n"
        "**2️⃣ 手动添加信息源**\n"
        "`/add rss HackerNews https://hnrss.org/newest`\n"
        "`/add web 36kr https://36kr.com`\n"
        "可选指定分组:\n"
        "`/add rss 名称 URL 分组名`\n\n"
        "**3️⃣ 分组管理**\n"
        "`/groups` — 查看分组概览\n"
        "`/togglegroup 科技` — 启用/禁用整组\n"
        "`/delgroup 科技` — 删除整组\n\n"
        "**4️⃣ 单条管理**\n"
        "`/list` — 查看所有\n"
        "`/remove 名称` — 删除\n"
        "`/toggle 名称` — 启用/禁用\n\n"
        "**5️⃣ 定时推送**\n"
        "`/settime 09:30` — 设置推送时间\n"
        "`/digest` — 立即生成摘要\n\n"
        "💡 微信公众号推荐通过 [RSSHub](https://docs.rsshub.app/) 转为 RSS 后添加。",
        parse_mode="Markdown",
    )


# ─── Source CRUD ──────────────────────────────────────────────


@admin_only
async def add_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /add <type> <name> <url> [group] command."""
    args = context.args
    if not args or len(args) < 3:
        await update.message.reply_text(
            "❌ 用法: `/add <类型> <名称> <URL> [分组]`\n"
            "类型: `rss` / `web` / `wechat`\n\n"
            "示例:\n"
            "`/add rss HackerNews https://hnrss.org/newest`\n"
            "`/add rss HackerNews https://hnrss.org/newest 科技`",
            parse_mode="Markdown",
        )
        return

    source_type = args[0].lower()
    name = args[1]
    url = args[2]
    group_name = args[3] if len(args) > 3 else "默认"

    if source_type not in ("rss", "web", "wechat"):
        await update.message.reply_text(
            "❌ 不支持的类型。请使用: `rss`, `web`, `wechat`",
            parse_mode="Markdown",
        )
        return

    if not url.startswith(("http://", "https://")):
        await update.message.reply_text("❌ URL 必须以 http:// 或 https:// 开头")
        return

    success = models.add_source(name, url, source_type, group_name)
    if success:
        emoji = {"rss": "📡", "web": "🌐", "wechat": "💬"}.get(source_type, "📰")
        await update.message.reply_text(
            f"✅ 已添加信息源:\n"
            f"{emoji} **{name}** ({source_type})\n"
            f"📂 分组: {group_name}\n"
            f"🔗 `{url}`",
            parse_mode="Markdown",
        )
    else:
        await update.message.reply_text("❌ 添加失败，该 URL 可能已存在。")


@admin_only
async def remove_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /remove <name> command."""
    if not context.args:
        await update.message.reply_text(
            "❌ 用法: `/remove <名称>`\n"
            "使用 `/list` 查看所有信息源。",
            parse_mode="Markdown",
        )
        return

    name = context.args[0]
    success = models.remove_source(name)
    if success:
        await update.message.reply_text(f"✅ 已删除信息源: **{name}**", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"❌ 未找到信息源: **{name}**", parse_mode="Markdown")


@admin_only
async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /list command — shows sources grouped by group_name."""
    sources = models.list_sources()
    if not sources:
        await update.message.reply_text(
            "📭 暂无信息源。\n"
            "使用 `/add` 添加，或 `/import` 导入预设。",
            parse_mode="Markdown",
        )
        return

    current_time = models.get_setting("digest_time", "08:00")
    type_emoji = {"rss": "📡", "web": "🌐", "wechat": "💬"}

    # Group by group_name
    groups: dict[str, list] = {}
    for s in sources:
        groups.setdefault(s["group_name"], []).append(s)

    lines = [f"📋 **信息源列表** (推送时间: {current_time})\n"]
    for gname, items in groups.items():
        enabled_count = sum(1 for i in items if i["enabled"])
        lines.append(f"📂 **{gname}** ({enabled_count}/{len(items)} 启用)")
        for s in items:
            status = "✅" if s["enabled"] else "⏸️"
            emoji = type_emoji.get(s["source_type"], "📰")
            lines.append(f"  {status} {emoji} {s['name']}")
        lines.append("")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


@admin_only
async def toggle_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /toggle <name> command."""
    if not context.args:
        await update.message.reply_text(
            "❌ 用法: `/toggle <名称>`",
            parse_mode="Markdown",
        )
        return

    name = context.args[0]
    new_state = models.toggle_source(name)
    if new_state is None:
        await update.message.reply_text(f"❌ 未找到信息源: **{name}**", parse_mode="Markdown")
    else:
        status = "✅ 已启用" if new_state else "⏸️ 已禁用"
        await update.message.reply_text(f"{status}: **{name}**", parse_mode="Markdown")


# ─── Group Management ────────────────────────────────────────


@admin_only
async def groups_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /groups command — show group overview."""
    groups = models.list_groups()
    if not groups:
        await update.message.reply_text(
            "📭 暂无分组。\n"
            "使用 `/import` 导入预设，或 `/add` 添加信息源时指定分组。",
            parse_mode="Markdown",
        )
        return

    lines = ["📂 **分组概览**\n"]
    for g in groups:
        lines.append(
            f"• **{g['group_name']}** — "
            f"{g['enabled_count']}/{g['count']} 启用"
        )
    lines.append(f"\n管理: `/togglegroup <分组>` | `/delgroup <分组>`")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


@admin_only
async def presets_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /presets command — show available preset groups."""
    lines = ["📦 **可导入的预设信息源**\n"]
    for name, sources in PRESET_GROUPS.items():
        source_names = ", ".join(s["name"] for s in sources)
        lines.append(f"**{name}** ({len(sources)} 个源)")
        lines.append(f"  _{source_names}_\n")
    lines.append("使用 `/import <分组名>` 一键导入")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


@admin_only
async def import_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /import <preset_name> command — batch import a preset group."""
    if not context.args:
        await update.message.reply_text(
            "❌ 用法: `/import <分组名>`\n\n"
            "使用 `/presets` 查看可用预设。",
            parse_mode="Markdown",
        )
        return

    name = context.args[0]
    preset_sources = get_preset(name)
    canonical_name = get_preset_key(name)

    if preset_sources is None or canonical_name is None:
        available = ", ".join(f"`{n}`" for n in get_preset_names())
        await update.message.reply_text(
            f"❌ 未找到预设: **{name}**\n\n"
            f"可用预设: {available}",
            parse_mode="Markdown",
        )
        return

    # Add group_name to each source
    batch = [
        {**s, "group_name": canonical_name} for s in preset_sources
    ]
    success, skipped = models.add_sources_batch(batch)

    msg = f"📦 **已导入预设「{canonical_name}」**\n\n"
    msg += f"✅ 成功添加: {success} 个源\n"
    if skipped:
        msg += f"⏭️ 跳过 (已存在): {skipped} 个\n"
    msg += f"\n使用 `/list` 查看所有信息源。"

    await update.message.reply_text(msg, parse_mode="Markdown")


@admin_only
async def delgroup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /delgroup <group_name> — delete all sources in a group."""
    if not context.args:
        await update.message.reply_text(
            "❌ 用法: `/delgroup <分组名>`\n"
            "使用 `/groups` 查看所有分组。",
            parse_mode="Markdown",
        )
        return

    group_name = context.args[0]
    count = models.remove_group(group_name)
    if count > 0:
        await update.message.reply_text(
            f"🗑️ 已删除分组 **{group_name}** 中的 {count} 个信息源。",
            parse_mode="Markdown",
        )
    else:
        await update.message.reply_text(
            f"❌ 未找到分组: **{group_name}**",
            parse_mode="Markdown",
        )


@admin_only
async def togglegroup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /togglegroup <group_name> — enable/disable all in a group."""
    if not context.args:
        await update.message.reply_text(
            "❌ 用法: `/togglegroup <分组名>`",
            parse_mode="Markdown",
        )
        return

    group_name = context.args[0]
    new_state = models.toggle_group(group_name)
    if new_state is None:
        await update.message.reply_text(
            f"❌ 未找到分组: **{group_name}**",
            parse_mode="Markdown",
        )
    else:
        status = "✅ 已启用" if new_state else "⏸️ 已禁用"
        await update.message.reply_text(
            f"{status} 分组: **{group_name}**",
            parse_mode="Markdown",
        )


# ─── Scheduling & Digest ─────────────────────────────────────


@admin_only
async def settime_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /settime <HH:MM> command."""
    if not context.args:
        current = models.get_setting("digest_time", "08:00")
        await update.message.reply_text(
            f"⏰ 当前推送时间: **{current}** (北京时间)\n\n"
            f"用法: `/settime HH:MM`\n"
            f"示例: `/settime 09:30`",
            parse_mode="Markdown",
        )
        return

    time_str = context.args[0]
    match = re.match(r"^(\d{1,2}):(\d{2})$", time_str)
    if not match:
        await update.message.reply_text("❌ 时间格式错误，请使用 HH:MM 格式（如 09:30）")
        return

    hour, minute = int(match.group(1)), int(match.group(2))
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        await update.message.reply_text("❌ 时间超出范围（00:00 — 23:59）")
        return

    time_formatted = f"{hour:02d}:{minute:02d}"
    models.set_setting("digest_time", time_formatted)

    from bot.scheduler import reschedule_digest
    await reschedule_digest(context.application)

    await update.message.reply_text(
        f"✅ 推送时间已设置为 **{time_formatted}** (北京时间)",
        parse_mode="Markdown",
    )


@admin_only
async def digest_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /digest command — trigger immediate summary."""
    await update.message.reply_text("⏳ 正在抓取内容并生成摘要，请稍候...")

    from bot.scheduler import run_digest
    summary = await run_digest()

    if summary:
        if len(summary) > 4000:
            for i in range(0, len(summary), 4000):
                await update.message.reply_text(
                    summary[i : i + 4000], parse_mode="Markdown"
                )
        else:
            await update.message.reply_text(summary, parse_mode="Markdown")
    else:
        await update.message.reply_text(
            "😕 无法生成摘要。\n"
            "可能原因:\n"
            "• 没有启用的信息源\n"
            "• 信息源没有新内容\n"
            "• LLM API 调用失败\n\n"
            "请检查日志获取详细信息。"
        )
