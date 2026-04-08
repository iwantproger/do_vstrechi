"""Pydantic-схемы для календарной интеграции."""

from datetime import datetime
from typing import Optional, Any

from pydantic import BaseModel, Field


# ── Ответы ────────────────────────────────────────

class CalendarConnectionResponse(BaseModel):
    id: str
    external_calendar_id: str
    calendar_name: str
    calendar_color: Optional[str] = None
    is_read_enabled: bool = True
    is_write_target: bool = False
    last_sync_at: Optional[datetime] = None


class CalendarAccountResponse(BaseModel):
    id: str
    provider: str
    provider_email: Optional[str] = None
    status: str = "active"
    last_sync_at: Optional[datetime] = None
    calendars: list[CalendarConnectionResponse] = []


# ── Запросы ────────────────────────────────────────

class CalendarConnectionToggle(BaseModel):
    is_read_enabled: Optional[bool] = None
    is_write_target: Optional[bool] = None


class ScheduleCalendarRule(BaseModel):
    connection_id: str = Field(..., max_length=50)
    use_for_blocking: bool = True
    use_for_writing: bool = False


class ScheduleCalendarConfig(BaseModel):
    rules: list[ScheduleCalendarRule]


# ── Внутренние модели (провайдеры / sync) ──────────

class ExternalEvent(BaseModel):
    """Событие из внешнего календаря (busy-слот)."""
    external_id: str
    summary: Optional[str] = None
    start_time: datetime
    end_time: datetime
    is_all_day: bool = False
    etag: Optional[str] = None
    raw_data: Optional[dict[str, Any]] = None


class BookingExternalEvent(BaseModel):
    """Данные для создания события во внешнем календаре при бронировании."""
    summary: str = Field(..., max_length=500)
    description: Optional[str] = Field(None, max_length=5000)
    start_time: datetime
    end_time: datetime
    timezone: str = "UTC"
    location: Optional[str] = None
    meeting_link: Optional[str] = None
