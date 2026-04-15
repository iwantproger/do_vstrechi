"""Роут быстрого создания встречи."""
import uuid
import asyncpg
import structlog
from datetime import datetime, timedelta, date, time, timezone
from fastapi import APIRouter, Depends, HTTPException

from database import db
from auth import get_current_user
from schemas import QuickMeetingCreate
from utils import row_to_dict, generate_meeting_link

log = structlog.get_logger()
router = APIRouter()


async def get_or_create_default_schedule(conn, telegram_id: int) -> dict:
    """Find or create a hidden default schedule for personal meetings."""
    user = await conn.fetchrow("SELECT id FROM users WHERE telegram_id = $1", telegram_id)
    if not user:
        raise HTTPException(404, "Пользователь не найден")
    user_id = user["id"]

    schedule = await conn.fetchrow(
        "SELECT * FROM schedules WHERE user_id = $1 AND is_default = TRUE", user_id
    )
    if schedule:
        return dict(schedule)

    schedule = await conn.fetchrow(
        """
        INSERT INTO schedules
            (user_id, title, description, duration, buffer_time,
             work_days, start_time, end_time, platform, is_default)
        VALUES ($1, 'Личные встречи', 'Автоматическое расписание для личных событий',
                60, 0, '{0,1,2,3,4,5,6}', '00:00', '23:59', 'jitsi', TRUE)
        RETURNING *
        """,
        user_id,
    )
    return dict(schedule)


@router.post("/api/meetings/quick", status_code=201)
async def create_quick_meeting(
    data: QuickMeetingCreate,
    auth_user: dict = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(db),
):
    """Создать встречу вручную (организатор). Mode A: личная, Mode B: в расписание."""
    telegram_id = auth_user["id"]

    try:
        meeting_date = date.fromisoformat(data.date)
        start_h, start_m = map(int, data.start_time.split(":"))
    except (ValueError, IndexError):
        raise HTTPException(400, "Неверный формат даты или времени")

    scheduled_dt = datetime(
        meeting_date.year, meeting_date.month, meeting_date.day,
        start_h, start_m, tzinfo=timezone.utc,
    )

    end_dt = None
    if data.end_time:
        try:
            end_h, end_m = map(int, data.end_time.split(":"))
            end_date_val = date.fromisoformat(data.end_date) if data.end_date else meeting_date
            end_dt = datetime(
                end_date_val.year, end_date_val.month, end_date_val.day,
                end_h, end_m, tzinfo=timezone.utc,
            )
        except (ValueError, IndexError):
            raise HTTPException(400, "Неверный формат end_time/end_date")
        # Ночная встреча: 23:00→01:00 — если end <= start и end_date не задан, +1 день
        if end_dt <= scheduled_dt and not data.end_date:
            end_dt += timedelta(days=1)
        if end_dt <= scheduled_dt:
            raise HTTPException(400, "Время окончания должно быть позже начала")

    if data.schedule_id:
        try:
            schedule_uuid = uuid.UUID(data.schedule_id)
        except ValueError:
            raise HTTPException(400, "Неверный schedule_id")

        schedule = await conn.fetchrow(
            """
            SELECT s.* FROM schedules s
            JOIN users u ON s.user_id = u.id
            WHERE s.id = $1 AND u.telegram_id = $2 AND s.is_active = TRUE
            """,
            schedule_uuid, telegram_id,
        )
        if not schedule:
            raise HTTPException(404, "Расписание не найдено или нет доступа")

        duration = schedule["duration"]
        slot_end = scheduled_dt + timedelta(minutes=duration)
        conflict = await conn.fetchrow(
            """
            SELECT id FROM bookings
            WHERE schedule_id = $1
              AND status != 'cancelled'
              AND scheduled_time < $3
              AND (scheduled_time + ($4 * INTERVAL '1 minute')) > $2
            """,
            schedule_uuid, scheduled_dt, slot_end, duration,
        )
        if conflict:
            raise HTTPException(409, "Это время уже занято")

        platform = schedule["platform"]
        # Если end_time не передан — вычислить из duration расписания
        if end_dt is None:
            end_dt = scheduled_dt + timedelta(minutes=duration)
    else:
        default_schedule = await get_or_create_default_schedule(conn, telegram_id)
        schedule_uuid = default_schedule["id"]
        platform = default_schedule["platform"]

    # Личная встреча (без расписания) — не генерировать ссылку
    meeting_link = None if not data.schedule_id else generate_meeting_link(platform)
    guest_name = data.guest_name or data.title
    guest_contact = data.guest_contact or ""

    blocks_slots = data.blocks_slots if data.blocks_slots is not None else True

    booking = await conn.fetchrow(
        """
        INSERT INTO bookings
            (schedule_id, guest_name, guest_contact, scheduled_time,
             status, meeting_link, notes, title, end_time, is_manual, created_by,
             blocks_slots)
        VALUES ($1, $2, $3, $4, 'confirmed', $5, $6, $7, $8, TRUE, $9, $10)
        RETURNING *
        """,
        schedule_uuid, guest_name, guest_contact, scheduled_dt,
        meeting_link, data.notes, data.title, end_dt, telegram_id,
        blocks_slots,
    )

    log.info("quick_meeting_created", booking_id=str(booking["id"]), telegram_id=telegram_id)
    return row_to_dict(booking)
