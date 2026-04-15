"""Конфигурация — все переменные окружения и константы."""
import os
import time as _time

DATABASE_URL = os.environ["DATABASE_URL"]
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
INTERNAL_API_KEY = os.environ.get("INTERNAL_API_KEY", "")
BOT_INTERNAL_URL = os.environ.get("BOT_INTERNAL_URL", "http://bot:8080")
MINI_APP_URL = os.environ.get("MINI_APP_URL", "")
SECRET_KEY = os.environ.get("SECRET_KEY", "")

ADMIN_TELEGRAM_ID = int(os.environ.get("ADMIN_TELEGRAM_ID", "0"))
ADMIN_SESSION_TTL_HOURS = int(os.environ.get("ADMIN_SESSION_TTL_HOURS", "2"))
ADMIN_IP_ALLOWLIST = os.environ.get("ADMIN_IP_ALLOWLIST", "").strip()
ANONYMIZE_SALT = os.environ.get("ANONYMIZE_SALT", "do-vstrechi-2026")

# Encryption (Fernet) для токенов внешних календарей
ENCRYPTION_KEY = os.environ.get("ENCRYPTION_KEY", "")

# Google Calendar OAuth
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI", "")
# HTTPS base URL, used to build the webhook address (defaults to MINI_APP_URL)
CALENDAR_WEBHOOK_URL = os.environ.get("CALENDAR_WEBHOOK_URL", "")

# Telegram bot username (без @) — для OAuth-редиректа обратно в бот
BOT_USERNAME = os.environ.get("BOT_USERNAME", "")

_allowed_origins = os.environ.get("ALLOWED_ORIGINS", "").strip()
CORS_ORIGINS = (
    [o.strip() for o in _allowed_origins.split(",") if o.strip()]
    if _allowed_origins
    else ["https://dovstrechiapp.ru", "https://www.dovstrechiapp.ru"]
)
if MINI_APP_URL and MINI_APP_URL not in CORS_ORIGINS:
    CORS_ORIGINS.append(MINI_APP_URL)

APP_START_TIME = _time.time()
APP_VERSION = "1.2.0"

# Pre-compute owner anonymous_id for filtering in admin dashboards
import hashlib as _hashlib
OWNER_ANONYMOUS_ID: str | None = (
    _hashlib.sha256(f"{ADMIN_TELEGRAM_ID}:{ANONYMIZE_SALT}".encode()).hexdigest()[:12]
    if ADMIN_TELEGRAM_ID
    else None
)
