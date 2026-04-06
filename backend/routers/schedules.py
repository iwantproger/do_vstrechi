"""Роуты расписаний и доступных слотов."""
import uuid
import asyncpg
import structlog
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, available_timezones
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query

from database import db
from auth import get_current_user
from schemas import ScheduleCreate, ScheduleUpdate
from utils import row_to_dict, rows_to_list, _track_event

log = structlog.get_logger()
router = APIRouter()


@router.post("/api/schedules")
async def create_schedule(
    data: ScheduleCreate,
    auth_user: dict = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(db),
):
    telegram_id = auth_user["id"]
    user = await conn.fetchrow("SELECT id FROM users WHERE telegram_id = $1", telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден. Сначала /start")

    row = await conn.fetchrow(
        """
        INSERT INTO schedules
            (user_id, title, description, duration, buffer_time,
             work_days, start_time, end_time, location_mode, platform, min_booking_advance)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
        RETURNING *
        """,
        user["id"], data.title, data.description, data.duration, data.buffer_time,
        data.work_days,
        datetime.strptime(data.start_time, "%H:%M").time(),
        datetime.strptime(data.end_time, "%H:%M").time(),
        data.location_mode, data.platform, data.min_booking_advance or 0
    )
    await _track_event(conn, "schedule_created", telegram_id, {
        "schedule_id": str(row["id"]), "duration": data.duration, "platform": data.platform,
    })
    return row_to_dict(row)


@router.get("/api/schedules")
async def list_schedules(
    auth_user: dict = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(db),
):
    telegram_id = auth_user["id"]
    rows = await conn.fetch(
        """
        SELECT s.* FROM schedules s
        JOIN users u ON u.id = s.user_id
        WHERE u.telegram_id = $1 AND s.is_default = FALSE
        ORDER BY s.created_at DESC
        """,
        telegram_id
    )
    return rows_to_list(rows)


@router.get("/api/schedules/{schedule_id}")
async def get_schedule(schedule_id: str, conn: asyncpg.Connection = Depends(db)):
    try:
        sid = uuid.UUID(schedule_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Неверный формат ID")

    row = await conn.fetchrow("SELECT * FROM schedules WHERE id = $1", sid)
    if not row:
        raise HTTPException(status_code=404, detail="Расписание не найдено")
    return row_to_dict(row)


@router.delete("/api/schedules/{schedule_id}")
async def delete_schedule(
    schedule_id: str,
    auth_user: dict = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(db),
):
    try:
        sid = uuid.UUID(schedule_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Неверный формат ID")

    telegram_id = auth_user["id"]
    result = await conn.execute(
        """
        UPDATE schedules SET is_active = FALSE
        WHERE id = $1
          AND user_id = (SELECT id FROM users WHERE telegram_id = $2)
        """,
        sid, telegram_id
    )
    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail="Расписание не найдено или нет доступа")
    await _track_event(conn, "schedule_deleted", telegram_id, {"schedule_id": schedule_id})
    return {"success": True}


@router.patch("/api/schedules/{schedule_id}")
async def update_schedule(
    schedule_id: str,
    data: ScheduleUpdate,
    auth_user: dict = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(db),
):
    try:
        sid = uuid.UUID(schedule_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Неверный формат ID")

    telegram_id = auth_user["id"]
    updates = data.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="Нет полей для обновления")

    for tf in ("start_time", "end_time"):
        if tf in updates:
            updates[tf] = datetime.strptime(updates[tf], "%H:%M").time()

    set_parts = []
    values = []
    for i, (col, val) in enumerate(updates.items(), start=1):
        set_parts.append(f"{col} = ${i}")
        values.append(val)

    values.append(sid)
    values.append(telegram_id)
    n = len(values)

    row = await conn.fetchrow(
        f"""
        UPDATE schedules SET {', '.join(set_parts)}
        WHERE id = ${n - 1}
          AND user_id = (SELECT id FROM users WHERE telegram_id = ${n})
        RETURNING *
        """,
        *values,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Расписание не найдено или нет доступа")
    return row_to_dict(row)


@router.get("/api/available-slots/{schedule_id}")
async def available_slots(
    schedule_id: str,
    date: str = Query(..., description="YYYY-MM-DD"),
    viewer_tz: str = Query("UTC", description="Viewer IANA timezone"),
    conn: asyncpg.Connection = Depends(db),
):
    try:
        sid = uuid.UUID(schedule_id)
        target_date = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Неверный формат параметров")

    row = await conn.fetchrow(
        """
        SELECT s.*, u.timezone AS organizer_timezone
        FROM schedules s JOIN users u ON u.id = s.user_id
        WHERE s.id = $1 AND s.is_active = TRUE
        """,
        sid
    )
    if not row:
        raise HTTPException(status_code=404, detail="Расписание не найдено")
    schedule = dict(row)

    org_tz = ZoneInfo(schedule.get("organizer_timezone") or "UTC")
    vtz = ZoneInfo(viewer_tz) if viewer_tz in available_timezones() else ZoneInfo("UTC")

    day_of_week = target_date.weekday()
    if day_of_week not in schedule["work_days"]:
        return {"available_slots": [], "date": date}

    start_h, start_m = map(int, schedule["start_time"].strftime("%H:%M").split(":"))
    end_h, end_m = map(int, schedule["end_time"].strftime("%H:%M").split(":"))

    slot_start = datetime(target_date.year, target_date.month, target_date.day,
                          start_h, start_m, tzinfo=org_tz)
    slot_end = datetime(target_date.year, target_date.month, target_date.day,
                        end_h, end_m, tzinfo=org_tz)

    slot_start_utc = slot_start.astimezone(ZoneInfo("UTC"))
    slot_end_utc = slot_end.astimezone(ZoneInfo("UTC"))
    booked = await conn.fetch(
        """
        SELECT scheduled_time FROM bookings
        WHERE schedule_id = $1
          AND status NOT IN ('cancelled')
          AND scheduled_time >= $2
          AND scheduled_time < $3
        """,
        sid, slot_start_utc, slot_end_utc
    )
    booked_utc = {r["scheduled_time"].replace(second=0, microsecond=0) for r in booked}

    manual_booked = await conn.fetch(
        """
        SELECT b.scheduled_time FROM bookings b
        JOIN schedules s ON b.schedule_id = s.id
        WHERE s.user_id = (SELECT user_id FROM schedules WHERE id = $1)
          AND s.is_default = TRUE
          AND b.status != 'cancelled'
          AND b.scheduled_time >= $2
          AND b.scheduled_time < $3
        """,
        sid, slot_start_utc, slot_end_utc,
    )
    booked_utc.update({r["scheduled_time"].replace(second=0, microsecond=0) for r in manual_booked})

    step = timedelta(minutes=schedule["duration"] + schedule["buffer_time"])
    slot_duration = timedelta(minutes=schedule["duration"])
    now_utc = datetime.now(ZoneInfo("UTC"))
    min_advance = schedule.get("min_booking_advance") or 0
    earliest_bookable_utc = now_utc + timedelta(minutes=min_advance)

    slots = []
    current = slot_start
    while current + slot_duration <= slot_end:
        current_utc = current.astimezone(ZoneInfo("UTC")).replace(second=0, microsecond=0)
        if current_utc > earliest_bookable_utc and current_utc not in booked_utc:
            viewer_dt = current.astimezone(vtz)
            slots.append({
                "time": current.strftime("%H:%M"),
                "datetime": current_utc.isoformat(),
                "datetime_utc": current_utc.isoformat(),
                "datetime_local": viewer_dt.strftime("%H:%M"),
            })
        current += step

    if slots:
        await _track_event(conn, "slots_viewed", 0, {
            "schedule_id": schedule_id, "date": date, "slots_count": len(slots),
        })
    return {"available_slots": slots, "date": date}
