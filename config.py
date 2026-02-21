"""Configuration loader for EigenDigest Bot."""

import os
from dotenv import load_dotenv

load_dotenv()

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "0"))

# LLM (OpenAI-compatible)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")

# Database
DB_PATH = os.getenv("DB_PATH", "eigendigest.db")

# Scheduler defaults
DEFAULT_DIGEST_HOUR = 8
DEFAULT_DIGEST_MINUTE = 0
TIMEZONE = "Asia/Shanghai"
