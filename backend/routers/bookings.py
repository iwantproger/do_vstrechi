"""Роуты бронирований и напоминаний."""
import uuid
import asyncio
import asyncpg
import structlog
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query

from database import db
from auth import get_current_user, get_optional_user
from schemas import BookingCreate
from utils import row_to_dict, rows_to_list, generate_meeting_link, _track_event, _notify_bot_new_booking

log = structlog.get_logger()
router = APIRouter()


@router.post("/api/bookings")
async def create_booking(
    data: BookingCreate,
    conn: asyncpg.Connection = Depends(db),
    auth_user: dict | None = Depends(get_optional_user),
):
    try:
        sid = uuid.UUID(data.schedule_id)
        scheduled_time = datetime.fromisoformat(data.scheduled_time.replace("Z", "+00:00"))
    except ValueError as e:
        log.warning("invalid_booking_data", error=str(e))
        raise HTTPException(status_code=400, detail="Неверный формат данных")

    schedule = await conn.fetchrow("SELECT * FROM schedules WHERE id = $1 AND is_active = TRUE", sid)
    if not schedule:
        raise HTTPException(status_code=404, detail="Расписание не найдено")

    conflict = await conn.fetchrow(
        """
        SELECT id FROM bookings
        WHERE schedule_id = $1
          AND scheduled_time = $2
          AND status NOT IN ('cancelled')
        """,
        sid, scheduled_time
    )
    if conflict:
        raise HTTPException(status_code=409, detail="Это время уже занято")

    meeting_link = generate_meeting_link(schedule["platform"])
    guest_telegram_id = auth_user["id"] if auth_user else data.guest_telegram_id
    initial_status = 'pending' if schedule.get("requires_confirmation", True) else 'confirmed'

    row = await conn.fetchrow(
        """
        INSERT INTO bookings
            (schedule_id, guest_name, guest_contact, guest_telegram_id,
             scheduled_time, status, meeting_link, notes)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
        RETURNING *
        """,
        sid, data.guest_name, data.guest_contact, guest_telegram_id,
        scheduled_time, initial_status, meeting_link, data.notes
    )

    result = row_to_dict(row)

    organizer = await conn.fetchrow(
        "SELECT telegram_id, timezone FROM users WHERE id = $1", schedule["user_id"]
    )
    if organizer and organizer["telegram_id"]:
        asyncio.create_task(_notify_bot_new_booking(
            booking_id=str(result["id"]),
            organizer_telegram_id=organizer["telegram_id"],
            organizer_timezone=organizer.get("timezone") or "UTC",
            guest_name=data.guest_name,
            guest_contact=data.guest_contact,
            guest_telegram_id=guest_telegram_id,
            scheduled_time=data.scheduled_time,
            schedule_title=schedule["title"],
            meeting_link=meeting_link,
        ))

    await _track_event(conn, "booking_created", guest_telegram_id or 0, {
        "booking_id": str(result["id"]), "schedule_id": str(sid),
    })
    log.info("booking_created", booking_id=str(result["id"]), schedule_id=str(sid))
    return result


@router.get("/api/bookings")
async def list_bookings(
    auth_user: dict = Depends(get_current_user),
    role: Optional[str] = Query(None, description="organizer | guest | all"),
    conn: asyncpg.Connection = Depends(db),
):
    telegram_id = auth_user["id"]

    rows = await conn.fetch(
        """
        SELECT
            b.id,
            b.schedule_id,
            b.guest_name,
            b.guest_contact,
            b.guest_telegram_id,
            b.scheduled_time,
            b.status,
            b.meeting_link,
            b.notes,
            b.created_at,
            s.title        AS schedule_title,
            s.duration     AS schedule_duration,
            s.platform     AS schedule_platform,
            u.first_name   AS organizer_first_name,
            u.username     AS organizer_username,
            u.timezone     AS organizer_timezone,
            COALESCE(b.title, s.title) AS display_title,
            b.is_manual,
            b.end_time     AS booking_end_time,
            CASE
                WHEN u.telegram_id = $1 THEN 'organizer'
                ELSE 'guest'
            END AS my_role
        FROM bookings b
        JOIN schedules s ON s.id = b.schedule_id
        JOIN users u ON u.id = s.user_id
        WHERE
            (u.telegram_id = $1 OR b.guest_telegram_id = $1)
            AND b.status != 'cancelled'
        ORDER BY b.scheduled_time ASC
        """,
        telegram_id
    )

    result = rows_to_list(rows)

    if role == "organizer":
        result = [r for r in result if r["my_role"] == "organizer"]
    elif role == "guest":
        result = [r for r in result if r["my_role"] == "guest"]

    return result


@router.get("/api/bookings/pending-reminders")
async def get_pending_reminders(
    reminder_type: str = Query(...),
    conn: asyncpg.Connection = Depends(db),
):
    if reminder_type not in ("24h", "1h"):
        raise HTTPException(400, "reminder_type must be '24h' or '1h'")

    if reminder_type == "24h":
        flag_col = "reminder_24h_sent"
        interval = "INTERVAL '24 hours 15 minutes'"
        min_interval = "INTERVAL '23 hours 45 minutes'"
    else:
        flag_col = "reminder_1h_sent"
        interval = "INTERVAL '1 hour 15 minutes'"
        min_interval = "INTERVAL '45 minutes'"

    rows = await conn.fetch(f"""
        SELECT b.id, b.guest_name, b.guest_contact, b.guest_telegram_id,
               b.scheduled_time, b.meeting_link, b.notes,
               s.title AS schedule_title, s.duration,
               u.telegram_id AS organizer_telegram_id,
               u.first_name AS organizer_name,
               u.timezone AS organizer_timezone
        FROM bookings b
        JOIN schedules s ON b.schedule_id = s.id
        JOIN users u ON s.user_id = u.id
        WHERE b.status = 'confirmed'
          AND b.{flag_col} = FALSE
          AND b.scheduled_time > NOW()
          AND b.scheduled_time <= NOW() + {interval}
          AND b.scheduled_time >= NOW() + {min_interval}
    """)
    return {"bookings": [dict(r) for r in rows]}


@router.get("/api/bookings/{booking_id}")
async def get_booking(
    booking_id: str,
    auth_user: dict | None = Depends(get_optional_user),
    conn: asyncpg.Connection = Depends(db),
):
    """Получить детали одного бронирования."""
    try:
        bid = uuid.UUID(booking_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Неверный формат ID")

    row = await conn.fetchrow("""
        SELECT b.*,
               s.title       AS schedule_title,
               s.duration    AS schedule_duration,
               s.platform    AS schedule_platform,
               u.first_name  AS organizer_first_name,
               u.last_name   AS organizer_last_name,
               u.username    AS organizer_username
        FROM bookings b
        JOIN schedules s ON s.id = b.schedule_id
        JOIN users u ON u.id = s.user_id
        WHERE b.id = $1
    """, bid)
    if not row:
        raise HTTPException(status_code=404, detail="Бронирование не найдено")

    result = row_to_dict(row)

    if auth_user:
        tid = auth_user["id"]
        if result.get("guest_telegram_id") == tid:
            result["my_role"] = "guest"
        else:
            organizer_tid = await conn.fetchval(
                "SELECT telegram_id FROM users WHERE id = (SELECT user_id FROM schedules WHERE id = $1)",
                row["schedule_id"]
            )
            result["my_role"] = "organizer" if organizer_tid == tid else "viewer"

    return result


@router.patch("/api/bookings/{booking_id}/confirm")
async def confirm_booking(
    booking_id: str,
    auth_user: dict = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(db),
):
    telegram_id = auth_user["id"]
    try:
        bid = uuid.UUID(booking_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Неверный ID")

    row = await conn.fetchrow(
        """
        UPDATE bookings SET status = 'confirmed'
        WHERE id = $1
          AND schedule_id IN (
              SELECT s.id FROM schedules s
              JOIN users u ON u.id = s.user_id
              WHERE u.telegram_id = $2
          )
          AND status = 'pending'
        RETURNING *
        """,
        bid, telegram_id
    )
    if not row:
        raise HTTPException(status_code=404, detail="Бронирование не найдено или уже обработано")
    await _track_event(conn, "booking_confirmed", telegram_id, {"booking_id": booking_id})
    return row_to_dict(row)


@router.patch("/api/bookings/{booking_id}/cancel")
async def cancel_booking(
    booking_id: str,
    auth_user: dict = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(db),
):
    telegram_id = auth_user["id"]
    try:
        bid = uuid.UUID(booking_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Неверный ID")

    row = await conn.fetchrow(
        """
        UPDATE bookings SET status = 'cancelled'
        WHERE id = $1
          AND (
            schedule_id IN (
                SELECT s.id FROM schedules s
                JOIN users u ON u.id = s.user_id
                WHERE u.telegram_id = $2
            )
            OR
            guest_telegram_id = $2
          )
          AND status NOT IN ('cancelled', 'completed')
        RETURNING *
        """,
        bid, telegram_id
    )
    if not row:
        raise HTTPException(status_code=404, detail="Бронирование не найдено или нельзя отменить")
    await _track_event(conn, "booking_cancelled", telegram_id, {"booking_id": booking_id})
    return row_to_dict(row)


@router.patch("/api/bookings/{booking_id}/reminder-sent")
async def mark_reminder_sent(
    booking_id: str,
    reminder_type: str = Query(...),
    conn: asyncpg.Connection = Depends(db),
):
    if reminder_type not in ("24h", "1h"):
        raise HTTPException(400, "Invalid reminder_type")
    flag_col = "reminder_24h_sent" if reminder_type == "24h" else "reminder_1h_sent"
    await conn.execute(
        f"UPDATE bookings SET {flag_col} = TRUE WHERE id = $1",
        uuid.UUID(booking_id),
    )
    return {"ok": True}
