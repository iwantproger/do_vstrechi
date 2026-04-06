"""
До встречи — Backend API
FastAPI + asyncpg (PostgreSQL)
"""

import os
import sys
import uuid
import hmac
import hashlib
import json
import asyncio
import logging
import secrets
import time as _time
from datetime import datetime, timedelta, date, time, timezone
from typing import Optional, List, Any
from contextlib import asynccontextmanager
from urllib.parse import parse_qs
from zoneinfo import ZoneInfo, available_timezones

import asyncpg
import httpx
import structlog
from fastapi import FastAPI, HTTPException, Query, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)
log = structlog.get_logger()

DATABASE_URL = os.environ["DATABASE_URL"]
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
INTERNAL_API_KEY = os.environ.get("INTERNAL_API_KEY", "")
BOT_INTERNAL_URL = os.environ.get("BOT_INTERNAL_URL", "http://bot:8080")

ADMIN_TELEGRAM_ID = int(os.environ.get("ADMIN_TELEGRAM_ID", "0"))
ADMIN_SESSION_TTL_HOURS = int(os.environ.get("ADMIN_SESSION_TTL_HOURS", "2"))
ADMIN_IP_ALLOWLIST = os.environ.get("ADMIN_IP_ALLOWLIST", "").strip()
ANONYMIZE_SALT = os.environ.get("ANONYMIZE_SALT", "do-vstrechi-2026")

_start_time = _time.time()

# ─────────────────────────────���───────────────────────────
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
# Admin authentication (Telegram Login Widget)
# ─────────────────────────────────────────────────────────

_login_attempts: dict[str, list[float]] = {}


def _check_login_rate_limit(ip: str) -> bool:
    """Returns True if IP is rate-limited (>3 attempts in 5 min)."""
    now = datetime.now(timezone.utc).timestamp()
    attempts = _login_attempts.get(ip, [])
    attempts = [t for t in attempts if now - t < 300]
    _login_attempts[ip] = attempts
    return len(attempts) >= 3


def _record_login_attempt(ip: str):
    now = datetime.now(timezone.utc).timestamp()
    _login_attempts.setdefault(ip, []).append(now)


def verify_telegram_login(auth_data: dict) -> bool:
    """Verify Telegram Login Widget data (HMAC-SHA256 with SHA256(BOT_TOKEN))."""
    try:
        check_hash = auth_data.get("hash", "")
        if not check_hash:
            return False
        data_check_string = "\n".join(
            f"{k}={auth_data[k]}"
            for k in sorted(auth_data.keys())
            if k != "hash"
        )
        secret_key = hashlib.sha256(BOT_TOKEN.encode()).digest()
        computed_hash = hmac.new(
            secret_key, data_check_string.encode(), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(computed_hash, check_hash):
            return False
        auth_date = int(auth_data.get("auth_date", 0))
        now_ts = datetime.now(timezone.utc).timestamp()
        if now_ts - auth_date > 300:
            return False
        return True
    except Exception:
        return False


async def create_admin_session(telegram_id: int, ip: str, user_agent: str, conn) -> str:
    """Deactivate existing sessions, create new one, log to audit."""
    await conn.execute(
        "UPDATE admin_sessions SET is_active = FALSE WHERE telegram_id = $1",
        telegram_id,
    )
    session_token = secrets.token_urlsafe(64)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=ADMIN_SESSION_TTL_HOURS)
    await conn.execute(
        """
        INSERT INTO admin_sessions (telegram_id, session_token, ip_address, user_agent, expires_at)
        VALUES ($1, $2, $3::inet, $4, $5)
        """,
        telegram_id, session_token, ip, user_agent, expires_at,
    )
    await log_admin_action("login", ip, {"user_agent": user_agent}, conn)
    return session_token


async def validate_admin_session(session_token: str, conn) -> dict | None:
    """Check session is active, not expired, and belongs to the admin."""
    row = await conn.fetchrow(
        """
        SELECT * FROM admin_sessions
        WHERE session_token = $1 AND is_active = TRUE AND expires_at > NOW()
        """,
        session_token,
    )
    if not row:
        return None
    if row["telegram_id"] != ADMIN_TELEGRAM_ID:
        return None
    return dict(row)


def anonymize_id(telegram_id: int) -> str:
    """SHA256(telegram_id:salt), first 12 chars."""
    return hashlib.sha256(f"{telegram_id}:{ANONYMIZE_SALT}".encode()).hexdigest()[:12]


async def log_admin_action(action: str, ip: str, details: dict | None, conn):
    """Insert into admin_audit_log."""
    await conn.execute(
        """
        INSERT INTO admin_audit_log (action, details, ip_address)
        VALUES ($1, $2::jsonb, $3::inet)
        """,
        action, json.dumps(details) if details else None, ip,
    )


_session_checked: set[str] = set()


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


async def get_admin_user(request: Request, conn=Depends(db)):
    """FastAPI dependency: validate admin session from cookie."""
    session_token = request.cookies.get("admin_session")
    if not session_token:
        raise HTTPException(status_code=401, detail="Authentication failed")

    session = await validate_admin_session(session_token, conn)
    if not session:
        raise HTTPException(status_code=401, detail="Authentication failed")

    if ADMIN_IP_ALLOWLIST:
        allowed_ips = [ip.strip() for ip in ADMIN_IP_ALLOWLIST.split(",")]
        client_ip = request.headers.get("X-Real-IP", request.client.host)
        if client_ip not in allowed_ips:
            raise HTTPException(status_code=403, detail="Access denied")

    return session


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pool
    log.info("Connecting to PostgreSQL…")
    _pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
    log.info("PostgreSQL pool ready")

    # Idempotent migrations — safe to run on every startup
    async with _pool.acquire() as conn:
        await conn.execute("""
            ALTER TABLE users
                ADD COLUMN IF NOT EXISTS timezone TEXT NOT NULL DEFAULT 'UTC';
        """)
        await conn.execute("""
            ALTER TABLE bookings
                ADD COLUMN IF NOT EXISTS reminder_24h_sent BOOLEAN NOT NULL DEFAULT FALSE;
        """)
        await conn.execute("""
            ALTER TABLE bookings
                ADD COLUMN IF NOT EXISTS reminder_1h_sent BOOLEAN NOT NULL DEFAULT FALSE;
        """)
        await conn.execute("""
            ALTER TABLE schedules
                ADD COLUMN IF NOT EXISTS is_default BOOLEAN NOT NULL DEFAULT FALSE;
        """)
        await conn.execute("""
            ALTER TABLE bookings ADD COLUMN IF NOT EXISTS title TEXT;
        """)
        await conn.execute("""
            ALTER TABLE bookings ADD COLUMN IF NOT EXISTS end_time TIMESTAMPTZ;
        """)
        await conn.execute("""
            ALTER TABLE bookings
                ADD COLUMN IF NOT EXISTS is_manual BOOLEAN NOT NULL DEFAULT FALSE;
        """)
        await conn.execute("""
            ALTER TABLE bookings ADD COLUMN IF NOT EXISTS created_by BIGINT;
        """)
    log.info("Migrations applied")

    yield
    await _pool.close()
    log.info("PostgreSQL pool closed")

# ─────────────────────────────────────────────────────────
# App
# ─────────────────────────────────────────────────────────

app = FastAPI(title="До встречи API", version="2.0.0", lifespan=lifespan)

MINI_APP_URL = os.environ.get("MINI_APP_URL", "")
_cors_origins = [
    "https://dovstrechiapp.ru",
    "https://www.dovstrechiapp.ru",
    *([] if not MINI_APP_URL else [MINI_APP_URL]),
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "X-Init-Data"],
)


# ─────────────────────────────────────────────────────────
# Structlog request context middleware
# ─────────────────────────────────────────────────────────

class StructlogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = uuid.uuid4().hex[:8]
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )
        start = _time.monotonic()
        response = await call_next(request)
        duration_ms = round((_time.monotonic() - start) * 1000, 1)
        if request.url.path not in ("/", "/health"):
            log.info(
                "request_handled",
                status_code=response.status_code,
                duration_ms=duration_ms,
            )
        response.headers["X-Request-ID"] = request_id
        return response

app.add_middleware(StructlogMiddleware)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    log.error("unhandled_exception", exc_type=type(exc).__name__, detail=str(exc)[:500])
    try:
        async with _pool.acquire() as conn:
            await _track_event(conn, "error", 0, {
                "exc_type": type(exc).__name__,
                "detail": str(exc)[:500],
                "path": request.url.path,
                "method": request.method,
            }, severity="error")
    except Exception:
        pass
    if isinstance(exc, HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


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
    min_booking_advance: Optional[int] = Field(0, ge=0, le=10080)

class ScheduleUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    duration: Optional[int] = Field(None, ge=5, le=480)
    buffer_time: Optional[int] = Field(None, ge=0, le=120)
    work_days: Optional[List[int]] = None
    start_time: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    end_time: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    location_mode: Optional[str] = Field(None, max_length=50)
    platform: Optional[str] = Field(None, max_length=50)
    is_active: Optional[bool] = None
    min_booking_advance: Optional[int] = Field(None, ge=0, le=10080)

class QuickMeetingCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    start_time: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    end_time: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    schedule_id: Optional[str] = Field(None, max_length=50)
    guest_name: Optional[str] = Field(None, max_length=200)
    guest_contact: Optional[str] = Field(None, max_length=200)
    notes: Optional[str] = Field(None, max_length=2000)

class BookingCreate(BaseModel):
    schedule_id: str = Field(..., max_length=50)
    guest_name: str = Field(..., min_length=1, max_length=200)
    guest_contact: str = Field(..., min_length=1, max_length=200)
    guest_telegram_id: Optional[int] = None
    scheduled_time: str = Field(..., max_length=50)
    notes: Optional[str] = Field(None, max_length=2000)

class TelegramLoginData(BaseModel):
    id: int = Field(..., ge=1)
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)
    username: Optional[str] = Field(None, max_length=100)
    photo_url: Optional[str] = Field(None, max_length=500)
    auth_date: int = Field(..., ge=0)
    hash: str = Field(..., min_length=64, max_length=64)

class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=5000)
    description_plain: Optional[str] = Field(None, max_length=2000)
    status: str = Field("backlog", pattern=r"^(backlog|in_progress|done)$")
    source: str = Field("manual", pattern=r"^(manual|git_commit|ai_generated|github_issue)$")
    source_ref: Optional[str] = Field(None, max_length=500)
    tags: List[str] = []

class TaskUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=5000)
    description_plain: Optional[str] = Field(None, max_length=2000)
    status: Optional[str] = Field(None, pattern=r"^(backlog|in_progress|done)$")
    tags: Optional[List[str]] = None

class TaskReorder(BaseModel):
    status: str = Field(..., pattern=r"^(backlog|in_progress|done)$")
    task_ids: List[str]

class AppEvent(BaseModel):
    event_type: str = Field(..., min_length=1, max_length=50)
    session_id: Optional[str] = Field(None, max_length=100)
    metadata: Optional[dict] = None
    severity: str = Field("info", pattern=r"^(info|warn|error|critical)$")

class CleanupRequest(BaseModel):
    older_than_days: int = Field(default=30, ge=7, le=365)
    severity: str = Field(default="info", pattern=r"^(info|warn)$")

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


async def _track_event(
    conn: asyncpg.Connection,
    event_type: str,
    telegram_id: int = 0,
    metadata: dict | None = None,
    severity: str = "info",
    session_id: str | None = None,
) -> None:
    """Write an event to app_events (fire-and-forget safe)."""
    try:
        anon_id = anonymize_id(telegram_id)
        await conn.execute(
            """
            INSERT INTO app_events (event_type, anonymous_id, session_id, metadata, severity)
            VALUES ($1, $2, $3, $4::jsonb, $5)
            """,
            event_type, anon_id, session_id,
            json.dumps(metadata) if metadata else None,
            severity,
        )
    except Exception:
        log.warning("track_event_failed", event_type=event_type)


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
                log.info("bot_notified", booking_id=kwargs.get("booking_id"))
            else:
                log.warning("bot_notification_failed", response=result)
    except Exception as e:
        log.warning("bot_notification_error", error=str(e))

# ─────────────────────────────────────────────────────────
# Quick meeting helper
# ─────────────────────────────────────────────────────────

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
        log.error("health_check_failed", error=str(e))
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
    is_new = row["created_at"] == row["updated_at"] if row else False
    await _track_event(conn, "user_auth", telegram_id, {"timezone": tz, "is_new": is_new})
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
        WHERE u.telegram_id = $1 AND s.is_default = FALSE
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

    row = await conn.fetchrow("SELECT * FROM schedules WHERE id = $1", sid)
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
    await _track_event(conn, "schedule_deleted", telegram_id, {"schedule_id": schedule_id})
    return {"success": True}

@app.patch("/api/schedules/{schedule_id}")
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

    # Конвертировать time-строки в объекты time
    for tf in ("start_time", "end_time"):
        if tf in updates:
            updates[tf] = datetime.strptime(updates[tf], "%H:%M").time()

    # Динамически строить SET clause
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

# ─────────────────────────────────────────────────────────
# Quick meeting
# ─────────────────────────────────────────────────────────

@app.post("/api/meetings/quick", status_code=201)
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
        start_time_obj = time(start_h, start_m)
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
            end_dt = datetime(
                meeting_date.year, meeting_date.month, meeting_date.day,
                end_h, end_m, tzinfo=timezone.utc,
            )
        except (ValueError, IndexError):
            raise HTTPException(400, "Неверный формат end_time")
        if end_dt <= scheduled_dt:
            raise HTTPException(400, "end_time должен быть позже start_time")

    if data.schedule_id:
        # Mode B: конкретное расписание организатора
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
        end_dt = None  # для Mode B end_time вычисляется из duration
    else:
        # Mode A: дефолтное (личное) расписание
        default_schedule = await get_or_create_default_schedule(conn, telegram_id)
        schedule_uuid = default_schedule["id"]
        platform = default_schedule["platform"]

    meeting_link = generate_meeting_link(platform)
    guest_name = data.guest_name or data.title
    guest_contact = data.guest_contact or ""

    booking = await conn.fetchrow(
        """
        INSERT INTO bookings
            (schedule_id, guest_name, guest_contact, scheduled_time,
             status, meeting_link, notes, title, end_time, is_manual, created_by)
        VALUES ($1, $2, $3, $4, 'confirmed', $5, $6, $7, $8, TRUE, $9)
        RETURNING *
        """,
        schedule_uuid, guest_name, guest_contact, scheduled_dt,
        meeting_link, data.notes, data.title, end_dt, telegram_id,
    )

    log.info("quick_meeting_created", booking_id=str(booking["id"]), telegram_id=telegram_id)
    return row_to_dict(booking)


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

    # Также блокируем ручные встречи из дефолтного расписания того же организатора
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
        log.warning("invalid_booking_data", error=str(e))
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

    await _track_event(conn, "booking_created", guest_telegram_id or 0, {
        "booking_id": str(result["id"]), "schedule_id": str(sid),
    })
    log.info("booking_created", booking_id=str(result["id"]), schedule_id=str(sid))
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
    await _track_event(conn, "booking_confirmed", telegram_id, {"booking_id": booking_id})
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
    await _track_event(conn, "booking_cancelled", telegram_id, {"booking_id": booking_id})
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


# ─────────────────────────────────────────────────────────
# Admin auth
# ─────────────────────────────────────────────────────────

@app.post("/api/admin/auth/login")
async def admin_login(
    data: TelegramLoginData,
    request: Request,
    conn: asyncpg.Connection = Depends(db),
):
    client_ip = request.headers.get("X-Real-IP", request.client.host)

    if _check_login_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="Too many attempts")

    _record_login_attempt(client_ip)

    auth_dict = data.model_dump(exclude_none=True)
    log.info("admin_login_attempt", telegram_id=data.id, username=data.username)
    if not verify_telegram_login(auth_dict):
        raise HTTPException(status_code=401, detail="Authentication failed")

    if data.id != ADMIN_TELEGRAM_ID:
        raise HTTPException(status_code=401, detail="Authentication failed")

    if ADMIN_IP_ALLOWLIST:
        allowed_ips = [ip.strip() for ip in ADMIN_IP_ALLOWLIST.split(",")]
        if client_ip not in allowed_ips:
            raise HTTPException(status_code=401, detail="Authentication failed")

    user_agent = request.headers.get("User-Agent", "")
    session_token = await create_admin_session(data.id, client_ip, user_agent, conn)

    ttl_seconds = ADMIN_SESSION_TTL_HOURS * 3600
    response = JSONResponse(content={"status": "ok", "expires_in": ttl_seconds})
    response.set_cookie(
        key="admin_session",
        value=session_token,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=ttl_seconds,
        path="/api/admin",
    )
    log.info("admin_login", client_ip=client_ip, session_prefix=session_token[:8])
    return response


@app.post("/api/admin/auth/logout")
async def admin_logout(
    request: Request,
    session: dict = Depends(get_admin_user),
    conn: asyncpg.Connection = Depends(db),
):
    await conn.execute(
        "UPDATE admin_sessions SET is_active = FALSE WHERE id = $1",
        session["id"],
    )
    client_ip = request.headers.get("X-Real-IP", request.client.host)
    await log_admin_action("logout", client_ip, None, conn)

    # Remove from session_checked cache
    token_prefix = session["session_token"][:8]
    _session_checked.discard(token_prefix)

    response = JSONResponse(content={"status": "ok"})
    response.delete_cookie(key="admin_session", path="/api/admin")
    return response


@app.get("/api/admin/auth/me")
async def admin_me(
    request: Request,
    session: dict = Depends(get_admin_user),
    conn: asyncpg.Connection = Depends(db),
):
    # Log session_check only once per session
    token_prefix = session["session_token"][:8]
    if token_prefix not in _session_checked:
        client_ip = request.headers.get("X-Real-IP", request.client.host)
        await log_admin_action("session_check", client_ip, {"session": token_prefix}, conn)
        _session_checked.add(token_prefix)

    return {
        "telegram_id": session["telegram_id"],
        "expires_at": session["expires_at"].isoformat(),
        "ip": str(session["ip_address"]),
    }


# ─────────────────────────────────────────────────────────
# Admin dashboard
# ─────────────────────────────────────────────────────────

@app.get("/api/admin/dashboard/summary")
async def admin_dashboard_summary(
    request: Request,
    session: dict = Depends(get_admin_user),
    conn: asyncpg.Connection = Depends(db),
):
    client_ip = request.headers.get("X-Real-IP", request.client.host)
    await log_admin_action("view_dashboard", client_ip, {"path": "/api/admin/dashboard/summary"}, conn)

    row = await conn.fetchrow("""
        SELECT
            (SELECT COUNT(*) FROM users) AS total_users,
            (SELECT COUNT(DISTINCT s.user_id) FROM schedules s
             JOIN bookings b ON b.schedule_id = s.id
             WHERE b.created_at > NOW() - INTERVAL '7 days') AS active_users_7d,
            (SELECT COUNT(*) FROM bookings) AS total_bookings,
            (SELECT COUNT(*) FROM bookings WHERE DATE(scheduled_time) = CURRENT_DATE) AS bookings_today,
            (SELECT COUNT(*) FROM app_events
             WHERE severity IN ('error', 'critical')
             AND created_at > NOW() - INTERVAL '24 hours') AS errors_24h,
            (SELECT COUNT(*) FROM bookings WHERE status = 'pending') AS pending_bookings
    """)
    return row_to_dict(row)


@app.get("/api/admin/dashboard/bookings-trend")
async def admin_bookings_trend(
    request: Request,
    days: int = Query(30, ge=1, le=90),
    session: dict = Depends(get_admin_user),
    conn: asyncpg.Connection = Depends(db),
):
    rows = await conn.fetch(
        """
        SELECT DATE(scheduled_time) AS date, COUNT(*) AS count
        FROM bookings
        WHERE scheduled_time >= NOW() - ($1 || ' days')::interval
        GROUP BY DATE(scheduled_time)
        ORDER BY date
        """,
        str(days),
    )
    return [{"date": str(r["date"]), "count": r["count"]} for r in rows]


@app.get("/api/admin/dashboard/platforms")
async def admin_platforms(
    session: dict = Depends(get_admin_user),
    conn: asyncpg.Connection = Depends(db),
):
    rows = await conn.fetch(
        "SELECT platform, COUNT(*) AS count FROM schedules WHERE is_active = TRUE GROUP BY platform"
    )
    return rows_to_list(rows)


# ─────────────────────────────────────────────────────────
# Admin logs (app_events)
# ─────────────────────────────────────────────────────────

@app.get("/api/admin/logs")
async def admin_logs(
    request: Request,
    event_type: Optional[str] = None,
    severity: Optional[str] = None,
    anonymous_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    session: dict = Depends(get_admin_user),
    conn: asyncpg.Connection = Depends(db),
):
    client_ip = request.headers.get("X-Real-IP", request.client.host)
    await log_admin_action("view_logs", client_ip, {"path": "/api/admin/logs"}, conn)

    conditions = []
    params: list[Any] = []
    idx = 1

    if event_type:
        conditions.append(f"event_type = ${idx}")
        params.append(event_type)
        idx += 1
    if severity:
        conditions.append(f"severity = ${idx}")
        params.append(severity)
        idx += 1
    if anonymous_id:
        conditions.append(f"anonymous_id = ${idx}")
        params.append(anonymous_id)
        idx += 1
    if date_from:
        conditions.append(f"created_at >= ${idx}::timestamptz")
        params.append(date_from)
        idx += 1
    if date_to:
        conditions.append(f"created_at <= ${idx}::timestamptz")
        params.append(date_to)
        idx += 1
    if search:
        conditions.append(f"metadata::text ILIKE ${idx}")
        params.append(f"%{search}%")
        idx += 1

    where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    total = await conn.fetchval(
        f"SELECT COUNT(*) FROM app_events {where_clause}", *params
    )

    offset = (page - 1) * per_page
    params.append(per_page)
    params.append(offset)
    rows = await conn.fetch(
        f"""
        SELECT * FROM app_events {where_clause}
        ORDER BY created_at DESC
        LIMIT ${idx} OFFSET ${idx + 1}
        """,
        *params,
    )

    return {"items": rows_to_list(rows), "total": total, "page": page, "per_page": per_page}


@app.get("/api/admin/logs/stats")
async def admin_logs_stats(
    session: dict = Depends(get_admin_user),
    conn: asyncpg.Connection = Depends(db),
):
    row = await conn.fetchrow("""
        SELECT
            COUNT(*) AS total_events,
            COUNT(*) FILTER (WHERE severity = 'info') AS sev_info,
            COUNT(*) FILTER (WHERE severity = 'warn') AS sev_warn,
            COUNT(*) FILTER (WHERE severity = 'error') AS sev_error,
            COUNT(*) FILTER (WHERE severity = 'critical') AS sev_critical,
            COUNT(DISTINCT anonymous_id) AS unique_users
        FROM app_events
        WHERE created_at > NOW() - INTERVAL '24 hours'
    """)

    type_rows = await conn.fetch("""
        SELECT event_type, COUNT(*) AS count
        FROM app_events
        WHERE created_at > NOW() - INTERVAL '24 hours'
        GROUP BY event_type
    """)

    return {
        "total_events": row["total_events"],
        "by_severity": {
            "info": row["sev_info"],
            "warn": row["sev_warn"],
            "error": row["sev_error"],
            "critical": row["sev_critical"],
        },
        "by_type": {r["event_type"]: r["count"] for r in type_rows},
        "unique_users": row["unique_users"],
    }


# ─────────────────────────────────────────────────────────
# Admin tasks (Kanban CRUD)
# ─────────────────────────────────────────────────────────

@app.get("/api/admin/tasks")
async def admin_list_tasks(
    session: dict = Depends(get_admin_user),
    conn: asyncpg.Connection = Depends(db),
):
    rows = await conn.fetch(
        "SELECT * FROM admin_tasks ORDER BY status, priority ASC"
    )
    result: dict[str, list] = {"backlog": [], "in_progress": [], "done": []}
    for r in rows:
        d = row_to_dict(r)
        result.setdefault(d["status"], []).append(d)
    return result


@app.post("/api/admin/tasks", status_code=201)
async def admin_create_task(
    data: TaskCreate,
    request: Request,
    session: dict = Depends(get_admin_user),
    conn: asyncpg.Connection = Depends(db),
):
    max_priority = await conn.fetchval(
        "SELECT COALESCE(MAX(priority), -1) FROM admin_tasks WHERE status = $1",
        data.status,
    )
    row = await conn.fetchrow(
        """
        INSERT INTO admin_tasks (title, description, description_plain, status, priority, source, source_ref, tags)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        RETURNING *
        """,
        data.title, data.description, data.description_plain,
        data.status, max_priority + 1,
        data.source, data.source_ref, data.tags,
    )
    client_ip = request.headers.get("X-Real-IP", request.client.host)
    await log_admin_action("task_create", client_ip, {"task_id": str(row["id"]), "title": data.title}, conn)
    return row_to_dict(row)


@app.patch("/api/admin/tasks/reorder")
async def admin_reorder_tasks(
    data: TaskReorder,
    session: dict = Depends(get_admin_user),
    conn: asyncpg.Connection = Depends(db),
):
    for idx, tid in enumerate(data.task_ids):
        try:
            task_uuid = uuid.UUID(tid)
        except ValueError:
            raise HTTPException(400, f"Invalid UUID: {tid}")
        await conn.execute(
            "UPDATE admin_tasks SET priority = $1, status = $2 WHERE id = $3",
            idx, data.status, task_uuid,
        )
    return {"status": "ok"}


@app.patch("/api/admin/tasks/{task_id}")
async def admin_update_task(
    task_id: str,
    data: TaskUpdate,
    request: Request,
    session: dict = Depends(get_admin_user),
    conn: asyncpg.Connection = Depends(db),
):
    try:
        tid = uuid.UUID(task_id)
    except ValueError:
        raise HTTPException(400, "Invalid task ID")

    existing = await conn.fetchrow("SELECT * FROM admin_tasks WHERE id = $1", tid)
    if not existing:
        raise HTTPException(404, "Task not found")

    updates = data.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(400, "No fields to update")

    # If status changed, recalculate priority (append to end of new column)
    if "status" in updates and updates["status"] != existing["status"]:
        max_priority = await conn.fetchval(
            "SELECT COALESCE(MAX(priority), -1) FROM admin_tasks WHERE status = $1",
            updates["status"],
        )
        updates["priority"] = max_priority + 1

    set_parts = []
    values: list[Any] = []
    for i, (col, val) in enumerate(updates.items(), start=1):
        set_parts.append(f"{col} = ${i}")
        values.append(val)

    values.append(tid)
    n = len(values)

    row = await conn.fetchrow(
        f"UPDATE admin_tasks SET {', '.join(set_parts)} WHERE id = ${n} RETURNING *",
        *values,
    )

    client_ip = request.headers.get("X-Real-IP", request.client.host)
    await log_admin_action(
        "task_update", client_ip,
        {"task_id": task_id, "changes": list(updates.keys())},
        conn,
    )
    return row_to_dict(row)


@app.delete("/api/admin/tasks/{task_id}")
async def admin_delete_task(
    task_id: str,
    request: Request,
    session: dict = Depends(get_admin_user),
    conn: asyncpg.Connection = Depends(db),
):
    try:
        tid = uuid.UUID(task_id)
    except ValueError:
        raise HTTPException(400, "Invalid task ID")

    row = await conn.fetchrow("DELETE FROM admin_tasks WHERE id = $1 RETURNING id, title", tid)
    if not row:
        raise HTTPException(404, "Task not found")

    client_ip = request.headers.get("X-Real-IP", request.client.host)
    await log_admin_action(
        "task_delete", client_ip,
        {"task_id": task_id, "title": row["title"]},
        conn,
    )
    return {"status": "deleted"}


# ─────────────────────────────────────────────────────────
# Admin audit log
# ─────────────────────────────────────────────────────────

@app.get("/api/admin/audit-log")
async def admin_audit_log_list(
    action: Optional[str] = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    session: dict = Depends(get_admin_user),
    conn: asyncpg.Connection = Depends(db),
):
    if action:
        total = await conn.fetchval(
            "SELECT COUNT(*) FROM admin_audit_log WHERE action = $1", action
        )
        rows = await conn.fetch(
            """
            SELECT * FROM admin_audit_log WHERE action = $1
            ORDER BY created_at DESC LIMIT $2 OFFSET $3
            """,
            action, per_page, (page - 1) * per_page,
        )
    else:
        total = await conn.fetchval("SELECT COUNT(*) FROM admin_audit_log")
        rows = await conn.fetch(
            "SELECT * FROM admin_audit_log ORDER BY created_at DESC LIMIT $1 OFFSET $2",
            per_page, (page - 1) * per_page,
        )

    return {"items": rows_to_list(rows), "total": total, "page": page, "per_page": per_page}


# ─────────────────────────────────────────────────────────
# Event tracking (public — from Mini App)
# ─────────────────────────────────────────────────────────

@app.post("/api/events")
async def receive_event(
    data: AppEvent,
    request: Request,
    conn: asyncpg.Connection = Depends(db),
    auth_user: dict | None = Depends(get_optional_user),
):
    telegram_id = auth_user["id"] if auth_user else 0
    anon_id = anonymize_id(telegram_id)

    await conn.execute(
        """
        INSERT INTO app_events (event_type, anonymous_id, session_id, metadata, severity)
        VALUES ($1, $2, $3, $4::jsonb, $5)
        """,
        data.event_type, anon_id, data.session_id,
        json.dumps(data.metadata) if data.metadata else None,
        data.severity,
    )
    return {"status": "ok"}


# ─────────────────────────────────────────────────────────
# Admin system info
# ─────────────────────────────────────────────────────────

@app.get("/api/admin/system/info")
async def admin_system_info(
    session: dict = Depends(get_admin_user),
    conn: asyncpg.Connection = Depends(db),
):
    counts = await conn.fetchrow("""
        SELECT
            (SELECT COUNT(*) FROM users)                           AS users,
            (SELECT COUNT(*) FROM schedules WHERE is_active = TRUE) AS schedules_active,
            (SELECT COUNT(*) FROM bookings)                        AS bookings_total,
            (SELECT COUNT(*) FROM app_events)                      AS events_total,
            (SELECT COUNT(*) FROM admin_tasks)                     AS tasks_total
    """)
    tables_count = await conn.fetchval(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public'"
    )
    return {
        "version": app.version,
        "python_version": sys.version.split()[0],
        "uptime_seconds": int(_time.time() - _start_time),
        "database": {
            "pool_size": _pool.get_size(),
            "pool_free": _pool.get_idle_size(),
            "tables_count": tables_count,
        },
        "counts": dict(counts) if counts else {},
        "environment": {
            "admin_ip_allowlist": ADMIN_IP_ALLOWLIST or "не задан",
            "cors_origins": _cors_origins,
            "rate_limits": "api: 10r/s, booking: 5r/m, admin: 5r/s, admin_auth: 3r/m",
        },
    }


# ─────────────────────────────────────────────────────────
# Admin sessions — invalidate all except current
# ─────────────────────────────────────────────────────────

@app.post("/api/admin/sessions/invalidate-all")
async def invalidate_all_sessions(
    request: Request,
    session: dict = Depends(get_admin_user),
    conn: asyncpg.Connection = Depends(db),
):
    current_token = request.cookies.get("admin_session", "")
    count = await conn.fetchval(
        "SELECT COUNT(*) FROM admin_sessions WHERE is_active = TRUE AND session_token != $1",
        current_token,
    )
    await conn.execute(
        "UPDATE admin_sessions SET is_active = FALSE WHERE is_active = TRUE AND session_token != $1",
        current_token,
    )
    client_ip = request.headers.get("X-Real-IP", request.client.host)
    await log_admin_action(
        "invalidate_sessions", client_ip,
        {"invalidated_count": count or 0}, conn,
    )
    return {"status": "ok", "invalidated": count or 0}


# ─────────────────────────────────────────────────────────
# Admin maintenance — cleanup old events
# ─────────────────────────────────────────────────────────

@app.post("/api/admin/maintenance/cleanup-events")
async def cleanup_events(
    data: CleanupRequest,
    request: Request,
    session: dict = Depends(get_admin_user),
    conn: asyncpg.Connection = Depends(db),
):
    count = await conn.fetchval(
        "SELECT COUNT(*) FROM app_events WHERE severity = $1 AND created_at < NOW() - INTERVAL '1 day' * $2",
        data.severity, data.older_than_days,
    )
    await conn.execute(
        "DELETE FROM app_events WHERE severity = $1 AND created_at < NOW() - INTERVAL '1 day' * $2",
        data.severity, data.older_than_days,
    )
    client_ip = request.headers.get("X-Real-IP", request.client.host)
    await log_admin_action(
        "cleanup_events", client_ip,
        {"deleted": count or 0, "severity": data.severity, "older_than_days": data.older_than_days},
        conn,
    )
    return {"status": "ok", "deleted": count or 0}
