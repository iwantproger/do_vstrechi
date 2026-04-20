"""Latency buffer: batched INSERT into api_latency_log every 10s.

Tracks response times for key API paths. Auto-cleanup: drops rows > 7 days.
"""
import asyncio
from typing import Optional

import asyncpg
import structlog

log = structlog.get_logger()

_MAX_QUEUE = 5000
_FLUSH_INTERVAL_S = 10.0
_TRACKED_PREFIXES = (
    "/api/bookings",
    "/api/schedules",
    "/api/users/auth",
    "/api/available-slots/",
)


class LatencyBuffer:
    def __init__(self) -> None:
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=_MAX_QUEUE)
        self._pool: Optional[asyncpg.Pool] = None
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()

    def should_track(self, path: str) -> bool:
        return any(path.startswith(p) for p in _TRACKED_PREFIXES)

    def add(self, path: str, method: str, status_code: int, duration_ms: float) -> None:
        try:
            self._queue.put_nowait((path, method, status_code, round(duration_ms, 2)))
        except asyncio.QueueFull:
            pass

    async def start(self, pool: asyncpg.Pool) -> None:
        if self._task is not None:
            return
        self._pool = pool
        self._stop_event.clear()
        self._task = asyncio.create_task(self._flush_loop())
        # Cleanup old rows on start
        try:
            async with pool.acquire() as conn:
                await conn.execute("DELETE FROM api_latency_log WHERE created_at < NOW() - INTERVAL '7 days'")
        except Exception:
            pass
        log.info("latency_buffer_started")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stop_event.set()
        try:
            await asyncio.wait_for(self._task, timeout=5)
        except asyncio.TimeoutError:
            self._task.cancel()
        await self._flush_once()
        self._task = None

    async def _flush_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=_FLUSH_INTERVAL_S)
            except asyncio.TimeoutError:
                pass
            if self._queue.qsize() > 0:
                await self._flush_once()

    async def _flush_once(self) -> None:
        if not self._pool:
            return
        items = []
        for _ in range(500):
            if self._queue.empty():
                break
            items.append(self._queue.get_nowait())
        if not items:
            return

        params: list = []
        placeholders: list[str] = []
        for i, (path, method, status, dur) in enumerate(items):
            base = i * 4
            placeholders.append(f"(${base+1}, ${base+2}, ${base+3}, ${base+4})")
            params.extend([path, method, status, dur])

        sql = (
            "INSERT INTO api_latency_log (path, method, status_code, duration_ms) VALUES "
            + ", ".join(placeholders)
        )
        try:
            async with self._pool.acquire() as conn:
                await conn.execute(sql, *params)
        except Exception as e:
            log.warning("latency_buffer_flush_error", error=str(e), batch_size=len(items))


latency_buffer = LatencyBuffer()
