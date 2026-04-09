"""Google OAuth 2.0 web server flow — авторизация и обмен кодов."""

import hmac
import hashlib
import time
from urllib.parse import urlencode

import httpx
import structlog

from config import (
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    GOOGLE_REDIRECT_URI,
    SECRET_KEY,
)

log = structlog.get_logger()

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

SCOPES = " ".join([
    "https://www.googleapis.com/auth/calendar.readonly",  # list calendars (calendarList.list)
    "https://www.googleapis.com/auth/calendar.events",    # create/update/delete events
    "https://www.googleapis.com/auth/userinfo.email",     # show connected account email
])

STATE_MAX_AGE = 600  # 10 минут


def sign_state(telegram_id: int) -> str:
    """Подписать state HMAC-SHA256: telegram_id:timestamp:signature."""
    ts = str(int(time.time()))
    payload = f"{telegram_id}:{ts}"
    sig = hmac.new(
        SECRET_KEY.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()[:16]
    return f"{payload}:{sig}"


def verify_state(state: str) -> int:
    """Проверить подпись и TTL state → telegram_id. ValueError если невалидный."""
    parts = state.split(":")
    if len(parts) != 3:
        raise ValueError("Invalid OAuth state format")

    telegram_id_str, ts_str, sig = parts

    # Проверка подписи
    payload = f"{telegram_id_str}:{ts_str}"
    expected = hmac.new(
        SECRET_KEY.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()[:16]
    if not hmac.compare_digest(sig, expected):
        raise ValueError("Invalid OAuth state signature")

    # Проверка TTL
    try:
        ts = int(ts_str)
    except ValueError:
        raise ValueError("Invalid OAuth state timestamp")
    if time.time() - ts > STATE_MAX_AGE:
        raise ValueError("OAuth state expired (max 10 min)")

    return int(telegram_id_str)


def get_google_auth_url(state: str) -> str:
    """Сформировать URL для Google OAuth consent screen."""
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPES,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


async def exchange_google_code(code: str) -> dict:
    """Обменять authorization code на токены."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(GOOGLE_TOKEN_URL, data={
            "code": code,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code",
        })
    if resp.status_code != 200:
        log.warning("google_token_exchange_failed", status=resp.status_code, body=resp.text[:500])
        raise ValueError(f"Token exchange failed: {resp.status_code}")

    data = resp.json()
    return {
        "access_token": data["access_token"],
        "refresh_token": data.get("refresh_token"),
        "expires_in": data.get("expires_in", 3600),
    }


async def get_google_user_email(access_token: str) -> str:
    """Получить email пользователя через Google userinfo."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
    if resp.status_code != 200:
        raise ValueError(f"Failed to get user info: {resp.status_code}")
    return resp.json().get("email", "")
