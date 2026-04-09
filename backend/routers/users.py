"""Роуты пользователей."""
import json
import asyncpg
import structlog
from zoneinfo import available_timezones
from fastapi import APIRouter, Depends, HTTPException, Request

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


@router.get("/api/users/{telegram_id}")
async def get_user(telegram_id: int, conn: asyncpg.Connection = Depends(db)):
    row = await conn.fetchrow("SELECT * FROM users WHERE telegram_id = $1", telegram_id)
    if not row:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return row_to_dict(row)
