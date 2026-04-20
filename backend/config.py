"""Конфигурация — все переменные окружения и константы."""
import os
import time as _time

DATABASE_URL = os.environ["DATABASE_URL"]
DATABASE_ADMIN_URL = os.environ.get("DATABASE_ADMIN_URL", DATABASE_URL)
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
# Секрет для аутентификации бот↔backend. Обязательная переменная.
# Генерация: openssl rand -hex 32
INTERNAL_API_KEY = os.environ.get("INTERNAL_API_KEY", "")
assert INTERNAL_API_KEY, "INTERNAL_API_KEY is required — generate with: openssl rand -hex 32"
BOT_INTERNAL_URL = os.environ.get("BOT_INTERNAL_URL", "http://bot:8080")
MINI_APP_URL = os.environ.get("MINI_APP_URL", "")
SECRET_KEY = os.environ.get("SECRET_KEY", "")

ADMIN_TELEGRAM_ID = int(os.environ.get("ADMIN_TELEGRAM_ID", "0"))

_admin_ids_raw = os.environ.get("ADMIN_TELEGRAM_IDS", "")
if _admin_ids_raw:
    ADMIN_TELEGRAM_IDS: set[int] = set(
        int(x.strip()) for x in _admin_ids_raw.split(",") if x.strip().isdigit()
    )
else:
    ADMIN_TELEGRAM_IDS = {ADMIN_TELEGRAM_ID} if ADMIN_TELEGRAM_ID else set()

ADMIN_OWNER_ID = int(_admin_ids_raw.split(",")[0].strip() or "0") if _admin_ids_raw else ADMIN_TELEGRAM_ID
ADMIN_SESSION_TTL_HOURS = int(os.environ.get("ADMIN_SESSION_TTL_HOURS", "2"))
ADMIN_IP_ALLOWLIST = os.environ.get("ADMIN_IP_ALLOWLIST", "").strip()
# SECURITY: ANONYMIZE_SALT must be provided via env — no default allowed.
# Used to hash telegram_id → anonymous_id for analytics. A weak/known salt
# would allow reversing anonymous_id back to telegram_id via rainbow tables.
ANONYMIZE_SALT = os.environ["ANONYMIZE_SALT"]
assert len(ANONYMIZE_SALT) >= 16, "ANONYMIZE_SALT must be at least 16 characters"

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
APP_VERSION = "1.4.0"

# Prod launch date — analytics only counts data from this date
PROD_LAUNCH_DATE = os.environ.get("PROD_LAUNCH_DATE", "")

from datetime import datetime as _dt, timezone as _tz
def get_prod_cutoff():
    """Return prod cutoff datetime for SQL. If not set, returns epoch (no filtering)."""
    if PROD_LAUNCH_DATE:
        try:
            return _dt.strptime(PROD_LAUNCH_DATE, "%Y-%m-%d").replace(tzinfo=_tz.utc)
        except ValueError:
            pass
    return _dt(2000, 1, 1, tzinfo=_tz.utc)

# Pre-compute owner anonymous_id for filtering in admin dashboards
import hashlib as _hashlib
OWNER_ANONYMOUS_ID: str | None = (
    _hashlib.sha256(f"{ADMIN_TELEGRAM_ID}:{ANONYMIZE_SALT}".encode()).hexdigest()[:12]
    if ADMIN_TELEGRAM_ID
    else None
)
