"""Абстрактный базовый класс для провайдеров календарей."""

from abc import ABC, abstractmethod
from datetime import datetime

from calendars.schemas import ExternalEvent, BookingExternalEvent


class CalendarProvider(ABC):
    """Единый интерфейс для Google, Yandex, Apple, Outlook."""

    provider_name: str

    @abstractmethod
    async def list_calendars(self, account_data: dict) -> list[dict]:
        """Получить список календарей в аккаунте.

        Возвращает list[dict] с ключами:
          external_calendar_id, calendar_name, calendar_color
        """
        ...

    @abstractmethod
    async def read_events(
        self,
        account_data: dict,
        calendar_id: str,
        time_min: datetime,
        time_max: datetime,
        sync_token: str | None = None,
    ) -> tuple[list[ExternalEvent], str | None]:
        """Прочитать события (busy-слоты) за период.

        Возвращает (events, new_sync_token).
        Если sync_token передан — инкрементальная синхронизация.
        """
        ...

    @abstractmethod
    async def create_event(
        self,
        account_data: dict,
        calendar_id: str,
        event: BookingExternalEvent,
    ) -> tuple[str, str | None]:
        """Создать событие во внешнем календаре.

        Возвращает (external_event_id, etag).
        """
        ...

    @abstractmethod
    async def update_event(
        self,
        account_data: dict,
        calendar_id: str,
        external_event_id: str,
        event: BookingExternalEvent,
        etag: str | None = None,
    ) -> str | None:
        """Обновить событие. Возвращает новый etag или None."""
        ...

    @abstractmethod
    async def delete_event(
        self,
        account_data: dict,
        calendar_id: str,
        external_event_id: str,
    ) -> bool:
        """Удалить событие. Возвращает True если удалено."""
        ...

    async def refresh_token_if_needed(
        self, account_data: dict
    ) -> dict | None:
        """Обновить access_token если истёк.

        Возвращает dict с новыми токенами или None если обновление не нужно.
        """
        return None
