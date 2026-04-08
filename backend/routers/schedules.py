"""Роуты расписаний и доступных слотов."""
import uuid
import asyncio
import asyncpg
import structlog
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, available_timezones
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query

from database import db
from auth import get_current_user
from schemas import ScheduleCreate, ScheduleUpdate
from utils import row_to_dict, rows_to_list, _track_event, _notify_bot_status_change

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
             work_days, start_time, end_time, location_mode, platform,
             min_booking_advance, requires_confirmation)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
        RETURNING *
        """,
        user["id"], data.title, data.description, data.duration, data.buffer_time,
        data.work_days,
        datetime.strptime(data.start_time, "%H:%M").time(),
        datetime.strptime(data.end_time, "%H:%M").time(),
        data.location_mode, data.platform, data.min_booking_advance or 0,
        data.requires_confirmation
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

    row = await conn.fetchrow("""
        SELECT s.*,
               u.first_name  AS organizer_first_name,
               u.last_name   AS organizer_last_name,
               u.username    AS organizer_username
        FROM schedules s
        JOIN users u ON u.id = s.user_id
        WHERE s.id = $1
    """, sid)
    if not row:
        raise HTTPException(status_code=404, detail="Расписание не найдено")
    return row_to_dict(row)


@router.delete("/api/schedules/{schedule_id}")
async def delete_schedule(
    schedule_id: str,
    cancel_meetings: bool = Query(False, description="Отменить все будущие встречи"),
    auth_user: dict = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(db),
):
    try:
        sid = uuid.UUID(schedule_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Неверный формат ID")

    telegram_id = auth_user["id"]

    schedule = await conn.fetchrow(
        """
        SELECT s.id, s.title FROM schedules s
        JOIN users u ON u.id = s.user_id
        WHERE s.id = $1 AND u.telegram_id = $2
        """,
        sid, telegram_id
    )
    if not schedule:
        raise HTTPException(status_code=404, detail="Расписание не найдено или нет доступа")

    await conn.execute("UPDATE schedules SET is_active = FALSE WHERE id = $1", sid)

    cancelled_count = 0
    if cancel_meetings:
        now = datetime.now(timezone.utc)
        cancelled_rows = await conn.fetch(
            """
            UPDATE bookings
            SET status = 'cancelled'
            WHERE schedule_id = $1
              AND scheduled_time > $2
              AND status NOT IN ('cancelled', 'completed')
            RETURNING id, guest_telegram_id, guest_name, scheduled_time
            """,
            sid, now,
        )
        cancelled_count = len(cancelled_rows)
        for b in cancelled_rows:
            if b["guest_telegram_id"]:
                asyncio.create_task(_notify_bot_status_change(
                    booking_id=str(b["id"]),
                    new_status="cancelled",
                    initiator_telegram_id=telegram_id,
                    organizer_telegram_id=telegram_id,
                    guest_telegram_id=b["guest_telegram_id"],
                    guest_name=b["guest_name"],
                    schedule_title=schedule["title"],
                    scheduled_time=str(b["scheduled_time"]),
                    organizer_timezone="UTC",
                ))

    await _track_event(conn, "schedule_deleted", telegram_id, {
        "schedule_id": schedule_id, "cancel_meetings": cancel_meetings,
        "cancelled_count": cancelled_count,
    })
    log.info("schedule_deleted", schedule_id=schedule_id,
             cancel_meetings=cancel_meetings, cancelled=cancelled_count)
    return {"success": True, "meetings_cancelled": cancelled_count}


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

    try:
        org_tz_str = schedule.get("organizer_timezone") or "UTC"
        org_tz = ZoneInfo(org_tz_str)
    except Exception:
        log.warning("unknown_organizer_tz", schedule_id=schedule_id, tz=schedule.get("organizer_timezone"))
        org_tz = ZoneInfo("UTC")

    vtz = ZoneInfo(viewer_tz) if viewer_tz in available_timezones() else ZoneInfo("UTC")

    day_of_week = target_date.weekday()
    if day_of_week not in (schedule["work_days"] or []):
        return {"available_slots": [], "date": date}

    try:
        start_h, start_m = map(int, schedule["start_time"].strftime("%H:%M").split(":"))
        end_h, end_m = map(int, schedule["end_time"].strftime("%H:%M").split(":"))

        slot_start = datetime(target_date.year, target_date.month, target_date.day,
                              start_h, start_m, tzinfo=org_tz)
        slot_end = datetime(target_date.year, target_date.month, target_date.day,
                            end_h, end_m, tzinfo=org_tz)

        slot_start_utc = slot_start.astimezone(ZoneInfo("UTC"))
        slot_end_utc = slot_end.astimezone(ZoneInfo("UTC"))

        # Fetch ALL organizer bookings (across all their schedules) that could overlap with
        # the requested day window (expanded by max possible buffer = 2h on each side).
        organizer_bookings = await conn.fetch(
            """
            SELECT b.scheduled_time,
                   COALESCE(s.duration, 60)     AS duration,
                   COALESCE(s.buffer_time, 0)   AS buffer_time
            FROM bookings b
            JOIN schedules s ON s.id = b.schedule_id
            WHERE s.user_id = $1
              AND b.status NOT IN ('cancelled')
              AND b.scheduled_time >= $2 - INTERVAL '2 hours'
              AND b.scheduled_time <  $3 + INTERVAL '2 hours'
            """,
            schedule["user_id"], slot_start_utc, slot_end_utc,
        )

        # Build list of (occ_start, occ_end) intervals in UTC, including buffer on both sides.
        occupied: list[tuple[datetime, datetime]] = []
        for r in organizer_bookings:
            occ_start = r["scheduled_time"].replace(second=0, microsecond=0)
            occ_end   = occ_start + timedelta(minutes=int(r["duration"]) + int(r["buffer_time"]))
            occupied.append((occ_start, occ_end))

        duration_min = int(schedule["duration"])
        buffer_min   = int(schedule["buffer_time"] or 0)
        step = timedelta(minutes=duration_min + buffer_min)
        slot_duration = timedelta(minutes=duration_min)
        if slot_duration.total_seconds() <= 0:
            log.warning("invalid_slot_duration", schedule_id=schedule_id, duration=duration_min)
            return {"available_slots": [], "date": date}

        now_utc = datetime.now(ZoneInfo("UTC"))
        min_advance = int(schedule.get("min_booking_advance") or 0)
        earliest_bookable_utc = now_utc + timedelta(minutes=min_advance)

        slots = []
        current = slot_start
        while current + slot_duration <= slot_end:
            current_utc = current.astimezone(ZoneInfo("UTC")).replace(second=0, microsecond=0)
            slot_end_utc_candidate = current_utc + slot_duration
            if current_utc > earliest_bookable_utc:
                # Overlap check: slot [current_utc, slot_end_utc_candidate) vs each occupied interval
                conflict = any(
                    current_utc < occ_end and slot_end_utc_candidate > occ_start
                    for occ_start, occ_end in occupied
                )
                if not conflict:
                    viewer_dt = current.astimezone(vtz)
                    slots.append({
                        "time": current.strftime("%H:%M"),
                        "datetime": current_utc.isoformat(),
                        "datetime_utc": current_utc.isoformat(),
                        "datetime_local": viewer_dt.strftime("%H:%M"),
                    })
            current += step

    except Exception as e:
        log.error("available_slots_error", schedule_id=schedule_id, date=date,
                  error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Ошибка расчёта слотов")

    if slots:
        await _track_event(conn, "slots_viewed", 0, {
            "schedule_id": schedule_id, "date": date, "slots_count": len(slots),
        })
    log.debug("available_slots_ok", schedule_id=schedule_id, date=date,
              slots_count=len(slots), org_tz=org_tz_str)
    return {"available_slots": slots, "date": date}
