"""Google Calendar адаптер — реализация CalendarProvider."""

import asyncio
from datetime import datetime, timedelta, timezone

import structlog
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from config import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
from calendars.base import CalendarProvider
from calendars.schemas import ExternalEvent, BookingExternalEvent
from calendars.encryption import decrypt_token

log = structlog.get_logger()

SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.readonly",
]


class GoogleCalendarProvider(CalendarProvider):
    """Google Calendar API v3 через google-api-python-client."""

    provider_name = "google"

    def _get_credentials(self, account_data: dict) -> Credentials:
        """Расшифровать токены → google Credentials."""
        access_token = decrypt_token(account_data["access_token_encrypted"])
        refresh_token = None
        if account_data.get("refresh_token_encrypted"):
            refresh_token = decrypt_token(account_data["refresh_token_encrypted"])

        return Credentials(
            token=access_token,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=GOOGLE_CLIENT_ID,
            client_secret=GOOGLE_CLIENT_SECRET,
            scopes=SCOPES,
        )

    def _build_service(self, credentials: Credentials):
        """Создать Google Calendar API service (синхронный)."""
        return build("calendar", "v3", credentials=credentials, cache_discovery=False)

    async def list_calendars(self, account_data: dict) -> list[dict]:
        """Получить список календарей пользователя."""
        creds = self._get_credentials(account_data)

        def _fetch():
            service = self._build_service(creds)
            result = []
            page_token = None
            while True:
                resp = service.calendarList().list(pageToken=page_token).execute()
                for item in resp.get("items", []):
                    result.append({
                        "external_calendar_id": item["id"],
                        "calendar_name": item.get("summary", item["id"]),
                        "calendar_color": item.get("backgroundColor"),
                        "is_primary": item.get("primary", False),
                    })
                page_token = resp.get("nextPageToken")
                if not page_token:
                    break
            return result

        return await asyncio.to_thread(_fetch)

    async def read_events(
        self,
        account_data: dict,
        calendar_id: str,
        time_min: datetime,
        time_max: datetime,
        sync_token: str | None = None,
    ) -> tuple[list[ExternalEvent], str | None]:
        """Прочитать события за период (или инкрементально по sync_token)."""
        creds = self._get_credentials(account_data)

        def _fetch():
            service = self._build_service(creds)
            events_api = service.events()
            all_events = []
            page_token = None

            while True:
                try:
                    if sync_token and not page_token:
                        resp = events_api.list(
                            calendarId=calendar_id,
                            syncToken=sync_token,
                            pageToken=page_token,
                        ).execute()
                    else:
                        kwargs = {
                            "calendarId": calendar_id,
                            "timeMin": time_min.isoformat(),
                            "timeMax": time_max.isoformat(),
                            "singleEvents": True,
                            "orderBy": "startTime",
                            "maxResults": 250,
                        }
                        if page_token:
                            kwargs["pageToken"] = page_token
                        resp = events_api.list(**kwargs).execute()
                except HttpError as e:
                    if e.resp.status == 410:
                        # Sync token expired → полная resync
                        log.warning("google_sync_token_expired", calendar_id=calendar_id)
                        resp = events_api.list(
                            calendarId=calendar_id,
                            timeMin=time_min.isoformat(),
                            timeMax=time_max.isoformat(),
                            singleEvents=True,
                            orderBy="startTime",
                            maxResults=250,
                        ).execute()
                    else:
                        raise

                for item in resp.get("items", []):
                    if item.get("status") == "cancelled":
                        continue
                    ev = _parse_event(item)
                    if ev:
                        all_events.append(ev)

                page_token = resp.get("nextPageToken")
                if not page_token:
                    break

            new_sync_token = resp.get("nextSyncToken")
            return all_events, new_sync_token

        return await asyncio.to_thread(_fetch)

    async def create_event(
        self,
        account_data: dict,
        calendar_id: str,
        event: BookingExternalEvent,
    ) -> tuple[str, str | None]:
        """Создать событие в Google Calendar."""
        creds = self._get_credentials(account_data)
        body = _build_event_body(event)

        def _create():
            service = self._build_service(creds)
            result = service.events().insert(
                calendarId=calendar_id, body=body
            ).execute()
            return result["id"], result.get("etag")

        return await asyncio.to_thread(_create)

    async def update_event(
        self,
        account_data: dict,
        calendar_id: str,
        external_event_id: str,
        event: BookingExternalEvent,
        etag: str | None = None,
    ) -> str | None:
        """Обновить событие в Google Calendar."""
        creds = self._get_credentials(account_data)
        body = _build_event_body(event)

        def _update():
            service = self._build_service(creds)
            result = service.events().update(
                calendarId=calendar_id,
                eventId=external_event_id,
                body=body,
            ).execute()
            return result.get("etag")

        return await asyncio.to_thread(_update)

    async def delete_event(
        self,
        account_data: dict,
        calendar_id: str,
        external_event_id: str,
    ) -> bool:
        """Удалить событие из Google Calendar."""
        creds = self._get_credentials(account_data)

        def _delete():
            service = self._build_service(creds)
            try:
                service.events().delete(
                    calendarId=calendar_id, eventId=external_event_id
                ).execute()
                return True
            except HttpError as e:
                if e.resp.status == 404:
                    return True  # уже удалено
                raise

        return await asyncio.to_thread(_delete)

    async def refresh_token_if_needed(self, account_data: dict) -> dict | None:
        """Обновить access_token если истекает через < 5 минут."""
        expires_at = account_data.get("token_expires_at")
        if expires_at and expires_at > datetime.now(timezone.utc) + timedelta(minutes=5):
            return None  # ещё актуален

        if not account_data.get("refresh_token_encrypted"):
            return None  # нечем обновлять

        creds = self._get_credentials(account_data)
        if not creds.refresh_token:
            return None

        def _refresh():
            creds.refresh(Request())
            return {
                "access_token": creds.token,
                "expires_at": creds.expiry.replace(tzinfo=timezone.utc) if creds.expiry else None,
            }

        try:
            refreshed = await asyncio.to_thread(_refresh)
            return refreshed
        except Exception as e:
            log.warning("google_token_refresh_failed", error=str(e))
            raise


# ── Helpers ──────────────────────────────────────

def _parse_event(item: dict) -> ExternalEvent | None:
    """Google event dict → ExternalEvent."""
    start_raw = item.get("start", {})
    end_raw = item.get("end", {})

    is_all_day = "date" in start_raw and "dateTime" not in start_raw

    if is_all_day:
        start_str = start_raw["date"] + "T00:00:00+00:00"
        end_str = end_raw["date"] + "T00:00:00+00:00"
    else:
        start_str = start_raw.get("dateTime")
        end_str = end_raw.get("dateTime")

    if not start_str or not end_str:
        return None

    return ExternalEvent(
        external_id=item["id"],
        summary=item.get("summary"),
        start_time=datetime.fromisoformat(start_str),
        end_time=datetime.fromisoformat(end_str),
        is_all_day=is_all_day,
        etag=item.get("etag"),
        raw_data=item,
    )


def _build_event_body(event: BookingExternalEvent) -> dict:
    """BookingExternalEvent → Google Calendar event body."""
    description = event.description or ""
    if event.meeting_link:
        description += f"\n\nСсылка на встречу: {event.meeting_link}"

    body = {
        "summary": event.summary,
        "description": description.strip(),
        "start": {
            "dateTime": event.start_time.isoformat(),
            "timeZone": event.timezone,
        },
        "end": {
            "dateTime": event.end_time.isoformat(),
            "timeZone": event.timezone,
        },
    }
    if event.location:
        body["location"] = event.location
    return body
