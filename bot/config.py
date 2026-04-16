"""Конфигурация бота — переменные окружения."""
import os

BOT_TOKEN        = os.environ["BOT_TOKEN"]
BACKEND_URL      = os.environ.get("BACKEND_API_URL", "http://backend:8000")
MINI_APP_URL     = os.environ.get("MINI_APP_URL", "https://YOUR_DOMAIN.ru")
INTERNAL_API_KEY = os.environ.get("INTERNAL_API_KEY", "")
REDIS_URL        = os.environ.get("REDIS_URL", "")

# ── Webhook mode ──────────────────────────────────────────
WEBHOOK_ENABLED = os.environ.get("WEBHOOK_ENABLED", "false").lower() == "true"
WEBHOOK_HOST    = os.environ.get("WEBHOOK_HOST", "")       # e.g. https://dovstrechiapp.ru
WEBHOOK_PATH    = os.environ.get("WEBHOOK_PATH", "/bot/webhook")
WEBHOOK_SECRET  = os.environ.get("WEBHOOK_SECRET", "")     # X-Telegram-Bot-Api-Secret-Token
BOT_PORT        = int(os.environ.get("BOT_PORT", "8080"))
