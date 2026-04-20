"""Роуты пользователей."""
import json
import os
import time
import asyncpg
import httpx
from httpx import ConnectTimeout, ReadTimeout, HTTPError
import structlog
from zoneinfo import available_timezones
from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.responses import Response

from database import db
from auth import get_current_user, get_internal_caller
from schemas import UserAuth, NotificationSettingsUpdate
from utils import row_to_dict, _track_event

log = structlog.get_logger()
router = APIRouter()

# In-memory avatar cache: telegram_id → (expires_at, content, media_type)
_avatar_cache: dict[int, tuple[float, bytes, str]] = {}
_AVATAR_TTL = 3600  # 1 hour

_AVATAR_COLORS = [
    "#5B9BD5", "#70AD47", "#ED7D31", "#FFC000",
    "#9E67AB", "#4BACC6", "#E05050", "#26A69A",
]


def _make_initials_svg(telegram_id: int) -> bytes:
    color = _AVATAR_COLORS[telegram_id % len(_AVATAR_COLORS)]
    letter = str(telegram_id)[-1]
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128">'
        f'<rect width="128" height="128" rx="64" fill="{color}"/>'
        f'<text x="64" y="64" dy=".35em" text-anchor="middle" '
        f'font-family="sans-serif" font-size="56" font-weight="bold" fill="white">'
        f'{letter}</text></svg>'
    )
    return svg.encode()


def _avatar_fallback(telegram_id: int, now: float) -> Response:
    svg = _make_initials_svg(telegram_id)
    _avatar_cache[telegram_id] = (now + _AVATAR_TTL, svg, "image/svg+xml")
    return Response(
        content=svg,
        media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.post("/api/users/auth")
async def auth_user(
    data: UserAuth,
    user: dict = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(db),
):
    telegram_id = user["id"]
    tz = data.timezone if data.timezone and data.timezone in available_timezones() else "UTC"
    row = await conn.fetchrow(
        """
        INSERT INTO users (telegram_id, username, first_name, last_name, timezone)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (telegram_id) DO UPDATE
            SET username   = EXCLUDED.username,
                first_name = EXCLUDED.first_name,
                last_name  = EXCLUDED.last_name,
                timezone   = EXCLUDED.timezone,
                updated_at = NOW()
        RETURNING *
        """,
        telegram_id, data.username, data.first_name, data.last_name, tz
    )
    is_new = row["created_at"] == row["updated_at"] if row else False
    await _track_event(conn, "user_auth", telegram_id, {"timezone": tz, "is_new": is_new})
    return row_to_dict(row)


_NOTIF_DEFAULTS = {"reminders": ["1440", "60", "5"], "customReminders": [], "booking_notif": True, "reminder_notif": True}


@router.get("/api/users/notification-settings")
async def get_notification_settings(
    auth_user: dict = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(db),
):
    """Настройки уведомлений текущего пользователя."""
    row = await conn.fetchrow(
        "SELECT reminder_settings FROM users WHERE telegram_id = $1",
        auth_user["id"],
    )
    if not row:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    settings = row["reminder_settings"] or {}
    # Гарантируем наличие всех полей в ответе
    return {
        "reminders": settings.get("reminders", _NOTIF_DEFAULTS["reminders"]),
        "customReminders": settings.get("customReminders", []),
        "booking_notif": settings.get("booking_notif", True),
        "reminder_notif": settings.get("reminder_notif", True),
    }


@router.patch("/api/users/notification-settings")
async def update_notification_settings(
    data: NotificationSettingsUpdate,
    auth_user: dict = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(db),
):
    """Частичное обновление настроек уведомлений (merge с текущим значением)."""
    telegram_id = auth_user["id"]
    # Читаем текущие настройки
    current = await conn.fetchval(
        "SELECT reminder_settings FROM users WHERE telegram_id = $1",
        telegram_id,
    )
    if current is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    merged = dict(current) if current else dict(_NOTIF_DEFAULTS)
    # Merge только переданных полей
    patch = data.model_dump(exclude_none=True)
    merged.update(patch)
    await conn.execute(
        "UPDATE users SET reminder_settings = $1::jsonb WHERE telegram_id = $2",
        json.dumps(merged), telegram_id,
    )
    return merged


@router.patch("/api/users/{telegram_id}/morning-summary-sent")
async def mark_morning_summary_sent(
    telegram_id: int,
    _auth=Depends(get_internal_caller),
    conn: asyncpg.Connection = Depends(db),
):
    """Mark that the morning organizer summary was sent today (prevents duplicate sends)."""
    await conn.execute(
        "UPDATE users SET morning_summary_sent_date = CURRENT_DATE WHERE telegram_id = $1",
        telegram_id,
    )
    return {"ok": True}


@router.get("/api/users/{telegram_id}/avatar")
async def get_user_avatar(telegram_id: int):
    """Проксирует аватарку пользователя из Telegram Bot API. Fallback: SVG. Cache: 1 час."""
    now = time.time()

    # Check in-memory cache
    cached = _avatar_cache.get(telegram_id)
    if cached and cached[0] > now:
        return Response(
            content=cached[1],
            media_type=cached[2],
            headers={"Cache-Control": "public, max-age=3600"},
        )

    bot_token = os.getenv("BOT_TOKEN")
    if not bot_token:
        return _avatar_fallback(telegram_id, now)

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(5.0, connect=5.0)) as client:
            resp = await client.get(
                f"https://api.telegram.org/bot{bot_token}/getUserProfilePhotos",
                params={"user_id": telegram_id, "limit": 1},
            )
            data = resp.json()

        if not data.get("ok") or not data["result"]["photos"]:
            return _avatar_fallback(telegram_id, now)

        photo_sizes = data["result"]["photos"][0]
        file_id = photo_sizes[min(1, len(photo_sizes) - 1)]["file_id"]

        async with httpx.AsyncClient(timeout=httpx.Timeout(5.0, connect=5.0)) as client:
            resp = await client.get(
                f"https://api.telegram.org/bot{bot_token}/getFile",
                params={"file_id": file_id},
            )
            file_data = resp.json()

        if not file_data.get("ok"):
            return _avatar_fallback(telegram_id, now)

        file_path = file_data["result"]["file_path"]

        async with httpx.AsyncClient(timeout=httpx.Timeout(8.0, connect=5.0)) as client:
            img_resp = await client.get(
                f"https://api.telegram.org/file/bot{bot_token}/{file_path}"
            )

        if img_resp.status_code != 200:
            return _avatar_fallback(telegram_id, now)

        content = img_resp.content
        _avatar_cache[telegram_id] = (now + _AVATAR_TTL, content, "image/jpeg")
        return Response(
            content=content,
            media_type="image/jpeg",
            headers={"Cache-Control": "public, max-age=3600"},
        )

    except (ConnectTimeout, ReadTimeout):
        log.warning("avatar_timeout", telegram_id=telegram_id)
        return _avatar_fallback(telegram_id, now)
    except HTTPError as exc:
        log.warning("avatar_http_error", telegram_id=telegram_id, error=str(exc))
        return _avatar_fallback(telegram_id, now)
    except Exception as exc:
        log.error("avatar_unexpected_error", telegram_id=telegram_id, error=str(exc))
        return _avatar_fallback(telegram_id, now)


@router.get("/api/users/{telegram_id}")
async def get_user(telegram_id: int, conn: asyncpg.Connection = Depends(db)):
    row = await conn.fetchrow("SELECT * FROM users WHERE telegram_id = $1", telegram_id)
    if not row:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return row_to_dict(row)
