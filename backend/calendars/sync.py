"""Sync Engine — фоновая синхронизация с внешними календарями."""

import asyncio
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
        """Основной цикл — sync all accounts каждые SYNC_INTERVAL секунд."""
        while self._running:
            try:
                await self.sync_all_accounts()
            except Exception as e:
                log.error("sync_loop_error", error=str(e))
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
        """Синхронизировать один календарь: read_events → upsert busy slots."""
        connection_id = str(connection["id"])
        try:
            events, new_token = await provider.read_events(
                account_data,
                connection["external_calendar_id"],
                time_min,
                time_max,
                sync_token=connection.get("sync_token"),
            )
            events_dicts = [e.model_dump() for e in events]
            await cal_db.upsert_external_busy_slots(conn, connection_id, events_dicts)

            # При полной синхронизации (без sync_token) — удалить устаревшие слоты
            if not connection.get("sync_token"):
                valid_ids = {e.external_id for e in events}
                await cal_db.delete_stale_busy_slots(conn, connection_id, valid_ids)

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
                {"events_count": len(events)},
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
                               ca.token_expires_at, ca.provider, ca.status
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
                               ca.token_expires_at, ca.provider, ca.status
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

                    deleted = await provider.delete_event(
                        account_data, c["external_calendar_id"], m["external_event_id"],
                    )

                    await cal_db.update_event_mapping_status(
                        conn, mapping_id, "deleted",
                    )
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
