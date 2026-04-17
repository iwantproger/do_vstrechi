"""Конфигурация бота — переменные окружения."""
import os

BOT_TOKEN        = os.environ["BOT_TOKEN"]
BACKEND_URL      = os.environ.get("BACKEND_API_URL", "http://backend:8000")
MINI_APP_URL     = os.environ.get("MINI_APP_URL", "https://YOUR_DOMAIN.ru")
INTERNAL_API_KEY = os.environ.get("INTERNAL_API_KEY", "")
REDIS_URL        = os.environ.get("REDIS_URL", "")
BOT_USERNAME     = os.environ.get("BOT_USERNAME", "do_vstrechi_bot")

# Admin IDs
_admin_ids_raw = os.environ.get("ADMIN_TELEGRAM_IDS", "")
_admin_id_single = int(os.environ.get("ADMIN_TELEGRAM_ID", "0"))
if _admin_ids_raw:
    ADMIN_TELEGRAM_IDS: set[int] = set(
        int(x.strip()) for x in _admin_ids_raw.split(",") if x.strip().isdigit()
    )
else:
    ADMIN_TELEGRAM_IDS = {_admin_id_single} if _admin_id_single else set()

ADMIN_OWNER_ID = int(_admin_ids_raw.split(",")[0].strip() or "0") if _admin_ids_raw else _admin_id_single

# ── Webhook mode ──────────────────────────────────────────
WEBHOOK_ENABLED = os.environ.get("WEBHOOK_ENABLED", "false").lower() == "true"
WEBHOOK_HOST    = os.environ.get("WEBHOOK_HOST", "")       # e.g. https://dovstrechiapp.ru
WEBHOOK_PATH    = os.environ.get("WEBHOOK_PATH", "/bot/webhook")
WEBHOOK_SECRET  = os.environ.get("WEBHOOK_SECRET", "")     # X-Telegram-Bot-Api-Secret-Token
BOT_PORT        = int(os.environ.get("BOT_PORT", "8080"))
