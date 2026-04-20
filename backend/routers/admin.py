"""Роуты: admin dashboard, tasks, logs, sessions + event tracking."""
import uuid
import asyncpg
import structlog
import statistics
from typing import Optional, Any
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from database import db, get_pool
from auth import (
    get_admin_user, get_admin_or_internal, get_optional_user,
    verify_telegram_login, create_admin_session, log_admin_action,
    _check_login_rate_limit, _record_login_attempt, _session_checked,
    ADMIN_SESSION_TTL_HOURS, ADMIN_IP_ALLOWLIST,
)
from schemas import TelegramLoginData, TaskCreate, TaskUpdate, TaskReorder, AppEvent, CleanupRequest
from utils import row_to_dict, rows_to_list
from config import CORS_ORIGINS, APP_VERSION, APP_START_TIME, ADMIN_TELEGRAM_ID, ADMIN_TELEGRAM_IDS, ADMIN_OWNER_ID, OWNER_ANONYMOUS_ID, PROD_LAUNCH_DATE, get_prod_cutoff

import sys
import time as _time

log = structlog.get_logger()
router = APIRouter()

# ─────────────────────────────────────────────────────────
# SQL column whitelists (defense-in-depth against injection
# via dynamically-built UPDATE/WHERE clauses)
# ─────────────────────────────────────────────────────────
ALLOWED_TASK_COLUMNS = {
    "title", "description", "description_plain",
    "status", "tags", "priority",
}

# Simple module-level TTL cache for expensive queries (5 minutes).
_TTL_CACHE: dict[str, tuple[float, Any]] = {}
_TTL_SECONDS = 300.0


def _cache_get(key: str) -> Any:
    entry = _TTL_CACHE.get(key)
    if entry is None:
        return None
    ts, value = entry
    if _time.time() - ts > _TTL_SECONDS:
        return None
    return value


def _cache_set(key: str, value: Any) -> None:
    _TTL_CACHE[key] = (_time.time(), value)


# ─────────────────────────────────────────────────────────
# Admin auth
# ─────────────────────────────────────────────────────────

@router.post("/api/admin/auth/login")
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

    if data.id not in ADMIN_TELEGRAM_IDS:
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


@router.post("/api/admin/auth/logout")
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

    token_prefix = session["session_token"][:8]
    _session_checked.discard(token_prefix)

    response = JSONResponse(content={"status": "ok"})
    response.delete_cookie(key="admin_session", path="/api/admin")
    return response


@router.get("/api/admin/auth/me")
async def admin_me(
    request: Request,
    session: dict = Depends(get_admin_user),
    conn: asyncpg.Connection = Depends(db),
):
    token_prefix = session["session_token"][:8]
    if token_prefix not in _session_checked:
        client_ip = request.headers.get("X-Real-IP", request.client.host)
        await log_admin_action("session_check", client_ip, {"session": token_prefix}, conn)
        if len(_session_checked) > 10000:
            _session_checked.clear()
        _session_checked.add(token_prefix)

    return {
        "telegram_id": session["telegram_id"],
        "expires_at": session["expires_at"].isoformat(),
        "ip": str(session["ip_address"]),
    }


# ─────────────────────────────────────────────────────────
# Admin dashboard
# ─────────────────────────────────────────────────────────

@router.get("/api/admin/dashboard/summary")
async def admin_dashboard_summary(
    request: Request,
    session: dict = Depends(get_admin_user),
    conn: asyncpg.Connection = Depends(db),
):
    client_ip = request.headers.get("X-Real-IP", request.client.host)
    await log_admin_action("view_dashboard", client_ip, {"path": "/api/admin/dashboard/summary"}, conn)

    owner_id = ADMIN_TELEGRAM_ID or 0
    cutoff = get_prod_cutoff()
    row = await conn.fetchrow("""
        SELECT
            (SELECT COUNT(*) FROM users WHERE telegram_id != $1 AND created_at >= $2) AS total_users,
            (SELECT COUNT(DISTINCT s.user_id) FROM schedules s
             JOIN bookings b ON b.schedule_id = s.id
             JOIN users u ON u.id = s.user_id
             WHERE b.created_at > NOW() - INTERVAL '7 days'
             AND u.telegram_id != $1
             AND u.created_at >= $2) AS active_users_7d,
            (SELECT COUNT(*) FROM bookings b
             JOIN schedules s ON s.id = b.schedule_id
             JOIN users u ON u.id = s.user_id
             WHERE u.telegram_id != $1
             AND u.created_at >= $2
             AND (b.guest_telegram_id IS NULL OR b.guest_telegram_id != $1)) AS total_bookings,
            (SELECT COUNT(*) FROM bookings b
             JOIN schedules s ON s.id = b.schedule_id
             JOIN users u ON u.id = s.user_id
             WHERE DATE(b.scheduled_time) = CURRENT_DATE
             AND u.telegram_id != $1
             AND u.created_at >= $2
             AND (b.guest_telegram_id IS NULL OR b.guest_telegram_id != $1)) AS bookings_today,
            (SELECT COUNT(*) FROM app_events
             WHERE severity IN ('error', 'critical')
             AND created_at > NOW() - INTERVAL '24 hours') AS errors_24h,
            (SELECT COUNT(*) FROM bookings b
             JOIN schedules s ON s.id = b.schedule_id
             JOIN users u ON u.id = s.user_id
             WHERE b.status = 'pending'
             AND u.telegram_id != $1
             AND u.created_at >= $2
             AND (b.guest_telegram_id IS NULL OR b.guest_telegram_id != $1)) AS pending_bookings
    """, owner_id, cutoff)
    return row_to_dict(row)


@router.get("/api/admin/dashboard/bookings-trend")
async def admin_bookings_trend(
    request: Request,
    days: int = Query(30, ge=1, le=90),
    session: dict = Depends(get_admin_user),
    conn: asyncpg.Connection = Depends(db),
):
    owner_id = ADMIN_TELEGRAM_ID or 0
    cutoff = get_prod_cutoff()
    rows = await conn.fetch(
        """
        SELECT DATE(b.scheduled_time) AS date, COUNT(*) AS count
        FROM bookings b
        JOIN schedules s ON s.id = b.schedule_id
        JOIN users u ON u.id = s.user_id
        WHERE b.scheduled_time >= NOW() - INTERVAL '1 day' * $1
        AND u.telegram_id != $2
        AND u.created_at >= $3
        AND (b.guest_telegram_id IS NULL OR b.guest_telegram_id != $2)
        GROUP BY DATE(b.scheduled_time)
        ORDER BY date
        """,
        days, owner_id, cutoff,
    )
    return [{"date": str(r["date"]), "count": r["count"]} for r in rows]


@router.get("/api/admin/dashboard/platforms")
async def admin_platforms(
    session: dict = Depends(get_admin_user),
    conn: asyncpg.Connection = Depends(db),
):
    owner_id = ADMIN_TELEGRAM_ID or 0
    cutoff = get_prod_cutoff()
    rows = await conn.fetch(
        """
        SELECT s.platform, COUNT(*) AS count FROM schedules s
        JOIN users u ON u.id = s.user_id
        WHERE s.is_active = TRUE AND u.telegram_id != $1
        AND s.created_at >= $2
        GROUP BY s.platform
        """,
        owner_id, cutoff,
    )
    return rows_to_list(rows)


# ─────────────────────────────────────────────────────────
# Admin logs (app_events)
# ─────────────────────────────────────────────────────────

@router.get("/api/admin/logs")
async def admin_logs(
    request: Request,
    event_type: Optional[str] = None,
    severity: Optional[str] = None,
    anonymous_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    search: Optional[str] = None,
    include_owner: bool = Query(default=False),
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

    if not include_owner and OWNER_ANONYMOUS_ID:
        conditions.append(f"anonymous_id != ${idx}")
        params.append(OWNER_ANONYMOUS_ID)
        idx += 1

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


@router.get("/api/admin/logs/stats")
async def admin_logs_stats(
    include_owner: bool = Query(default=False),
    session: dict = Depends(get_admin_user),
    conn: asyncpg.Connection = Depends(db),
):
    owner_filter = ""
    params: list[Any] = []
    if not include_owner and OWNER_ANONYMOUS_ID:
        owner_filter = "AND anonymous_id != $1"
        params.append(OWNER_ANONYMOUS_ID)

    row = await conn.fetchrow(f"""
        SELECT
            COUNT(*) AS total_events,
            COUNT(*) FILTER (WHERE severity = 'info') AS sev_info,
            COUNT(*) FILTER (WHERE severity = 'warn') AS sev_warn,
            COUNT(*) FILTER (WHERE severity = 'error') AS sev_error,
            COUNT(*) FILTER (WHERE severity = 'critical') AS sev_critical,
            COUNT(DISTINCT anonymous_id) AS unique_users
        FROM app_events
        WHERE created_at > NOW() - INTERVAL '24 hours'
        {owner_filter}
    """, *params)

    type_rows = await conn.fetch(f"""
        SELECT event_type, COUNT(*) AS count
        FROM app_events
        WHERE created_at > NOW() - INTERVAL '24 hours'
        {owner_filter}
        GROUP BY event_type
    """, *params)

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

@router.get("/api/admin/tasks")
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


@router.post("/api/admin/tasks", status_code=201)
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


@router.patch("/api/admin/tasks/reorder")
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


@router.patch("/api/admin/tasks/{task_id}")
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

    if "status" in updates and updates["status"] != existing["status"]:
        max_priority = await conn.fetchval(
            "SELECT COALESCE(MAX(priority), -1) FROM admin_tasks WHERE status = $1",
            updates["status"],
        )
        updates["priority"] = max_priority + 1

    set_parts = []
    values: list[Any] = []
    for i, (col, val) in enumerate(updates.items(), start=1):
        # Defense-in-depth: even though `updates` comes from a validated
        # Pydantic model, reject anything not in the explicit whitelist.
        if col not in ALLOWED_TASK_COLUMNS:
            raise HTTPException(400, f"Invalid field: {col}")
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


@router.delete("/api/admin/tasks/{task_id}")
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

@router.get("/api/admin/audit-log")
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
# Admin system info
# ─────────────────────────────────────────────────────────

@router.get("/api/admin/system/info")
async def admin_system_info(
    session: dict = Depends(get_admin_user),
    conn: asyncpg.Connection = Depends(db),
):
    pool = await get_pool()
    owner_id = ADMIN_TELEGRAM_ID or 0
    cutoff = get_prod_cutoff()
    counts = await conn.fetchrow("""
        WITH non_owner_users AS (
            SELECT id FROM users WHERE telegram_id != $1 AND created_at >= $2
        )
        SELECT
            (SELECT COUNT(*) FROM non_owner_users) AS users,
            (SELECT COUNT(*) FROM schedules s
             WHERE s.is_active = TRUE
               AND s.created_at >= $2
               AND s.user_id IN (SELECT id FROM non_owner_users)) AS schedules_active,
            (SELECT COUNT(*) FROM bookings b
             WHERE b.schedule_id IN (
                 SELECT s.id FROM schedules s
                 WHERE s.user_id IN (SELECT id FROM non_owner_users)
             )
             AND b.created_at >= $2
             AND (b.guest_telegram_id IS NULL OR b.guest_telegram_id != $1)) AS bookings_total,
            (SELECT COUNT(*) FROM app_events) AS events_total,
            (SELECT COUNT(*) FROM admin_tasks) AS tasks_total
    """, owner_id, cutoff)
    # Static information_schema lookup — cache 5 min to avoid per-request pg_catalog scan.
    tables_count = _cache_get("tables_count")
    if tables_count is None:
        tables_count = await conn.fetchval(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public'"
        )
        _cache_set("tables_count", tables_count)
    return {
        "version": APP_VERSION,
        "python_version": sys.version.split()[0],
        "uptime_seconds": int(_time.time() - APP_START_TIME),
        "prod_launch_date": PROD_LAUNCH_DATE or None,
        "database": {
            "pool_size": pool.get_size(),
            "pool_free": pool.get_idle_size(),
            "tables_count": tables_count,
        },
        "counts": dict(counts) if counts else {},
        "environment": {
            "admin_ip_allowlist": ADMIN_IP_ALLOWLIST or "не задан",
            "cors_origins": CORS_ORIGINS,
            "rate_limits": "api: 10r/s, booking: 5r/m, admin: 5r/s, admin_auth: 3r/m",
        },
    }


# ─────────────────────────────────────────────────────────
# Admin sessions — invalidate all except current
# ─────────────────────────────────────────────────────────

@router.post("/api/admin/sessions/invalidate-all")
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

@router.post("/api/admin/maintenance/cleanup-events")
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


# ─────────────────────────────────────────────────────────
# Event tracking (public — from Mini App)
# ─────────────────────────────────────────────────────────
# Analytics
# ─────────────────────────────────────────────────────────

@router.get("/api/admin/analytics/funnel")
async def analytics_funnel(
    session: dict = Depends(get_admin_user),
    conn: asyncpg.Connection = Depends(db),
):
    owner_id = ADMIN_TELEGRAM_ID or 0
    cutoff = get_prod_cutoff()
    row = await conn.fetchrow("""
        SELECT
          (SELECT COUNT(*) FROM users WHERE telegram_id != $1 AND created_at >= $2) AS registered,
          (SELECT COUNT(DISTINCT u.id) FROM users u
           JOIN schedules s ON s.user_id = u.id
           WHERE u.telegram_id != $1 AND u.created_at >= $2
             AND s.is_default = FALSE) AS created_schedule,
          (SELECT COUNT(DISTINCT u.id) FROM users u
           JOIN schedules s ON s.user_id = u.id
           JOIN bookings b ON b.schedule_id = s.id
           WHERE u.telegram_id != $1 AND u.created_at >= $2
             AND b.status != 'cancelled') AS received_booking
    """, owner_id, cutoff)
    registered = row["registered"]
    steps = [
        {"name": "Регистрация", "count": registered, "percent": 100},
        {"name": "Создал расписание", "count": row["created_schedule"],
         "percent": round(row["created_schedule"] / registered * 100) if registered else 0},
        {"name": "Получил бронирование", "count": row["received_booking"],
         "percent": round(row["received_booking"] / registered * 100) if registered else 0},
    ]
    return {"steps": steps}


_RETENTION_INTERVALS = {"day1": 1, "day7": 7, "day30": 30}

@router.get("/api/admin/analytics/retention")
async def analytics_retention(
    period: str = Query("day7"),
    session: dict = Depends(get_admin_user),
    conn: asyncpg.Connection = Depends(db),
):
    days = _RETENTION_INTERVALS.get(period, 7)
    owner_id = ADMIN_TELEGRAM_ID or 0
    cutoff = get_prod_cutoff()

    rows = await conn.fetch("""
        WITH cohort AS (
          SELECT id, telegram_id, DATE(created_at) AS reg_date
          FROM users WHERE telegram_id != $1 AND created_at >= $3
        ),
        activity AS (
          SELECT DISTINCT c.id AS user_id, DATE(s.created_at) AS activity_date
          FROM cohort c JOIN schedules s ON s.user_id = c.id
          UNION
          SELECT DISTINCT c.id, DATE(b.created_at)
          FROM cohort c JOIN schedules s ON s.user_id = c.id
          JOIN bookings b ON b.schedule_id = s.id
        )
        SELECT
          c.reg_date,
          COUNT(DISTINCT c.id) AS cohort_size,
          COUNT(DISTINCT CASE WHEN a.activity_date >= c.reg_date + make_interval(days => $2) THEN c.id END) AS retained
        FROM cohort c
        LEFT JOIN activity a ON a.user_id = c.id
        GROUP BY c.reg_date
        HAVING COUNT(DISTINCT c.id) >= 1
        ORDER BY c.reg_date DESC
        LIMIT 30
    """, owner_id, days, cutoff)

    cohorts = []
    total_size = 0
    total_retained = 0
    for r in rows:
        size = r["cohort_size"]
        retained = r["retained"]
        total_size += size
        total_retained += retained
        cohorts.append({
            "date": str(r["reg_date"]),
            "cohort_size": size,
            "retained": retained,
            "rate": round(retained / size * 100) if size else 0,
        })

    return {
        "period": period,
        "cohorts": cohorts,
        "overall_rate": round(total_retained / total_size * 100) if total_size else 0,
    }


@router.get("/api/admin/analytics/organizer-stats")
async def analytics_organizer_stats(
    session: dict = Depends(get_admin_user),
    conn: asyncpg.Connection = Depends(db),
):
    owner_id = ADMIN_TELEGRAM_ID or 0
    cutoff = get_prod_cutoff()
    rows = await conn.fetch("""
        SELECT
          u.id,
          COALESCE(u.first_name, '') AS first_name,
          COALESCE(LEFT(u.last_name, 1), '') AS last_initial,
          u.username,
          COUNT(DISTINCT s.id) FILTER (WHERE s.is_active = TRUE AND s.is_default = FALSE) AS schedules_count,
          COUNT(DISTINCT b.id) FILTER (WHERE b.status != 'cancelled') AS bookings_count,
          MAX(b.created_at) FILTER (WHERE b.status != 'cancelled') AS last_booking
        FROM users u
        LEFT JOIN schedules s ON s.user_id = u.id
        LEFT JOIN bookings b ON b.schedule_id = s.id
        WHERE u.telegram_id != $1 AND u.created_at >= $2
        GROUP BY u.id, u.first_name, u.last_name, u.username
        ORDER BY bookings_count DESC
        LIMIT 20
    """, owner_id, cutoff)

    organizers = []
    total_schedules = 0
    total_bookings = 0
    for r in rows:
        name = r["first_name"]
        if r["last_initial"]:
            name += " " + r["last_initial"] + "."
        organizers.append({
            "name": name.strip() or "—",
            "username": r["username"],
            "schedules": r["schedules_count"],
            "bookings": r["bookings_count"],
            "last_booking": r["last_booking"].isoformat() if r["last_booking"] else None,
        })
        total_schedules += r["schedules_count"]
        total_bookings += r["bookings_count"]

    n = len(organizers) or 1
    return {
        "organizers": organizers,
        "averages": {
            "schedules_per_organizer": round(total_schedules / n, 1),
            "bookings_per_organizer": round(total_bookings / n, 1),
        },
    }


@router.get("/api/admin/analytics/registrations-trend")
async def analytics_registrations_trend(
    days: int = Query(30, ge=1, le=365),
    session: dict = Depends(get_admin_user),
    conn: asyncpg.Connection = Depends(db),
):
    owner_id = ADMIN_TELEGRAM_ID or 0
    cutoff = get_prod_cutoff()
    rows = await conn.fetch("""
        SELECT DATE(created_at) AS date, COUNT(*) AS count
        FROM users
        WHERE telegram_id != $1
          AND created_at >= $3
          AND created_at >= NOW() - INTERVAL '1 day' * $2
        GROUP BY DATE(created_at)
        ORDER BY date
    """, owner_id, days, cutoff)
    return [{"date": str(r["date"]), "count": r["count"]} for r in rows]


@router.get("/api/admin/analytics/time-to-value")
async def analytics_time_to_value(
    session: dict = Depends(get_admin_user),
    conn: asyncpg.Connection = Depends(db),
):
    owner_id = ADMIN_TELEGRAM_ID or 0
    cutoff = get_prod_cutoff()
    rows = await conn.fetch("""
        SELECT
          u.id,
          EXTRACT(EPOCH FROM (MIN(b.created_at) - u.created_at)) / 3600 AS hours_to_value
        FROM users u
        JOIN schedules s ON s.user_id = u.id
        JOIN bookings b ON b.schedule_id = s.id AND b.status != 'cancelled'
        WHERE u.telegram_id != $1 AND u.created_at >= $2
        GROUP BY u.id, u.created_at
    """, owner_id, cutoff)

    hours_list = [float(r["hours_to_value"]) for r in rows if r["hours_to_value"] is not None]
    users_with = len(hours_list)

    total_users = await conn.fetchval(
        "SELECT COUNT(*) FROM users WHERE telegram_id != $1 AND created_at >= $2", owner_id, cutoff
    )
    users_without = total_users - users_with

    median_hours = None
    average_hours = None
    if hours_list:
        median_hours = round(statistics.median(hours_list), 1)
        average_hours = round(statistics.mean(hours_list), 1)

    buckets = [
        ("< 1ч", 0, 1),
        ("1-6ч", 1, 6),
        ("6-24ч", 6, 24),
        ("1-7д", 24, 168),
        ("> 7д", 168, float("inf")),
    ]
    distribution = []
    for label, lo, hi in buckets:
        count = sum(1 for h in hours_list if lo <= h < hi)
        distribution.append({"bucket": label, "count": count})

    return {
        "median_hours": median_hours,
        "average_hours": average_hours,
        "users_with_value": users_with,
        "users_without_value": users_without,
        "distribution": distribution,
    }


# ─────────────────────────────────────────────────────────
# Analytics v2: activation, guest-funnel, quality, operational, growth
# ─────────────────────────────────────────────────────────

@router.get("/api/admin/analytics/activation")
async def analytics_activation(
    session: dict = Depends(get_admin_user),
    conn: asyncpg.Connection = Depends(db),
):
    owner_id = ADMIN_TELEGRAM_ID or 0
    cutoff = get_prod_cutoff()
    rows = await conn.fetch("""
        SELECT EXTRACT(EPOCH FROM (MIN(b.created_at) - u.created_at)) / 3600 AS hours
        FROM users u
        JOIN schedules s ON s.user_id = u.id
        JOIN bookings b ON b.schedule_id = s.id AND b.status NOT IN ('cancelled')
        WHERE u.telegram_id != $1 AND u.created_at >= $2
        GROUP BY u.id, u.created_at
    """, owner_id, cutoff)
    hours_list = sorted([float(r["hours"]) for r in rows if r["hours"] is not None])
    activated = len(hours_list)

    total = await conn.fetchval(
        "SELECT COUNT(*) FROM users WHERE telegram_id != $1 AND created_at >= $2", owner_id, cutoff
    )

    median = hours_list[len(hours_list) // 2] if hours_list else None
    p90 = hours_list[int(len(hours_list) * 0.9)] if hours_list else None

    return {
        "ttfv_organizer": {
            "median_hours": round(median, 1) if median is not None else None,
            "p90_hours": round(p90, 1) if p90 is not None else None,
            "count": activated,
        },
        "activation_rate": {
            "activated": activated,
            "total": total,
            "rate": round(activated / total * 100, 1) if total else 0,
        },
    }


_GUEST_FUNNEL_STEPS = [
    ("schedule_viewed", "Открыли расписание"),
    ("date_selected", "Выбрали дату"),
    ("slot_selected", "Выбрали слот"),
    ("form_opened", "Открыли форму"),
    ("booking_submitted", "Отправили бронь"),
    ("booking_success", "Успешно забронировали"),
]

@router.get("/api/admin/analytics/guest-funnel")
async def analytics_guest_funnel(
    days: int = Query(30, ge=1, le=365),
    session: dict = Depends(get_admin_user),
    conn: asyncpg.Connection = Depends(db),
):
    cutoff = get_prod_cutoff()
    event_types = [s[0] for s in _GUEST_FUNNEL_STEPS]
    rows = await conn.fetch("""
        SELECT event_type, COUNT(*) AS count
        FROM app_events
        WHERE event_type = ANY($1)
          AND created_at >= NOW() - INTERVAL '1 day' * $2
          AND created_at >= $3
        GROUP BY event_type
    """, event_types, days, cutoff)

    counts = {r["event_type"]: r["count"] for r in rows}
    steps = []
    for event, name in _GUEST_FUNNEL_STEPS:
        steps.append({"name": name, "event": event, "count": counts.get(event, 0)})

    first = steps[0]["count"] if steps else 0
    last = steps[-1]["count"] if steps else 0
    return {
        "steps": steps,
        "conversion_rate": round(last / first * 100, 1) if first else 0,
        "period_days": days,
    }


@router.get("/api/admin/analytics/quality")
async def analytics_quality(
    session: dict = Depends(get_admin_user),
    conn: asyncpg.Connection = Depends(db),
):
    owner_id = ADMIN_TELEGRAM_ID or 0
    cutoff = get_prod_cutoff()
    row = await conn.fetchrow("""
        SELECT
          COUNT(*) FILTER (WHERE status = 'pending' AND created_at < NOW() - INTERVAL '24 hours') AS timed_out,
          COUNT(*) FILTER (WHERE status = 'pending') AS total_pending,
          COUNT(*) FILTER (WHERE status = 'cancelled') AS cancelled,
          COUNT(*) AS total
        FROM bookings
        WHERE created_at >= $1
    """, cutoff)

    total = row["total"] or 1
    errors_count = await conn.fetchval("""
        SELECT COUNT(*) FROM app_events
        WHERE severity IN ('error','critical') AND created_at >= $1
    """, cutoff)

    avg_row = await conn.fetchrow("""
        SELECT AVG(bc)::float AS avg_meetings FROM (
            SELECT COUNT(b.id) AS bc
            FROM users u
            JOIN schedules s ON s.user_id = u.id
            JOIN bookings b ON b.schedule_id = s.id AND b.status NOT IN ('cancelled')
            WHERE u.telegram_id != $1 AND u.created_at >= $2
            GROUP BY u.id
        ) sub
    """, owner_id, cutoff)

    return {
        "pending_timeout_rate": round((row["timed_out"] or 0) / (row["total_pending"] or 1) * 100, 1),
        "cancellation_rate": round((row["cancelled"] or 0) / total * 100, 1),
        "error_per_1000_bookings": round((errors_count or 0) / total * 1000, 1),
        "avg_meetings_per_organizer": round(avg_row["avg_meetings"] or 0, 1),
    }


@router.get("/api/admin/analytics/operational")
async def analytics_operational(
    session: dict = Depends(get_admin_user),
    conn: asyncpg.Connection = Depends(db),
):
    pool = await get_pool()
    size = pool.get_size()
    free = pool.get_idle_size()
    row = await conn.fetchrow("""
        SELECT
          COUNT(*) AS total,
          COUNT(*) FILTER (WHERE severity IN ('error','critical')) AS errors,
          COUNT(*) FILTER (WHERE severity = 'warn') AS warnings
        FROM app_events
        WHERE created_at > NOW() - INTERVAL '24 hours'
    """)
    return {
        "db_pool": {"size": size, "free": free, "usage_percent": round((size - free) / size * 100) if size else 0},
        "events_24h": {"total": row["total"], "errors": row["errors"], "warnings": row["warnings"]},
        "api_health": "ok",
    }


@router.get("/api/admin/analytics/growth")
async def analytics_growth(
    session: dict = Depends(get_admin_user),
    conn: asyncpg.Connection = Depends(db),
):
    owner_id = ADMIN_TELEGRAM_ID or 0
    cutoff = get_prod_cutoff()
    row = await conn.fetchrow("""
        SELECT
          COUNT(*) FILTER (WHERE created_at >= CURRENT_DATE) AS today,
          COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '7 days') AS week,
          COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '30 days') AS month
        FROM users
        WHERE telegram_id != $1 AND created_at >= $2
    """, owner_id, cutoff)

    # WAU / MAU
    wau = await conn.fetchval("""
        SELECT COUNT(DISTINCT user_id) FROM (
          SELECT user_id FROM schedules WHERE created_at > NOW() - INTERVAL '7 days'
          UNION
          SELECT s.user_id FROM bookings b JOIN schedules s ON s.id = b.schedule_id
          WHERE b.created_at > NOW() - INTERVAL '7 days'
        ) a
    """)
    mau = await conn.fetchval("""
        SELECT COUNT(DISTINCT user_id) FROM (
          SELECT user_id FROM schedules WHERE created_at > NOW() - INTERVAL '30 days'
          UNION
          SELECT s.user_id FROM bookings b JOIN schedules s ON s.id = b.schedule_id
          WHERE b.created_at > NOW() - INTERVAL '30 days'
        ) a
    """)

    return {
        "registrations_today": row["today"],
        "registrations_7d": row["week"],
        "registrations_30d": row["month"],
        "wau": wau or 0,
        "mau": mau or 0,
        "wau_mau_ratio": round((wau or 0) / mau * 100, 1) if mau else 0,
    }


# ─────────────────────────────────────────────────────────

@router.post("/api/events")
async def receive_event(
    data: AppEvent,
    request: Request,
    auth_user: dict | None = Depends(get_optional_user),
):
    telegram_id = auth_user["id"] if auth_user else 0
    # Route through the in-memory EventBuffer — no DB roundtrip on hot path.
    from event_buffer import event_buffer
    event_buffer.add(
        event_type=data.event_type,
        telegram_id=telegram_id,
        metadata=data.metadata,
        severity=data.severity,
        session_id=data.session_id,
    )
    return {"status": "ok"}


# ── Admin management ───────────────────────────────────

@router.get("/api/admin/admins")
async def list_admins(session: dict = Depends(get_admin_or_internal)):
    return {"owner_id": ADMIN_OWNER_ID, "admin_ids": sorted(ADMIN_TELEGRAM_IDS)}


@router.post("/api/admin/admins")
async def add_admin(
    request: Request,
    session: dict = Depends(get_admin_or_internal),
    conn: asyncpg.Connection = Depends(db),
):
    if session["telegram_id"] != ADMIN_OWNER_ID:
        raise HTTPException(403, "Only owner can manage admins")
    body = await request.json()
    new_id = body.get("telegram_id")
    if not new_id or not isinstance(new_id, int):
        raise HTTPException(400, "telegram_id required (int)")
    ADMIN_TELEGRAM_IDS.add(new_id)
    client_ip = request.headers.get("X-Real-IP", request.client.host)
    await log_admin_action("add_admin", client_ip, {"new_admin_id": new_id}, conn)
    return {"status": "ok", "admin_ids": sorted(ADMIN_TELEGRAM_IDS)}


@router.delete("/api/admin/admins/{telegram_id}")
async def remove_admin(
    telegram_id: int,
    request: Request,
    session: dict = Depends(get_admin_or_internal),
    conn: asyncpg.Connection = Depends(db),
):
    if session["telegram_id"] != ADMIN_OWNER_ID:
        raise HTTPException(403, "Only owner can manage admins")
    if telegram_id == ADMIN_OWNER_ID:
        raise HTTPException(400, "Cannot remove owner")
    ADMIN_TELEGRAM_IDS.discard(telegram_id)
    await conn.execute(
        "UPDATE admin_sessions SET is_active = FALSE WHERE telegram_id = $1", telegram_id
    )
    client_ip = request.headers.get("X-Real-IP", request.client.host)
    await log_admin_action("remove_admin", client_ip, {"removed_admin_id": telegram_id}, conn)
    return {"status": "ok", "admin_ids": sorted(ADMIN_TELEGRAM_IDS)}


# ── User data reset (admin self-reset for testing) ─────

@router.post("/api/admin/reset-user")
async def reset_user_data(
    request: Request,
    session: dict = Depends(get_admin_or_internal),
    conn: asyncpg.Connection = Depends(db),
):
    """Reset user data. Admins reset own data; owner can reset any user via target_id body param."""
    try:
        return await _do_reset(request, session, conn)
    except HTTPException:
        raise
    except Exception as e:
        log.error("reset_user_error", error=str(e), exc_info=True)
        raise HTTPException(500, f"Reset failed: {type(e).__name__}: {e}")


async def _do_reset(request: Request, session: dict, conn):
    telegram_id = session["telegram_id"]

    # Owner can reset another user
    try:
        body = await request.json()
    except Exception:
        body = {}
    target_id = body.get("target_telegram_id")
    if target_id and isinstance(target_id, int):
        if telegram_id != ADMIN_OWNER_ID:
            raise HTTPException(403, "Only owner can reset other users")
        telegram_id = target_id

    user = await conn.fetchrow(
        "SELECT id FROM users WHERE telegram_id = $1", telegram_id
    )
    if not user:
        raise HTTPException(404, f"User {telegram_id} not found in DB")
    user_id = user["id"]

    # Collect booking IDs for this user (as organizer)
    org_booking_ids = [r["id"] for r in await conn.fetch(
        "SELECT b.id FROM bookings b JOIN schedules s ON b.schedule_id = s.id WHERE s.user_id = $1",
        user_id,
    )]
    # Collect booking IDs as guest
    guest_booking_ids = [r["id"] for r in await conn.fetch(
        "SELECT id FROM bookings WHERE guest_telegram_id = $1", telegram_id,
    )]
    all_booking_ids = list(set(org_booking_ids + guest_booking_ids))

    # Delete in FK-safe order — every step wrapped in try/except
    # 1. sent_reminders → bookings
    for table in ["sent_reminders", "event_mapping"]:
        try:
            if all_booking_ids:
                await conn.execute(
                    f"DELETE FROM {table} WHERE booking_id = ANY($1::uuid[])",
                    all_booking_ids,
                )
        except Exception:
            pass

    # 2. external_busy_slots → calendar_connections
    try:
        await conn.execute("""
            DELETE FROM external_busy_slots WHERE connection_id IN (
                SELECT cc.id FROM calendar_connections cc
                JOIN calendar_accounts ca ON ca.id = cc.account_id
                WHERE ca.user_id = $1)
        """, user_id)
    except Exception:
        pass

    # 3. sync_log → calendar_accounts/connections
    try:
        await conn.execute("""
            DELETE FROM sync_log WHERE account_id IN (
                SELECT id FROM calendar_accounts WHERE user_id = $1)
        """, user_id)
    except Exception:
        pass

    # 4. schedule_calendar_rules → schedules, calendar_connections
    try:
        await conn.execute(
            "DELETE FROM schedule_calendar_rules WHERE schedule_id IN (SELECT id FROM schedules WHERE user_id = $1)",
            user_id,
        )
    except Exception:
        pass

    # 5. calendar_connections → calendar_accounts
    try:
        await conn.execute("""
            DELETE FROM calendar_connections WHERE account_id IN (
                SELECT id FROM calendar_accounts WHERE user_id = $1)
        """, user_id)
    except Exception:
        pass

    # 6. calendar_accounts
    try:
        await conn.execute("DELETE FROM calendar_accounts WHERE user_id = $1", user_id)
    except Exception:
        pass

    # 7. Bookings (organizer + guest)
    org_deleted = 0
    guest_deleted = 0
    try:
        r = await conn.execute(
            "DELETE FROM bookings WHERE schedule_id IN (SELECT id FROM schedules WHERE user_id = $1)",
            user_id,
        )
        org_deleted = int(r.split()[-1])
    except Exception:
        pass
    try:
        r = await conn.execute("DELETE FROM bookings WHERE guest_telegram_id = $1", telegram_id)
        guest_deleted = int(r.split()[-1])
    except Exception:
        pass

    # 8. Schedules
    sched_deleted = 0
    try:
        r = await conn.execute("DELETE FROM schedules WHERE user_id = $1", user_id)
        sched_deleted = int(r.split()[-1])
    except Exception:
        pass

    try:
        client_ip = request.headers.get("X-Real-IP", request.client.host)
        await log_admin_action("reset_user", client_ip, {
            "telegram_id": telegram_id,
            "schedules_deleted": sched_deleted,
            "org_bookings_deleted": org_deleted,
            "guest_bookings_deleted": guest_deleted,
        }, conn)
    except Exception:
        pass

    return {
        "status": "ok",
        "deleted": {
            "schedules": sched_deleted,
            "bookings_as_organizer": org_deleted,
            "bookings_as_guest": guest_deleted,
        },
    }
