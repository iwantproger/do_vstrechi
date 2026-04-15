"""Утилиты — чистые и почти-чистые функции."""
import uuid
import hashlib
from typing import Any

import httpx
import structlog

from config import ANONYMIZE_SALT, BOT_INTERNAL_URL, INTERNAL_API_KEY

log = structlog.get_logger()


def row_to_dict(row) -> dict:
    """asyncpg Record → plain dict. None-safe wrapper around dict(row).

    Intentionally thin: many call sites rely on the None-passthrough behavior
    (e.g. `return row_to_dict(await conn.fetchrow(...))`), which bare dict()
    would not handle. Do NOT inline without auditing every caller.
    """
    if row is None:
        return None
    return dict(row)


def rows_to_list(rows) -> list:
    """asyncpg Records → list of dicts (equivalent to [dict(r) for r in rows])."""
    return [dict(r) for r in rows]


def generate_meeting_link(platform: str) -> str | None:
    """Генерирует ссылку на конференцию. Возвращает None для offline и other."""
    if platform in ("offline", "other"):
        return None
    room = str(uuid.uuid4()).replace("-", "")[:12]
    return f"https://meet.jit.si/dovstrechi-{room}"


def anonymize_id(telegram_id: int) -> str:
    """SHA256(telegram_id:salt), first 12 chars."""
    return hashlib.sha256(f"{telegram_id}:{ANONYMIZE_SALT}".encode()).hexdigest()[:12]


async def _track_event(
    conn,
    event_type: str,
    telegram_id: int = 0,
    metadata: dict | None = None,
    severity: str = "info",
    session_id: str | None = None,
) -> None:
    """Record an app event via the in-memory EventBuffer.

    Signature keeps `conn` for backwards compatibility with existing callers;
    the parameter is ignored — events go to a background batched INSERT.
    This is fire-and-forget and never raises.
    """
    try:
        from event_buffer import event_buffer
        event_buffer.add(
            event_type=event_type,
            telegram_id=telegram_id,
            metadata=metadata,
            severity=severity,
            session_id=session_id,
        )
    except Exception:
        log.warning("track_event_failed", event_type=event_type)


async def _notify_bot_new_booking(**kwargs: Any) -> None:
    """Fire-and-forget: tell bot to message the organizer about a new booking."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.post(
                f"{BOT_INTERNAL_URL}/internal/notify",
                json=kwargs,
                headers={"X-Internal-Key": INTERNAL_API_KEY},
            )
            result = resp.json()
            if result.get("ok"):
                log.info("bot_notified", booking_id=kwargs.get("booking_id"))
            else:
                log.warning("bot_notification_failed", response=result)
    except Exception as e:
        log.warning("bot_notification_error", error=str(e))


async def _notify_bot_status_change(**kwargs: Any) -> None:
    """Fire-and-forget: notify bot that a booking changed status (confirmed/cancelled)."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(
                f"{BOT_INTERNAL_URL}/internal/status-change",
                json=kwargs,
                headers={"X-Internal-Key": INTERNAL_API_KEY},
            )
    except Exception as e:
        log.warning("bot_status_notification_error", error=str(e))
