"""Telegram bot command handlers — multi-user version."""

import logging
import re
import shlex

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

from db import models
from db.presets import (
    PRESET_GROUPS,
    get_preset,
    get_preset_key,
    get_preset_names,
    get_onboarding_preset_names,
)

logger = logging.getLogger(__name__)

# Conversation states for adding a source
WAIT_URL, WAIT_TYPE, WAIT_NAME, WAIT_GROUP = range(4)
ADMIN_WAIT_ACTION_KEY = "admin_wait_action"
ADMIN_WAIT_ADDUSER = "admin_wait_adduser"
ADMIN_WAIT_KICK = "admin_wait_kick"
USER_WAIT_CUSTOM_TIME_KEY = "user_wait_custom_time"
USER_WAIT_JOIN_CODE_KEY = "user_wait_join_code"


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
        
    rows = [
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
            InlineKeyboardButton("🕒 设置时间", callback_data="cmd_settime"),
        ],
    ]
    if models.is_admin(uid):
        rows.append([InlineKeyboardButton("👑 管理员面板", callback_data="cmd_admin")])
    return text, InlineKeyboardMarkup(rows)


def build_back_menu_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 返回菜单", callback_data="cmd_menu")]])


def build_help_ui(uid: int):
    lines = [
        "📖 **命令帮助**\n",
        "默认推荐直接使用按钮完成操作；以下是命令行用法：\n",
        "**基础命令**",
        "• `/start`：打开主界面（等同返回菜单）",
        "• `/help`：查看命令帮助",
        "• `/join <邀请码>`：使用邀请码加入（未授权用户）",
        "",
        "**信息源管理**",
        "• `/add <类型> <名称> <URL> [分组]`",
        "  类型支持：`rss` / `web` / `wechat`",
        "• `/list`：查看信息源列表",
        "• `/remove <名称>`：删除一个信息源",
        "• `/toggle <名称>`：启用/禁用一个信息源",
        "",
        "**分组管理**",
        "• `/groups`：查看分组概览",
        "• `/presets`：查看可导入预设",
        "• `/import <分组名>`：导入预设分组",
        "• `/togglegroup <分组名>`：启用/禁用整组",
        "• `/delgroup <分组名>`：删除整组",
        "",
        "**推送相关**",
        "• `/settime`：打开时间设置面板",
        "• `/settime <HH:MM>`：直接设置推送时间",
        "• `/digest`：立即生成一次摘要",
    ]

    if models.is_admin(uid):
        lines.extend([
            "",
            "**管理员命令**",
            "• `/admin`：打开管理员面板",
            "• `/invite`：生成邀请码",
            "• `/users`：查看用户列表",
            "• `/adduser <user_id> [用户名]`：直接添加用户",
            "• `/kick <user_id>`：移除用户",
        ])

    rows = [[InlineKeyboardButton("🔙 返回菜单", callback_data="cmd_menu")]]
    if models.is_admin(uid):
        rows.insert(0, [InlineKeyboardButton("👑 管理员面板", callback_data="cmd_admin")])
    return "\n".join(lines), InlineKeyboardMarkup(rows)


def build_admin_panel_ui():
    text = (
        "👑 **管理员面板**\n\n"
        "优先使用按钮操作：\n"
        "• 生成邀请码\n"
        "• 查看用户列表\n"
        "• 直接添加用户\n"
        "• 移除用户"
    )
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎟️ 生成邀请码", callback_data="adm_invite"),
            InlineKeyboardButton("👥 用户列表", callback_data="adm_users"),
        ],
        [
            InlineKeyboardButton("➕ 添加用户", callback_data="adm_adduser"),
            InlineKeyboardButton("🗑️ 移除用户", callback_data="adm_kick"),
        ],
        [InlineKeyboardButton("🔙 返回菜单", callback_data="cmd_menu")],
    ])
    return text, keyboard


def build_admin_result_keyboard(action: str | None = None):
    rows = []
    if action == ADMIN_WAIT_ADDUSER:
        rows.append(
            [
                InlineKeyboardButton("➕ 继续添加", callback_data="adm_adduser"),
                InlineKeyboardButton("👥 用户列表", callback_data="adm_users"),
            ]
        )
    elif action == ADMIN_WAIT_KICK:
        rows.append(
            [
                InlineKeyboardButton("🗑️ 继续移除", callback_data="adm_kick"),
                InlineKeyboardButton("👥 用户列表", callback_data="adm_users"),
            ]
        )
    else:
        rows.append(
            [
                InlineKeyboardButton("👥 用户列表", callback_data="adm_users"),
                InlineKeyboardButton("🎟️ 邀请码", callback_data="adm_invite"),
            ]
        )
    rows.append([InlineKeyboardButton("👑 管理员面板", callback_data="cmd_admin")])
    rows.append([InlineKeyboardButton("🔙 返回菜单", callback_data="cmd_menu")])
    return InlineKeyboardMarkup(rows)


def build_admin_wait_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👑 返回管理员面板", callback_data="adm_cancel_wait")],
        [InlineKeyboardButton("🔙 返回菜单", callback_data="cmd_menu")],
    ])


def build_admin_users_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕ 添加用户", callback_data="adm_adduser"),
            InlineKeyboardButton("🗑️ 移除用户", callback_data="adm_kick"),
        ],
        [InlineKeyboardButton("👑 返回管理员面板", callback_data="cmd_admin")],
        [InlineKeyboardButton("🔙 返回菜单", callback_data="cmd_menu")],
    ])


def build_admin_invite_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔁 再生成一个", callback_data="adm_invite"),
            InlineKeyboardButton("👥 用户列表", callback_data="adm_users"),
        ],
        [InlineKeyboardButton("👑 返回管理员面板", callback_data="cmd_admin")],
        [InlineKeyboardButton("🔙 返回菜单", callback_data="cmd_menu")],
    ])


def build_time_wait_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🕒 返回时间设置", callback_data="cmd_settime")],
        [InlineKeyboardButton("🔙 返回菜单", callback_data="cmd_menu")],
    ])

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
        group_ref_id = g["group_ref_id"]
        buttons.append([
            InlineKeyboardButton(f"{status} {gname} ({g['enabled_count']}/{g['count']})", callback_data=f"tglgrp_{group_ref_id}"),
            InlineKeyboardButton("🗑️", callback_data=f"delgrp_{group_ref_id}")
        ])
        
    buttons.append([InlineKeyboardButton("🔙 返回菜单", callback_data="cmd_menu")])
    return text, InlineKeyboardMarkup(buttons)


def build_presets_ui():
    lines = ["📦 **可导入的预设分组**\n"]
    for name, sources in PRESET_GROUPS.items():
        lines.append(f"• **{name}** ({len(sources)} 个信息源)")
    lines.append("\n点击下方按钮一键导入。")

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

    return "\n".join(lines), InlineKeyboardMarkup(buttons)


def build_settime_ui(uid: int):
    current = models.get_setting(uid, "digest_time", "08:00")
    text = (
        "⏰ **推送时间设置**\n\n"
        f"当前时间：**{current}**（北京时间）\n\n"
        "点击下方常用时间即可修改；如需其他时间，点击「✍️ 自定义时间」。"
    )
    quick_times = ["07:00", "08:00", "09:00", "12:00", "18:00", "21:00"]
    buttons = []
    row = []
    for t in quick_times:
        row.append(InlineKeyboardButton(t, callback_data=f"settime_{t.replace(':', '')}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("✍️ 自定义时间", callback_data="settime_custom")])
    buttons.append([InlineKeyboardButton("🔙 返回菜单", callback_data="cmd_menu")])
    return text, InlineKeyboardMarkup(buttons)


# ─── Auth Decorators ─────────────────────────────────────────


def authorized(func):
    """Decorator: only authorized users (in users table) can use this command."""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, **kwargs):
        uid = update.effective_user.id
        if not models.is_authorized(uid):
            _, keyboard = _build_intro_ui()
            await update.message.reply_text(
                "⛔ 你还未获得授权。\n"
                "请使用 `/join <邀请码>` 加入。",
                parse_mode="Markdown",
                reply_markup=keyboard,
            )
            return
        return await func(update, context, **kwargs)
    return wrapper


def admin_only(func):
    """Decorator: only admin can use this command."""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, **kwargs):
        uid = update.effective_user.id
        if not models.is_admin(uid):
            await update.message.reply_text("⛔ 此命令仅管理员可用。", reply_markup=build_back_menu_keyboard())
            return
        return await func(update, context, **kwargs)
    return wrapper


def _uid(update: Update) -> int:
    """Shorthand to get user_id from update."""
    return update.effective_user.id


def _import_onboarding_sources(user_id: int) -> tuple[int, int, list[str]]:
    """Import onboarding preset groups for a user."""
    total_added = 0
    total_skipped = 0
    onboarding_groups = get_onboarding_preset_names()

    for group_name in onboarding_groups:
        sources = PRESET_GROUPS[group_name]
        batch = [{**s, "group_name": group_name} for s in sources]
        added, skipped = models.add_sources_batch(user_id, batch)
        total_added += added
        total_skipped += skipped

    return total_added, total_skipped, onboarding_groups


def _build_users_text() -> str:
    users = models.list_users()
    if not users:
        return "👥 **用户列表**\n\n暂无用户。"

    lines = [f"👥 **用户列表** ({len(users)} 人)\n"]
    for u in users:
        role_emoji = "👑" if u["role"] == "admin" else "👤"
        name = u["username"] or str(u["user_id"])
        lines.append(
            f"{role_emoji} **{name}** (`{u['user_id']}`)\n"
            f"   📡 {u['source_count']} 个源"
        )
    return "\n".join(lines)


def _add_user_by_admin(target_id: int, username: str = "") -> str:
    if target_id <= 0:
        return "❌ user_id 必须是正整数。"

    existing = models.get_user(target_id)
    if existing:
        role_text = "管理员" if existing["role"] == "admin" else "普通用户"
        return f"ℹ️ 用户 `{target_id}` 已存在（{role_text}）。"

    models.add_user(target_id, username, "user")
    total_added, total_skipped, onboarding_groups = _import_onboarding_sources(target_id)

    msg_lines = [
        "✅ **用户添加成功**",
        f"🆔 user_id: `{target_id}`",
        f"📦 已导入核心预设: **{total_added}** 条（{len(onboarding_groups)} 个分组）",
    ]
    if username:
        msg_lines.insert(2, f"👤 用户名: **{username}**")
    if total_skipped:
        msg_lines.append(f"⏭️ 跳过重复: {total_skipped}")
    msg_lines.append("用户现在可直接点击对话窗口里的 Start 按钮开始使用。")
    return "\n".join(msg_lines)


def _kick_user_by_admin(target_id: int) -> str:
    if target_id <= 0:
        return "❌ user_id 必须是正整数。"

    user = models.get_user(target_id)
    if user and user["role"] == "admin":
        return "❌ 不能移除管理员用户。"

    if models.remove_user(target_id):
        return f"✅ 已移除用户 `{target_id}` 及其所有数据。"
    return f"❌ 未找到用户 `{target_id}`。"


def _parse_time_input(time_str: str) -> tuple[int, int] | None:
    """Parse time text into (hour, minute). Accepts HH:MM or HMM/HHMM."""
    value = time_str.strip().replace("：", ":")
    if re.match(r"^\d{3,4}$", value):
        digits = value.zfill(4)
        hour, minute = int(digits[:2]), int(digits[2:])
    else:
        match = re.match(r"^(\d{1,2}):(\d{2})$", value)
        if not match:
            return None
        hour, minute = int(match.group(1)), int(match.group(2))

    if 0 <= hour <= 23 and 0 <= minute <= 59:
        return hour, minute
    return None


def _build_intro_ui():
    text = (
        "👋 **欢迎来到 EigenDigest Bot！**\n\n"
        "🤖 我是一个智能信息摘要助手：\n\n"
        "• 📡 聚合你关注的 RSS、新闻网站、微信公众号\n"
        "• 🧠 每天通过 AI 自动生成精华摘要\n"
        "• ⏰ 在你设定的时间准时推送\n\n"
        "点击下方按钮输入邀请码即可开始。"
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔑 输入邀请码", callback_data="intro_join")],
        [InlineKeyboardButton("📖 了解更多", callback_data="intro_detail")],
    ])
    return text, keyboard


def _build_intro_wait_keyboard():
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔙 返回欢迎页", callback_data="intro_welcome")]]
    )


def _build_join_success_ui(uid: int, username: str):
    models.add_user(uid, username, "user")
    total_added, _, onboarding_groups = _import_onboarding_sources(uid)
    return build_main_menu(
        uid,
        (
            "🎉 **欢迎加入 EigenDigest！**\n\n"
            f"已为你导入 **{total_added}** 个核心信息源（{len(onboarding_groups)} 个分组）。\n"
            "如需扩展主题，点击菜单中的「📦 导入预设」即可。"
        ),
    )


# ─── Public Commands (no auth required) ──────────────────────


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start — different message for authorized vs unauthed users."""
    context.user_data.pop(ADMIN_WAIT_ACTION_KEY, None)
    context.user_data.pop(USER_WAIT_CUSTOM_TIME_KEY, None)
    context.user_data.pop(USER_WAIT_JOIN_CODE_KEY, None)
    uid = _uid(update)
    if models.is_authorized(uid):
        text, keyboard = build_main_menu(uid)
        await update.message.reply_text(
            text,
            parse_mode="Markdown",
            reply_markup=keyboard,
        )
    else:
        text, keyboard = _build_intro_ui()
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)


async def join_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /join <code> — use invite code to join."""
    context.user_data.pop(USER_WAIT_JOIN_CODE_KEY, None)
    uid = _uid(update)

    if models.is_authorized(uid):
        await update.message.reply_text("✅ 你已经是授权用户了！", reply_markup=build_back_menu_keyboard())
        return

    if not context.args:
        _, keyboard = _build_intro_ui()
        await update.message.reply_text(
            "❌ 请输入邀请码。\n也可以直接点击「🔑 输入邀请码」按钮后发送邀请码。",
            parse_mode="Markdown",
            reply_markup=keyboard,
        )
        return

    code = context.args[0]
    if not models.use_invite_code(code, uid):
        _, keyboard = _build_intro_ui()
        await update.message.reply_text("❌ 邀请码无效或已被使用。", reply_markup=keyboard)
        return

    # Create user
    username = update.effective_user.username or update.effective_user.first_name or ""
    text, keyboard = _build_join_success_ui(uid, username)
    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


# ─── User Commands ────────────────────────────────────────────


@authorized
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE, from_callback: bool = False):
    """Handle /help command — command usage reference."""
    context.user_data.pop(ADMIN_WAIT_ACTION_KEY, None)
    context.user_data.pop(USER_WAIT_CUSTOM_TIME_KEY, None)
    context.user_data.pop(USER_WAIT_JOIN_CODE_KEY, None)
    uid = update.callback_query.from_user.id if from_callback else _uid(update)

    text, keyboard = build_help_ui(uid)

    if update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=keyboard)
    else:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)


@authorized
async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the add source conversation."""
    uid = update.effective_user.id
    args = context.args
    
    # If user provided args, do the quick add (backward compatible)
    if args and len(args) >= 3:
        # Support quoted args, and tolerate names/groups containing spaces.
        parsed_args = args
        if update.message and update.message.text:
            try:
                tokens = shlex.split(update.message.text)
                if len(tokens) > 1:
                    parsed_args = tokens[1:]
            except ValueError:
                parsed_args = args

        source_type = parsed_args[0].lower()
        url_index = next(
            (i for i, token in enumerate(parsed_args[1:], start=1) if token.startswith(("http://", "https://"))),
            -1,
        )
        if url_index < 2:
            await update.message.reply_text(
                "❌ 用法: `/add <类型> <名称> <URL> [分组]`\n"
                "示例: `/add rss OpenAI博客 https://openai.com/blog/rss.xml AI`",
                parse_mode="Markdown",
                reply_markup=build_back_menu_keyboard(),
            )
            return ConversationHandler.END

        name = " ".join(parsed_args[1:url_index]).strip()
        url = parsed_args[url_index]
        group_name = " ".join(parsed_args[url_index + 1:]).strip() or "默认"
        
        if source_type not in ("rss", "web", "wechat"):
            await update.message.reply_text(
                "❌ 类型必须是: `rss`, `web`, `wechat`",
                parse_mode="Markdown",
                reply_markup=build_back_menu_keyboard(),
            )
            return ConversationHandler.END
        if not url.startswith(("http://", "https://")):
            await update.message.reply_text(
                "❌ URL 必须以 http:// 或 https:// 开头",
                reply_markup=build_back_menu_keyboard(),
            )
            return ConversationHandler.END
            
        success = models.add_source(uid, name, url, source_type, group_name)
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 查看信息源", callback_data="cmd_list")],
            [InlineKeyboardButton("🔙 返回菜单", callback_data="cmd_menu")],
        ])
        if success:
            emoji = {"rss": "📡", "web": "🌐", "wechat": "💬"}.get(source_type, "📰")
            await update.message.reply_text(
                f"✅ 已添加: {emoji} **{name}** ({source_type})\n"
                f"📂 {group_name}  🔗 `{url}`",
                parse_mode="Markdown",
                reply_markup=keyboard,
            )
        else:
            await update.message.reply_text("❌ 添加失败，该 URL 可能已存在。", reply_markup=keyboard)
        return ConversationHandler.END

    # Start interactive wizard
    context.user_data.clear()
    
    msg = update.callback_query.message if update.callback_query else update.message
    text = (
        "➕ **添加信息源**\n\n"
        "请发送信息源的 **URL** (必须以 http:// 或 https:// 开头)\n"
        "发送 /cancel 可以随时取消。"
    )
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 返回菜单", callback_data="cmd_menu")]])
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=keyboard)
    else:
        await msg.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)
    return WAIT_URL

async def add_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    if not url.startswith(("http://", "https://")):
        await update.message.reply_text(
            "❌ URL 必须以 http:// 或 https:// 开头。请重新输入，或发送 /cancel 取消。",
            reply_markup=build_back_menu_keyboard(),
        )
        return WAIT_URL
        
    context.user_data['url'] = url
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📡 RSS/Atom", callback_data="addtype_rss")],
        [InlineKeyboardButton("🌐 网页", callback_data="addtype_web")],
        [InlineKeyboardButton("💬 微信公众号", callback_data="addtype_wechat")],
        [InlineKeyboardButton("🔙 返回菜单", callback_data="cmd_menu")],
    ])
    await update.message.reply_text("请选择该信息源的**类型** 👇", reply_markup=keyboard, parse_mode="Markdown")
    return WAIT_TYPE

async def add_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "cmd_menu":
        return await add_cancel_to_menu(update, context)
    source_type = query.data.split('_')[1]
    context.user_data['type'] = source_type
    
    emoji = {"rss": "📡", "web": "🌐", "wechat": "💬"}.get(source_type, "📰")
    await query.edit_message_text(
        f"已选择类型: {emoji} **{source_type}**\n\n请输入该信息源的**名称**:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 返回菜单", callback_data="cmd_menu")]]),
    )
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
    buttons.append([InlineKeyboardButton("🔙 返回菜单", callback_data="cmd_menu")])
    
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
    await update.message.reply_text("已取消添加操作。", reply_markup=build_back_menu_keyboard())
    return ConversationHandler.END


async def add_cancel_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel add conversation and return to main menu."""
    context.user_data.clear()
    query = update.callback_query
    if query:
        await query.answer()
        uid = query.from_user.id
        text, keyboard = build_main_menu(uid, "已取消添加操作。")
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=keyboard)
    return ConversationHandler.END

def get_add_handler():
    return ConversationHandler(
        entry_points=[
            CommandHandler('add', add_start),
            CallbackQueryHandler(add_start, pattern="^cmd_add$")
        ],
        states={
            WAIT_URL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_url),
                CallbackQueryHandler(add_cancel_to_menu, pattern="^cmd_menu$"),
            ],
            WAIT_TYPE: [
                CallbackQueryHandler(add_type, pattern="^(addtype_.*|cmd_menu)$"),
            ],
            WAIT_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_name),
                CallbackQueryHandler(add_cancel_to_menu, pattern="^cmd_menu$"),
            ],
            WAIT_GROUP: [
                CallbackQueryHandler(add_group, pattern="^addgroup_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_group),
                CallbackQueryHandler(add_cancel_to_menu, pattern="^cmd_menu$"),
            ]
        },
        fallbacks=[
            CommandHandler('cancel', cancel_add),
            CallbackQueryHandler(add_cancel_to_menu, pattern="^cmd_menu$"),
        ]
    )


@authorized
async def remove_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /remove <name>."""
    uid = _uid(update)
    if not context.args:
        await update.message.reply_text(
            "❌ 用法: `/remove <名称>`",
            parse_mode="Markdown",
            reply_markup=build_back_menu_keyboard(),
        )
        return
    name = " ".join(context.args).strip()
    if models.remove_source(uid, name):
        await update.message.reply_text(
            f"✅ 已删除: **{name}**",
            parse_mode="Markdown",
            reply_markup=build_back_menu_keyboard(),
        )
    else:
        await update.message.reply_text(
            f"❌ 未找到: **{name}**",
            parse_mode="Markdown",
            reply_markup=build_back_menu_keyboard(),
        )


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
        await update.message.reply_text(
            "❌ 用法: `/toggle <名称>`",
            parse_mode="Markdown",
            reply_markup=build_back_menu_keyboard(),
        )
        return
    name = " ".join(context.args).strip()
    new_state = models.toggle_source(uid, name)
    if new_state is None:
        await update.message.reply_text(
            f"❌ 未找到: **{name}**",
            parse_mode="Markdown",
            reply_markup=build_back_menu_keyboard(),
        )
    else:
        status = "✅ 已启用" if new_state else "⏸️ 已禁用"
        await update.message.reply_text(
            f"{status}: **{name}**",
            parse_mode="Markdown",
            reply_markup=build_back_menu_keyboard(),
        )


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
    text, keyboard = build_presets_ui()
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)


@authorized
async def import_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /import <preset> — batch import preset sources."""
    uid = _uid(update)
    if not context.args:
        await update.message.reply_text(
            "❌ 用法: `/import <分组名>`\n或先在菜单中点击「📦 导入预设」查看可用分组。",
            parse_mode="Markdown",
            reply_markup=build_back_menu_keyboard(),
        )
        return

    name = " ".join(context.args).strip()
    preset_sources = get_preset(name)
    canonical_name = get_preset_key(name)

    if preset_sources is None or canonical_name is None:
        available = ", ".join(f"`{n}`" for n in get_preset_names())
        await update.message.reply_text(
            f"❌ 未找到预设: **{name}**\n可用: {available}",
            parse_mode="Markdown",
            reply_markup=build_back_menu_keyboard(),
        )
        return

    batch = [{**s, "group_name": canonical_name} for s in preset_sources]
    success, skipped = models.add_sources_batch(uid, batch)

    msg = f"📦 **已导入「{canonical_name}」**\n✅ 添加: {success}"
    if skipped:
        msg += f" | ⏭️ 跳过: {skipped}"
    await update.message.reply_text(
        msg,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 查看信息源", callback_data="cmd_list")],
            [InlineKeyboardButton("🔙 返回菜单", callback_data="cmd_menu")],
        ]),
    )


@authorized
async def delgroup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /delgroup <group>."""
    uid = _uid(update)
    if not context.args:
        await update.message.reply_text(
            "❌ 用法: `/delgroup <分组名>`",
            parse_mode="Markdown",
            reply_markup=build_back_menu_keyboard(),
        )
        return
    group_name = " ".join(context.args).strip()
    count = models.remove_group(uid, group_name)
    if count > 0:
        await update.message.reply_text(
            f"🗑️ 已删除 **{group_name}** ({count} 个源)",
            parse_mode="Markdown",
            reply_markup=build_back_menu_keyboard(),
        )
    else:
        await update.message.reply_text(
            f"❌ 未找到分组: **{group_name}**",
            parse_mode="Markdown",
            reply_markup=build_back_menu_keyboard(),
        )


@authorized
async def togglegroup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /togglegroup <group>."""
    uid = _uid(update)
    if not context.args:
        await update.message.reply_text(
            "❌ 用法: `/togglegroup <分组名>`",
            parse_mode="Markdown",
            reply_markup=build_back_menu_keyboard(),
        )
        return
    group_name = " ".join(context.args).strip()
    new_state = models.toggle_group(uid, group_name)
    if new_state is None:
        await update.message.reply_text(
            f"❌ 未找到分组: **{group_name}**",
            parse_mode="Markdown",
            reply_markup=build_back_menu_keyboard(),
        )
    else:
        status = "✅ 已启用" if new_state else "⏸️ 已禁用"
        await update.message.reply_text(
            f"{status}: **{group_name}**",
            parse_mode="Markdown",
            reply_markup=build_back_menu_keyboard(),
        )


# ─── Scheduling & Digest ─────────────────────────────────────


@authorized
async def settime_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /settime <HH:MM>."""
    uid = _uid(update)
    context.user_data.pop(USER_WAIT_CUSTOM_TIME_KEY, None)
    if not context.args:
        text, keyboard = build_settime_ui(uid)
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)
        return

    parsed = _parse_time_input(context.args[0])
    if not parsed:
        await update.message.reply_text(
            "❌ 格式错误，请使用 HH:MM（如 09:30）或 4 位数字（如 0930）。",
            reply_markup=build_back_menu_keyboard(),
        )
        return

    hour, minute = parsed
    time_formatted = f"{hour:02d}:{minute:02d}"
    models.set_setting(uid, "digest_time", time_formatted)

    text, keyboard = build_settime_ui(uid)
    await update.message.reply_text(
        f"✅ 推送时间已设置为 **{time_formatted}** (北京时间)\n\n{text}",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


@authorized
async def digest_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /digest — trigger immediate summary for this user."""
    uid = _uid(update)
    await update.message.reply_text(
        "⏳ 正在抓取内容并生成摘要，请稍候...",
        reply_markup=build_back_menu_keyboard(),
    )

    from bot.scheduler import run_digest_for_user
    summary = await run_digest_for_user(uid)

    if summary:
        if len(summary) > 4000:
            for i in range(0, len(summary), 4000):
                await update.message.reply_text(summary[i:i+4000], parse_mode="Markdown")
        else:
            await update.message.reply_text(summary, parse_mode="Markdown")
        await update.message.reply_text(
            "✅ 摘要生成完成。",
            reply_markup=build_back_menu_keyboard(),
        )
    else:
        await update.message.reply_text(
            "😕 无法生成摘要。\n"
            "• 没有启用的信息源\n"
            "• 信息源没有新内容\n"
            "• LLM API 调用失败",
            reply_markup=build_back_menu_keyboard(),
        )


# ─── Admin Commands ───────────────────────────────────────────


@admin_only
async def admin_panel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /admin — open admin panel."""
    context.user_data.pop(ADMIN_WAIT_ACTION_KEY, None)
    context.user_data.pop(USER_WAIT_CUSTOM_TIME_KEY, None)
    text, keyboard = build_admin_panel_ui()
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)


@admin_only
async def invite_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /invite — generate an invite code."""
    context.user_data.pop(ADMIN_WAIT_ACTION_KEY, None)
    uid = _uid(update)
    code = models.create_invite_code(uid)
    await update.message.reply_text(
        f"🎟️ **邀请码已生成**\n\n"
        f"```\n{code}\n```\n\n"
        f"发送给好友，让对方点击「🔑 输入邀请码」后发送该邀请码。\n\n"
        f"每个邀请码仅可使用一次。",
        parse_mode="Markdown",
        reply_markup=build_admin_invite_keyboard(),
    )


@admin_only
async def users_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /users — list all authorized users."""
    context.user_data.pop(ADMIN_WAIT_ACTION_KEY, None)
    await update.message.reply_text(
        _build_users_text(),
        parse_mode="Markdown",
        reply_markup=build_admin_users_keyboard(),
    )


@admin_only
async def adduser_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /adduser <user_id> [username] — add user directly by Telegram user_id."""
    context.user_data.pop(ADMIN_WAIT_ACTION_KEY, None)
    if not context.args:
        context.user_data[ADMIN_WAIT_ACTION_KEY] = ADMIN_WAIT_ADDUSER
        await update.message.reply_text(
            "➕ **添加用户**\n\n请直接发送：`user_id` 或 `user_id 用户名`\n例如：`123456789 alice`",
            parse_mode="Markdown",
            reply_markup=build_admin_wait_keyboard(),
        )
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text(
            "❌ user_id 必须是数字",
            reply_markup=build_admin_result_keyboard(ADMIN_WAIT_ADDUSER),
        )
        return

    username = " ".join(context.args[1:]).strip() if len(context.args) > 1 else ""
    await update.message.reply_text(
        _add_user_by_admin(target_id, username),
        parse_mode="Markdown",
        reply_markup=build_admin_result_keyboard(ADMIN_WAIT_ADDUSER),
    )


@admin_only
async def kick_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /kick <user_id> — remove a user."""
    context.user_data.pop(ADMIN_WAIT_ACTION_KEY, None)
    if not context.args:
        context.user_data[ADMIN_WAIT_ACTION_KEY] = ADMIN_WAIT_KICK
        await update.message.reply_text(
            "🗑️ **移除用户**\n\n请直接发送要移除的 `user_id`。",
            parse_mode="Markdown",
            reply_markup=build_admin_wait_keyboard(),
        )
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text(
            "❌ user_id 必须是数字",
            reply_markup=build_admin_result_keyboard(ADMIN_WAIT_KICK),
        )
        return

    await update.message.reply_text(
        _kick_user_by_admin(target_id),
        parse_mode="Markdown",
        reply_markup=build_admin_result_keyboard(ADMIN_WAIT_KICK),
    )


async def admin_text_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button-guided text input (custom time + admin adduser/kick)."""
    if not update.message:
        return

    uid = _uid(update)
    join_waiting = context.user_data.get(USER_WAIT_JOIN_CODE_KEY)
    if join_waiting:
        if models.is_authorized(uid):
            context.user_data.pop(USER_WAIT_JOIN_CODE_KEY, None)
            text, keyboard = build_main_menu(uid)
            await update.message.reply_text(
                "✅ 你已经是授权用户了，直接使用菜单即可。",
                reply_markup=keyboard,
            )
            return

        code = update.message.text.strip()
        if not code:
            return
        if not models.use_invite_code(code, uid):
            await update.message.reply_text(
                "❌ 邀请码无效或已被使用，请重试。",
                reply_markup=_build_intro_wait_keyboard(),
            )
            return

        username = update.effective_user.username or update.effective_user.first_name or ""
        context.user_data.pop(USER_WAIT_JOIN_CODE_KEY, None)
        text, keyboard = _build_join_success_ui(uid, username)
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)
        return

    custom_time_waiting = context.user_data.get(USER_WAIT_CUSTOM_TIME_KEY)
    if custom_time_waiting:
        if not models.is_authorized(uid):
            context.user_data.pop(USER_WAIT_CUSTOM_TIME_KEY, None)
            return

        parsed = _parse_time_input(update.message.text.strip())
        if not parsed:
            await update.message.reply_text(
                "❌ 时间格式错误，请输入 HH:MM（如 09:30）。",
                reply_markup=build_time_wait_keyboard(),
            )
            return

        hour, minute = parsed
        time_formatted = f"{hour:02d}:{minute:02d}"
        models.set_setting(uid, "digest_time", time_formatted)
        context.user_data.pop(USER_WAIT_CUSTOM_TIME_KEY, None)
        text, keyboard = build_settime_ui(uid)
        await update.message.reply_text(
            f"✅ 推送时间已设置为 **{time_formatted}** (北京时间)\n\n{text}",
            parse_mode="Markdown",
            reply_markup=keyboard,
        )
        return

    action = context.user_data.get(ADMIN_WAIT_ACTION_KEY)
    if not action:
        return

    if not models.is_admin(uid):
        context.user_data.pop(ADMIN_WAIT_ACTION_KEY, None)
        return

    raw = update.message.text.strip()
    if not raw:
        return
    if raw.lower() in {"cancel", "/cancel", "取消", "返回"}:
        context.user_data.pop(ADMIN_WAIT_ACTION_KEY, None)
        text, keyboard = build_admin_panel_ui()
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)
        return

    if action == ADMIN_WAIT_ADDUSER:
        parts = raw.split(maxsplit=1)
        try:
            target_id = int(parts[0])
        except ValueError:
            await update.message.reply_text(
                "❌ 格式错误，请输入：`user_id` 或 `user_id 用户名`",
                parse_mode="Markdown",
                reply_markup=build_admin_wait_keyboard(),
            )
            return

        username = parts[1].strip() if len(parts) > 1 else ""
        context.user_data.pop(ADMIN_WAIT_ACTION_KEY, None)
        await update.message.reply_text(
            _add_user_by_admin(target_id, username),
            parse_mode="Markdown",
            reply_markup=build_admin_result_keyboard(ADMIN_WAIT_ADDUSER),
        )
        return

    if action == ADMIN_WAIT_KICK:
        try:
            target_id = int(raw.split()[0])
        except ValueError:
            await update.message.reply_text(
                "❌ 格式错误，请输入要移除的 `user_id`",
                parse_mode="Markdown",
                reply_markup=build_admin_wait_keyboard(),
            )
            return

        context.user_data.pop(ADMIN_WAIT_ACTION_KEY, None)
        await update.message.reply_text(
            _kick_user_by_admin(target_id),
            parse_mode="Markdown",
            reply_markup=build_admin_result_keyboard(ADMIN_WAIT_KICK),
        )


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
        await query.edit_message_text(
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
            "向管理员索取邀请码后，点击「🔑 输入邀请码」并发送邀请码即可开始使用。",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔑 输入邀请码", callback_data="intro_join")],
                [InlineKeyboardButton("🔙 返回欢迎页", callback_data="intro_welcome")],
            ]),
        )
        return
    if data == "intro_join":
        context.user_data[USER_WAIT_JOIN_CODE_KEY] = True
        await query.edit_message_text(
            "🔑 **输入邀请码**\n\n请直接发送邀请码文本，我会自动完成加入流程。",
            parse_mode="Markdown",
            reply_markup=_build_intro_wait_keyboard(),
        )
        return
    if data == "intro_welcome":
        context.user_data.pop(USER_WAIT_JOIN_CODE_KEY, None)
        text, keyboard = _build_intro_ui()
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=keyboard)
        return

    # All other callbacks require authorization
    if not models.is_authorized(uid):
        text, keyboard = _build_intro_ui()
        await query.message.reply_text(
            "⛔ 请先点击「🔑 输入邀请码」并发送邀请码。",
            parse_mode="Markdown",
            reply_markup=keyboard,
        )
        return

    # Leaving admin input mode unless we are entering adduser/kick input flow.
    if data not in ("adm_adduser", "adm_kick"):
        context.user_data.pop(ADMIN_WAIT_ACTION_KEY, None)
    # Leaving custom time input mode unless we are entering it.
    if data != "settime_custom":
        context.user_data.pop(USER_WAIT_CUSTOM_TIME_KEY, None)
    context.user_data.pop(USER_WAIT_JOIN_CODE_KEY, None)

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
    elif data == "cmd_settime":
        text, keyboard = build_settime_ui(uid)
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=keyboard)
    elif data == "settime_custom":
        context.user_data[USER_WAIT_CUSTOM_TIME_KEY] = True
        await query.edit_message_text(
            "✍️ **自定义推送时间**\n\n"
            "请直接发送时间（`HH:MM`），例如：`09:30`。",
            parse_mode="Markdown",
            reply_markup=build_time_wait_keyboard(),
        )
    elif data == "cmd_admin":
        if not models.is_admin(uid):
            await query.answer("仅管理员可用", show_alert=True)
            return
        context.user_data.pop(ADMIN_WAIT_ACTION_KEY, None)
        text, keyboard = build_admin_panel_ui()
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=keyboard)
    elif data == "adm_cancel_wait":
        context.user_data.pop(ADMIN_WAIT_ACTION_KEY, None)
        if models.is_admin(uid):
            text, keyboard = build_admin_panel_ui()
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=keyboard)
        else:
            text, keyboard = build_main_menu(uid)
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=keyboard)
    elif data == "adm_invite":
        if not models.is_admin(uid):
            await query.answer("仅管理员可用", show_alert=True)
            return
        code = models.create_invite_code(uid)
        await query.edit_message_text(
            f"🎟️ **邀请码已生成**\n\n"
            f"```\n{code}\n```\n\n"
            "分享给用户后，对方点击「🔑 输入邀请码」并发送该邀请码。",
            parse_mode="Markdown",
            reply_markup=build_admin_invite_keyboard(),
        )
    elif data == "adm_users":
        if not models.is_admin(uid):
            await query.answer("仅管理员可用", show_alert=True)
            return
        await query.edit_message_text(
            _build_users_text(),
            parse_mode="Markdown",
            reply_markup=build_admin_users_keyboard(),
        )
    elif data == "adm_adduser":
        if not models.is_admin(uid):
            await query.answer("仅管理员可用", show_alert=True)
            return
        context.user_data[ADMIN_WAIT_ACTION_KEY] = ADMIN_WAIT_ADDUSER
        await query.edit_message_text(
            "➕ **添加用户**\n\n"
            "请发送：`user_id` 或 `user_id 用户名`\n\n"
            "例如：`123456789 alice`",
            parse_mode="Markdown",
            reply_markup=build_admin_wait_keyboard(),
        )
    elif data == "adm_kick":
        if not models.is_admin(uid):
            await query.answer("仅管理员可用", show_alert=True)
            return
        context.user_data[ADMIN_WAIT_ACTION_KEY] = ADMIN_WAIT_KICK
        await query.edit_message_text(
            "🗑️ **移除用户**\n\n"
            "请发送要移除的 `user_id`。",
            parse_mode="Markdown",
            reply_markup=build_admin_wait_keyboard(),
        )
    elif data.startswith("settime_"):
        hhmm = data.split("_", 1)[1]
        if len(hhmm) != 4 or not hhmm.isdigit():
            return
        time_formatted = f"{hhmm[:2]}:{hhmm[2:]}"
        models.set_setting(uid, "digest_time", time_formatted)
        text, keyboard = build_main_menu(
            uid,
            f"✅ 推送时间已设置为 **{time_formatted}** (北京时间)",
        )
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=keyboard)
    elif data == "cmd_digest":
        await query.message.reply_text(
            "⏳ 正在抓取内容并生成摘要，请稍候...",
            reply_markup=build_back_menu_keyboard(),
        )
        from bot.scheduler import run_digest_for_user
        summary = await run_digest_for_user(uid)
        if summary:
            if len(summary) > 4000:
                for i in range(0, len(summary), 4000):
                    await query.message.reply_text(summary[i:i+4000], parse_mode="Markdown")
            else:
                await query.message.reply_text(summary, parse_mode="Markdown")
            await query.message.reply_text("✅ 摘要生成完成。", reply_markup=build_back_menu_keyboard())
        else:
            await query.message.reply_text(
                "😕 暂无可用内容。请检查是否有启用的信息源。",
                reply_markup=build_back_menu_keyboard(),
            )
    elif data == "cmd_help":
        await help_command(update, context, from_callback=True)
    elif data.startswith("import_"):
        group_name = data[7:]  # Remove "import_" prefix
        await _cb_import(query, uid, group_name)
    elif data.startswith("tglsrc_"):
        try:
            sid = int(data.split('_')[1])
        except (ValueError, IndexError):
            return
        changed = models.toggle_source_by_id(uid, sid)
        if changed is not None:
            text, keyboard = build_list_ui(uid)
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=keyboard)
    elif data.startswith("delsrc_"):
        try:
            sid = int(data.split('_')[1])
        except (ValueError, IndexError):
            return
        removed = models.remove_source_by_id(uid, sid)
        if removed:
            text, keyboard = build_list_ui(uid)
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=keyboard)
    elif data.startswith("tglgrp_"):
        try:
            group_ref_id = int(data.split('_', 1)[1])
        except (ValueError, IndexError):
            return
        changed = models.toggle_group_by_ref_id(uid, group_ref_id)
        if changed is not None:
            text, keyboard = build_groups_ui(uid)
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=keyboard)
    elif data.startswith("delgrp_"):
        try:
            group_ref_id = int(data.split('_', 1)[1])
        except (ValueError, IndexError):
            return
        removed = models.remove_group_by_ref_id(uid, group_ref_id)
        if removed > 0:
            text, keyboard = build_groups_ui(uid)
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=keyboard)


async def _cb_presets(query):
    """Show presets with import buttons (from button press)."""
    text, keyboard = build_presets_ui()
    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


async def _cb_import(query, uid: int, group_name: str):
    """Import a preset group (from button press)."""
    preset_sources = get_preset(group_name)
    canonical_name = get_preset_key(group_name)

    if preset_sources is None or canonical_name is None:
        await query.message.reply_text(
            f"❌ 未找到预设: {group_name}",
            reply_markup=build_back_menu_keyboard(),
        )
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
            [InlineKeyboardButton("🔙 返回菜单", callback_data="cmd_menu")],
        ]),
    )
