"""Роуты пользователей."""
import json
import os
import asyncpg
import httpx
import structlog
from zoneinfo import available_timezones
from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.responses import Response

from database import db
from auth import get_current_user
from schemas import UserAuth
from utils import row_to_dict, _track_event

log = structlog.get_logger()
router = APIRouter()


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


@router.patch("/api/users/notification-settings")
async def update_notification_settings(
    request: Request,
    conn: asyncpg.Connection = Depends(db),
    auth_user: dict = Depends(get_current_user),
):
    body = await request.json()
    telegram_id = auth_user["id"]
    settings = json.dumps(body.get("settings", {}))
    await conn.execute(
        "UPDATE users SET reminder_settings = $1::jsonb WHERE telegram_id = $2",
        settings, telegram_id,
    )
    return {"ok": True}


@router.get("/api/users/{telegram_id}/avatar")
async def get_user_avatar(telegram_id: int):
    """Проксирует аватарку пользователя из Telegram Bot API. Cache-Control: 1 час."""
    bot_token = os.getenv("BOT_TOKEN")
    if not bot_token:
        raise HTTPException(status_code=503, detail="Bot token not configured")

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"https://api.telegram.org/bot{bot_token}/getUserProfilePhotos",
            params={"user_id": telegram_id, "limit": 1},
        )
        data = resp.json()

    if not data.get("ok") or not data["result"]["photos"]:
        raise HTTPException(status_code=404, detail="No avatar")

    photo_sizes = data["result"]["photos"][0]
    # Берём средний размер (~320px) или последний если только один
    file_id = photo_sizes[min(1, len(photo_sizes) - 1)]["file_id"]

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"https://api.telegram.org/bot{bot_token}/getFile",
            params={"file_id": file_id},
        )
        file_data = resp.json()

    if not file_data.get("ok"):
        raise HTTPException(status_code=404, detail="File not found")

    file_path = file_data["result"]["file_path"]

    async with httpx.AsyncClient(timeout=15.0) as client:
        img_resp = await client.get(
            f"https://api.telegram.org/file/bot{bot_token}/{file_path}"
        )

    if img_resp.status_code != 200:
        raise HTTPException(status_code=404, detail="Image not available")

    return Response(
        content=img_resp.content,
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.get("/api/users/{telegram_id}")
async def get_user(telegram_id: int, conn: asyncpg.Connection = Depends(db)):
    row = await conn.fetchrow("SELECT * FROM users WHERE telegram_id = $1", telegram_id)
    if not row:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return row_to_dict(row)
