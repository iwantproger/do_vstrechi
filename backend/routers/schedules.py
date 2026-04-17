"""Роуты расписаний и доступных слотов."""
import os
import uuid
import asyncio
import calendar as _calendar
import asyncpg
import structlog
from datetime import datetime, timedelta, timezone, date as _date
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
             location_address, min_booking_advance, requires_confirmation, custom_link)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)
        RETURNING *
        """,
        user["id"], data.title, data.description, data.duration, data.buffer_time,
        data.work_days,
        datetime.strptime(data.start_time, "%H:%M").time(),
        datetime.strptime(data.end_time, "%H:%M").time(),
        data.location_mode, data.platform, data.location_address,
        data.min_booking_advance or 0, data.requires_confirmation, data.custom_link
    )
    await _track_event(conn, "schedule_created", telegram_id, {
        "schedule_id": str(row["id"]), "duration": data.duration, "platform": data.platform,
    })
    return row_to_dict(row)


@router.post("/api/schedules/default")
async def create_default_schedule(
    auth_user: dict = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(db),
):
    """Create a visible default schedule for a new user (called from bot on first /start)."""
    telegram_id = auth_user["id"]
    user = await conn.fetchrow(
        "SELECT id, first_name FROM users WHERE telegram_id = $1", telegram_id
    )
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    # Don't create if user already has visible active schedules
    existing = await conn.fetchval(
        "SELECT COUNT(*) FROM schedules WHERE user_id = $1 AND is_default = FALSE AND is_active = TRUE",
        user["id"],
    )
    if existing > 0:
        return {"created": False, "schedule": None}

    first_name = user["first_name"] or "Пользователь"
    title = f"Свободное время. {first_name}"
    description = "Мои свободные слоты. Вы можете забронировать удобное время."

    row = await conn.fetchrow(
        """
        INSERT INTO schedules
            (user_id, title, description, duration, buffer_time,
             work_days, start_time, end_time, platform,
             min_booking_advance, requires_confirmation, is_active, is_default)
        VALUES ($1, $2, $3, 45, 15,
                '{0,1,2,3,4}', '09:00', '18:00', 'jitsi',
                60, TRUE, TRUE, FALSE)
        RETURNING *
        """,
        user["id"], title, description,
    )
    await _track_event(conn, "schedule_created", telegram_id, {
        "schedule_id": str(row["id"]), "duration": 45, "platform": "jitsi",
        "source": "default_onboarding",
    })
    return {"created": True, "schedule": row_to_dict(row)}


@router.get("/api/schedules")
async def list_schedules(
    auth_user: dict = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    page: Optional[int] = Query(None, ge=1),
    per_page: Optional[int] = Query(None, ge=1, le=100),
    conn: asyncpg.Connection = Depends(db),
):
    telegram_id = auth_user["id"]

    # If caller opted into page/per_page, translate to limit/offset.
    # Otherwise keep existing limit/offset contract.
    if page is not None or per_page is not None:
        pp = per_page or 100
        pg = page or 1
        limit = pp
        offset = (pg - 1) * pp
    else:
        pp = limit
        pg = (offset // limit) + 1 if limit else 1

    total_row = await conn.fetchrow(
        """
        SELECT COUNT(*) FROM schedules s
        JOIN users u ON u.id = s.user_id
        WHERE u.telegram_id = $1 AND s.is_default = FALSE
        """,
        telegram_id
    )
    total = total_row[0] if total_row else 0
    rows = await conn.fetch(
        """
        SELECT s.* FROM schedules s
        JOIN users u ON u.id = s.user_id
        WHERE u.telegram_id = $1 AND s.is_default = FALSE
        ORDER BY s.created_at DESC
        LIMIT $2 OFFSET $3
        """,
        telegram_id, limit, offset
    )
    items = rows_to_list(rows)
    has_more = (offset + len(items)) < total
    # Preserve existing fields (schedules/total/limit/offset) + add paginated metadata.
    return {
        "schedules": items,
        "total": total,
        "limit": limit,
        "offset": offset,
        "page": pg,
        "per_page": pp,
        "has_more": has_more,
    }


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


@router.get("/api/schedules/{schedule_id}/share")
async def get_schedule_share(
    schedule_id: str,
    conn: asyncpg.Connection = Depends(db),
):
    """Единый формат share-сообщения для расписания."""
    try:
        uid = uuid.UUID(schedule_id)
    except ValueError:
        raise HTTPException(400, "Неверный формат ID")

    sched = await conn.fetchrow(
        "SELECT id, title FROM schedules WHERE id = $1 AND is_active = TRUE", uid
    )
    if not sched:
        raise HTTPException(404, "Расписание не найдено или на паузе")

    bot_username = os.getenv("BOT_USERNAME", "do_vstrechi_bot")
    mini_app_url = os.getenv("MINI_APP_URL", "https://dovstrechiapp.ru")
    tg_link = f"https://t.me/{bot_username}/app?startapp={schedule_id}"
    web_link = f"{mini_app_url}?schedule_id={schedule_id}"

    text_html = (
        f"Вот мои свободные слоты — выбирайте удобное время!\n\n"
        f"До встречи! 🙌\n\n"
        f'Или <a href="{web_link}">открыть в браузере</a>\n\n'
        f"Ссылка для копирования:\n"
        f"<code>{tg_link}</code>"
    )

    text_plain = (
        f"Вот мои свободные слоты — выбирайте удобное время!\n"
        f"До встречи! 🙌\n\n"
        f"Открыть в браузере:\n{web_link}"
    )

    return {
        "direct_link": tg_link,
        "browser_link": web_link,
        "text_html": text_html,
        "text_plain": text_plain,
    }


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
        # Only bookings with blocks_slots=TRUE block availability.
        # Uses b.end_time when available (manual meetings) to get accurate intervals.
        organizer_bookings = await conn.fetch(
            """
            SELECT b.scheduled_time,
                   b.end_time                   AS booking_end_time,
                   COALESCE(s.duration, 60)     AS duration,
                   COALESCE(s.buffer_time, 0)   AS buffer_time
            FROM bookings b
            JOIN schedules s ON s.id = b.schedule_id
            WHERE s.user_id = $1
              AND b.status NOT IN ('cancelled')
              AND b.blocks_slots = TRUE
              AND b.scheduled_time >= $2::timestamptz - INTERVAL '24 hours'
              AND b.scheduled_time <  $3::timestamptz + INTERVAL '24 hours'
            """,
            schedule["user_id"], slot_start_utc, slot_end_utc,
        )

        # Build list of (occ_start, occ_end) intervals in UTC, including buffer on both sides.
        occupied: list[tuple[datetime, datetime]] = []
        for r in organizer_bookings:
            occ_start = r["scheduled_time"].replace(second=0, microsecond=0)
            if r["booking_end_time"]:
                # Manual meetings: use explicit end_time + buffer from booking's schedule
                occ_end = r["booking_end_time"].replace(second=0, microsecond=0)
            else:
                occ_end = occ_start + timedelta(minutes=int(r["duration"]))
            occ_end += timedelta(minutes=int(r["buffer_time"]))
            occupied.append((occ_start, occ_end))

        # External busy slots из подключённых календарей
        try:
            from calendars.db import get_schedule_calendar_rules, get_external_busy_slots
            rules = await get_schedule_calendar_rules(conn, str(sid))
            blocking_ids = [str(r["connection_id"]) for r in rules if r.get("use_for_blocking")]

            # Zero-config: если правил нет — блокируем всеми read-enabled календарями
            if not blocking_ids:
                organizer_id = schedule["user_id"]
                all_conns = await conn.fetch(
                    """
                    SELECT cc.id FROM calendar_connections cc
                    JOIN calendar_accounts ca ON ca.id = cc.account_id
                    WHERE ca.user_id = $1
                      AND ca.status = 'active'
                      AND cc.is_read_enabled = TRUE
                    """,
                    organizer_id,
                )
                blocking_ids = [str(c["id"]) for c in all_conns]

            if blocking_ids:
                ext_busy = await get_external_busy_slots(
                    conn, blocking_ids, slot_start_utc, slot_end_utc,
                )
                for eb in ext_busy:
                    occupied.append((eb["start_time"], eb["end_time"]))
        except Exception as e:
            log.warning("external_busy_slots_error", schedule_id=schedule_id, error=str(e))

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


# ─────────────────────────────────────────────────────────
# Month batch endpoint
# Single SQL for all bookings in the month; Python loop per work-day.
# Response shape: {"YYYY-MM-DD": [{"time":"HH:MM","datetime":"ISO"}, ...], ...}
# ─────────────────────────────────────────────────────────
@router.get("/api/available-slots/{schedule_id}/month")
async def available_slots_month(
    schedule_id: str,
    year: int = Query(..., ge=2020, le=2100),
    month: int = Query(..., ge=1, le=12),
    viewer_tz: str = Query("UTC", description="Viewer IANA timezone"),
    conn: asyncpg.Connection = Depends(db),
):
    try:
        sid = uuid.UUID(schedule_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Неверный формат ID")

    row = await conn.fetchrow(
        """
        SELECT s.*, u.timezone AS organizer_timezone
        FROM schedules s JOIN users u ON u.id = s.user_id
        WHERE s.id = $1 AND s.is_active = TRUE
        """,
        sid,
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

    # Month window in organizer TZ → UTC bounds (±24h safety margin).
    _, last_day = _calendar.monthrange(year, month)
    month_first = datetime(year, month, 1, 0, 0, tzinfo=org_tz)
    month_last = datetime(year, month, last_day, 23, 59, tzinfo=org_tz)
    month_first_utc = month_first.astimezone(ZoneInfo("UTC")) - timedelta(hours=24)
    month_last_utc = month_last.astimezone(ZoneInfo("UTC")) + timedelta(hours=24)

    # ONE query for all organizer's bookings in the month window
    organizer_bookings = await conn.fetch(
        """
        SELECT b.scheduled_time,
               b.end_time                 AS booking_end_time,
               COALESCE(s.duration, 60)   AS duration,
               COALESCE(s.buffer_time, 0) AS buffer_time
        FROM bookings b
        JOIN schedules s ON s.id = b.schedule_id
        WHERE s.user_id = $1
          AND b.status NOT IN ('cancelled')
          AND b.blocks_slots = TRUE
          AND b.scheduled_time >= $2::timestamptz
          AND b.scheduled_time <  $3::timestamptz
        """,
        schedule["user_id"], month_first_utc, month_last_utc,
    )

    occupied: list[tuple[datetime, datetime]] = []
    for r in organizer_bookings:
        occ_start = r["scheduled_time"].replace(second=0, microsecond=0)
        if r["booking_end_time"]:
            occ_end = r["booking_end_time"].replace(second=0, microsecond=0)
        else:
            occ_end = occ_start + timedelta(minutes=int(r["duration"]))
        occ_end += timedelta(minutes=int(r["buffer_time"]))
        occupied.append((occ_start, occ_end))

    # External busy slots across the month (one call)
    try:
        from calendars.db import get_schedule_calendar_rules, get_external_busy_slots
        rules = await get_schedule_calendar_rules(conn, str(sid))
        blocking_ids = [str(r["connection_id"]) for r in rules if r.get("use_for_blocking")]

        if not blocking_ids:
            organizer_id = schedule["user_id"]
            all_conns = await conn.fetch(
                """
                SELECT cc.id FROM calendar_connections cc
                JOIN calendar_accounts ca ON ca.id = cc.account_id
                WHERE ca.user_id = $1
                  AND ca.status = 'active'
                  AND cc.is_read_enabled = TRUE
                """,
                organizer_id,
            )
            blocking_ids = [str(c["id"]) for c in all_conns]

        if blocking_ids:
            ext_busy = await get_external_busy_slots(
                conn, blocking_ids, month_first_utc, month_last_utc,
            )
            for eb in ext_busy:
                occupied.append((eb["start_time"], eb["end_time"]))
    except Exception as e:
        log.warning("month_external_busy_slots_error", schedule_id=schedule_id, error=str(e))

    duration_min = int(schedule["duration"])
    buffer_min = int(schedule["buffer_time"] or 0)
    step = timedelta(minutes=duration_min + buffer_min)
    slot_duration = timedelta(minutes=duration_min)
    if slot_duration.total_seconds() <= 0:
        log.warning("invalid_slot_duration", schedule_id=schedule_id, duration=duration_min)
        return {}

    start_h, start_m = map(int, schedule["start_time"].strftime("%H:%M").split(":"))
    end_h, end_m = map(int, schedule["end_time"].strftime("%H:%M").split(":"))
    work_days = schedule["work_days"] or []

    now_utc = datetime.now(ZoneInfo("UTC"))
    min_advance = int(schedule.get("min_booking_advance") or 0)
    earliest_bookable_utc = now_utc + timedelta(minutes=min_advance)

    result: dict[str, list] = {}
    for day in range(1, last_day + 1):
        d = _date(year, month, day)
        if d.weekday() not in work_days:
            continue
        slot_start = datetime(d.year, d.month, d.day, start_h, start_m, tzinfo=org_tz)
        slot_end = datetime(d.year, d.month, d.day, end_h, end_m, tzinfo=org_tz)

        day_slots = []
        current = slot_start
        while current + slot_duration <= slot_end:
            current_utc = current.astimezone(ZoneInfo("UTC")).replace(second=0, microsecond=0)
            candidate_end_utc = current_utc + slot_duration
            if current_utc > earliest_bookable_utc:
                conflict = any(
                    current_utc < occ_end and candidate_end_utc > occ_start
                    for occ_start, occ_end in occupied
                )
                if not conflict:
                    viewer_dt = current.astimezone(vtz)
                    day_slots.append({
                        "time": current.strftime("%H:%M"),
                        "datetime": current_utc.isoformat(),
                        "datetime_utc": current_utc.isoformat(),
                        "datetime_local": viewer_dt.strftime("%H:%M"),
                    })
            current += step

        if day_slots:
            result[d.isoformat()] = day_slots

    return result
