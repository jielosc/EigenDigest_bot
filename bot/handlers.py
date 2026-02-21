"""Telegram bot command handlers — multi-user version."""

import logging
import re

from telegram import Update
from telegram.ext import ContextTypes

import config
from db import models
from db.presets import PRESET_GROUPS, get_preset, get_preset_key, get_preset_names

logger = logging.getLogger(__name__)


# ─── Auth Decorators ─────────────────────────────────────────


def authorized(func):
    """Decorator: only authorized users (in users table) can use this command."""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        uid = update.effective_user.id
        if not models.is_authorized(uid):
            await update.message.reply_text(
                "⛔ 你还未获得授权。\n"
                "请使用 `/join <邀请码>` 加入。",
                parse_mode="Markdown",
            )
            return
        return await func(update, context)
    return wrapper


def admin_only(func):
    """Decorator: only admin can use this command."""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        uid = update.effective_user.id
        if not models.is_admin(uid):
            await update.message.reply_text("⛔ 此命令仅管理员可用。")
            return
        return await func(update, context)
    return wrapper


def _uid(update: Update) -> int:
    """Shorthand to get user_id from update."""
    return update.effective_user.id


# ─── Public Commands (no auth required) ──────────────────────


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start — different message for authorized vs unauthed users."""
    uid = _uid(update)
    if models.is_authorized(uid):
        digest_time = models.get_setting(uid, "digest_time", "08:00")
        await update.message.reply_text(
            "🤖 **EigenDigest Bot**\n\n"
            "每天定时为你总结各信息源的内容。\n\n"
            "📋 **信息源管理：**\n"
            "`/add <类型> <名称> <URL> [分组]`\n"
            "`/remove <名称>` | `/list` | `/toggle <名称>`\n\n"
            "📂 **分组管理：**\n"
            "`/presets` | `/import <分组>` | `/groups`\n"
            "`/delgroup <分组>` | `/togglegroup <分组>`\n\n"
            "⏰ **推送设置：**\n"
            f"`/settime <HH:MM>` (当前: {digest_time})\n"
            "`/digest` — 立即生成摘要\n\n"
            "`/help` — 详细帮助",
            parse_mode="Markdown",
        )
    else:
        await update.message.reply_text(
            "🤖 **EigenDigest Bot**\n\n"
            "这是一个每日信息摘要 Bot。\n"
            "请使用邀请码加入:\n\n"
            "`/join <邀请码>`",
            parse_mode="Markdown",
        )


async def join_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /join <code> — use invite code to join."""
    uid = _uid(update)

    if models.is_authorized(uid):
        await update.message.reply_text("✅ 你已经是授权用户了！")
        return

    if not context.args:
        await update.message.reply_text(
            "❌ 用法: `/join <邀请码>`",
            parse_mode="Markdown",
        )
        return

    code = context.args[0]
    if not models.use_invite_code(code, uid):
        await update.message.reply_text("❌ 邀请码无效或已被使用。")
        return

    # Create user
    username = update.effective_user.username or update.effective_user.first_name or ""
    models.add_user(uid, username, "user")

    # Import all presets as base sources for the new user
    total_added = 0
    total_skipped = 0
    for group_name, sources in PRESET_GROUPS.items():
        batch = [{**s, "group_name": group_name} for s in sources]
        added, skipped = models.add_sources_batch(uid, batch)
        total_added += added
        total_skipped += skipped

    await update.message.reply_text(
        f"🎉 **欢迎加入 EigenDigest！**\n\n"
        f"已为你导入 {total_added} 个基础信息源。\n"
        f"你可以使用以下命令管理:\n\n"
        f"`/list` — 查看所有信息源\n"
        f"`/groups` — 查看分组\n"
        f"`/delgroup <分组>` — 删除不感兴趣的分组\n"
        f"`/import <分组>` — 导入更多预设\n"
        f"`/settime <HH:MM>` — 设置推送时间\n\n"
        f"`/help` — 查看完整帮助",
        parse_mode="Markdown",
    )


# ─── User Commands ────────────────────────────────────────────


@authorized
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command."""
    uid = _uid(update)
    is_adm = models.is_admin(uid)
    admin_section = ""
    if is_adm:
        admin_section = (
            "\n**🔑 管理员命令：**\n"
            "`/invite` — 生成邀请码\n"
            "`/users` — 查看所有用户\n"
            "`/kick <user_id>` — 移除用户\n"
        )

    await update.message.reply_text(
        "📖 **使用指南**\n\n"
        "**1️⃣ 快速开始 — 导入预设**\n"
        "`/presets` — 查看可用预设\n"
        "`/import 科技` — 一键导入\n\n"
        "**2️⃣ 手动添加**\n"
        "`/add rss 名称 URL [分组]`\n"
        "`/add web 名称 URL [分组]`\n\n"
        "**3️⃣ 分组管理**\n"
        "`/groups` | `/togglegroup <分组>` | `/delgroup <分组>`\n\n"
        "**4️⃣ 单条管理**\n"
        "`/list` | `/remove <名称>` | `/toggle <名称>`\n\n"
        "**5️⃣ 定时推送**\n"
        "`/settime 09:30` | `/digest`\n"
        + admin_section,
        parse_mode="Markdown",
    )


@authorized
async def add_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /add <type> <name> <url> [group]."""
    uid = _uid(update)
    args = context.args
    if not args or len(args) < 3:
        await update.message.reply_text(
            "❌ 用法: `/add <类型> <名称> <URL> [分组]`\n"
            "类型: `rss` / `web` / `wechat`\n\n"
            "示例: `/add rss HackerNews https://hnrss.org/newest 科技`",
            parse_mode="Markdown",
        )
        return

    source_type = args[0].lower()
    name = args[1]
    url = args[2]
    group_name = args[3] if len(args) > 3 else "默认"

    if source_type not in ("rss", "web", "wechat"):
        await update.message.reply_text("❌ 类型必须是: `rss`, `web`, `wechat`", parse_mode="Markdown")
        return
    if not url.startswith(("http://", "https://")):
        await update.message.reply_text("❌ URL 必须以 http:// 或 https:// 开头")
        return

    success = models.add_source(uid, name, url, source_type, group_name)
    if success:
        emoji = {"rss": "📡", "web": "🌐", "wechat": "💬"}.get(source_type, "📰")
        await update.message.reply_text(
            f"✅ 已添加: {emoji} **{name}** ({source_type})\n"
            f"📂 {group_name}  🔗 `{url}`",
            parse_mode="Markdown",
        )
    else:
        await update.message.reply_text("❌ 添加失败，该 URL 可能已存在。")


@authorized
async def remove_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /remove <name>."""
    uid = _uid(update)
    if not context.args:
        await update.message.reply_text("❌ 用法: `/remove <名称>`", parse_mode="Markdown")
        return
    name = context.args[0]
    if models.remove_source(uid, name):
        await update.message.reply_text(f"✅ 已删除: **{name}**", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"❌ 未找到: **{name}**", parse_mode="Markdown")


@authorized
async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /list — show user's sources grouped."""
    uid = _uid(update)
    sources = models.list_sources(uid)
    if not sources:
        await update.message.reply_text(
            "📭 暂无信息源。\n`/import <分组>` 导入预设，或 `/add` 手动添加。",
            parse_mode="Markdown",
        )
        return

    digest_time = models.get_setting(uid, "digest_time", "08:00")
    type_emoji = {"rss": "📡", "web": "🌐", "wechat": "💬"}

    groups: dict[str, list] = {}
    for s in sources:
        groups.setdefault(s["group_name"], []).append(s)

    lines = [f"📋 **我的信息源** (推送: {digest_time})\n"]
    for gname, items in groups.items():
        enabled_count = sum(1 for i in items if i["enabled"])
        lines.append(f"📂 **{gname}** ({enabled_count}/{len(items)})")
        for s in items:
            status = "✅" if s["enabled"] else "⏸️"
            emoji = type_emoji.get(s["source_type"], "📰")
            lines.append(f"  {status} {emoji} {s['name']}")
        lines.append("")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


@authorized
async def toggle_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /toggle <name>."""
    uid = _uid(update)
    if not context.args:
        await update.message.reply_text("❌ 用法: `/toggle <名称>`", parse_mode="Markdown")
        return
    name = context.args[0]
    new_state = models.toggle_source(uid, name)
    if new_state is None:
        await update.message.reply_text(f"❌ 未找到: **{name}**", parse_mode="Markdown")
    else:
        status = "✅ 已启用" if new_state else "⏸️ 已禁用"
        await update.message.reply_text(f"{status}: **{name}**", parse_mode="Markdown")


# ─── Group Management ────────────────────────────────────────


@authorized
async def groups_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /groups — show user's group overview."""
    uid = _uid(update)
    groups = models.list_groups(uid)
    if not groups:
        await update.message.reply_text(
            "📭 暂无分组。使用 `/import` 导入预设。",
            parse_mode="Markdown",
        )
        return

    lines = ["📂 **我的分组**\n"]
    for g in groups:
        lines.append(f"• **{g['group_name']}** — {g['enabled_count']}/{g['count']} 启用")
    lines.append(f"\n`/togglegroup <分组>` | `/delgroup <分组>`")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


@authorized
async def presets_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /presets — show available presets."""
    lines = ["📦 **可导入的预设**\n"]
    for name, sources in PRESET_GROUPS.items():
        source_names = ", ".join(s["name"] for s in sources)
        lines.append(f"**{name}** ({len(sources)} 个)")
        lines.append(f"  _{source_names}_\n")
    lines.append("`/import <分组名>` 一键导入")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


@authorized
async def import_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /import <preset> — batch import preset sources."""
    uid = _uid(update)
    if not context.args:
        await update.message.reply_text(
            "❌ 用法: `/import <分组名>`\n`/presets` 查看可用预设。",
            parse_mode="Markdown",
        )
        return

    name = context.args[0]
    preset_sources = get_preset(name)
    canonical_name = get_preset_key(name)

    if preset_sources is None or canonical_name is None:
        available = ", ".join(f"`{n}`" for n in get_preset_names())
        await update.message.reply_text(
            f"❌ 未找到预设: **{name}**\n可用: {available}",
            parse_mode="Markdown",
        )
        return

    batch = [{**s, "group_name": canonical_name} for s in preset_sources]
    success, skipped = models.add_sources_batch(uid, batch)

    msg = f"📦 **已导入「{canonical_name}」**\n✅ 添加: {success}"
    if skipped:
        msg += f" | ⏭️ 跳过: {skipped}"
    await update.message.reply_text(msg, parse_mode="Markdown")


@authorized
async def delgroup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /delgroup <group>."""
    uid = _uid(update)
    if not context.args:
        await update.message.reply_text("❌ 用法: `/delgroup <分组名>`", parse_mode="Markdown")
        return
    group_name = context.args[0]
    count = models.remove_group(uid, group_name)
    if count > 0:
        await update.message.reply_text(
            f"🗑️ 已删除 **{group_name}** ({count} 个源)", parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(f"❌ 未找到分组: **{group_name}**", parse_mode="Markdown")


@authorized
async def togglegroup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /togglegroup <group>."""
    uid = _uid(update)
    if not context.args:
        await update.message.reply_text("❌ 用法: `/togglegroup <分组名>`", parse_mode="Markdown")
        return
    group_name = context.args[0]
    new_state = models.toggle_group(uid, group_name)
    if new_state is None:
        await update.message.reply_text(f"❌ 未找到分组: **{group_name}**", parse_mode="Markdown")
    else:
        status = "✅ 已启用" if new_state else "⏸️ 已禁用"
        await update.message.reply_text(f"{status}: **{group_name}**", parse_mode="Markdown")


# ─── Scheduling & Digest ─────────────────────────────────────


@authorized
async def settime_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /settime <HH:MM>."""
    uid = _uid(update)
    if not context.args:
        current = models.get_setting(uid, "digest_time", "08:00")
        await update.message.reply_text(
            f"⏰ 当前推送时间: **{current}** (北京时间)\n"
            f"用法: `/settime HH:MM`",
            parse_mode="Markdown",
        )
        return

    time_str = context.args[0]
    match = re.match(r"^(\d{1,2}):(\d{2})$", time_str)
    if not match:
        await update.message.reply_text("❌ 格式错误，请使用 HH:MM（如 09:30）")
        return

    hour, minute = int(match.group(1)), int(match.group(2))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        await update.message.reply_text("❌ 时间超出范围（00:00 — 23:59）")
        return

    time_formatted = f"{hour:02d}:{minute:02d}"
    models.set_setting(uid, "digest_time", time_formatted)

    await update.message.reply_text(
        f"✅ 推送时间已设置为 **{time_formatted}** (北京时间)",
        parse_mode="Markdown",
    )


@authorized
async def digest_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /digest — trigger immediate summary for this user."""
    uid = _uid(update)
    await update.message.reply_text("⏳ 正在抓取内容并生成摘要，请稍候...")

    from bot.scheduler import run_digest_for_user
    summary = await run_digest_for_user(uid)

    if summary:
        if len(summary) > 4000:
            for i in range(0, len(summary), 4000):
                await update.message.reply_text(summary[i:i+4000], parse_mode="Markdown")
        else:
            await update.message.reply_text(summary, parse_mode="Markdown")
    else:
        await update.message.reply_text(
            "😕 无法生成摘要。\n"
            "• 没有启用的信息源\n"
            "• 信息源没有新内容\n"
            "• LLM API 调用失败"
        )


# ─── Admin Commands ───────────────────────────────────────────


@admin_only
async def invite_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /invite — generate an invite code."""
    uid = _uid(update)
    code = models.create_invite_code(uid)
    await update.message.reply_text(
        f"🎟️ **邀请码已生成**\n\n"
        f"```\n{code}\n```\n\n"
        f"发送给好友，让对方使用:\n"
        f"`/join {code}`\n\n"
        f"每个邀请码仅可使用一次。",
        parse_mode="Markdown",
    )


@admin_only
async def users_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /users — list all authorized users."""
    users = models.list_users()
    if not users:
        await update.message.reply_text("暂无用户。")
        return

    lines = [f"👥 **用户列表** ({len(users)} 人)\n"]
    for u in users:
        role_emoji = "👑" if u["role"] == "admin" else "👤"
        name = u["username"] or str(u["user_id"])
        lines.append(
            f"{role_emoji} **{name}** (`{u['user_id']}`)\n"
            f"   📡 {u['source_count']} 个源"
        )
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


@admin_only
async def kick_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /kick <user_id> — remove a user."""
    if not context.args:
        await update.message.reply_text("❌ 用法: `/kick <user_id>`", parse_mode="Markdown")
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ user_id 必须是数字")
        return

    if target_id == config.ADMIN_USER_ID:
        await update.message.reply_text("❌ 不能移除管理员自己")
        return

    if models.remove_user(target_id):
        await update.message.reply_text(f"✅ 已移除用户 `{target_id}` 及其所有数据", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"❌ 未找到用户 `{target_id}`", parse_mode="Markdown")
