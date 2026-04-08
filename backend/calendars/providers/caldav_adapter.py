"""CalDAV провайдер — базовый адаптер для Yandex Calendar и Apple iCloud Calendar.

Использует python-caldav (sync) обёрнутый в asyncio.to_thread().
CTag используется вместо sync_token для инкрементальной оптимизации:
если CTag не изменился — полный fetch пропускается.
"""

import asyncio
import uuid
from datetime import date as dt_date, datetime, timedelta, timezone

import structlog
import caldav
import caldav.lib.error as caldav_error
from icalendar import Calendar as iCal, Event as iEvent

from calendars.base import CalendarProvider
from calendars.schemas import ExternalEvent, BookingExternalEvent
from calendars.encryption import decrypt_token

log = structlog.get_logger()

# CalDAV property namespaces
CTAG_PROP = '{http://calendarserver.org/ns/}getctag'
ETAG_PROP = '{DAV:}getetag'
COLOR_PROP_APPLE = '{http://apple.com/ns/ical/}calendar-color'
COLOR_PROP_NS = '{http://calendarserver.org/ns/}calendar-color'


class CalDAVAuthError(Exception):
    """Неверные учётные данные (HTTP 401/403)."""
    pass


# ── Helpers ──────────────────────────────────────────────


def _get_ctag(cal: caldav.Calendar) -> str | None:
    """Получить CTag (аналог sync token) — None если сервер не поддерживает."""
    try:
        props = cal.get_properties([CTAG_PROP])
        return props.get(CTAG_PROP)
    except Exception:
        return None


def _build_ics(event: BookingExternalEvent, uid: str) -> str:
    """Создать iCalendar VEVENT строку из BookingExternalEvent."""
    cal = iCal()
    cal.add('prodid', '-//DoVstrechi//Calendar//RU')
    cal.add('version', '2.0')

    ev = iEvent()
    ev.add('uid', uid)
    ev.add('dtstamp', datetime.now(timezone.utc))
    ev.add('dtstart', event.start_time)
    ev.add('dtend', event.end_time)
    ev.add('summary', event.summary)

    description = event.description or ""
    if event.meeting_link:
        description = (description + f"\n\nСсылка на встречу: {event.meeting_link}").strip()
    if description:
        ev.add('description', description)

    if event.location:
        ev.add('location', event.location)

    cal.add_component(ev)
    return cal.to_ical().decode('utf-8')


def _parse_caldav_events(ev_obj) -> list[ExternalEvent]:
    """Распарсить CalDAV CalendarObjectResource → список ExternalEvent.

    Возвращает список (может быть пустым при ошибке парсинга или отменённом событии).
    Для повторяющихся событий (RECURRENCE-ID) генерирует уникальный external_id.
    """
    results = []
    try:
        raw = ev_obj.data
        if isinstance(raw, str):
            raw = raw.encode('utf-8')
        ical_obj = iCal.from_ical(raw)

        for component in ical_obj.walk():
            if component.name != 'VEVENT':
                continue

            status = str(component.get('STATUS', '')).upper()
            if status == 'CANCELLED':
                continue

            uid_prop = component.get('UID')
            if not uid_prop:
                continue
            uid = str(uid_prop)

            # Уникальный ID для экземпляров повторяющихся событий
            recurrence_id = component.get('RECURRENCE-ID')
            if recurrence_id:
                rec_dt = recurrence_id.dt
                if isinstance(rec_dt, dt_date) and not isinstance(rec_dt, datetime):
                    rec_str = rec_dt.strftime('%Y%m%d')
                else:
                    try:
                        rec_str = rec_dt.strftime('%Y%m%dT%H%M%S')
                    except Exception:
                        rec_str = str(hash(str(recurrence_id)))
                external_id = f"{uid}_{rec_str}"
            else:
                external_id = uid

            dtstart = component.get('DTSTART')
            dtend = component.get('DTEND')
            if not dtstart:
                continue

            start = dtstart.dt
            end = dtend.dt if dtend else None

            is_all_day = isinstance(start, dt_date) and not isinstance(start, datetime)

            if is_all_day:
                start_dt = datetime(start.year, start.month, start.day, tzinfo=timezone.utc)
                if end and isinstance(end, dt_date) and not isinstance(end, datetime):
                    end_dt = datetime(end.year, end.month, end.day, tzinfo=timezone.utc)
                else:
                    end_dt = start_dt + timedelta(days=1)
            else:
                start_dt = start if start.tzinfo else start.replace(tzinfo=timezone.utc)
                if end is None:
                    end_dt = start_dt + timedelta(hours=1)
                elif isinstance(end, dt_date) and not isinstance(end, datetime):
                    end_dt = datetime(end.year, end.month, end.day, tzinfo=timezone.utc)
                else:
                    end_dt = end if end.tzinfo else end.replace(tzinfo=timezone.utc)

            summary = str(component.get('SUMMARY', '')) or None

            results.append(ExternalEvent(
                external_id=external_id,
                summary=summary,
                start_time=start_dt,
                end_time=end_dt,
                is_all_day=is_all_day,
                raw_data={"uid": uid},
            ))

    except Exception as e:
        log.warning(
            "caldav_parse_event_error",
            error=str(e),
            url=str(getattr(ev_obj, 'url', '')),
        )
    return results


# ── Provider ─────────────────────────────────────────────


class CalDAVCalendarProvider(CalendarProvider):
    """Базовый CalDAV провайдер (Yandex и Apple наследуют от него).

    Все операции — synchronous caldav calls, обёрнутые в asyncio.to_thread().
    """

    provider_name = "caldav"
    default_url = ""

    def _get_client(self, account_data: dict) -> caldav.DAVClient:
        """Создать DAVClient из account_data."""
        url = account_data.get("caldav_url") or self.default_url
        username = account_data.get("caldav_username", "")
        pwd_enc = account_data.get("caldav_password_encrypted")
        if not pwd_enc:
            raise ValueError("Нет пароля для CalDAV аккаунта")
        password = decrypt_token(pwd_enc)
        return caldav.DAVClient(url=url, username=username, password=password)

    def _get_calendar(self, client: caldav.DAVClient, calendar_id: str) -> caldav.Calendar:
        """Получить Calendar объект по URL (без HTTP-запроса)."""
        return caldav.Calendar(client=client, url=calendar_id)

    async def list_calendars(self, account_data: dict) -> list[dict]:
        """Получить список календарей аккаунта."""
        def _fetch() -> list[dict]:
            try:
                client = self._get_client(account_data)
                principal = client.principal()
                cals = principal.calendars()
            except caldav_error.AuthorizationError as e:
                raise CalDAVAuthError("Неверный email или пароль") from e
            except Exception as e:
                err_str = str(e).lower()
                if any(x in err_str for x in ("401", "403", "unauthorized", "forbidden")):
                    raise CalDAVAuthError("Неверный email или пароль") from e
                raise

            result = []
            for cal in cals:
                name = ""
                try:
                    name = cal.name or ""
                except Exception:
                    pass

                color = None
                try:
                    props = cal.get_properties([COLOR_PROP_APPLE])
                    color = props.get(COLOR_PROP_APPLE)
                    if not color:
                        props2 = cal.get_properties([COLOR_PROP_NS])
                        color = props2.get(COLOR_PROP_NS)
                except Exception:
                    pass

                cal_url = str(cal.url)
                if not name:
                    parts = [p for p in cal_url.rstrip("/").split("/") if p]
                    name = parts[-1] if parts else "Календарь"

                result.append({
                    "external_calendar_id": cal_url,
                    "calendar_name": name,
                    "calendar_color": color,
                })
            return result

        return await asyncio.to_thread(_fetch)

    async def read_events(
        self,
        account_data: dict,
        calendar_id: str,
        time_min: datetime,
        time_max: datetime,
        sync_token: str | None = None,
    ) -> tuple[list[ExternalEvent], list[str], str | None, bool]:
        """Прочитать события за период.

        sync_token хранит CTag. Если CTag не изменился — возвращает пустой список
        с is_full_sync=False (нет изменений, не нужен upsert/delete).
        При изменении CTag или первом запуске — полный fetch, is_full_sync=True.
        """
        def _fetch():
            client = self._get_client(account_data)
            cal = self._get_calendar(client, calendar_id)

            current_ctag = _get_ctag(cal)

            # CTag не изменился — нечего синхронизировать
            if current_ctag and sync_token and current_ctag == sync_token:
                return [], [], sync_token, False

            # Полный fetch (CTag изменился или первый запуск)
            try:
                events_raw = cal.search(
                    start=time_min,
                    end=time_max,
                    event=True,
                    expand=True,
                )
            except Exception:
                # Fallback: search без expand (некоторые серверы не поддерживают expand)
                try:
                    events_raw = cal.search(
                        start=time_min,
                        end=time_max,
                        event=True,
                    )
                except Exception as e:
                    log.warning("caldav_search_failed",
                                provider=self.provider_name,
                                calendar_id=calendar_id,
                                error=str(e))
                    return [], [], current_ctag, True

            all_events: list[ExternalEvent] = []
            for ev_obj in events_raw:
                all_events.extend(_parse_caldav_events(ev_obj))

            return all_events, [], current_ctag, True

        return await asyncio.to_thread(_fetch)

    async def create_event(
        self,
        account_data: dict,
        calendar_id: str,
        event: BookingExternalEvent,
    ) -> tuple[str, str | None]:
        """Создать событие в CalDAV календаре. Возвращает (uid, etag|None)."""
        def _create():
            uid = str(uuid.uuid4())
            ics = _build_ics(event, uid)
            client = self._get_client(account_data)
            cal = self._get_calendar(client, calendar_id)
            saved = cal.save_event(ics)
            etag = None
            try:
                props = saved.get_properties([ETAG_PROP])
                etag = props.get(ETAG_PROP)
            except Exception:
                pass
            return uid, etag

        return await asyncio.to_thread(_create)

    async def update_event(
        self,
        account_data: dict,
        calendar_id: str,
        external_event_id: str,
        event: BookingExternalEvent,
        etag: str | None = None,
    ) -> str | None:
        """Обновить событие по UID. Возвращает новый etag или None.

        Пробует прямой URL ({calendar_url}/{uid}.ics) как для delete_event.
        """
        def _update():
            new_ics = _build_ics(event, uid=external_event_id)
            client = self._get_client(account_data)
            cal = self._get_calendar(client, calendar_id)

            # Первая попытка: прямой URL
            event_url = calendar_id.rstrip("/") + "/" + external_event_id + ".ics"
            try:
                ev_obj = caldav.CalendarObjectResource(client=client, url=event_url)
                ev_obj.data = new_ics
                ev_obj.save()
                return None
            except caldav_error.NotFoundError:
                log.info("caldav_update_not_found_skip", uid=external_event_id)
                return None
            except Exception:
                pass  # Fallback: поиск через REPORT

            # Fallback: event_by_uid
            try:
                ev_obj = cal.event_by_uid(external_event_id)
            except caldav_error.NotFoundError:
                log.info("caldav_update_not_found_skip", uid=external_event_id)
                return None
            except Exception as e:
                log.warning("caldav_update_find_error",
                            uid=external_event_id, error=str(e))
                return None
            ev_obj.data = new_ics
            ev_obj.save()
            return None

        return await asyncio.to_thread(_update)

    async def delete_event(
        self,
        account_data: dict,
        calendar_id: str,
        external_event_id: str,
    ) -> bool:
        """Удалить событие по UID. Возвращает True (в т.ч. если уже удалено).

        Сначала пробует прямой URL ({calendar_url}/{uid}.ics) — быстрее и надёжнее
        для серверов, которые не поддерживают calendar-query REPORT (Apple iCloud).
        Fallback — event_by_uid через REPORT.
        """
        def _delete():
            client = self._get_client(account_data)
            cal = self._get_calendar(client, calendar_id)

            # Первая попытка: прямой URL по UID (не требует REPORT)
            event_url = calendar_id.rstrip("/") + "/" + external_event_id + ".ics"
            try:
                ev_obj = caldav.CalendarObjectResource(client=client, url=event_url)
                ev_obj.delete()
                return True
            except caldav_error.NotFoundError:
                return True  # Уже удалено
            except Exception:
                pass  # Fallback: поиск через REPORT

            # Fallback: event_by_uid через REPORT
            try:
                ev_obj = cal.event_by_uid(external_event_id)
                ev_obj.delete()
                return True
            except caldav_error.NotFoundError:
                return True
            except Exception as e:
                log.warning("caldav_delete_error",
                            uid=external_event_id, error=str(e))
                return False

        return await asyncio.to_thread(_delete)

    async def refresh_token_if_needed(self, account_data: dict) -> dict | None:
        """CalDAV использует password auth — токены не обновляются."""
        return None
