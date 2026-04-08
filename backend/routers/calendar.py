"""Роуты календарной интеграции — OAuth, accounts, connections, sync, webhooks."""

import asyncio
from datetime import datetime, timedelta, timezone

import asyncpg
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from config import BOT_USERNAME, INTERNAL_API_KEY, MINI_APP_URL, CALENDAR_WEBHOOK_URL
from database import db, get_pool
from auth import get_current_user
from calendars.encryption import encrypt_token
from calendars.schemas import (
    CalendarConnectionToggle,
    ScheduleCalendarConfig,
    CalDAVConnectRequest,
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


def _oauth_page(success: bool, error_key: str = "") -> str:
    """Вернуть HTML-страницу после OAuth callback."""
    tg_url = f"https://t.me/{BOT_USERNAME}?start=calendar_connected" if BOT_USERNAME else ""

    if success:
        icon = "✅"
        title = "Google Calendar подключён!"
        subtitle = "Возвращайтесь в Telegram — приложение уже обновилось."
        btn_text = "Вернуться в Telegram"
        js_redirect = f"window.location.href = '{tg_url}';" if tg_url else ""
    else:
        labels = {
            "cancelled":     "Вы отменили подключение Google Calendar.",
            "no_code":       "Ошибка: не получен код авторизации от Google.",
            "invalid_state": "Ошибка безопасности: недействительный параметр state.",
            "user_not_found":"Ошибка: пользователь не найден. Попробуйте ещё раз.",
            "token_exchange":"Ошибка обмена токенов с Google. Попробуйте позже.",
        }
        icon = "❌"
        title = "Не удалось подключить календарь"
        subtitle = labels.get(error_key, "Произошла ошибка. Попробуйте ещё раз.")
        btn_text = "Вернуться в Telegram"
        js_redirect = f"window.location.href = '{tg_url}';" if tg_url else ""

    auto_redirect_script = f"""
    <script>
      setTimeout(function() {{ {js_redirect} }}, 1500);
    </script>""" if js_redirect else ""

    tg_btn = f'<a href="{tg_url}" class="btn">{btn_text}</a>' if tg_url else ""

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      min-height: 100dvh;
      display: flex; align-items: center; justify-content: center;
      background: #17212b;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      color: #e8edf2;
      padding: 24px;
    }}
    .card {{
      background: #232e3c;
      border-radius: 16px;
      padding: 40px 32px;
      text-align: center;
      max-width: 360px;
      width: 100%;
      box-shadow: 0 4px 24px rgba(0,0,0,.35);
    }}
    .icon {{ font-size: 48px; margin-bottom: 16px; }}
    h1 {{ font-size: 20px; font-weight: 600; margin-bottom: 8px; }}
    p {{ font-size: 14px; color: #93a3b5; line-height: 1.5; margin-bottom: 28px; }}
    .btn {{
      display: inline-block;
      background: #2ca5e0;
      color: #fff;
      text-decoration: none;
      padding: 12px 28px;
      border-radius: 10px;
      font-size: 15px;
      font-weight: 500;
      transition: opacity .15s;
    }}
    .btn:hover {{ opacity: .85; }}
    .hint {{ margin-top: 16px; font-size: 12px; color: #637080; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">{icon}</div>
    <h1>{title}</h1>
    <p>{subtitle}</p>
    {tg_btn}
    {"<p class='hint'>Перенаправляем автоматически…</p>" if js_redirect else ""}
  </div>
  {auto_redirect_script}
</body>
</html>"""


# ── Google OAuth ──────────────────────────────────

@router.get("/google/auth-url")
async def google_auth_url(auth_user: dict = Depends(get_current_user)):
    """Вернуть Google OAuth URL с подписанным state.

    Frontend получает URL через API (с initData), затем открывает его
    через tg.openLink() во внешнем браузере. Браузер идёт напрямую на
    Google — наш backend в этом шаге не участвует.
    """
    state = sign_state(auth_user["id"])
    url = get_google_auth_url(state)
    return {"url": url}


@router.get("/google/callback")
async def google_callback(
    code: str = Query(None),
    state: str = Query(""),
    error: str = Query(None),
    conn: asyncpg.Connection = Depends(db),
):
    """OAuth callback от Google (без auth — redirect от Google)."""
    # Пользователь отказал
    if error:
        log.info("google_oauth_denied", error=error)
        return HTMLResponse(_oauth_page(success=False, error_key="cancelled"))

    if not code:
        return HTMLResponse(_oauth_page(success=False, error_key="no_code"))

    # Проверка state
    try:
        telegram_id = verify_state(state)
    except ValueError as e:
        log.warning("google_oauth_invalid_state", error=str(e))
        return HTMLResponse(_oauth_page(success=False, error_key="invalid_state"))

    # Найти пользователя
    user = await conn.fetchrow(
        "SELECT id FROM users WHERE telegram_id = $1", telegram_id
    )
    if not user:
        return HTMLResponse(_oauth_page(success=False, error_key="user_not_found"))
    user_id = user["id"]

    # Обменять code на токены
    try:
        tokens = await exchange_google_code(code)
    except ValueError as e:
        log.error("google_token_exchange_error", error=str(e))
        return HTMLResponse(_oauth_page(success=False, error_key="token_exchange"))

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
    calendars_list: list = []
    account_data_for_cals = {
        "access_token_encrypted": access_enc,
        "refresh_token_encrypted": refresh_enc,
    }
    try:
        provider = get_provider("google")
        calendars_list = await provider.list_calendars(account_data_for_cals)
        for cal in calendars_list:
            await cal_db.upsert_calendar_connection(conn, str(account_id), cal)
        log.info("google_calendars_fetched", count=len(calendars_list))
    except Exception as e:
        log.warning("google_calendars_fetch_error", error=str(e))
        # Аккаунт создан, календари подтянутся при следующей синхронизации

    await cal_db.log_sync(
        conn, str(account_id), None, "oauth_connect", "success",
        {"email": email, "calendars": len(calendars_list)},
    )

    # Подписаться на webhook push-уведомления для каждого read-enabled календаря
    asyncio.create_task(_subscribe_account_webhooks(
        str(account_id), account_data_for_cals,
    ))

    return HTMLResponse(_oauth_page(success=True))


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
        "SELECT * FROM calendar_accounts WHERE id = $1 AND user_id = $2",
        account_id, user["id"],
    )
    if not account:
        raise HTTPException(status_code=404, detail="Аккаунт не найден")

    # Отписаться от webhook-подписок (graceful — не блокирует удаление)
    try:
        from calendars.providers.google_webhooks import unsubscribe as webhook_unsubscribe
        connections_with_hooks = await cal_db.get_account_connections_with_webhooks(conn, account_id)
        account_data = dict(account)
        for c in connections_with_hooks:
            channel_id = c.get("webhook_channel_id")
            resource_id = c.get("webhook_resource_id")
            if channel_id and resource_id:
                try:
                    await webhook_unsubscribe(account_data, channel_id, resource_id)
                    log.info("webhook_unsubscribed_on_delete",
                             connection_id=str(c["id"]), channel_id=channel_id)
                except Exception as e:
                    log.warning("webhook_unsubscribe_failed_on_delete",
                                connection_id=str(c["id"]), error=str(e))
    except Exception as e:
        log.warning("webhook_cleanup_error", account_id=account_id, error=str(e))

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
    channel_token = request.headers.get("X-Goog-Channel-Token", "")

    # Проверить webhook token если передан (опционально)
    if channel_token and INTERNAL_API_KEY and channel_token != INTERNAL_API_KEY:
        log.warning("google_webhook_invalid_token", channel_id=channel_id)
        return {"ok": True}  # Всегда 200 — не сообщать Google об отказе

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
        if row:
            await cal_db.log_sync(
                conn, None, str(row["id"]),
                "webhook_received", "success",
                {"resource_state": resource_state, "channel_id": channel_id},
            )

    if not row:
        log.info("google_webhook_stale", channel_id=channel_id)
        return {"ok": True}

    # Запустить incremental sync в background
    sync_engine = request.app.state.sync_engine
    asyncio.create_task(sync_engine.sync_single_calendar(str(row["id"])))
    return {"ok": True}


# ── CalDAV Connect ────────────────────────────────

@router.post("/caldav/connect")
async def caldav_connect(
    body: CalDAVConnectRequest,
    auth_user: dict = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(db),
):
    """Подключить CalDAV-провайдер (Yandex или Apple) через email + app-specific password.

    Шаги:
    1. Проверка credentials через list_calendars() (fail-fast, не сохраняет при ошибке)
    2. Создание или обновление calendar_account
    3. Upsert всех найденных calendar_connections
    """
    from calendars.providers.caldav_adapter import CalDAVAuthError

    try:
        provider = get_provider(body.provider)
    except KeyError:
        raise HTTPException(400, detail=f"Провайдер '{body.provider}' не поддерживается")

    user = await conn.fetchrow(
        "SELECT id FROM users WHERE telegram_id = $1", auth_user["id"]
    )
    if not user:
        raise HTTPException(404, detail="Пользователь не найден")

    email = body.email.strip()
    password_enc = encrypt_token(body.password)

    # Проверка credentials: list_calendars() без сохранения в БД
    temp_account = {
        "caldav_url": None,       # использует default_url провайдера
        "caldav_username": email,
        "caldav_password_encrypted": password_enc,
    }
    try:
        calendars_list = await provider.list_calendars(temp_account)
    except CalDAVAuthError:
        raise HTTPException(400, detail="Неверный email или пароль")
    except Exception as e:
        import traceback as _tb
        log.error(
            "caldav_connect_failed",
            provider=body.provider,
            error=str(e),
            exc_type=type(e).__name__,
            traceback=_tb.format_exc(),
        )
        raise HTTPException(
            502,
            detail="Не удалось подключиться к календарю. Проверьте email и пароль приложения.",
        )

    # Проверить, не подключён ли уже такой аккаунт
    existing = await conn.fetchrow(
        """
        SELECT id FROM calendar_accounts
        WHERE user_id = $1 AND provider = $2 AND provider_email = $3
        """,
        user["id"], body.provider, email,
    )

    if existing:
        account_id = str(existing["id"])
        await conn.execute(
            """
            UPDATE calendar_accounts
            SET caldav_password_encrypted = $2,
                caldav_username = $3,
                status = 'active',
                last_error = NULL
            WHERE id = $1
            """,
            existing["id"], password_enc, email,
        )
        log.info("caldav_account_reconnected",
                 user_id=str(user["id"]), provider=body.provider)
    else:
        account = await cal_db.create_calendar_account(conn, str(user["id"]), {
            "provider": body.provider,
            "provider_email": email,
            "caldav_username": email,
            "caldav_password_encrypted": password_enc,
            "status": "active",
        })
        account_id = str(account["id"])
        log.info("caldav_account_created",
                 user_id=str(user["id"]), provider=body.provider,
                 calendars_count=len(calendars_list))

    # Сохранить / обновить calendar_connections
    for cal_data in calendars_list:
        await cal_db.upsert_calendar_connection(conn, account_id, cal_data)

    await cal_db.log_sync(
        conn, account_id, None, "caldav_connect", "success",
        {"provider": body.provider, "email": email, "calendars": len(calendars_list)},
    )

    # Вернуть полные данные нового аккаунта
    accounts = await cal_db.get_user_calendar_accounts(conn, str(user["id"]))
    new_account = next((a for a in accounts if str(a["id"]) == account_id), None)
    if new_account:
        new_account.pop("access_token_encrypted", None)
        new_account.pop("refresh_token_encrypted", None)
        new_account.pop("caldav_password_encrypted", None)
        return new_account
    return {"ok": True}


# ── Helpers ───────────────────────────────────────

async def _subscribe_account_webhooks(account_id: str, account_data: dict):
    """
    Подписаться на push-уведомления для всех read-enabled календарей аккаунта.
    Запускается как fire-and-forget задача после OAuth connect.
    """
    from calendars.providers.google_webhooks import subscribe_to_calendar
    from database import get_pool

    webhook_url = CALENDAR_WEBHOOK_URL or (MINI_APP_URL + "/api/calendar/webhook/google")
    if not webhook_url or webhook_url == "/api/calendar/webhook/google":
        log.warning("webhook_subscribe_skipped_no_url", account_id=account_id)
        return

    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            connections = await cal_db.get_calendar_connections(conn, account_id)
            for c in connections:
                if not c.get("is_read_enabled", True):
                    continue
                connection_id = str(c["id"])
                try:
                    result = await subscribe_to_calendar(
                        account_data,
                        c["external_calendar_id"],
                        webhook_url,
                    )
                    if result:
                        await cal_db.update_connection_webhook(
                            conn, connection_id,
                            result["channel_id"], result["resource_id"], result["expires_at"],
                        )
                        log.info("webhook_subscribed_on_connect",
                                 connection_id=connection_id,
                                 channel_id=result["channel_id"])
                except Exception as e:
                    log.warning("webhook_subscribe_per_connection_error",
                                connection_id=connection_id, error=str(e))
    except Exception as e:
        log.warning("subscribe_account_webhooks_error", account_id=account_id, error=str(e))


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
