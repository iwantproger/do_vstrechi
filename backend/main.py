"""
До встречи — Backend API
FastAPI + asyncpg (PostgreSQL)
"""

import os
import uuid
import hmac
import hashlib
import json
import asyncio
import logging
from datetime import datetime, timedelta, date, time, timezone
from typing import Optional, List, Any
from contextlib import asynccontextmanager
from urllib.parse import parse_qs
from zoneinfo import ZoneInfo, available_timezones

import asyncpg
import httpx
from fastapi import FastAPI, HTTPException, Query, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DATABASE_URL = os.environ["DATABASE_URL"]
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
INTERNAL_API_KEY = os.environ.get("INTERNAL_API_KEY", "")
BOT_INTERNAL_URL = os.environ.get("BOT_INTERNAL_URL", "http://bot:8080")

# ─────────────────────────────────────────────────────────
# Telegram initData validation (HMAC-SHA256)
# ─────────────────────────────────────────────────────────

def validate_init_data(init_data: str, bot_token: str, max_age_seconds: int = 86400) -> dict | None:
    """Validate Telegram WebApp initData per https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app"""
    try:
        parsed = dict(parse_qs(init_data, keep_blank_values=True))
        parsed = {k: v[0] for k, v in parsed.items()}
        check_hash = parsed.pop("hash", "")
        if not check_hash:
            return None
        data_check_string = "\n".join(
            f"{k}={parsed[k]}" for k in sorted(parsed.keys())
        )
        secret_key = hmac.new(
            b"WebAppData", bot_token.encode(), hashlib.sha256
        ).digest()
        computed_hash = hmac.new(
            secret_key, data_check_string.encode(), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(computed_hash, check_hash):
            return None
        # Reject expired initData
        auth_date_str = parsed.get("auth_date")
        if auth_date_str:
            now_ts = datetime.now(timezone.utc).timestamp()
            if now_ts - int(auth_date_str) > max_age_seconds:
                return None
        user_json = parsed.get("user")
        if not user_json:
            return None
        return json.loads(user_json)
    except Exception:
        return None


async def get_current_user(request: Request) -> dict:
    """FastAPI dependency: extract authenticated user from Telegram initData or internal key."""
    # Internal API key for bot-to-backend calls
    internal_key = request.headers.get("X-Internal-Key")
    if internal_key and INTERNAL_API_KEY and hmac.compare_digest(internal_key, INTERNAL_API_KEY):
        tid = request.query_params.get("telegram_id")
        if tid:
            return {"id": int(tid)}
        raise HTTPException(status_code=401, detail="Missing telegram_id for internal call")

    # Telegram initData validation
    init_data = request.headers.get("X-Init-Data")
    if not init_data:
        raise HTTPException(status_code=401, detail="Требуется авторизация через Telegram")

    user = validate_init_data(init_data, BOT_TOKEN)
    if not user:
        raise HTTPException(status_code=401, detail="Невалидная подпись Telegram")

    return user


async def get_optional_user(request: Request) -> dict | None:
    """Same as get_current_user but returns None instead of 401 (for public endpoints)."""
    init_data = request.headers.get("X-Init-Data")
    if not init_data:
        return None
    return validate_init_data(init_data, BOT_TOKEN)


# ─────────────────────────────────────────────────────────
# Database pool
# ─────────────────────────────────────────────────────────

_pool: asyncpg.Pool | None = None

async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        raise RuntimeError("DB pool not initialized")
    return _pool

async def db() -> asyncpg.Connection:
    pool = await get_pool()
    async with pool.acquire() as conn:
        yield conn

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pool
    log.info("Connecting to PostgreSQL…")
    _pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
    log.info("PostgreSQL pool ready")
    yield
    await _pool.close()
    log.info("PostgreSQL pool closed")

# ─────────────────────────────────────────────────────────
# App
# ─────────────────────────────────────────────────────────

app = FastAPI(title="До встречи API", version="2.0.0", lifespan=lifespan)

MINI_APP_URL = os.environ.get("MINI_APP_URL", "")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://dovstrechiapp.ru",
        "https://www.dovstrechiapp.ru",
        *([] if not MINI_APP_URL else [MINI_APP_URL]),
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "X-Init-Data"],
)

# ─────────────────────────────────────────────────────────
# Pydantic models
# ─────────────────────────────────────────────────────────

class UserAuth(BaseModel):
    username: Optional[str] = Field(None, max_length=100)
    first_name: Optional[str] = Field(None, max_length=200)
    last_name: Optional[str] = Field(None, max_length=200)
    timezone: Optional[str] = "UTC"

class ScheduleCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    duration: int = Field(60, ge=5, le=480)
    buffer_time: int = Field(0, ge=0, le=120)
    work_days: List[int] = [0, 1, 2, 3, 4]
    start_time: str = Field("09:00", pattern=r"^\d{2}:\d{2}$")
    end_time: str = Field("18:00", pattern=r"^\d{2}:\d{2}$")
    location_mode: str = Field("fixed", max_length=50)
    platform: str = Field("jitsi", max_length=50)

class BookingCreate(BaseModel):
    schedule_id: str = Field(..., max_length=50)
    guest_name: str = Field(..., min_length=1, max_length=200)
    guest_contact: str = Field(..., min_length=1, max_length=200)
    guest_telegram_id: Optional[int] = None
    scheduled_time: str = Field(..., max_length=50)
    notes: Optional[str] = Field(None, max_length=2000)

def row_to_dict(row) -> dict:
    """asyncpg Record → plain dict"""
    if row is None:
        return None
    return dict(row)

def rows_to_list(rows) -> list:
    return [dict(r) for r in rows]

# ─────────────────────────────────────────────────────────
# Генерация Jitsi-ссылки
# ─────────────────────────────────────────────────────────

def generate_meeting_link(platform: str) -> str:
    room = str(uuid.uuid4()).replace("-", "")[:12]
    if platform == "jitsi":
        return f"https://meet.jit.si/dovstrechi-{room}"
    return f"https://meet.jit.si/dovstrechi-{room}"


async def _notify_bot_new_booking(**kwargs: Any) -> None:
    """Fire-and-forget: tell bot to message the organizer about a new booking."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.post(
                f"{BOT_INTERNAL_URL}/internal/notify",
                json=kwargs,
                headers={"X-Internal-Key": INTERNAL_API_KEY},
            )
            result = resp.json()
            if result.get("ok"):
                log.info(f"Bot notified about booking {kwargs.get('booking_id')}")
            else:
                log.warning(f"Bot notification failed: {result}")
    except Exception as e:
        log.warning(f"Failed to notify bot about new booking: {e}")

# ─────────────────────────────────────────────────────────
# Health
# ─────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {"message": "До встречи API", "version": "2.0.0", "status": "running"}

@app.get("/health")
async def health(conn: asyncpg.Connection = Depends(db)):
    try:
        await conn.fetchval("SELECT 1")
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        log.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Database unavailable")

# ─────────────────────────────────────────────────────────
# Users
# ─────────────────────────────────────────────────────────

@app.post("/api/users/auth")
async def auth_user(
    data: UserAuth,
    user: dict = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(db)
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
    return row_to_dict(row)

@app.get("/api/users/{telegram_id}")
async def get_user(telegram_id: int, conn: asyncpg.Connection = Depends(db)):
    row = await conn.fetchrow("SELECT * FROM users WHERE telegram_id = $1", telegram_id)
    if not row:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return row_to_dict(row)

# ─────────────────────────────────────────────────────────
# Schedules
# ─────────────────────────────────────────────────────────

@app.post("/api/schedules")
async def create_schedule(
    data: ScheduleCreate,
    auth_user: dict = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(db)
):
    telegram_id = auth_user["id"]
    # Находим пользователя
    user = await conn.fetchrow("SELECT id FROM users WHERE telegram_id = $1", telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден. Сначала /start")

    row = await conn.fetchrow(
        """
        INSERT INTO schedules
            (user_id, title, description, duration, buffer_time,
             work_days, start_time, end_time, location_mode, platform)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
        RETURNING *
        """,
        user["id"], data.title, data.description, data.duration, data.buffer_time,
        data.work_days,
        datetime.strptime(data.start_time, "%H:%M").time(),
        datetime.strptime(data.end_time, "%H:%M").time(),
        data.location_mode, data.platform
    )
    return row_to_dict(row)

@app.get("/api/schedules")
async def list_schedules(
    auth_user: dict = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(db)
):
    telegram_id = auth_user["id"]

    rows = await conn.fetch(
        """
        SELECT s.* FROM schedules s
        JOIN users u ON u.id = s.user_id
        WHERE u.telegram_id = $1 AND s.is_active = TRUE
        ORDER BY s.created_at DESC
        """,
        telegram_id
    )
    return rows_to_list(rows)

@app.get("/api/schedules/{schedule_id}")
async def get_schedule(schedule_id: str, conn: asyncpg.Connection = Depends(db)):
    try:
        sid = uuid.UUID(schedule_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Неверный формат ID")

    row = await conn.fetchrow("SELECT * FROM schedules WHERE id = $1 AND is_active = TRUE", sid)
    if not row:
        raise HTTPException(status_code=404, detail="Расписание не найдено")
    return row_to_dict(row)

@app.delete("/api/schedules/{schedule_id}")
async def delete_schedule(
    schedule_id: str,
    auth_user: dict = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(db)
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
    return {"success": True}

# ─────────────────────────────────────────────────────────
# Available slots
# ─────────────────────────────────────────────────────────

@app.get("/api/available-slots/{schedule_id}")
async def available_slots(
    schedule_id: str,
    date: str = Query(..., description="YYYY-MM-DD"),
    viewer_tz: str = Query("UTC", description="Viewer IANA timezone"),
    conn: asyncpg.Connection = Depends(db)
):
    try:
        sid = uuid.UUID(schedule_id)
        target_date = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Неверный формат параметров")

    # Schedule + organizer timezone
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

    # Проверка рабочего дня (0=Пн)
    day_of_week = target_date.weekday()
    if day_of_week not in schedule["work_days"]:
        return {"available_slots": [], "date": date}

    # Генерация слотов в зоне организатора
    start_h, start_m = map(int, schedule["start_time"].strftime("%H:%M").split(":"))
    end_h, end_m = map(int, schedule["end_time"].strftime("%H:%M").split(":"))

    slot_start = datetime(target_date.year, target_date.month, target_date.day,
                          start_h, start_m, tzinfo=org_tz)
    slot_end = datetime(target_date.year, target_date.month, target_date.day,
                        end_h, end_m, tzinfo=org_tz)

    # Бронирования в UTC-диапазоне рабочего дня
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

    step = timedelta(minutes=schedule["duration"] + schedule["buffer_time"])
    slot_duration = timedelta(minutes=schedule["duration"])
    now_utc = datetime.now(ZoneInfo("UTC"))

    slots = []
    current = slot_start
    while current + slot_duration <= slot_end:
        current_utc = current.astimezone(ZoneInfo("UTC")).replace(second=0, microsecond=0)
        if current_utc > now_utc and current_utc not in booked_utc:
            viewer_dt = current.astimezone(vtz)
            slots.append({
                "time": current.strftime("%H:%M"),
                "datetime": current_utc.isoformat(),
                "datetime_utc": current_utc.isoformat(),
                "datetime_local": viewer_dt.strftime("%H:%M"),
            })
        current += step

    return {"available_slots": slots, "date": date}

# ─────────────────────────────────────────────────────────
# Bookings
# ─────────────────────────────────────────────────────────

@app.post("/api/bookings")
async def create_booking(
    data: BookingCreate,
    conn: asyncpg.Connection = Depends(db),
    auth_user: dict | None = Depends(get_optional_user),
):
    try:
        sid = uuid.UUID(data.schedule_id)
        scheduled_time = datetime.fromisoformat(data.scheduled_time.replace("Z", "+00:00"))
    except ValueError as e:
        log.warning(f"Invalid booking data: {e}")
        raise HTTPException(status_code=400, detail="Неверный формат данных")

    schedule = await conn.fetchrow("SELECT * FROM schedules WHERE id = $1 AND is_active = TRUE", sid)
    if not schedule:
        raise HTTPException(status_code=404, detail="Расписание не найдено")

    # Проверка дублирования
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

    # Prefer guest_telegram_id from validated initData over body field
    guest_telegram_id = auth_user["id"] if auth_user else data.guest_telegram_id

    row = await conn.fetchrow(
        """
        INSERT INTO bookings
            (schedule_id, guest_name, guest_contact, guest_telegram_id,
             scheduled_time, status, meeting_link, notes)
        VALUES ($1,$2,$3,$4,$5,'pending',$6,$7)
        RETURNING *
        """,
        sid, data.guest_name, data.guest_contact, guest_telegram_id,
        scheduled_time, meeting_link, data.notes
    )

    result = row_to_dict(row)

    # Notify organizer via bot
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

    log.info(f"New booking created: {result['id']} for schedule {sid}")
    return result


@app.get("/api/bookings")
async def list_bookings(
    auth_user: dict = Depends(get_current_user),
    role: Optional[str] = Query(None, description="organizer | guest | all"),
    conn: asyncpg.Connection = Depends(db)
):
    """
    Возвращает встречи для текущего пользователя:
    - role=organizer → встречи, где пользователь организатор
    - role=guest     → встречи, где пользователь гость
    - role=all (по умолчанию) → и те и другие
    """
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
            u.telegram_id  AS organizer_telegram_id,
            u.first_name   AS organizer_first_name,
            u.username     AS organizer_username,
            u.timezone     AS organizer_timezone,
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


@app.patch("/api/bookings/{booking_id}/confirm")
async def confirm_booking(
    booking_id: str,
    auth_user: dict = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(db)
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
    return row_to_dict(row)


@app.patch("/api/bookings/{booking_id}/cancel")
async def cancel_booking(
    booking_id: str,
    auth_user: dict = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(db)
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
            -- Организатор может отменять любые
            schedule_id IN (
                SELECT s.id FROM schedules s
                JOIN users u ON u.id = s.user_id
                WHERE u.telegram_id = $2
            )
            OR
            -- Гость может отменять свои
            guest_telegram_id = $2
          )
          AND status NOT IN ('cancelled', 'completed')
        RETURNING *
        """,
        bid, telegram_id
    )
    if not row:
        raise HTTPException(status_code=404, detail="Бронирование не найдено или нельзя отменить")
    return row_to_dict(row)


# ─────────────────────────────────────────────────────────
# Reminders
# ─────────────────────────────────────────────────────────

@app.get("/api/bookings/pending-reminders")
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


@app.patch("/api/bookings/{booking_id}/reminder-sent")
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


# ─────────────────────────────────────────────────────────
# Stats
# ─────────────────────────────────────────────────────────

@app.get("/api/stats")
async def get_stats(
    auth_user: dict = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(db)
):
    telegram_id = auth_user["id"]
    stats = await conn.fetchrow(
        """
        SELECT
            COUNT(DISTINCT s.id) FILTER (WHERE s.is_active)             AS active_schedules,
            COUNT(b.id)                                                  AS total_bookings,
            COUNT(b.id) FILTER (WHERE b.status = 'pending')             AS pending_bookings,
            COUNT(b.id) FILTER (WHERE b.status = 'confirmed')           AS confirmed_bookings,
            COUNT(b.id) FILTER (WHERE b.scheduled_time > NOW())         AS upcoming_bookings
        FROM schedules s
        LEFT JOIN bookings b ON b.schedule_id = s.id
        JOIN users u ON u.id = s.user_id
        WHERE u.telegram_id = $1
        """,
        telegram_id
    )
    return row_to_dict(stats)
