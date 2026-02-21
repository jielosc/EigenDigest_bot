"""Telegram bot command handlers — multi-user version."""

import logging
import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

import config
from db import models
from db.presets import PRESET_GROUPS, get_preset, get_preset_key, get_preset_names

logger = logging.getLogger(__name__)

# Conversation states for adding a source
WAIT_URL, WAIT_TYPE, WAIT_NAME, WAIT_GROUP = range(4)


# ─── UI Builders ─────────────────────────────────────────────

def build_main_menu(uid: int, base_text: str = None):
    digest_time = models.get_setting(uid, "digest_time", "08:00")
    sources = models.list_sources(uid)
    enabled_count = sum(1 for s in sources if s['enabled'])
    
    text = (
        "🤖 **EigenDigest 控制面板**\n\n"
        f"⏰ 推送时间: **{digest_time}** (北京时间)\n"
        f"📋 信息源: **{enabled_count}/{len(sources)}** 已启用\n\n"
        "点击下方按钮进行管理 👇"
    )
    if base_text:
        text = f"{base_text}\n\n{text}"
        
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕ 添加信息源", callback_data="cmd_add"),
            InlineKeyboardButton("📰 立即生成摘要", callback_data="cmd_digest"),
        ],
        [
            InlineKeyboardButton("📋 管理信息源", callback_data="cmd_list"),
            InlineKeyboardButton("📂 管理分组", callback_data="cmd_groups"),
        ],
        [
            InlineKeyboardButton("📦 导入预设", callback_data="cmd_presets"),
            InlineKeyboardButton("📖 帮助/设置", callback_data="cmd_help"),
        ],
    ])
    return text, keyboard

def build_list_ui(uid: int):
    sources = models.list_sources(uid)
    if not sources:
        text = "📭 暂无信息源。\n点击下方添加信息源或导入预设 👇"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ 添加信息源", callback_data="cmd_add")],
            [InlineKeyboardButton("📦 导入预设", callback_data="cmd_presets")],
            [InlineKeyboardButton("🔙 返回菜单", callback_data="cmd_menu")]
        ])
        return text, keyboard

    digest_time = models.get_setting(uid, "digest_time", "08:00")
    groups: dict[str, list] = {}
    for s in sources:
        groups.setdefault(s["group_name"], []).append(s)

    text = f"📋 **我的信息源** (推送: {digest_time})\n💡 点击名称启用/暂停，点击 🗑️ 删除"
    buttons = []
    for gname, items in groups.items():
        enabled_count = sum(1 for i in items if i["enabled"])
        buttons.append([InlineKeyboardButton(f"📂 {gname} ({enabled_count}/{len(items)})", callback_data="noop")])
        for s in items:
            status = "✅" if s["enabled"] else "⏸️"
            buttons.append([
                InlineKeyboardButton(f"{status} {s['name']}", callback_data=f"tglsrc_{s['id']}"),
                InlineKeyboardButton("🗑️", callback_data=f"delsrc_{s['id']}")
            ])
            
    buttons.append([InlineKeyboardButton("🔙 返回菜单", callback_data="cmd_menu")])
    return text, InlineKeyboardMarkup(buttons)

def build_groups_ui(uid: int):
    groups = models.list_groups(uid)
    if not groups:
        text = "📭 暂无分组。\n点击下方添加或导入预设 👇"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ 添加信息源", callback_data="cmd_add")],
            [InlineKeyboardButton("📦 导入预设", callback_data="cmd_presets")],
            [InlineKeyboardButton("🔙 返回菜单", callback_data="cmd_menu")]
        ])
        return text, keyboard

    text = "📂 **我的分组**\n💡 点击名称启用/暂停整组，点击 🗑️ 删除整组"
    buttons = []
    for g in groups:
        status = "✅" if g['enabled_count'] > 0 else "⏸️"
        gname = g['group_name']
        cutoff = gname.encode('utf-8')[:40].decode('utf-8', 'ignore')
        buttons.append([
            InlineKeyboardButton(f"{status} {gname} ({g['enabled_count']}/{g['count']})", callback_data=f"tglgrp_{cutoff}"),
            InlineKeyboardButton("🗑️", callback_data=f"delgrp_{cutoff}")
        ])
        
    buttons.append([InlineKeyboardButton("🔙 返回菜单", callback_data="cmd_menu")])
    return text, InlineKeyboardMarkup(buttons)


# ─── Auth Decorators ─────────────────────────────────────────


def authorized(func):
    """Decorator: only authorized users (in users table) can use this command."""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, **kwargs):
        uid = update.effective_user.id
        if not models.is_authorized(uid):
            await update.message.reply_text(
                "⛔ 你还未获得授权。\n"
                "请使用 `/join <邀请码>` 加入。",
                parse_mode="Markdown",
            )
            return
        return await func(update, context, **kwargs)
    return wrapper


def admin_only(func):
    """Decorator: only admin can use this command."""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, **kwargs):
        uid = update.effective_user.id
        if not models.is_admin(uid):
            await update.message.reply_text("⛔ 此命令仅管理员可用。")
            return
        return await func(update, context, **kwargs)
    return wrapper


def _uid(update: Update) -> int:
    """Shorthand to get user_id from update."""
    return update.effective_user.id


# ─── Public Commands (no auth required) ──────────────────────


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start — different message for authorized vs unauthed users."""
    uid = _uid(update)
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start — different message for authorized vs unauthed users."""
    uid = _uid(update)
    if models.is_authorized(uid):
        text, keyboard = build_main_menu(uid)
        await update.message.reply_text(
            text,
            parse_mode="Markdown",
            reply_markup=keyboard,
        )
    else:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📖 了解更多", callback_data="intro_detail")],
        ])
        await update.message.reply_text(
            "👋 **欢迎来到 EigenDigest Bot！**\n\n"
            "🤖 我是一个智能信息摘要助手：\n\n"
            "• 📡 聚合你关注的 RSS、新闻网站、微信公众号\n"
            "• 🧠 每天通过 AI 自动生成精华摘要\n"
            "• ⏰ 在你设定的时间准时推送\n\n"
            "要开始使用，请输入邀请码：\n"
            "`/join <邀请码>`",
            parse_mode="Markdown",
            reply_markup=keyboard,
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

    text, keyboard = build_main_menu(uid, f"🎉 **欢迎加入 EigenDigest！**\n\n已为你导入 **{total_added}** 个基础信息源。")
    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


# ─── User Commands ────────────────────────────────────────────


@authorized
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE, from_callback: bool = False):
    """Handle /help command."""
    msg = update.callback_query.message if from_callback else update.message
    uid = update.callback_query.from_user.id if from_callback else _uid(update)

    is_adm = models.is_admin(uid)
    admin_section = ""
    if is_adm:
        admin_section = (
            "\n**🔑 管理员命令：**\n"
            "`/invite` — 生成邀请码\n"
            "`/users` — 查看所有用户\n"
            "`/kick <user_id>` — 移除用户\n"
        )

    text = (
        "📖 **使用指南**\n\n"
        "💡 提示：所有操作都可以通过 **菜单面板** 完成。\n"
        "如果你喜欢用命令，可以参考以下格式：\n\n"
        "**手动添加**\n"
        "`/add rss 名称 URL [分组]`\n"
        "`/add web 名称 URL [分组]`\n\n"
        "**合并管理**\n"
        "`/import <分组名>` 一键导入预设\n"
        "`/settime 09:30` 设置时间\n"
        f"{admin_section}"
    )
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 返回菜单", callback_data="cmd_menu")]])
    
    if update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=keyboard)
    else:
        await msg.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)


@authorized
async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the add source conversation."""
    uid = update.effective_user.id
    args = context.args
    
    # If user provided args, do the quick add (backward compatible)
    if args and len(args) >= 3:
        source_type = args[0].lower()
        name = args[1]
        url = args[2]
        group_name = args[3] if len(args) > 3 else "默认"
        
        if source_type not in ("rss", "web", "wechat"):
            await update.message.reply_text("❌ 类型必须是: `rss`, `web`, `wechat`", parse_mode="Markdown")
            return ConversationHandler.END
        if not url.startswith(("http://", "https://")):
            await update.message.reply_text("❌ URL 必须以 http:// 或 https:// 开头")
            return ConversationHandler.END
            
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
        return ConversationHandler.END

    # Start interactive wizard
    context.user_data.clear()
    
    msg = update.callback_query.message if update.callback_query else update.message
    text = (
        "➕ **添加信息源**\n\n"
        "请发送信息源的 **URL** (必须以 http:// 或 https:// 开头)\n"
        "发送 /cancel 可以随时取消。"
    )
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, parse_mode="Markdown")
    else:
        await msg.reply_text(text, parse_mode="Markdown")
    return WAIT_URL

async def add_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    if not url.startswith(("http://", "https://")):
        await update.message.reply_text("❌ URL 必须以 http:// 或 https:// 开头。请重新输入，或发送 /cancel 取消。")
        return WAIT_URL
        
    context.user_data['url'] = url
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📡 RSS/Atom", callback_data="addtype_rss")],
        [InlineKeyboardButton("🌐 网页", callback_data="addtype_web")],
        [InlineKeyboardButton("💬 微信公众号", callback_data="addtype_wechat")]
    ])
    await update.message.reply_text("请选择该信息源的**类型** 👇", reply_markup=keyboard, parse_mode="Markdown")
    return WAIT_TYPE

async def add_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    source_type = query.data.split('_')[1]
    context.user_data['type'] = source_type
    
    emoji = {"rss": "📡", "web": "🌐", "wechat": "💬"}.get(source_type, "📰")
    await query.edit_message_text(f"已选择类型: {emoji} **{source_type}**\n\n请输入该信息源的**名称**:", parse_mode="Markdown")
    return WAIT_NAME

async def add_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    context.user_data['name'] = name
    
    uid = update.effective_user.id
    groups = models.list_groups(uid)
    
    buttons = []
    row = []
    for g in groups:
        row.append(InlineKeyboardButton(f"📂 {g['group_name']}", callback_data=f"addgroup_{g['group_name']}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
        
    buttons.append([InlineKeyboardButton("🆕 默认分组", callback_data="addgroup_默认")])
    
    await update.message.reply_text(
        f"已输入名称: **{name}**\n\n请**直接回复**新分组名称，或点击下方按钮**选择**现有分组:",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="Markdown"
    )
    return WAIT_GROUP

async def add_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        group_name = query.data.split('_', 1)[1]
        msg = query.message
    else:
        group_name = update.message.text.strip()
        msg = update.message
        
    url = context.user_data['url']
    source_type = context.user_data['type']
    name = context.user_data['name']
    
    success = models.add_source(uid, name, url, source_type, group_name)
    
    emoji = {"rss": "📡", "web": "🌐", "wechat": "💬"}.get(source_type, "📰")
    if success:
        text = (f"✅ **添加成功！**\n\n"
                f"{emoji} **{name}** ({source_type})\n"
                f"📂 {group_name}\n🔗 `{url}`")
    else:
        text = "❌ 添加失败，该 URL 可能已存在。"
        
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 返回菜单", callback_data="cmd_menu"),
         InlineKeyboardButton("📋 查看信息源", callback_data="cmd_list")]
    ])
    
    if update.callback_query:
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=keyboard)
    else:
        await msg.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)
        
    context.user_data.clear()
    return ConversationHandler.END

async def cancel_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("已取消添加操作。")
    return ConversationHandler.END

def get_add_handler():
    return ConversationHandler(
        entry_points=[
            CommandHandler('add', add_start),
            CallbackQueryHandler(add_start, pattern="^cmd_add$")
        ],
        states={
            WAIT_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_url)],
            WAIT_TYPE: [CallbackQueryHandler(add_type, pattern="^addtype_")],
            WAIT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_name)],
            WAIT_GROUP: [
                CallbackQueryHandler(add_group, pattern="^addgroup_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_group)
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel_add)]
    )


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
    """Handle /list — show user's sources (now via UI builder)."""
    uid = _uid(update)
    text, keyboard = build_list_ui(uid)
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)


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
    """Handle /groups — show user's group overview (now via UI builder)."""
    uid = _uid(update)
    text, keyboard = build_groups_ui(uid)
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)


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


# ─── Callback Query Handler (button presses) ─────────────────


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline keyboard button presses."""
    query = update.callback_query
    uid = query.from_user.id
    data = query.data

    if data == "noop":
        await query.answer()
        return
        
    if not data.startswith(("addtype_", "addgroup_")):
        await query.answer()

    if data == "intro_detail":
        await query.message.reply_text(
            "📖 **关于 EigenDigest**\n\n"
            "EigenDigest 是一个信息聚合摘要机器人。\n\n"
            "**支持的信息源类型：**\n"
            "• 📡 RSS / Atom 订阅\n"
            "• 🌐 网页内容抓取\n"
            "• 💬 微信公众号（通过 RSSHub）\n\n"
            "**工作流程：**\n"
            "1. 你添加感兴趣的信息源\n"
            "2. Bot 每天定时抓取最新内容\n"
            "3. AI 自动生成精华摘要\n"
            "4. 准时推送到你的 Telegram\n\n"
            "向管理员索取邀请码后，发送：\n"
            "`/join <邀请码>` 即可开始使用！",
            parse_mode="Markdown",
        )
        return

    # All other callbacks require authorization
    if not models.is_authorized(uid):
        await query.message.reply_text("⛔ 请先使用 `/join <邀请码>` 加入。", parse_mode="Markdown")
        return

    if data == "cmd_menu":
        text, keyboard = build_main_menu(uid)
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=keyboard)
    elif data == "cmd_list":
        text, keyboard = build_list_ui(uid)
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=keyboard)
    elif data == "cmd_groups":
        text, keyboard = build_groups_ui(uid)
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=keyboard)
    elif data == "cmd_presets":
        await _cb_presets(query)
    elif data == "cmd_digest":
        await query.message.reply_text("⏳ 正在抓取内容并生成摘要，请稍候...")
        from bot.scheduler import run_digest_for_user
        summary = await run_digest_for_user(uid)
        if summary:
            if len(summary) > 4000:
                for i in range(0, len(summary), 4000):
                    await query.message.reply_text(summary[i:i+4000], parse_mode="Markdown")
            else:
                await query.message.reply_text(summary, parse_mode="Markdown")
        else:
            await query.message.reply_text("😕 暂无可用内容。请检查是否有启用的信息源。")
    elif data == "cmd_help":
        await help_command(update, context, from_callback=True)
    elif data.startswith("import_"):
        group_name = data[7:]  # Remove "import_" prefix
        await _cb_import(query, uid, group_name)
    elif data.startswith("tglsrc_"):
        sid = int(data.split('_')[1])
        sources = models.list_sources(uid)
        src = next((s for s in sources if s['id'] == sid), None)
        if src:
            models.toggle_source(uid, src['name'])
            text, keyboard = build_list_ui(uid)
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=keyboard)
    elif data.startswith("delsrc_"):
        sid = int(data.split('_')[1])
        sources = models.list_sources(uid)
        src = next((s for s in sources if s['id'] == sid), None)
        if src:
            models.remove_source(uid, src['name'])
            text, keyboard = build_list_ui(uid)
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=keyboard)
    elif data.startswith("tglgrp_"):
        gname = data.split('_', 1)[1]
        models.toggle_group(uid, gname)
        text, keyboard = build_groups_ui(uid)
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=keyboard)
    elif data.startswith("delgrp_"):
        gname = data.split('_', 1)[1]
        models.remove_group(uid, gname)
        text, keyboard = build_groups_ui(uid)
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=keyboard)


async def _cb_presets(query):
    """Show presets with import buttons (from button press)."""
    lines = ["📦 **可导入的预设**\n"]
    for name, sources in PRESET_GROUPS.items():
        source_names = ", ".join(s["name"] for s in sources)
        lines.append(f"**{name}** ({len(sources)} 个)")
        lines.append(f"  _{source_names}_\n")

    # Create import buttons for each preset
    buttons = []
    row = []
    for name in PRESET_GROUPS:
        row.append(InlineKeyboardButton(f"📥 {name}", callback_data=f"import_{name}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
        
    buttons.append([InlineKeyboardButton("🔙 返回菜单", callback_data="cmd_menu")])

    await query.edit_message_text(
        "\n".join(lines) + "\n点击下方按钮一键导入 👇",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def _cb_import(query, uid: int, group_name: str):
    """Import a preset group (from button press)."""
    preset_sources = get_preset(group_name)
    canonical_name = get_preset_key(group_name)

    if preset_sources is None or canonical_name is None:
        await query.message.reply_text(f"❌ 未找到预设: {group_name}")
        return

    batch = [{**s, "group_name": canonical_name} for s in preset_sources]
    success, skipped = models.add_sources_batch(uid, batch)

    msg = f"📦 **已导入「{canonical_name}」**\n✅ 添加: {success}"
    if skipped:
        msg += f" | ⏭️ 跳过: {skipped}"

    await query.message.reply_text(
        msg,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 查看信息源", callback_data="cmd_list")],
        ]),
    )
