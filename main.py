"""EigenDigest Bot — main entry point (multi-user)."""

import logging
from pathlib import Path
import sys

from telegram import BotCommand, BotCommandScopeDefault, BotCommandScopeAllPrivateChats, MenuButtonCommands
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler

import config
from db import models
from bot import handlers
from bot.scheduler import setup_scheduler

# Store logs next to the configured DB, which is writable in Docker (/data).
log_path = Path(config.DB_PATH).parent / "eigendigest.log"
log_path.parent.mkdir(parents=True, exist_ok=True)

# Configure logging
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_path, encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

BOT_DESCRIPTION = (
    "EigenDigest 是一个智能信息摘要机器人。\n\n"
    "添加 RSS、网页和微信公众号信息源后，"
    "我会每天按你设定的时间自动抓取内容并生成 AI 精华摘要。"
)


def main():
    """Initialize and run the bot."""
    # Validate config
    if not config.TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN is not set. Please configure .env file.")
        sys.exit(1)
    if not config.OPENAI_API_KEY:
        logger.error("OPENAI_API_KEY is not set. Please configure .env file.")
        sys.exit(1)
    if config.ADMIN_USER_ID == 0:
        logger.error("ADMIN_USER_ID is not set. Please configure .env file.")
        sys.exit(1)

    # Initialize database
    models.init_db()
    logger.info("Database initialized.")

    # post_init callback: start scheduler + register bot metadata/menu
    async def post_init(application):
        setup_scheduler(application)

        # Register commands in Telegram's "/" menu
        commands = [
            BotCommand("start", "开始使用"),
            BotCommand("help", "查看帮助"),
            BotCommand("list", "查看信息源"),
            BotCommand("add", "添加信息源"),
            BotCommand("remove", "删除信息源"),
            BotCommand("toggle", "启用/禁用信息源"),
            BotCommand("groups", "查看分组"),
            BotCommand("presets", "查看预设"),
            BotCommand("import", "导入预设分组"),
            BotCommand("delgroup", "删除整组"),
            BotCommand("togglegroup", "启用/禁用整组"),
            BotCommand("settime", "设置推送时间"),
            BotCommand("digest", "立即生成摘要"),
            BotCommand("join", "使用邀请码加入"),
            BotCommand("invite", "生成邀请码 (管理员)"),
            BotCommand("adduser", "按ID添加用户 (管理员)"),
            BotCommand("users", "查看用户 (管理员)"),
            BotCommand("kick", "移除用户 (管理员)"),
        ]
        try:
            await application.bot.delete_my_commands(scope=BotCommandScopeDefault())
            await application.bot.delete_my_commands(scope=BotCommandScopeAllPrivateChats())
        except Exception as e:
            logger.warning(f"Could not delete old commands: {e}")

        await application.bot.set_my_commands(commands, scope=BotCommandScopeDefault())
        await application.bot.set_my_commands(commands, scope=BotCommandScopeAllPrivateChats())

        try:
            await application.bot.set_my_description(BOT_DESCRIPTION)
        except Exception as e:
            logger.warning(f"Could not set bot description: {e}")
        
        try:
            await application.bot.set_chat_menu_button(menu_button=MenuButtonCommands())
        except Exception as e:
            logger.warning(f"Could not set menu button: {e}")
        logger.info("Scheduler and bot commands initialized.")

    # Build Telegram application
    app = (
        ApplicationBuilder()
        .token(config.TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    # Public commands (no auth required)
    app.add_handler(CommandHandler("start", handlers.start_command))
    app.add_handler(CommandHandler("join", handlers.join_command))

    # User commands (authorized users)
    app.add_handler(CommandHandler("help", handlers.help_command))
    app.add_handler(handlers.get_add_handler())
    app.add_handler(CommandHandler("remove", handlers.remove_command))
    app.add_handler(CommandHandler("list", handlers.list_command))
    app.add_handler(CommandHandler("toggle", handlers.toggle_command))
    app.add_handler(CommandHandler("settime", handlers.settime_command))
    app.add_handler(CommandHandler("digest", handlers.digest_command))

    # Group management (authorized users)
    app.add_handler(CommandHandler("groups", handlers.groups_command))
    app.add_handler(CommandHandler("presets", handlers.presets_command))
    app.add_handler(CommandHandler("import", handlers.import_command))
    app.add_handler(CommandHandler("delgroup", handlers.delgroup_command))
    app.add_handler(CommandHandler("togglegroup", handlers.togglegroup_command))

    # Admin commands
    app.add_handler(CommandHandler("invite", handlers.invite_command))
    app.add_handler(CommandHandler("adduser", handlers.adduser_command))
    app.add_handler(CommandHandler("users", handlers.users_command))
    app.add_handler(CommandHandler("kick", handlers.kick_command))

    # Inline button callbacks
    app.add_handler(CallbackQueryHandler(handlers.callback_handler))

    # Start polling
    logger.info("🚀 EigenDigest Bot is starting...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
