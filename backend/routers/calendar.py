"""Роуты календарной интеграции — OAuth, accounts, connections, sync, webhooks."""

import asyncio
from datetime import datetime, timedelta, timezone

import asyncpg
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse

from config import MINI_APP_URL
from database import db, get_pool
from auth import get_current_user
from calendars.encryption import encrypt_token
from calendars.schemas import (
    CalendarConnectionToggle,
    ScheduleCalendarConfig,
)
from calendars.registry import get_provider
from calendars.providers.google_oauth import (
    sign_state,
    verify_state,
    get_google_auth_url,
    exchange_google_code,
    get_google_user_email,
)
import calendars.db as cal_db

log = structlog.get_logger()
router = APIRouter(prefix="/api/calendar", tags=["calendar"])


# ── Google OAuth ──────────────────────────────────

@router.get("/google/auth")
async def google_auth_redirect(auth_user: dict = Depends(get_current_user)):
    """Начать OAuth flow — redirect на Google consent screen."""
    state = sign_state(auth_user["id"])
    url = get_google_auth_url(state)
    return RedirectResponse(url=url, status_code=302)


@router.get("/google/callback")
async def google_callback(
    code: str = Query(None),
    state: str = Query(""),
    error: str = Query(None),
    conn: asyncpg.Connection = Depends(db),
):
    """OAuth callback от Google (без auth — redirect от Google)."""
    redirect_base = MINI_APP_URL or "/"

    # Пользователь отказал
    if error:
        log.info("google_oauth_denied", error=error)
        return RedirectResponse(
            url=f"{redirect_base}?calendar_error=cancelled", status_code=302
        )

    if not code:
        return RedirectResponse(
            url=f"{redirect_base}?calendar_error=no_code", status_code=302
        )

    # Проверка state
    try:
        telegram_id = verify_state(state)
    except ValueError as e:
        log.warning("google_oauth_invalid_state", error=str(e))
        return RedirectResponse(
            url=f"{redirect_base}?calendar_error=invalid_state", status_code=302
        )

    # Найти пользователя
    user = await conn.fetchrow(
        "SELECT id FROM users WHERE telegram_id = $1", telegram_id
    )
    if not user:
        return RedirectResponse(
            url=f"{redirect_base}?calendar_error=user_not_found", status_code=302
        )
    user_id = user["id"]

    # Обменять code на токены
    try:
        tokens = await exchange_google_code(code)
    except ValueError as e:
        log.error("google_token_exchange_error", error=str(e))
        return RedirectResponse(
            url=f"{redirect_base}?calendar_error=token_exchange", status_code=302
        )

    # Получить email
    try:
        email = await get_google_user_email(tokens["access_token"])
    except ValueError:
        email = None

    # Зашифровать токены
    access_enc = encrypt_token(tokens["access_token"])
    refresh_enc = encrypt_token(tokens["refresh_token"]) if tokens.get("refresh_token") else None
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=tokens.get("expires_in", 3600))

    # Сохранить аккаунт (или обновить токены если уже подключён)
    existing = await conn.fetchrow(
        """
        SELECT id FROM calendar_accounts
        WHERE user_id = $1 AND provider = 'google' AND provider_email = $2
        """,
        user_id, email,
    )

    if existing:
        account_id = existing["id"]
        await cal_db.update_account_tokens(conn, str(account_id), {
            "access_token_encrypted": access_enc,
            "refresh_token_encrypted": refresh_enc,
            "token_expires_at": expires_at,
        })
        log.info("google_account_reconnected", user_id=str(user_id), email=email)
    else:
        account = await cal_db.create_calendar_account(conn, user_id, {
            "provider": "google",
            "provider_email": email,
            "access_token_encrypted": access_enc,
            "refresh_token_encrypted": refresh_enc,
            "token_expires_at": expires_at,
        })
        account_id = account["id"]
        log.info("google_account_created", user_id=str(user_id), email=email)

    # Получить список календарей и сохранить
    try:
        account_data = {
            "access_token_encrypted": access_enc,
            "refresh_token_encrypted": refresh_enc,
        }
        provider = get_provider("google")
        calendars_list = await provider.list_calendars(account_data)
        for cal in calendars_list:
            await cal_db.upsert_calendar_connection(conn, str(account_id), cal)
        log.info("google_calendars_fetched", count=len(calendars_list))
    except Exception as e:
        log.warning("google_calendars_fetch_error", error=str(e))
        # Аккаунт создан, календари подтянутся при следующей синхронизации

    await cal_db.log_sync(
        conn, str(account_id), None, "oauth_connect", "success",
        {"email": email, "calendars": len(calendars_list) if 'calendars_list' in dir() else 0},
    )

    return RedirectResponse(
        url=f"{redirect_base}?calendar_connected=google", status_code=302
    )


# ── Accounts ──────────────────────────────────────

@router.get("/accounts")
async def list_accounts(
    auth_user: dict = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(db),
):
    """Список подключённых календарных аккаунтов с календарями."""
    user = await conn.fetchrow(
        "SELECT id FROM users WHERE telegram_id = $1", auth_user["id"]
    )
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    accounts = await cal_db.get_user_calendar_accounts(conn, user["id"])
    # Убрать зашифрованные токены из ответа
    for acc in accounts:
        acc.pop("access_token_encrypted", None)
        acc.pop("refresh_token_encrypted", None)
        acc.pop("caldav_password_encrypted", None)
    return accounts


@router.delete("/accounts/{account_id}")
async def delete_account(
    account_id: str,
    auth_user: dict = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(db),
):
    """Отключить календарный аккаунт (CASCADE удалит всё связанное)."""
    user = await conn.fetchrow(
        "SELECT id FROM users WHERE telegram_id = $1", auth_user["id"]
    )
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    # Проверка владения
    account = await conn.fetchrow(
        "SELECT id FROM calendar_accounts WHERE id = $1 AND user_id = $2",
        account_id, user["id"],
    )
    if not account:
        raise HTTPException(status_code=404, detail="Аккаунт не найден")

    await conn.execute("DELETE FROM calendar_accounts WHERE id = $1", account_id)
    log.info("calendar_account_deleted", account_id=account_id)
    return {"ok": True}


# ── Connections (toggle read/write) ────────────────

@router.post("/connections/{connection_id}/toggle")
async def toggle_connection(
    connection_id: str,
    body: CalendarConnectionToggle,
    auth_user: dict = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(db),
):
    """Переключить чтение/запись для календаря."""
    user = await conn.fetchrow(
        "SELECT id FROM users WHERE telegram_id = $1", auth_user["id"]
    )
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    # Проверка владения: connection → account → user
    row = await conn.fetchrow(
        """
        SELECT cc.id, cc.account_id
        FROM calendar_connections cc
        JOIN calendar_accounts ca ON ca.id = cc.account_id
        WHERE cc.id = $1 AND ca.user_id = $2
        """,
        connection_id, user["id"],
    )
    if not row:
        raise HTTPException(status_code=404, detail="Календарь не найден")

    # Если включается write_target — сбросить у остальных в том же аккаунте
    if body.is_write_target is True:
        await conn.execute(
            """
            UPDATE calendar_connections
            SET is_write_target = FALSE
            WHERE account_id = $1 AND id != $2
            """,
            row["account_id"], connection_id,
        )

    updated = await cal_db.toggle_calendar_connection(
        conn, connection_id, body.model_dump(exclude_none=True)
    )
    return updated


# ── Schedule Calendar Config ──────────────────────

@router.get("/schedules/{schedule_id}/calendar-config")
async def get_schedule_calendar_config(
    schedule_id: str,
    auth_user: dict = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(db),
):
    """Привязки календарей к расписанию."""
    await _verify_schedule_ownership(conn, schedule_id, auth_user["id"])
    rules = await cal_db.get_schedule_calendar_rules(conn, schedule_id)
    return {"rules": rules}


@router.put("/schedules/{schedule_id}/calendar-config")
async def set_schedule_calendar_config(
    schedule_id: str,
    body: ScheduleCalendarConfig,
    auth_user: dict = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(db),
):
    """Заменить привязки календарей для расписания."""
    await _verify_schedule_ownership(conn, schedule_id, auth_user["id"])
    rules_data = [r.model_dump() for r in body.rules]
    await cal_db.set_schedule_calendar_rules(conn, schedule_id, rules_data)
    rules = await cal_db.get_schedule_calendar_rules(conn, schedule_id)
    return {"rules": rules}


# ── Manual Sync ───────────────────────────────────

@router.post("/accounts/{account_id}/sync")
async def trigger_sync(
    account_id: str,
    request: Request,
    auth_user: dict = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(db),
):
    """Принудительная синхронизация аккаунта (background)."""
    user = await conn.fetchrow(
        "SELECT id FROM users WHERE telegram_id = $1", auth_user["id"]
    )
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    account = await conn.fetchrow(
        "SELECT id FROM calendar_accounts WHERE id = $1 AND user_id = $2",
        account_id, user["id"],
    )
    if not account:
        raise HTTPException(status_code=404, detail="Аккаунт не найден")

    sync_engine = request.app.state.sync_engine
    asyncio.create_task(sync_engine.sync_account(str(account_id)))
    return {"ok": True, "message": "Синхронизация запущена"}


# ── Google Webhook ────────────────────────────────

@router.post("/webhook/google")
async def google_webhook(request: Request):
    """Webhook от Google Calendar push notifications (всегда 200)."""
    channel_id = request.headers.get("X-Goog-Channel-Id", "")
    resource_id = request.headers.get("X-Goog-Resource-Id", "")
    resource_state = request.headers.get("X-Goog-Resource-State", "")

    log.info("google_webhook_received",
             channel_id=channel_id, resource_state=resource_state)

    # Initial sync notification — just acknowledge
    if resource_state == "sync":
        return {"ok": True}

    if not channel_id:
        return {"ok": True}

    # Найти connection по webhook_channel_id
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id FROM calendar_connections WHERE webhook_channel_id = $1",
            channel_id,
        )

    if not row:
        log.debug("google_webhook_stale", channel_id=channel_id)
        return {"ok": True}

    # Запустить sync в background
    sync_engine = request.app.state.sync_engine
    asyncio.create_task(sync_engine.sync_single_calendar(str(row["id"])))
    return {"ok": True}


# ── Helpers ───────────────────────────────────────

async def _verify_schedule_ownership(conn, schedule_id: str, telegram_id: int):
    """Проверить что расписание принадлежит пользователю."""
    row = await conn.fetchrow(
        """
        SELECT s.id FROM schedules s
        JOIN users u ON u.id = s.user_id
        WHERE s.id = $1 AND u.telegram_id = $2
        """,
        schedule_id, telegram_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Расписание не найдено")
