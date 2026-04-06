"""Конфигурация бота — переменные окружения."""
import os

BOT_TOKEN        = os.environ["BOT_TOKEN"]
BACKEND_URL      = os.environ.get("BACKEND_API_URL", "http://backend:8000")
MINI_APP_URL     = os.environ.get("MINI_APP_URL", "https://YOUR_DOMAIN.ru")
INTERNAL_API_KEY = os.environ.get("INTERNAL_API_KEY", "")
