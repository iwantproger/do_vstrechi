"""Telegram InitData HMAC-SHA256 validation и admin session auth."""
import hmac
import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs

import asyncpg
import structlog
from fastapi import Request, HTTPException, Depends

from config import (
    BOT_TOKEN, INTERNAL_API_KEY,
    ADMIN_TELEGRAM_ID, ADMIN_TELEGRAM_IDS, ADMIN_SESSION_TTL_HOURS, ADMIN_IP_ALLOWLIST,
)
from database import db

log = structlog.get_logger()

# ─────────────────────────────────────────────────────────
# In-memory state (per-process)
# ─────────────────────────────────────────────────────────

_login_attempts: dict[str, list[float]] = {}
_session_checked: set[str] = set()


# ─────────────────────────────────────────────────────────
# Telegram Mini App auth (initData)
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
    internal_key = request.headers.get("X-Internal-Key")
    if internal_key and INTERNAL_API_KEY and hmac.compare_digest(internal_key, INTERNAL_API_KEY):
        tid = request.query_params.get("telegram_id")
        if tid:
            return {"id": int(tid)}
        raise HTTPException(status_code=401, detail="Missing telegram_id for internal call")

    init_data = request.headers.get("X-Init-Data")
    if not init_data:
        raise HTTPException(status_code=401, detail="Требуется авторизация через Telegram")

    user = validate_init_data(init_data, BOT_TOKEN)
    if not user:
        raise HTTPException(status_code=401, detail="Невалидная подпись Telegram")

    return user


async def get_optional_user(request: Request) -> dict | None:
    """Same as get_current_user but returns None instead of 401 (for public endpoints)."""
    internal_key = request.headers.get("X-Internal-Key")
    if internal_key and INTERNAL_API_KEY and hmac.compare_digest(internal_key, INTERNAL_API_KEY):
        tid = request.query_params.get("telegram_id")
        if tid:
            try:
                return {"id": int(tid)}
            except ValueError:
                return None
        return None

    init_data = request.headers.get("X-Init-Data")
    if not init_data:
        return None
    return validate_init_data(init_data, BOT_TOKEN)


# ─────────────────────────────────────────────────────────
# Admin authentication (Telegram Login Widget)
# ─────────────────────────────────────────────────────────

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
    if row["telegram_id"] not in ADMIN_TELEGRAM_IDS:
        return None
    return dict(row)


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


async def get_admin_or_internal(request: Request, conn=Depends(db)) -> dict:
    """Accept either admin cookie (web panel) or X-Internal-Key (bot).
    For internal key: telegram_id from query params must be in ADMIN_TELEGRAM_IDS.
    """
    internal_key = request.headers.get("X-Internal-Key")
    if internal_key and INTERNAL_API_KEY and hmac.compare_digest(internal_key, INTERNAL_API_KEY):
        tid_str = request.query_params.get("telegram_id")
        if tid_str:
            tid = int(tid_str)
            if tid in ADMIN_TELEGRAM_IDS:
                return {"telegram_id": tid, "via": "internal_key"}
        raise HTTPException(status_code=401, detail="Authentication failed")

    return await get_admin_user(request, conn)


async def log_admin_action(action: str, ip: str, details: dict | None, conn):
    """Insert into admin_audit_log."""
    await conn.execute(
        """
        INSERT INTO admin_audit_log (action, details, ip_address)
        VALUES ($1, $2::jsonb, $3::inet)
        """,
        action, json.dumps(details) if details else None, ip,
    )
