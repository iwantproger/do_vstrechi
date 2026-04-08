"""Yandex Calendar провайдер (CalDAV).

Отличия от базового CalDAV:
- CalDAV URL: https://caldav.yandex.ru/
- Rate limiting: пауза 1 сек перед каждой write-операцией
- Аутентификация: email + пароль приложения (создаётся в Яндекс ID → Пароли)
"""

import asyncio

from calendars.schemas import BookingExternalEvent
from calendars.providers.caldav_adapter import CalDAVCalendarProvider


class YandexCalendarProvider(CalDAVCalendarProvider):
    """Yandex Calendar через CalDAV."""

    provider_name = "yandex"
    default_url = "https://caldav.yandex.ru/"

    async def create_event(
        self,
        account_data: dict,
        calendar_id: str,
        event: BookingExternalEvent,
    ) -> tuple[str, str | None]:
        """Создать событие с паузой 1 сек (rate limiting)."""
        await asyncio.sleep(1)
        return await super().create_event(account_data, calendar_id, event)

    async def update_event(
        self,
        account_data: dict,
        calendar_id: str,
        external_event_id: str,
        event: BookingExternalEvent,
        etag: str | None = None,
    ) -> str | None:
        """Обновить событие с паузой 1 сек (rate limiting)."""
        await asyncio.sleep(1)
        return await super().update_event(
            account_data, calendar_id, external_event_id, event, etag
        )

    async def delete_event(
        self,
        account_data: dict,
        calendar_id: str,
        external_event_id: str,
    ) -> bool:
        """Удалить событие с паузой 1 сек (rate limiting)."""
        await asyncio.sleep(1)
        return await super().delete_event(account_data, calendar_id, external_event_id)
