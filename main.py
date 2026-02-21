"""EigenDigest Bot — main entry point (multi-user)."""

import logging
import sys

from telegram.ext import ApplicationBuilder, CommandHandler

import config
from db import models
from bot import handlers
from bot.scheduler import setup_scheduler

# Configure logging
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("eigendigest.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


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

    # post_init callback: start scheduler after event loop is running
    async def post_init(application):
        setup_scheduler(application)
        logger.info("Scheduler initialized in post_init.")

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
    app.add_handler(CommandHandler("add", handlers.add_command))
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
    app.add_handler(CommandHandler("users", handlers.users_command))
    app.add_handler(CommandHandler("kick", handlers.kick_command))

    # Start polling
    logger.info("🚀 EigenDigest Bot is starting...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
