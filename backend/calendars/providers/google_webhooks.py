"""Google Calendar push-notification (webhook) подписки."""

import asyncio
import uuid
from datetime import datetime, timezone

import structlog
from googleapiclient.errors import HttpError

log = structlog.get_logger()


async def subscribe_to_calendar(
    account_data: dict,
    calendar_id: str,
    webhook_url: str,
    channel_id: str | None = None,
    channel_token: str | None = None,
) -> dict | None:
    """
    Создать Google push-notification подписку для календаря.

    Возвращает {channel_id, resource_id, expires_at} или None если
    подписка невозможна (shared/public calendar, 403, etc.).
    """
    if channel_id is None:
        channel_id = str(uuid.uuid4())

    def _subscribe():
        from calendars.providers.google import GoogleCalendarProvider
        provider = GoogleCalendarProvider()
        creds = provider._get_credentials(account_data)
        service = provider._build_service(creds)
        body: dict = {
            "id": channel_id,
            "type": "web_hook",
            "address": webhook_url,
        }
        if channel_token:
            body["token"] = channel_token
        return service.events().watch(calendarId=calendar_id, body=body).execute()

    try:
        result = await asyncio.to_thread(_subscribe)
    except HttpError as e:
        # 403 / 400 — shared или public calendar без поддержки watch
        if e.resp.status in (400, 403):
            log.info(
                "webhook_subscribe_unsupported",
                calendar_id=calendar_id,
                status=e.resp.status,
            )
            return None
        raise
    except Exception as e:
        log.warning("webhook_subscribe_error", calendar_id=calendar_id, error=str(e))
        return None

    expiration_ms = int(result.get("expiration", 0))
    expires_at = (
        datetime.fromtimestamp(expiration_ms / 1000, tz=timezone.utc)
        if expiration_ms
        else None
    )
    log.info(
        "webhook_subscribed",
        calendar_id=calendar_id,
        channel_id=result["id"],
        expires_at=expires_at.isoformat() if expires_at else None,
    )
    return {
        "channel_id": result["id"],
        "resource_id": result.get("resourceId"),
        "expires_at": expires_at,
    }


async def unsubscribe(
    account_data: dict,
    channel_id: str,
    resource_id: str,
) -> bool:
    """
    Отменить Google push-notification подписку.

    Возвращает True при успехе (в т.ч. если уже не существует).
    """
    def _unsubscribe():
        from calendars.providers.google import GoogleCalendarProvider
        provider = GoogleCalendarProvider()
        creds = provider._get_credentials(account_data)
        service = provider._build_service(creds)
        service.channels().stop(
            body={"id": channel_id, "resourceId": resource_id}
        ).execute()
        return True

    try:
        return await asyncio.to_thread(_unsubscribe)
    except HttpError as e:
        if e.resp.status in (400, 404, 410):
            log.info("webhook_unsubscribe_already_gone",
                     channel_id=channel_id, status=e.resp.status)
            return True
        log.warning("webhook_unsubscribe_error",
                    channel_id=channel_id, error=str(e))
        raise
