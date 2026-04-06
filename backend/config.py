"""Конфигурация — все переменные окружения и константы."""
import os
import time as _time

DATABASE_URL = os.environ["DATABASE_URL"]
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
INTERNAL_API_KEY = os.environ.get("INTERNAL_API_KEY", "")
BOT_INTERNAL_URL = os.environ.get("BOT_INTERNAL_URL", "http://bot:8080")
MINI_APP_URL = os.environ.get("MINI_APP_URL", "")

ADMIN_TELEGRAM_ID = int(os.environ.get("ADMIN_TELEGRAM_ID", "0"))
ADMIN_SESSION_TTL_HOURS = int(os.environ.get("ADMIN_SESSION_TTL_HOURS", "2"))
ADMIN_IP_ALLOWLIST = os.environ.get("ADMIN_IP_ALLOWLIST", "").strip()
ANONYMIZE_SALT = os.environ.get("ANONYMIZE_SALT", "do-vstrechi-2026")

CORS_ORIGINS = [
    "https://dovstrechiapp.ru",
    "https://www.dovstrechiapp.ru",
    *([] if not MINI_APP_URL else [MINI_APP_URL]),
]

APP_START_TIME = _time.time()
APP_VERSION = "2.0.0"
