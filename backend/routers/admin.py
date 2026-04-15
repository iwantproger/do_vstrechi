"""Роуты: admin dashboard, tasks, logs, sessions + event tracking."""
import uuid
import json
import asyncpg
import structlog
from typing import Optional, Any
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from database import db, get_pool
from auth import (
    get_admin_user, get_optional_user,
    verify_telegram_login, create_admin_session, log_admin_action,
    _check_login_rate_limit, _record_login_attempt, _session_checked,
    ADMIN_SESSION_TTL_HOURS, ADMIN_IP_ALLOWLIST,
)
from schemas import TelegramLoginData, TaskCreate, TaskUpdate, TaskReorder, AppEvent, CleanupRequest
from utils import row_to_dict, rows_to_list, anonymize_id
from config import CORS_ORIGINS, APP_VERSION, APP_START_TIME, ADMIN_TELEGRAM_ID, OWNER_ANONYMOUS_ID

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
ALLOWED_EVENT_FILTERS = {"event_type", "severity", "anonymous_id"}

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

    from auth import ADMIN_TELEGRAM_ID
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
    row = await conn.fetchrow("""
        SELECT
            (SELECT COUNT(*) FROM users WHERE telegram_id != $1) AS total_users,
            (SELECT COUNT(DISTINCT s.user_id) FROM schedules s
             JOIN bookings b ON b.schedule_id = s.id
             JOIN users u ON u.id = s.user_id
             WHERE b.created_at > NOW() - INTERVAL '7 days'
             AND u.telegram_id != $1) AS active_users_7d,
            (SELECT COUNT(*) FROM bookings b
             JOIN schedules s ON s.id = b.schedule_id
             JOIN users u ON u.id = s.user_id
             WHERE u.telegram_id != $1
             AND (b.guest_telegram_id IS NULL OR b.guest_telegram_id != $1)) AS total_bookings,
            (SELECT COUNT(*) FROM bookings b
             JOIN schedules s ON s.id = b.schedule_id
             JOIN users u ON u.id = s.user_id
             WHERE DATE(b.scheduled_time) = CURRENT_DATE
             AND u.telegram_id != $1
             AND (b.guest_telegram_id IS NULL OR b.guest_telegram_id != $1)) AS bookings_today,
            (SELECT COUNT(*) FROM app_events
             WHERE severity IN ('error', 'critical')
             AND created_at > NOW() - INTERVAL '24 hours') AS errors_24h,
            (SELECT COUNT(*) FROM bookings b
             JOIN schedules s ON s.id = b.schedule_id
             JOIN users u ON u.id = s.user_id
             WHERE b.status = 'pending'
             AND u.telegram_id != $1
             AND (b.guest_telegram_id IS NULL OR b.guest_telegram_id != $1)) AS pending_bookings
    """, owner_id)
    return row_to_dict(row)


@router.get("/api/admin/dashboard/bookings-trend")
async def admin_bookings_trend(
    request: Request,
    days: int = Query(30, ge=1, le=90),
    session: dict = Depends(get_admin_user),
    conn: asyncpg.Connection = Depends(db),
):
    owner_id = ADMIN_TELEGRAM_ID or 0
    rows = await conn.fetch(
        """
        SELECT DATE(b.scheduled_time) AS date, COUNT(*) AS count
        FROM bookings b
        JOIN schedules s ON s.id = b.schedule_id
        JOIN users u ON u.id = s.user_id
        WHERE b.scheduled_time >= NOW() - ($1 || ' days')::interval
        AND u.telegram_id != $2
        AND (b.guest_telegram_id IS NULL OR b.guest_telegram_id != $2)
        GROUP BY DATE(b.scheduled_time)
        ORDER BY date
        """,
        str(days), owner_id,
    )
    return [{"date": str(r["date"]), "count": r["count"]} for r in rows]


@router.get("/api/admin/dashboard/platforms")
async def admin_platforms(
    session: dict = Depends(get_admin_user),
    conn: asyncpg.Connection = Depends(db),
):
    owner_id = ADMIN_TELEGRAM_ID or 0
    rows = await conn.fetch(
        """
        SELECT s.platform, COUNT(*) AS count FROM schedules s
        JOIN users u ON u.id = s.user_id
        WHERE s.is_active = TRUE AND u.telegram_id != $1
        GROUP BY s.platform
        """,
        owner_id,
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
    # Single SQL with CTE filtering non-owner users once, reused by subqueries.
    counts = await conn.fetchrow("""
        WITH non_owner_users AS (
            SELECT id FROM users WHERE telegram_id != $1
        )
        SELECT
            (SELECT COUNT(*) FROM non_owner_users) AS users,
            (SELECT COUNT(*) FROM schedules s
             WHERE s.is_active = TRUE
               AND s.user_id IN (SELECT id FROM non_owner_users)) AS schedules_active,
            (SELECT COUNT(*) FROM bookings b
             WHERE b.schedule_id IN (
                 SELECT s.id FROM schedules s
                 WHERE s.user_id IN (SELECT id FROM non_owner_users)
             )
             AND (b.guest_telegram_id IS NULL OR b.guest_telegram_id != $1)) AS bookings_total,
            (SELECT COUNT(*) FROM app_events) AS events_total,
            (SELECT COUNT(*) FROM admin_tasks) AS tasks_total
    """, owner_id)
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
