"""Sync Engine — фоновая синхронизация с внешними календарями."""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import asyncpg
import structlog

from calendars.registry import get_provider
from calendars.encryption import encrypt_token
import calendars.db as cal_db

log = structlog.get_logger()

SYNC_INTERVAL = 600  # 10 минут
SYNC_WINDOW_PAST = timedelta(days=1)
SYNC_WINDOW_FUTURE = timedelta(days=30)


class CalendarSyncEngine:
    """Фоновый polling worker для двусторонней синхронизации календарей."""

    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self):
        """Запуск фонового sync loop. Вызывается из lifespan()."""
        self._running = True
        self._task = asyncio.create_task(self._loop())
        log.info("sync_engine_started", interval_sec=SYNC_INTERVAL)

    async def stop(self):
        """Graceful shutdown."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        log.info("sync_engine_stopped")

    async def _loop(self):
        """Основной цикл — sync all accounts + renew webhooks каждые SYNC_INTERVAL секунд."""
        while self._running:
            try:
                await self.sync_all_accounts()
            except Exception as e:
                log.error("sync_loop_error", error=str(e))
            try:
                await self.renew_expiring_webhooks()
            except Exception as e:
                log.error("webhook_renewal_loop_error", error=str(e))
            await asyncio.sleep(SYNC_INTERVAL)

    async def sync_all_accounts(self):
        """Синхронизировать все активные аккаунты."""
        async with self._pool.acquire() as conn:
            accounts = await conn.fetch(
                "SELECT id FROM calendar_accounts WHERE status = 'active'"
            )
        for acc in accounts:
            try:
                await self.sync_account(str(acc["id"]))
            except Exception as e:
                log.warning("sync_account_skipped", account_id=str(acc["id"]), error=str(e))

    async def sync_account(self, account_id: str):
        """Синхронизировать один аккаунт: refresh token → sync каждый read-enabled календарь."""
        async with self._pool.acquire() as conn:
            account = await conn.fetchrow(
                "SELECT * FROM calendar_accounts WHERE id = $1 AND status = 'active'",
                account_id,
            )
            if not account:
                return

            account_data = dict(account)
            try:
                provider = get_provider(account_data["provider"])
            except KeyError:
                log.warning("sync_unknown_provider", provider=account_data["provider"])
                return

            # Обновить токен если нужно
            try:
                refreshed = await provider.refresh_token_if_needed(account_data)
                if refreshed:
                    await cal_db.update_account_tokens(conn, account_id, {
                        "access_token_encrypted": encrypt_token(refreshed["access_token"]),
                        "refresh_token_encrypted": (
                            encrypt_token(refreshed["refresh_token"])
                            if refreshed.get("refresh_token")
                            else None
                        ),
                        "token_expires_at": refreshed.get("expires_at"),
                    })
                    account_data = dict(await conn.fetchrow(
                        "SELECT * FROM calendar_accounts WHERE id = $1", account_id,
                    ))
                    await cal_db.log_sync(
                        conn, account_id, None, "token_refresh", "success",
                    )
            except Exception as e:
                log.warning("token_refresh_failed", account_id=account_id, error=str(e))
                await cal_db.update_account_status(conn, account_id, "expired", str(e))
                await cal_db.log_sync(
                    conn, account_id, None, "token_refresh", "error", error=str(e),
                )
                return

            connections = await cal_db.get_calendar_connections(conn, account_id)
            now = datetime.now(timezone.utc)
            time_min = now - SYNC_WINDOW_PAST
            time_max = now + SYNC_WINDOW_FUTURE

            for c in connections:
                if not c["is_read_enabled"]:
                    continue
                await self._sync_calendar(
                    conn, provider, account_id, account_data, c, time_min, time_max,
                )

            await conn.execute(
                "UPDATE calendar_accounts SET last_sync_at = NOW() WHERE id = $1",
                account_id,
            )

    async def _sync_calendar(
        self, conn, provider, account_id, account_data, connection, time_min, time_max,
    ):
        """Синхронизировать один календарь: read_events → upsert/delete busy slots.

        - Полная синхронизация (без sync_token): upsert всех + удалить stale
        - Инкрементальная (с sync_token): upsert изменённых + удалить cancelled
        - 410 Gone в google.py → автоматически делает full resync и возвращает is_full_sync=True
        """
        connection_id = str(connection["id"])
        was_incremental = bool(connection.get("sync_token"))
        try:
            active_events, cancelled_ids, new_token, is_full_sync = await provider.read_events(
                account_data,
                connection["external_calendar_id"],
                time_min,
                time_max,
                sync_token=connection.get("sync_token"),
            )

            # Если sync_token был, но провайдер сделал full resync (410) — сброс токена в DB
            if was_incremental and is_full_sync:
                await conn.execute(
                    "UPDATE calendar_connections SET sync_token = NULL WHERE id = $1",
                    connection["id"],
                )

            events_dicts = [e.model_dump() for e in active_events]
            if events_dicts:
                await cal_db.upsert_external_busy_slots(conn, connection_id, events_dicts)

            if is_full_sync:
                # Полная синхронизация — удалить слоты которых нет в ответе
                valid_ids = {e.external_id for e in active_events}
                await cal_db.delete_stale_busy_slots(conn, connection_id, valid_ids)
            elif cancelled_ids:
                # Инкрементальная — удалить только помеченные cancelled
                await conn.execute(
                    """
                    DELETE FROM external_busy_slots
                    WHERE connection_id = $1
                      AND external_event_id = ANY($2)
                    """,
                    connection["id"], cancelled_ids,
                )

            if new_token:
                await conn.execute(
                    "UPDATE calendar_connections SET sync_token = $2, last_sync_at = NOW() WHERE id = $1",
                    connection["id"], new_token,
                )
            else:
                await conn.execute(
                    "UPDATE calendar_connections SET last_sync_at = NOW() WHERE id = $1",
                    connection["id"],
                )

            await cal_db.log_sync(
                conn, account_id, connection_id,
                "fetch_events", "success",
                {
                    "events_count": len(active_events),
                    "cancelled_count": len(cancelled_ids),
                    "incremental": not is_full_sync,
                },
            )
        except Exception as e:
            log.warning("sync_calendar_error", connection_id=connection_id, error=str(e))
            await cal_db.log_sync(
                conn, account_id, connection_id,
                "fetch_events", "error", error=str(e),
            )

    async def sync_single_calendar(self, connection_id: str):
        """Синхронизировать один календарь по ID (вызывается из webhook handler)."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT cc.*, ca.id AS cal_account_id, ca.provider, ca.status AS account_status,
                       ca.access_token_encrypted, ca.refresh_token_encrypted,
                       ca.token_expires_at
                FROM calendar_connections cc
                JOIN calendar_accounts ca ON ca.id = cc.account_id
                WHERE cc.id = $1
                """,
                connection_id,
            )
            if not row or row["account_status"] != "active":
                return

            account_id = str(row["cal_account_id"])
            account_data = dict(row)
            try:
                provider = get_provider(row["provider"])
            except KeyError:
                return

            now = datetime.now(timezone.utc)
            await self._sync_calendar(
                conn, provider, account_id, account_data, dict(row),
                now - SYNC_WINDOW_PAST, now + SYNC_WINDOW_FUTURE,
            )

    # ── Webhook Renewal ──────────────────────────────

    async def renew_expiring_webhooks(self):
        """Обновить webhook-подписки, истекающие в ближайшие 24 часа."""
        async with self._pool.acquire() as conn:
            expiring = await cal_db.get_connections_with_expiring_webhooks(conn)

        if not expiring:
            return

        log.info("webhook_renewal_start", count=len(expiring))
        for row in expiring:
            try:
                await self._renew_webhook(dict(row))
            except Exception as e:
                log.warning(
                    "webhook_renew_failed",
                    connection_id=str(row["id"]),
                    error=str(e),
                )

    async def _renew_webhook(self, connection: dict):
        """Отписаться от старой подписки и создать новую."""
        from calendars.providers.google_webhooks import subscribe_to_calendar, unsubscribe
        from config import MINI_APP_URL, CALENDAR_WEBHOOK_URL

        connection_id = str(connection["id"])

        # Отписаться от старой
        old_channel_id = connection.get("webhook_channel_id")
        old_resource_id = connection.get("webhook_resource_id")
        if old_channel_id and old_resource_id:
            try:
                await unsubscribe(connection, old_channel_id, old_resource_id)
            except Exception as e:
                log.warning("webhook_old_unsubscribe_failed",
                            connection_id=connection_id, error=str(e))

        # Создать новую подписку
        webhook_url = CALENDAR_WEBHOOK_URL or (MINI_APP_URL + "/api/calendar/webhook/google")
        new_channel_id = str(uuid.uuid4())
        result = await subscribe_to_calendar(
            connection,
            connection["external_calendar_id"],
            webhook_url,
            channel_id=new_channel_id,
        )

        async with self._pool.acquire() as conn:
            if result:
                await cal_db.update_connection_webhook(
                    conn, connection_id,
                    result["channel_id"], result["resource_id"], result["expires_at"],
                )
                log.info("webhook_renewed",
                         connection_id=connection_id,
                         new_channel_id=result["channel_id"])
            else:
                # Подписка невозможна (shared calendar) — очистить старые данные
                await cal_db.clear_connection_webhook(conn, connection_id)
                log.info("webhook_renewal_skipped_unsupported",
                         connection_id=connection_id)


# ── Standalone fire-and-forget helpers ──────────────

async def write_booking_to_calendars(
    pool: asyncpg.Pool,
    booking_id: str,
    schedule_id: str,
    guest_name: str,
    scheduled_time: datetime,
    duration_min: int,
    schedule_title: str,
    meeting_link: str | None = None,
):
    """Записать бронирование во все write-target календари расписания (fire-and-forget)."""
    try:
        async with pool.acquire() as conn:
            rules = await cal_db.get_schedule_calendar_rules(conn, schedule_id)
            write_rules = [r for r in rules if r.get("use_for_writing")]

            # Zero-config: если правил нет — искать все write-target connections организатора
            if not write_rules:
                organizer = await conn.fetchrow(
                    "SELECT user_id FROM schedules WHERE id = $1", schedule_id
                )
                if not organizer:
                    return
                write_conns = await conn.fetch(
                    """
                    SELECT cc.id FROM calendar_connections cc
                    JOIN calendar_accounts ca ON ca.id = cc.account_id
                    WHERE ca.user_id = $1
                      AND ca.status = 'active'
                      AND cc.is_write_target = TRUE
                    """,
                    organizer["user_id"],
                )
                # Fallback: если и write_target нет — берём первый read-enabled
                if not write_conns:
                    write_conns = await conn.fetch(
                        """
                        SELECT cc.id FROM calendar_connections cc
                        JOIN calendar_accounts ca ON ca.id = cc.account_id
                        WHERE ca.user_id = $1
                          AND ca.status = 'active'
                          AND cc.is_read_enabled = TRUE
                        LIMIT 1
                        """,
                        organizer["user_id"],
                    )
                write_rules = [{"connection_id": c["id"]} for c in write_conns]

            if not write_rules:
                return

            from calendars.schemas import BookingExternalEvent

            end_time = scheduled_time + timedelta(minutes=duration_min)
            event = BookingExternalEvent(
                summary=f"{schedule_title} — {guest_name}",
                description=f"Бронирование через «До встречи»\nГость: {guest_name}",
                start_time=scheduled_time,
                end_time=end_time,
                meeting_link=meeting_link,
            )

            for rule in write_rules:
                connection_id = str(rule["connection_id"])
                try:
                    c = await conn.fetchrow(
                        """
                        SELECT cc.*, ca.access_token_encrypted, ca.refresh_token_encrypted,
                               ca.token_expires_at, ca.provider, ca.status,
                               ca.caldav_url, ca.caldav_username, ca.caldav_password_encrypted
                        FROM calendar_connections cc
                        JOIN calendar_accounts ca ON ca.id = cc.account_id
                        WHERE cc.id = $1 AND ca.status = 'active'
                        """,
                        connection_id,
                    )
                    if not c:
                        continue

                    provider = get_provider(c["provider"])
                    account_data = dict(c)

                    ext_id, etag = await provider.create_event(
                        account_data, c["external_calendar_id"], event,
                    )

                    await cal_db.create_event_mapping(
                        conn, booking_id, connection_id, ext_id, etag=etag,
                    )
                    await cal_db.log_sync(
                        conn, None, connection_id,
                        "push_booking", "success",
                        {"booking_id": booking_id, "external_event_id": ext_id},
                    )
                    log.info("booking_written_to_calendar",
                             booking_id=booking_id, connection_id=connection_id)

                except Exception as e:
                    log.warning("booking_write_error",
                                booking_id=booking_id, connection_id=connection_id,
                                error=str(e))
                    await cal_db.log_sync(
                        conn, None, connection_id,
                        "push_booking", "error",
                        {"booking_id": booking_id}, error=str(e),
                    )
    except Exception as e:
        log.error("write_booking_to_calendars_error", booking_id=booking_id, error=str(e))


async def update_booking_in_calendars(pool: asyncpg.Pool, booking_id: str):
    """Обновить заголовок события при подтверждении бронирования (fire-and-forget)."""
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT set_config('app.is_internal', 'true', true)")
                booking = await conn.fetchrow(
                    """
                    SELECT b.guest_name, b.scheduled_time, b.end_time, b.meeting_link,
                           s.title AS schedule_title, s.duration
                    FROM bookings b
                    JOIN schedules s ON s.id = b.schedule_id
                    WHERE b.id = $1
                    """,
                    booking_id,
                )
                if not booking:
                    return

                mappings = await cal_db.get_event_mappings_for_booking(conn, booking_id)
                if not mappings:
                    return

                from calendars.schemas import BookingExternalEvent

                end_time = (
                    booking["end_time"]
                    if booking["end_time"]
                    else booking["scheduled_time"] + timedelta(minutes=int(booking["duration"]))
                )
                updated_event = BookingExternalEvent(
                    summary=f"✓ {booking['schedule_title']} — {booking['guest_name']}",
                    description=(
                        f"Встреча подтверждена\nГость: {booking['guest_name']}"
                    ),
                    start_time=booking["scheduled_time"],
                    end_time=end_time,
                    meeting_link=booking.get("meeting_link"),
                )

                for m in mappings:
                    if m.get("sync_status") == "deleted":
                        continue
                    connection_id = str(m["connection_id"])
                    mapping_id = str(m["id"])
                    try:
                        c = await conn.fetchrow(
                            """
                            SELECT cc.*, ca.access_token_encrypted, ca.refresh_token_encrypted,
                                   ca.token_expires_at, ca.provider, ca.status,
                                   ca.caldav_url, ca.caldav_username, ca.caldav_password_encrypted
                            FROM calendar_connections cc
                            JOIN calendar_accounts ca ON ca.id = cc.account_id
                            WHERE cc.id = $1 AND ca.status = 'active'
                            """,
                            connection_id,
                        )
                        if not c:
                            continue

                        provider = get_provider(c["provider"])
                        new_etag = await provider.update_event(
                            dict(c),
                            c["external_calendar_id"],
                            m["external_event_id"],
                            updated_event,
                            etag=m.get("etag"),
                        )
                        await conn.execute(
                            "UPDATE event_mapping SET etag = $2, last_synced_at = NOW() WHERE id = $1",
                            mapping_id, new_etag,
                        )
                        log.info("booking_confirmed_in_calendar",
                                 booking_id=booking_id, connection_id=connection_id)

                    except Exception as e:
                        log.warning("booking_confirm_update_error",
                                    booking_id=booking_id, connection_id=connection_id,
                                    error=str(e))
    except Exception as e:
        log.error("update_booking_in_calendars_error", booking_id=booking_id, error=str(e))


async def delete_booking_from_calendars(pool: asyncpg.Pool, booking_id: str):
    """Удалить события из всех внешних календарей при отмене бронирования (fire-and-forget)."""
    try:
        async with pool.acquire() as conn:
            mappings = await cal_db.get_event_mappings_for_booking(conn, booking_id)
            if not mappings:
                return

            for m in mappings:
                if m.get("sync_status") == "deleted":
                    continue
                mapping_id = str(m["id"])
                connection_id = str(m["connection_id"])
                try:
                    c = await conn.fetchrow(
                        """
                        SELECT cc.*, ca.access_token_encrypted, ca.refresh_token_encrypted,
                               ca.token_expires_at, ca.provider, ca.status,
                               ca.caldav_url, ca.caldav_username, ca.caldav_password_encrypted
                        FROM calendar_connections cc
                        JOIN calendar_accounts ca ON ca.id = cc.account_id
                        WHERE cc.id = $1 AND ca.status = 'active'
                        """,
                        connection_id,
                    )
                    if not c:
                        await cal_db.update_event_mapping_status(conn, mapping_id, "error", "account inactive")
                        continue

                    provider = get_provider(c["provider"])
                    account_data = dict(c)

                    await provider.delete_event(
                        account_data, c["external_calendar_id"], m["external_event_id"],
                    )

                    await cal_db.update_event_mapping_status(conn, mapping_id, "deleted")
                    await cal_db.log_sync(
                        conn, None, connection_id,
                        "delete_booking", "success",
                        {"booking_id": booking_id, "external_event_id": m["external_event_id"]},
                    )
                    log.info("booking_deleted_from_calendar",
                             booking_id=booking_id, connection_id=connection_id)

                except Exception as e:
                    log.warning("booking_delete_error",
                                booking_id=booking_id, connection_id=connection_id,
                                error=str(e))
                    await cal_db.update_event_mapping_status(conn, mapping_id, "error", str(e))
    except Exception as e:
        log.error("delete_booking_from_calendars_error", booking_id=booking_id, error=str(e))
