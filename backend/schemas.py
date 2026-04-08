"""Pydantic-схемы для валидации запросов и ответов."""
from typing import Optional, List
from pydantic import BaseModel, Field


class UserAuth(BaseModel):
    username: Optional[str] = Field(None, max_length=100)
    first_name: Optional[str] = Field(None, max_length=200)
    last_name: Optional[str] = Field(None, max_length=200)
    timezone: Optional[str] = "UTC"


class ScheduleCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    duration: int = Field(60, ge=5, le=480)
    buffer_time: int = Field(0, ge=0, le=120)
    work_days: List[int] = [0, 1, 2, 3, 4]
    start_time: str = Field("09:00", pattern=r"^\d{2}:\d{2}$")
    end_time: str = Field("18:00", pattern=r"^\d{2}:\d{2}$")
    location_mode: str = Field("fixed", max_length=50)
    platform: str = Field("jitsi", max_length=50)
    min_booking_advance: Optional[int] = Field(0, ge=0, le=10080)
    requires_confirmation: bool = Field(True)


class ScheduleUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    duration: Optional[int] = Field(None, ge=5, le=480)
    buffer_time: Optional[int] = Field(None, ge=0, le=120)
    work_days: Optional[List[int]] = None
    start_time: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    end_time: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    location_mode: Optional[str] = Field(None, max_length=50)
    platform: Optional[str] = Field(None, max_length=50)
    is_active: Optional[bool] = None
    min_booking_advance: Optional[int] = Field(None, ge=0, le=10080)
    requires_confirmation: Optional[bool] = None


class QuickMeetingCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    start_time: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    end_time: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    schedule_id: Optional[str] = Field(None, max_length=50)
    guest_name: Optional[str] = Field(None, max_length=200)
    guest_contact: Optional[str] = Field(None, max_length=200)
    notes: Optional[str] = Field(None, max_length=2000)


class BookingCreate(BaseModel):
    schedule_id: str = Field(..., max_length=50)
    guest_name: str = Field(..., min_length=1, max_length=200)
    guest_contact: str = Field(..., min_length=1, max_length=200)
    guest_telegram_id: Optional[int] = None
    scheduled_time: str = Field(..., max_length=50)
    notes: Optional[str] = Field(None, max_length=2000)


class TelegramLoginData(BaseModel):
    id: int = Field(..., ge=1)
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)
    username: Optional[str] = Field(None, max_length=100)
    photo_url: Optional[str] = Field(None, max_length=500)
    auth_date: int = Field(..., ge=0)
    hash: str = Field(..., min_length=64, max_length=64)


class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=5000)
    description_plain: Optional[str] = Field(None, max_length=2000)
    status: str = Field("backlog", pattern=r"^(backlog|in_progress|done)$")
    source: str = Field("manual", pattern=r"^(manual|git_commit|ai_generated|github_issue)$")
    source_ref: Optional[str] = Field(None, max_length=500)
    tags: List[str] = []


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=5000)
    description_plain: Optional[str] = Field(None, max_length=2000)
    status: Optional[str] = Field(None, pattern=r"^(backlog|in_progress|done)$")
    tags: Optional[List[str]] = None


class TaskReorder(BaseModel):
    status: str = Field(..., pattern=r"^(backlog|in_progress|done)$")
    task_ids: List[str]


class AppEvent(BaseModel):
    event_type: str = Field(..., min_length=1, max_length=50)
    session_id: Optional[str] = Field(None, max_length=100)
    metadata: Optional[dict] = None
    severity: str = Field("info", pattern=r"^(info|warn|error|critical)$")


class CleanupRequest(BaseModel):
    older_than_days: int = Field(default=30, ge=7, le=365)
    severity: str = Field(default="info", pattern=r"^(info|warn)$")
