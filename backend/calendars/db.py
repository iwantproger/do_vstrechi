"""DB-функции для календарной интеграции (asyncpg, параметризованные запросы)."""

from datetime import datetime
from typing import Any

from utils import row_to_dict, rows_to_list


# ── Calendar Accounts ─────────────────────────────

async def get_user_calendar_accounts(conn, user_id: str) -> list[dict]:
    """Все аккаунты пользователя + вложенные calendar_connections."""
    accounts = rows_to_list(await conn.fetch(
        "SELECT * FROM calendar_accounts WHERE user_id = $1 ORDER BY created_at",
        user_id,
    ))
    for acc in accounts:
        acc["calendars"] = rows_to_list(await conn.fetch(
            "SELECT * FROM calendar_connections WHERE account_id = $1 ORDER BY calendar_name",
            acc["id"],
        ))
    return accounts


async def create_calendar_account(conn, user_id: str, data: dict) -> dict:
    """Создать запись calendar_account (INSERT ... RETURNING *)."""
    row = await conn.fetchrow(
        """
        INSERT INTO calendar_accounts
            (user_id, provider, provider_email,
             access_token_encrypted, refresh_token_encrypted, token_expires_at,
             caldav_url, caldav_username, caldav_password_encrypted, status)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        RETURNING *
        """,
        user_id,
        data.get("provider"),
        data.get("provider_email"),
        data.get("access_token_encrypted"),
        data.get("refresh_token_encrypted"),
        data.get("token_expires_at"),
        data.get("caldav_url"),
        data.get("caldav_username"),
        data.get("caldav_password_encrypted"),
        data.get("status", "active"),
    )
    return row_to_dict(row)


async def update_account_tokens(conn, account_id: str, tokens: dict) -> None:
    """Обновить access/refresh токены и expiry."""
    await conn.execute(
        """
        UPDATE calendar_accounts
        SET access_token_encrypted = $2,
            refresh_token_encrypted = COALESCE($3, refresh_token_encrypted),
            token_expires_at = $4,
            status = 'active',
            last_error = NULL
        WHERE id = $1
        """,
        account_id,
        tokens["access_token_encrypted"],
        tokens.get("refresh_token_encrypted"),
        tokens.get("token_expires_at"),
    )


async def update_account_status(
    conn, account_id: str, status: str, error: str | None = None
) -> None:
    """Обновить статус аккаунта (active/expired/revoked/error)."""
    await conn.execute(
        "UPDATE calendar_accounts SET status = $2, last_error = $3 WHERE id = $1",
        account_id, status, error,
    )


# ── Calendar Connections ──────────────────────────

async def get_calendar_connections(conn, account_id: str) -> list[dict]:
    """Все календари в аккаунте."""
    return rows_to_list(await conn.fetch(
        "SELECT * FROM calendar_connections WHERE account_id = $1 ORDER BY calendar_name",
        account_id,
    ))


async def upsert_calendar_connection(conn, account_id: str, data: dict) -> dict:
    """Создать или обновить calendar_connection (ON CONFLICT по account + ext id)."""
    row = await conn.fetchrow(
        """
        INSERT INTO calendar_connections
            (account_id, external_calendar_id, calendar_name, calendar_color)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (account_id, external_calendar_id)
            DO UPDATE SET calendar_name = EXCLUDED.calendar_name,
                          calendar_color = EXCLUDED.calendar_color
        RETURNING *
        """,
        account_id,
        data["external_calendar_id"],
        data["calendar_name"],
        data.get("calendar_color"),
    )
    return row_to_dict(row)


async def toggle_calendar_connection(
    conn, connection_id: str, fields: dict
) -> dict:
    """Переключить is_read_enabled / is_write_target."""
    sets, args = [], [connection_id]
    idx = 2
    for col in ("is_read_enabled", "is_write_target"):
        if col in fields and fields[col] is not None:
            sets.append(f"{col} = ${idx}")
            args.append(fields[col])
            idx += 1
    if not sets:
        row = await conn.fetchrow(
            "SELECT * FROM calendar_connections WHERE id = $1", connection_id
        )
        return row_to_dict(row)
    row = await conn.fetchrow(
        f"UPDATE calendar_connections SET {', '.join(sets)} WHERE id = $1 RETURNING *",
        *args,
    )
    return row_to_dict(row)


# ── Schedule Calendar Rules ───────────────────────

async def get_schedule_calendar_rules(conn, schedule_id: str) -> list[dict]:
    """Привязки календарей к расписанию."""
    return rows_to_list(await conn.fetch(
        """
        SELECT r.*, c.calendar_name, c.external_calendar_id, a.provider
        FROM schedule_calendar_rules r
        JOIN calendar_connections c ON c.id = r.connection_id
        JOIN calendar_accounts a ON a.id = c.account_id
        WHERE r.schedule_id = $1
        """,
        schedule_id,
    ))


async def set_schedule_calendar_rules(
    conn, schedule_id: str, rules: list[dict]
) -> None:
    """Пересоздать привязки календарей для расписания (delete + insert)."""
    await conn.execute(
        "DELETE FROM schedule_calendar_rules WHERE schedule_id = $1",
        schedule_id,
    )
    for r in rules:
        await conn.execute(
            """
            INSERT INTO schedule_calendar_rules
                (schedule_id, connection_id, use_for_blocking, use_for_writing)
            VALUES ($1, $2, $3, $4)
            """,
            schedule_id,
            r["connection_id"],
            r.get("use_for_blocking", True),
            r.get("use_for_writing", False),
        )


# ── External Busy Slots ──────────────────────────

async def get_external_busy_slots(
    conn, connection_ids: list[str], start: datetime, end: datetime
) -> list[dict]:
    """Busy-слоты из внешних календарей за период."""
    if not connection_ids:
        return []
    return rows_to_list(await conn.fetch(
        """
        SELECT * FROM external_busy_slots
        WHERE connection_id = ANY($1)
          AND end_time > $2
          AND start_time < $3
        ORDER BY start_time
        """,
        connection_ids, start, end,
    ))


async def upsert_external_busy_slots(
    conn, connection_id: str, events: list[dict]
) -> int:
    """Upsert busy-слотов (ON CONFLICT обновление). Возвращает кол-во."""
    count = 0
    for ev in events:
        await conn.execute(
            """
            INSERT INTO external_busy_slots
                (connection_id, external_event_id, summary,
                 start_time, end_time, is_all_day, etag, raw_data, fetched_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, NOW())
            ON CONFLICT (connection_id, external_event_id)
                DO UPDATE SET summary = EXCLUDED.summary,
                              start_time = EXCLUDED.start_time,
                              end_time = EXCLUDED.end_time,
                              is_all_day = EXCLUDED.is_all_day,
                              etag = EXCLUDED.etag,
                              raw_data = EXCLUDED.raw_data,
                              fetched_at = NOW()
            """,
            connection_id,
            ev["external_id"],
            ev.get("summary"),
            ev["start_time"],
            ev["end_time"],
            ev.get("is_all_day", False),
            ev.get("etag"),
            ev.get("raw_data"),
        )
        count += 1
    return count


async def delete_stale_busy_slots(
    conn, connection_id: str, valid_external_ids: set[str]
) -> int:
    """Удалить слоты, которых больше нет у провайдера. Возвращает кол-во удалённых."""
    if not valid_external_ids:
        result = await conn.execute(
            "DELETE FROM external_busy_slots WHERE connection_id = $1",
            connection_id,
        )
        return int(result.split()[-1])
    result = await conn.execute(
        """
        DELETE FROM external_busy_slots
        WHERE connection_id = $1
          AND external_event_id != ALL($2)
        """,
        connection_id, list(valid_external_ids),
    )
    return int(result.split()[-1])


# ── Event Mapping ─────────────────────────────────

async def create_event_mapping(
    conn,
    booking_id: str,
    connection_id: str,
    external_id: str,
    url: str | None = None,
    etag: str | None = None,
) -> dict:
    """Связка бронирование → внешнее событие."""
    row = await conn.fetchrow(
        """
        INSERT INTO event_mapping
            (booking_id, connection_id, external_event_id,
             external_event_url, etag, sync_status)
        VALUES ($1, $2, $3, $4, $5, 'synced')
        RETURNING *
        """,
        booking_id, connection_id, external_id, url, etag,
    )
    return row_to_dict(row)


async def get_event_mappings_for_booking(conn, booking_id: str) -> list[dict]:
    """Все внешние события, привязанные к бронированию."""
    return rows_to_list(await conn.fetch(
        """
        SELECT em.*, cc.calendar_name, ca.provider
        FROM event_mapping em
        JOIN calendar_connections cc ON cc.id = em.connection_id
        JOIN calendar_accounts ca ON ca.id = cc.account_id
        WHERE em.booking_id = $1
        """,
        booking_id,
    ))


async def update_event_mapping_status(
    conn, mapping_id: str, status: str, error: str | None = None
) -> None:
    """Обновить статус маппинга (synced/pending/error/deleted)."""
    await conn.execute(
        """
        UPDATE event_mapping
        SET sync_status = $2, last_error = $3, last_synced_at = NOW()
        WHERE id = $1
        """,
        mapping_id, status, error,
    )


# ── Sync Log ──────────────────────────────────────

async def log_sync(
    conn,
    account_id: str | None,
    connection_id: str | None,
    action: str,
    status: str,
    details: Any = None,
    error: str | None = None,
) -> None:
    """Записать событие синхронизации в sync_log."""
    import json
    await conn.execute(
        """
        INSERT INTO sync_log
            (account_id, connection_id, action, status, details, error_message)
        VALUES ($1, $2, $3, $4, $5::jsonb, $6)
        """,
        account_id, connection_id, action, status,
        json.dumps(details) if details else None,
        error,
    )
