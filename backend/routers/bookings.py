"""Роуты бронирований и напоминаний."""
import json
import uuid
import asyncio
import asyncpg
import structlog
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import available_timezones
from fastapi import APIRouter, Depends, HTTPException, Query, Request


def _jsonb(val) -> dict:
    """asyncpg может вернуть JSONB как str в контексте RLS-транзакции."""
    if val is None:
        return {}
    if isinstance(val, str):
        return json.loads(val)
    return dict(val)

from database import db
from auth import get_current_user, get_optional_user, get_internal_caller
from schemas import BookingCreate
from utils import row_to_dict, rows_to_list, generate_meeting_link, _track_event, _notify_bot_new_booking, _notify_bot_status_change, _notify_bot_late_booking

log = structlog.get_logger()
router = APIRouter()


@router.post("/api/bookings")
async def create_booking(
    data: BookingCreate,
    request: Request,
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

    if schedule["platform"] == "other" and schedule.get("custom_link"):
        meeting_link = schedule["custom_link"]
    else:
        meeting_link = generate_meeting_link(schedule["platform"])
    guest_telegram_id = auth_user["id"] if auth_user else data.guest_telegram_id
    initial_status = 'pending' if schedule.get("requires_confirmation", True) else 'confirmed'

    # Валидация guest_timezone
    guest_tz = data.guest_timezone
    if guest_tz and guest_tz not in available_timezones():
        raise HTTPException(status_code=400, detail="Invalid timezone")

    row = await conn.fetchrow(
        """
        INSERT INTO bookings
            (schedule_id, guest_name, guest_contact, guest_telegram_id,
             scheduled_time, status, meeting_link, notes,
             platform, location_address, guest_timezone)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
        RETURNING *
        """,
        sid, data.guest_name, data.guest_contact, guest_telegram_id,
        scheduled_time, initial_status, meeting_link, data.notes,
        schedule["platform"],               # снапшот платформы
        schedule.get("location_address"),   # снапшот адреса
        guest_tz,
    )

    result = row_to_dict(row)

    organizer = await conn.fetchrow(
        "SELECT telegram_id, timezone, reminder_settings FROM users WHERE id = $1", schedule["user_id"]
    )
    # Определяем booking_notif для организатора и гостя
    org_settings = _jsonb(organizer["reminder_settings"]) if organizer else {}
    org_booking_notif = org_settings.get("booking_notif", True) if org_settings else True
    guest_booking_notif = True
    guest_row = None
    if guest_telegram_id:
        guest_row = await conn.fetchrow(
            "SELECT reminder_settings FROM users WHERE telegram_id = $1", guest_telegram_id
        )
        if guest_row and guest_row["reminder_settings"]:
            guest_booking_notif = _jsonb(guest_row["reminder_settings"]).get("booking_notif", True)
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
            requires_confirmation=bool(schedule.get("requires_confirmation", True)),
            org_booking_notif=org_booking_notif,
            guest_booking_notif=guest_booking_notif,
            guest_timezone=guest_tz,
        ))

    # Late booking: instant-напоминание если часть напоминаний не попадёт в обычное окно
    time_until_min = (scheduled_time - datetime.now(timezone.utc)).total_seconds() / 60
    _LATE_BUFFER = 5  # буфер между late-logic и обычным окном
    _late_recipients = []
    # Организатор
    if organizer and organizer["telegram_id"]:
        org_reminders = (org_settings.get("reminders") or ["1440", "60", "5"]) if org_settings else ["1440", "60", "5"]
        org_reminder_notif = org_settings.get("reminder_notif", True) if org_settings else True
        if org_reminder_notif:
            missed_org = [int(r) for r in org_reminders if int(r) > time_until_min + _LATE_BUFFER]
            if missed_org:
                _late_recipients.append(("org", organizer["telegram_id"], missed_org, organizer.get("timezone") or "UTC"))
    # Гость
    if guest_telegram_id:
        guest_settings = _jsonb(guest_row["reminder_settings"]) if guest_row else {}
        guest_reminders = guest_settings.get("reminders", ["1440", "60", "5"]) if guest_settings else ["1440", "60", "5"]
        guest_reminder_notif = guest_settings.get("reminder_notif", True) if guest_settings else True
        if guest_reminder_notif:
            missed_guest = [int(r) for r in guest_reminders if int(r) > time_until_min + _LATE_BUFFER]
            if missed_guest:
                _late_recipients.append(("guest", guest_telegram_id, missed_guest, guest_tz or (organizer.get("timezone") if organizer else "UTC") or "UTC"))

    if _late_recipients:
        for role, tid, missed, recipient_tz in _late_recipients:
            # Pre-record в sent_reminders чтобы обычный цикл не дублировал
            for m in missed:
                await conn.execute(
                    "INSERT INTO sent_reminders (booking_id, reminder_type) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                    result["id"], f"{m}:{role}",
                )
            asyncio.create_task(_notify_bot_late_booking(
                booking_id=str(result["id"]),
                recipient_telegram_id=tid,
                role=role,
                recipient_tz=recipient_tz,
                missed_reminders=missed,
                schedule_title=schedule["title"],
                scheduled_time=data.scheduled_time,
                meeting_link=meeting_link,
                duration=int(schedule["duration"]),
                time_until_min=int(time_until_min),
            ))
        log.info("late_booking_instant_triggered", booking_id=str(result["id"]),
                 recipients=len(_late_recipients))

    # Записать во внешние календари (fire-and-forget)
    try:
        from calendars.sync import write_booking_to_calendars
        pool = request.app.state.sync_engine._pool
        asyncio.create_task(write_booking_to_calendars(
            pool=pool,
            booking_id=str(result["id"]),
            schedule_id=str(sid),
            guest_name=data.guest_name,
            scheduled_time=scheduled_time,
            duration_min=int(schedule["duration"]),
            schedule_title=schedule["title"],
            meeting_link=meeting_link,
        ))
    except Exception as e:
        log.warning("calendar_write_schedule_error", error=str(e))

    await _track_event(conn, "booking_created", guest_telegram_id or 0, {
        "booking_id": str(result["id"]), "schedule_id": str(sid),
    })
    log.info("booking_created", booking_id=str(result["id"]), schedule_id=str(sid))
    return result


@router.get("/api/bookings")
async def list_bookings(
    auth_user: dict = Depends(get_current_user),
    role: Optional[str] = Query(None, description="organizer | guest | all"),
    schedule_id: Optional[str] = Query(None, description="Filter by schedule UUID"),
    future_only: bool = Query(False, description="Only future non-cancelled bookings"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    page: Optional[int] = Query(None, ge=1),
    per_page: Optional[int] = Query(None, ge=1, le=100),
    conn: asyncpg.Connection = Depends(db),
):
    telegram_id = auth_user["id"]

    # Translate page/per_page to limit/offset if explicitly given; preserve
    # existing limit/offset contract otherwise.
    if page is not None or per_page is not None:
        pp = per_page or 100
        pg = page or 1
        limit = pp
        offset = (pg - 1) * pp
    else:
        pp = limit
        pg = (offset // limit) + 1 if limit else 1

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
            COALESCE(b.platform, s.platform) AS platform,
            COALESCE(b.location_address, s.location_address) AS location_address,
            u.first_name   AS organizer_first_name,
            u.username     AS organizer_username,
            u.timezone     AS organizer_timezone,
            u.telegram_id  AS organizer_telegram_id,
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

    if schedule_id:
        result = [r for r in result if str(r.get("schedule_id", "")) == schedule_id]

    if future_only:
        now = datetime.now(timezone.utc)
        result = [
            r for r in result
            if r.get("status") not in ("cancelled", "completed")
            and r.get("scheduled_time") is not None
            and r["scheduled_time"] > now
        ]

    total = len(result)
    paginated = result[offset:offset + limit]
    has_more = (offset + len(paginated)) < total
    return {
        "bookings": paginated,
        "total": total,
        "limit": limit,
        "offset": offset,
        "page": pg,
        "per_page": pp,
        "has_more": has_more,
    }


@router.get("/api/bookings/pending-reminders-v2")
async def get_pending_reminders_v2(
    _auth=Depends(get_internal_caller),
    conn: asyncpg.Connection = Depends(db),
):
    """Напоминания per-user: организатор и гость получают по своим настройкам."""
    rows = await conn.fetch("""
        WITH org_mins AS (
            SELECT b.id AS booking_id,
                   'org'::text AS role,
                   u.telegram_id AS recipient_tid,
                   jsonb_array_elements_text(
                       COALESCE(u.reminder_settings->'reminders', '["1440","60","5"]'::jsonb)
                   )::int AS reminder_min
            FROM bookings b
            JOIN schedules s ON s.id = b.schedule_id
            JOIN users u ON u.id = s.user_id
            WHERE b.status IN ('confirmed', 'pending', 'no_answer')
              AND b.scheduled_time > NOW()
              AND COALESCE((u.reminder_settings->>'reminder_notif')::bool, true) = true
        ),
        guest_mins AS (
            SELECT b.id AS booking_id,
                   'guest'::text AS role,
                   b.guest_telegram_id AS recipient_tid,
                   jsonb_array_elements_text(
                       COALESCE(ug.reminder_settings->'reminders', '["1440","60","5"]'::jsonb)
                   )::int AS reminder_min
            FROM bookings b
            LEFT JOIN users ug ON ug.telegram_id = b.guest_telegram_id
            WHERE b.status IN ('confirmed', 'pending', 'no_answer')
              AND b.scheduled_time > NOW()
              AND b.guest_telegram_id IS NOT NULL
              AND COALESCE((ug.reminder_settings->>'reminder_notif')::bool, true) = true
        ),
        all_mins AS (SELECT * FROM org_mins UNION ALL SELECT * FROM guest_mins)
        SELECT
            b.id            AS booking_id,
            b.guest_name,
            b.guest_contact,
            b.guest_telegram_id,
            b.scheduled_time,
            b.meeting_link,
            b.status,
            s.title         AS schedule_title,
            s.duration,
            s.platform,
            u.telegram_id   AS organizer_telegram_id,
            u.first_name    AS organizer_name,
            u.timezone      AS organizer_timezone,
            b.guest_timezone,
            am.reminder_min,
            am.role,
            am.recipient_tid
        FROM all_mins am
        JOIN bookings b ON b.id = am.booking_id
        JOIN schedules s ON s.id = b.schedule_id
        JOIN users u ON u.id = s.user_id
        WHERE b.scheduled_time > NOW()
          AND b.scheduled_time <= NOW() + (am.reminder_min || ' minutes')::interval
          AND b.scheduled_time > NOW() + ((am.reminder_min - 15) || ' minutes')::interval
          AND NOT EXISTS (
              SELECT 1 FROM sent_reminders sr
              WHERE sr.booking_id = b.id
                AND sr.reminder_type = am.reminder_min::text || ':' || am.role
          )
        ORDER BY b.scheduled_time
    """)
    return {"reminders": [dict(r) for r in rows]}


@router.get("/api/bookings/confirmation-requests")
async def get_confirmation_requests(
    _auth=Depends(get_internal_caller),
    conn: asyncpg.Connection = Depends(db),
):
    """Встречи на сегодня, гостям которых нужно отправить утренний запрос «В силе?».

    Адаптивный floor: send_at = max(07:00 в TZ гостя, scheduled - 2ч).
    Не отправляем если осталось <1ч до встречи (слишком поздно реагировать).
    Не отправляем если target > deadline (встреча слишком рано, напр. 04:00).
    Опрос каждые 5 мин → окно 6 минут для надёжности.
    """
    rows = await conn.fetch("""
        WITH send_times AS (
            SELECT
                b.id AS booking_id,
                COALESCE(b.guest_timezone, u.timezone, 'UTC') AS rtz,
                -- 07:00 в TZ получателя, конвертированный в UTC
                (DATE_TRUNC('day', b.scheduled_time AT TIME ZONE COALESCE(b.guest_timezone, u.timezone, 'UTC'))
                    + INTERVAL '7 hours')
                  AT TIME ZONE COALESCE(b.guest_timezone, u.timezone, 'UTC') AS floor_utc,
                -- За 2 часа до встречи
                b.scheduled_time - INTERVAL '2 hours' AS target_2h,
                -- Дедлайн: за 1 час до встречи (позже отправлять нет смысла)
                b.scheduled_time - INTERVAL '1 hour'  AS deadline
            FROM bookings b
            JOIN schedules s ON s.id = b.schedule_id
            JOIN users u ON u.id = s.user_id
            WHERE b.status = 'confirmed'
              AND b.confirmation_asked = FALSE
              AND b.guest_telegram_id IS NOT NULL
              AND b.scheduled_time > NOW()
              AND DATE(b.created_at AT TIME ZONE COALESCE(b.guest_timezone, u.timezone, 'UTC'))
                  < DATE(b.scheduled_time AT TIME ZONE COALESCE(b.guest_timezone, u.timezone, 'UTC'))
        )
        SELECT b.id, b.guest_name, b.guest_telegram_id,
               b.scheduled_time, b.meeting_link, b.created_at,
               b.guest_timezone,
               s.title    AS schedule_title,
               s.duration,
               u.timezone AS organizer_timezone,
               u.telegram_id AS organizer_telegram_id
        FROM send_times st
        JOIN bookings b ON b.id = st.booking_id
        JOIN schedules s ON s.id = b.schedule_id
        JOIN users u ON u.id = s.user_id
        WHERE GREATEST(st.floor_utc, st.target_2h) <= st.deadline
          AND NOW() >= GREATEST(st.floor_utc, st.target_2h)
          AND NOW() <= st.deadline + INTERVAL '6 minutes'
    """)
    log.info("confirmation_requests_found", count=len(rows))
    return {"bookings": [dict(r) for r in rows]}


@router.patch("/api/bookings/{booking_id}/confirmation-asked")
async def mark_confirmation_asked(
    booking_id: str,
    _auth=Depends(get_internal_caller),
    conn: asyncpg.Connection = Depends(db),
):
    """Mark that confirmation was asked for this booking (called by bot after sending message)."""
    try:
        bid = uuid.UUID(booking_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Неверный ID")
    await conn.execute(
        "UPDATE bookings SET confirmation_asked = TRUE, confirmation_asked_at = NOW() WHERE id = $1",
        bid,
    )
    return {"ok": True}


@router.get("/api/bookings/no-answer-candidates")
async def get_no_answer_candidates(
    _auth=Depends(get_internal_caller),
    conn: asyncpg.Connection = Depends(db),
):
    """Bookings where confirmation was asked >1h ago but guest didn't respond."""
    rows = await conn.fetch("""
        SELECT b.id, b.guest_name, b.guest_telegram_id,
               b.scheduled_time, b.meeting_link,
               s.title    AS schedule_title,
               s.duration,
               u.timezone AS organizer_timezone,
               u.telegram_id AS organizer_telegram_id
        FROM bookings b
        JOIN schedules s ON b.schedule_id = s.id
        JOIN users u ON s.user_id = u.id
        WHERE b.status = 'confirmed'
          AND b.confirmation_asked = TRUE
          AND b.confirmation_asked_at IS NOT NULL
          AND b.confirmation_asked_at < NOW() - INTERVAL '1 hour'
          AND b.scheduled_time > NOW()
    """)
    return {"bookings": [dict(r) for r in rows]}


@router.patch("/api/bookings/{booking_id}/set-no-answer")
async def set_no_answer(
    booking_id: str,
    _auth=Depends(get_internal_caller),
    conn: asyncpg.Connection = Depends(db),
):
    """Transition booking to no_answer status."""
    try:
        bid = uuid.UUID(booking_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Неверный ID")
    row = await conn.fetchrow(
        """
        UPDATE bookings SET status = 'no_answer'
        WHERE id = $1
          AND status = 'confirmed'
          AND confirmation_asked = TRUE
          AND confirmation_asked_at IS NOT NULL
        RETURNING *
        """,
        bid,
    )
    if not row:
        return {"ok": False}

    # Notify organizer
    sched = await conn.fetchrow(
        "SELECT s.title, u.telegram_id, u.timezone FROM schedules s JOIN users u ON u.id = s.user_id WHERE s.id = $1",
        row["schedule_id"],
    )
    if sched and sched["telegram_id"]:
        asyncio.create_task(_notify_bot_status_change(
            booking_id=booking_id,
            new_status="no_answer",
            initiator_telegram_id=row.get("guest_telegram_id"),
            organizer_telegram_id=sched["telegram_id"],
            guest_telegram_id=row.get("guest_telegram_id"),
            guest_name=row["guest_name"],
            schedule_title=sched["title"],
            scheduled_time=str(row["scheduled_time"]),
            organizer_timezone=sched.get("timezone") or "UTC",
            guest_timezone=row.get("guest_timezone"),
        ))
    return {"ok": True}


@router.post("/api/sent-reminders")
async def record_sent_reminder(
    request: Request,
    _auth=Depends(get_internal_caller),
    conn: asyncpg.Connection = Depends(db),
):
    data = await request.json()
    try:
        bid = uuid.UUID(data["booking_id"])
    except (KeyError, ValueError):
        raise HTTPException(status_code=400, detail="Неверный booking_id")
    await conn.execute(
        """
        INSERT INTO sent_reminders (booking_id, reminder_type)
        VALUES ($1, $2)
        ON CONFLICT (booking_id, reminder_type) DO NOTHING
        """,
        bid, str(data.get("reminder_type", "")),
    )
    return {"ok": True}


@router.get("/api/bookings/morning-organizer-summary")
async def morning_organizer_summary(
    _auth=Depends(get_internal_caller),
    conn: asyncpg.Connection = Depends(db),
):
    """Organizers who have today's pending bookings and haven't received a morning summary yet."""
    rows = await conn.fetch("""
        SELECT
            u.telegram_id   AS organizer_telegram_id,
            u.timezone      AS organizer_timezone,
            b.id            AS booking_id,
            b.guest_name,
            b.scheduled_time,
            s.title         AS schedule_title,
            s.duration
        FROM bookings b
        JOIN schedules s ON b.schedule_id = s.id
        JOIN users u ON s.user_id = u.id
        WHERE b.status = 'pending'
          AND b.scheduled_time > NOW()
          AND DATE(b.scheduled_time AT TIME ZONE COALESCE(u.timezone, 'UTC'))
              = DATE(NOW() AT TIME ZONE COALESCE(u.timezone, 'UTC'))
          AND EXTRACT(HOUR FROM NOW() AT TIME ZONE COALESCE(u.timezone, 'UTC')) >= 9
          AND (
              u.morning_summary_sent_date IS NULL
              OR u.morning_summary_sent_date < DATE(NOW() AT TIME ZONE COALESCE(u.timezone, 'UTC'))
          )
        ORDER BY u.telegram_id, b.scheduled_time
    """)
    # Group bookings by organizer
    organizers: dict = {}
    for r in rows:
        tid = r["organizer_telegram_id"]
        if tid not in organizers:
            organizers[tid] = {
                "organizer_telegram_id": tid,
                "organizer_timezone": r["organizer_timezone"],
                "bookings": [],
            }
        organizers[tid]["bookings"].append({
            "id": str(r["booking_id"]),
            "guest_name": r["guest_name"],
            "scheduled_time": str(r["scheduled_time"]),
            "schedule_title": r["schedule_title"],
            "duration": r["duration"],
        })
    return {"organizers": list(organizers.values())}


@router.get("/api/bookings/morning-pending-guest-notice")
async def morning_pending_guest_notice(
    _auth=Depends(get_internal_caller),
    conn: asyncpg.Connection = Depends(db),
):
    """Pending-встречи на сегодня — уведомить гостя что организатор ещё не подтвердил.

    Использует тот же адаптивный floor 07:00, что и confirmation-requests.
    """
    rows = await conn.fetch("""
        WITH send_times AS (
            SELECT
                b.id AS booking_id,
                COALESCE(b.guest_timezone, u.timezone, 'UTC') AS rtz,
                (DATE_TRUNC('day', b.scheduled_time AT TIME ZONE COALESCE(b.guest_timezone, u.timezone, 'UTC'))
                    + INTERVAL '7 hours')
                  AT TIME ZONE COALESCE(b.guest_timezone, u.timezone, 'UTC') AS floor_utc,
                b.scheduled_time - INTERVAL '2 hours' AS target_2h,
                b.scheduled_time - INTERVAL '1 hour'  AS deadline
            FROM bookings b
            JOIN schedules s ON s.id = b.schedule_id
            JOIN users u ON u.id = s.user_id
            WHERE b.status = 'pending'
              AND b.guest_telegram_id IS NOT NULL
              AND b.confirmation_asked = FALSE
              AND b.scheduled_time > NOW()
        )
        SELECT b.id, b.guest_name, b.guest_telegram_id,
               b.scheduled_time, b.guest_timezone,
               s.title    AS schedule_title,
               s.duration,
               u.timezone AS organizer_timezone
        FROM send_times st
        JOIN bookings b ON b.id = st.booking_id
        JOIN schedules s ON s.id = b.schedule_id
        JOIN users u ON u.id = s.user_id
        WHERE GREATEST(st.floor_utc, st.target_2h) <= st.deadline
          AND NOW() >= GREATEST(st.floor_utc, st.target_2h)
          AND NOW() <= st.deadline + INTERVAL '6 minutes'
    """)
    return {"bookings": [dict(r) for r in rows]}


@router.post("/api/bookings/complete-past")
async def complete_past_bookings(
    _auth=Depends(get_internal_caller),
    conn: asyncpg.Connection = Depends(db),
):
    """Автопереходы прошедших встреч (вызывается ботом каждые 15 мин).

    confirmed + >30мин прошло → completed
    pending + >2ч прошло → expired (организатор забыл подтвердить)
    no_answer + прошло → expired (гость не ответил, встреча прошла)
    """
    r1 = await conn.execute("""
        UPDATE bookings SET status = 'completed'
        WHERE status = 'confirmed'
          AND scheduled_time < NOW() - INTERVAL '30 minutes'
    """)
    r2 = await conn.execute("""
        UPDATE bookings SET status = 'expired'
        WHERE status = 'pending'
          AND scheduled_time < NOW() - INTERVAL '2 hours'
    """)
    r3 = await conn.execute("""
        UPDATE bookings SET status = 'expired'
        WHERE status = 'no_answer'
          AND scheduled_time < NOW()
    """)
    completed = int(r1.split()[-1]) if r1 else 0
    expired_p = int(r2.split()[-1]) if r2 else 0
    expired_n = int(r3.split()[-1]) if r3 else 0
    if completed or expired_p or expired_n:
        log.info("stale_bookings_cleanup", completed=completed, expired_pending=expired_p, expired_noans=expired_n)
    return {"completed": completed, "expired": expired_p + expired_n}


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
    request: Request,
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
        UPDATE bookings
        SET status = 'confirmed',
            confirmation_asked = FALSE,
            confirmation_asked_at = NULL
        WHERE id = $1
          AND schedule_id IN (
              SELECT s.id FROM schedules s
              JOIN users u ON u.id = s.user_id
              WHERE u.telegram_id = $2
          )
          AND status IN ('pending', 'no_answer')
        RETURNING *
        """,
        bid, telegram_id
    )
    if not row:
        raise HTTPException(status_code=404, detail="Бронирование не найдено или уже обработано")
    await _track_event(conn, "booking_confirmed", telegram_id, {"booking_id": booking_id})

    if row.get("guest_telegram_id"):
        sched = await conn.fetchrow(
            "SELECT s.title, u.telegram_id, u.timezone FROM schedules s JOIN users u ON u.id = s.user_id WHERE s.id = $1",
            row["schedule_id"],
        )
        if sched:
            asyncio.create_task(_notify_bot_status_change(
                booking_id=booking_id,
                new_status="confirmed",
                initiator_telegram_id=telegram_id,
                organizer_telegram_id=sched["telegram_id"],
                guest_telegram_id=row["guest_telegram_id"],
                guest_name=row["guest_name"],
                schedule_title=sched["title"],
                scheduled_time=str(row["scheduled_time"]),
                organizer_timezone=sched.get("timezone") or "UTC",
                guest_timezone=row.get("guest_timezone"),
                meeting_link=row.get("meeting_link") or "",
            ))

    # Обновить заголовок события во внешних календарях (fire-and-forget)
    try:
        from calendars.sync import update_booking_in_calendars
        pool = request.app.state.sync_engine._pool
        asyncio.create_task(update_booking_in_calendars(pool, booking_id))
    except Exception as e:
        log.warning("calendar_confirm_update_error", error=str(e))

    return row_to_dict(row)


@router.patch("/api/bookings/{booking_id}/guest-confirm")
async def guest_confirm_booking(
    booking_id: str,
    auth_user: dict = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(db),
):
    """Guest confirms they're still coming (response to morning 'still coming?' message)."""
    telegram_id = auth_user["id"]
    try:
        bid = uuid.UUID(booking_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Неверный ID")

    row = await conn.fetchrow(
        """
        UPDATE bookings
        SET status = 'confirmed',
            confirmation_asked_at = NULL
        WHERE id = $1
          AND guest_telegram_id = $2
          AND status IN ('confirmed', 'no_answer')
        RETURNING *
        """,
        bid, telegram_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Бронирование не найдено или нельзя подтвердить")
    await _track_event(conn, "guest_confirmed", telegram_id, {"booking_id": booking_id})

    # Notify organizer that guest confirmed
    sched = await conn.fetchrow(
        "SELECT s.title, u.telegram_id, u.timezone FROM schedules s JOIN users u ON u.id = s.user_id WHERE s.id = $1",
        row["schedule_id"],
    )
    if sched and sched["telegram_id"]:
        asyncio.create_task(_notify_bot_status_change(
            booking_id=booking_id,
            new_status="guest_confirmed",
            initiator_telegram_id=telegram_id,
            organizer_telegram_id=sched["telegram_id"],
            guest_telegram_id=telegram_id,
            guest_name=row["guest_name"],
            schedule_title=sched["title"],
            scheduled_time=str(row["scheduled_time"]),
            organizer_timezone=sched.get("timezone") or "UTC",
            guest_timezone=row.get("guest_timezone"),
        ))

    return row_to_dict(row)


@router.patch("/api/bookings/{booking_id}/cancel")
async def cancel_booking(
    booking_id: str,
    request: Request,
    auth_user: dict = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(db),
):
    telegram_id = auth_user["id"]
    try:
        bid = uuid.UUID(booking_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Неверный ID")

    # Determine who is cancelling: organizer or guest
    organizer_check = await conn.fetchval(
        "SELECT u.telegram_id FROM schedules s JOIN users u ON u.id = s.user_id WHERE s.id = (SELECT schedule_id FROM bookings WHERE id = $1)",
        bid,
    )
    cancelled_by = "organizer" if organizer_check == telegram_id else "guest"

    row = await conn.fetchrow(
        """
        UPDATE bookings SET status = 'cancelled', cancelled_by = $3
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
        bid, telegram_id, cancelled_by
    )
    if not row:
        raise HTTPException(status_code=404, detail="Бронирование не найдено или нельзя отменить")
    await _track_event(conn, "booking_cancelled", telegram_id, {"booking_id": booking_id, "cancelled_by": cancelled_by})

    sched = await conn.fetchrow(
        "SELECT s.title, u.telegram_id, u.timezone FROM schedules s JOIN users u ON u.id = s.user_id WHERE s.id = $1",
        row["schedule_id"],
    )
    if sched and (row.get("guest_telegram_id") or sched["telegram_id"]):
        asyncio.create_task(_notify_bot_status_change(
            booking_id=booking_id,
            new_status="cancelled",
            initiator_telegram_id=telegram_id,
            organizer_telegram_id=sched["telegram_id"],
            guest_telegram_id=row.get("guest_telegram_id"),
            guest_name=row["guest_name"],
            schedule_title=sched["title"],
            scheduled_time=str(row["scheduled_time"]),
            organizer_timezone=sched.get("timezone") or "UTC",
            guest_timezone=row.get("guest_timezone"),
        ))

    # Удалить из внешних календарей (fire-and-forget)
    try:
        from calendars.sync import delete_booking_from_calendars
        pool = request.app.state.sync_engine._pool
        asyncio.create_task(delete_booking_from_calendars(pool, booking_id))
    except Exception as e:
        log.warning("calendar_delete_schedule_error", error=str(e))

    return row_to_dict(row)
