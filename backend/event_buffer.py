"""Event buffer: in-memory async queue → periodic batched INSERT into app_events.

Goals:
- Remove DB roundtrip from request hot paths (fire-and-forget tracking).
- Backpressure: non-blocking enqueue with drop-on-full and structlog warning.
- Multi-row INSERT every 5s or when batch >= 50.
- Graceful shutdown: drain queue on stop.
- Retry INSERT once on failure; on second failure log & drop batch.

Usage:
    from event_buffer import event_buffer
    event_buffer.add("schedule_created", telegram_id=123, metadata={...})
"""
import asyncio
import hashlib
import json
from typing import Optional

import asyncpg
import structlog

from config import ANONYMIZE_SALT

log = structlog.get_logger()

_MAX_QUEUE = 10000
_BATCH_THRESHOLD = 50
_FLUSH_INTERVAL_S = 5.0


def _anonymize(telegram_id: int) -> str:
    return hashlib.sha256(f"{telegram_id}:{ANONYMIZE_SALT}".encode()).hexdigest()[:12]


class EventBuffer:
    def __init__(self) -> None:
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=_MAX_QUEUE)
        self._pool: Optional[asyncpg.Pool] = None
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        self._dropped = 0

    # ─────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────
    def add(
        self,
        event_type: str,
        telegram_id: int = 0,
        metadata: dict | None = None,
        severity: str = "info",
        session_id: str | None = None,
    ) -> None:
        """Non-blocking enqueue. Drops event if queue is full."""
        item = (
            event_type,
            _anonymize(telegram_id),
            session_id,
            json.dumps(metadata) if metadata else None,
            severity,
        )
        try:
            self._queue.put_nowait(item)
        except asyncio.QueueFull:
            self._dropped += 1
            if self._dropped % 100 == 1:  # log first + every 100th drop
                log.warning(
                    "event_buffer_full_dropped",
                    event_type=event_type,
                    dropped_total=self._dropped,
                )

    async def start(self, pool: asyncpg.Pool) -> None:
        if self._task is not None:
            return
        self._pool = pool
        self._stop_event.clear()
        self._task = asyncio.create_task(self._flush_loop())
        log.info("event_buffer_started")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stop_event.set()
        try:
            await asyncio.wait_for(self._task, timeout=10)
        except asyncio.TimeoutError:
            log.warning("event_buffer_stop_timeout")
            self._task.cancel()
        # Final drain
        await self._flush_once(final=True)
        self._task = None
        log.info("event_buffer_stopped", dropped_total=self._dropped)

    # ─────────────────────────────────────────────────────────
    # Internals
    # ─────────────────────────────────────────────────────────
    async def _flush_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                # Wait up to flush interval, waking early when batch threshold hit.
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(), timeout=_FLUSH_INTERVAL_S
                    )
                except asyncio.TimeoutError:
                    pass  # normal timer tick

                if self._queue.qsize() > 0:
                    await self._flush_once()
            except Exception as e:
                log.error("event_buffer_loop_error", error=str(e))
                await asyncio.sleep(1)

    async def _drain(self, limit: int = 500) -> list[tuple]:
        items = []
        for _ in range(limit):
            if self._queue.empty():
                break
            items.append(self._queue.get_nowait())
        return items

    async def _flush_once(self, final: bool = False) -> None:
        if self._pool is None:
            return
        batch = await self._drain(limit=_MAX_QUEUE if final else 500)
        if not batch:
            return

        # Build multi-row INSERT: VALUES ($1,$2,$3,$4::jsonb,$5), ($6,$7,...)
        params: list = []
        placeholders: list[str] = []
        for i, row in enumerate(batch):
            base = i * 5
            placeholders.append(
                f"(${base+1}, ${base+2}, ${base+3}, ${base+4}::jsonb, ${base+5})"
            )
            params.extend(row)

        sql = (
            "INSERT INTO app_events "
            "(event_type, anonymous_id, session_id, metadata, severity) VALUES "
            + ", ".join(placeholders)
        )

        for attempt in (1, 2):
            try:
                async with self._pool.acquire() as conn:
                    await conn.execute(sql, *params)
                return  # success
            except Exception as e:
                log.warning(
                    "event_buffer_insert_failed",
                    attempt=attempt,
                    batch_size=len(batch),
                    error=str(e),
                )
                if attempt == 2:
                    log.error(
                        "event_buffer_batch_dropped",
                        batch_size=len(batch),
                    )
                    return
                await asyncio.sleep(0.5)


# Module-level singleton
event_buffer = EventBuffer()
