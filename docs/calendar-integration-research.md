# Интеграция внешних календарей — «До встречи»

Полный ресёрч, архитектура, модели данных, стратегия синхронизации и план реализации.

---

## 1. Резюме подхода

Система интеграции строится на двух абстракциях:

**Calendar Abstraction Layer** — единый интерфейс для всех провайдеров. Каждый провайдер реализует адаптер с методами: `list_calendars()`, `read_events()`, `create_event()`, `update_event()`, `delete_event()`.

**Sync Engine** — фоновый воркер для двусторонней синхронизации: чтение busy-слотов + запись бронирований.

Порядок внедрения:
- **Phase 1 (MVP):** Google Calendar — лучший API, webhooks, Python SDK
- **Phase 2:** Multi-calendar + priority logic
- **Phase 3:** CalDAV (Yandex + Apple) через `python-caldav`
- **Phase 4:** Microsoft Outlook (Graph API)

---

## 2. Ресёрч провайдеров

### 2.1 Google Calendar API v3

| Параметр | Значение |
|----------|----------|
| Аутентификация | OAuth 2.0 (authorization code flow) |
| Python SDK | `google-api-python-client`, `google-auth-oauthlib` |
| Scopes | `calendar.readonly` (чтение), `calendar.events` (R/W) |
| Чтение | `events.list()` с `timeMin/timeMax`, `singleEvents=True` |
| Создание | `events.insert()` |
| Обновление | `events.update()` / `events.patch()` |
| Удаление | `events.delete()` |
| Webhooks | Push notifications через `events.watch()` — POST на HTTPS endpoint |
| Webhook TTL | ~7 дней, нужно обновлять |
| Webhook payload | Только "что-то изменилось" (без деталей), далее `events.list(updatedMin=...)` |
| Sync tokens | `nextSyncToken` / `nextPageToken` |
| Rate limits | 1,000,000 запросов/день; per-user per-minute лимиты |
| Free/Busy | `freebusy.query()` — batch-запрос по нескольким календарям |
| Recurring | RRULE, развёртка через `singleEvents=True` |

Особенности: лучший API, OAuth верификация для production, refresh token ~6 мес при неактивности, webhook требует SSL.

### 2.2 Yandex Calendar

| Параметр | Значение |
|----------|----------|
| Протокол | CalDAV (RFC 4791) |
| Аутентификация | App-specific password ИЛИ OAuth token |
| CalDAV URL | `https://caldav.yandex.ru/` |
| Python библиотека | `python-caldav` (pip install caldav) — async через `caldav.aio` |
| CRUD | CalDAV REPORT / PUT .ics / DELETE |
| Webhooks | НЕ поддерживается |
| Rate limits | Агрессивные (60 сек/МБ с 2021), write → 504 timeout |
| Sync | `sync-collection` REPORT (ETag-based) |
| Телемост | Проприетарное свойство `X-TELEMOST-REQUIRED` |

Особенности: нет REST API, app password через Яндекс ID, агрессивный rate limiting, нет webhooks.

### 2.3 Apple Calendar (iCloud)

| Параметр | Значение |
|----------|----------|
| Протокол | CalDAV |
| Аутентификация | Basic Auth + app-specific password (16 символов) |
| CalDAV URL | `https://caldav.icloud.com/` → `pXX-caldav.icloud.com` |
| OAuth | НЕ поддерживается |
| Webhooks | НЕ поддерживается |
| PATCH | НЕ поддерживается — только полный PUT |

Особенности: самый ограниченный API, пользователь создаёт app password на appleid.apple.com, 2FA обязательна.

### 2.4 Microsoft Outlook (Graph API)

| Параметр | Значение |
|----------|----------|
| API | Microsoft Graph v1.0 |
| Аутентификация | OAuth 2.0 (Azure AD) |
| Endpoints | `/me/events`, `/me/calendars/{id}/events` |
| Webhooks | `POST /subscriptions`, TTL ~71 часов |
| Rate limits | 10,000/10мин |
| Sync | Delta queries (`/calendarView/delta`) |

Особенности: мощный REST API, Azure AD регистрация, webhook информативнее Google.

### Сравнительная таблица

| Фича | Google | Yandex | Apple | Outlook |
|------|--------|--------|-------|---------|
| API | REST | CalDAV | CalDAV | REST |
| OAuth | ✅ | ✅/app pwd | ❌ | ✅ |
| Webhooks | ✅ 7д | ❌ | ❌ | ✅ 3д |
| Sync tokens | ✅ | ETag | ETag | ✅ delta |
| Rate limits | 1M/д | Агрессивные | Умеренные | 10K/10м |
| Сложность | Средняя | Средняя | Высокая (UX) | Высокая (Azure) |

---

## 3. Архитектура

### 3.1 Компоненты

```
Frontend (Mini App)
  │ Calendar Connect UI / Selection UI / Schedule Config
  ▼
Backend API (FastAPI)
  │ /api/calendar/* endpoints
  ▼
Calendar Integration Service
  ├── Calendar Abstraction Layer
  │   ├── Google Adapter (REST)
  │   ├── CalDAV Adapter (Yandex + Apple)
  │   └── Outlook Adapter (Graph API)
  └── Sync Engine
      ├── Read busy slots (webhook/polling)
      ├── Write bookings → external calendar
      ├── Duplicate prevention (event_mapping)
      └── Conflict resolution (internal = source of truth)
  ▼
PostgreSQL
  calendar_accounts, calendar_connections, external_busy_slots,
  event_mapping, schedule_calendar_rules, sync_log
```

### 3.2 Принцип работы

1. Подключение → OAuth/credentials → tokens в БД (encrypted)
2. Выбор календарей → привязка к расписаниям
3. `GET /available-slots` → internal bookings + external busy slots
4. `POST /bookings` → создать в БД + записать в priority-календарь + event_mapping
5. Background sync → обновление busy-слотов, webhook processing

---

## 4. Модели данных (SQL)

```sql
-- Подключённые аккаунты
CREATE TABLE calendar_accounts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,                -- google/yandex/apple/outlook
    provider_email TEXT,
    access_token_encrypted TEXT,
    refresh_token_encrypted TEXT,
    token_expires_at TIMESTAMPTZ,
    caldav_url TEXT,                        -- для CalDAV провайдеров
    caldav_username TEXT,
    caldav_password_encrypted TEXT,
    status TEXT NOT NULL DEFAULT 'active',  -- active/expired/revoked/error
    last_error TEXT,
    last_sync_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_cal_acc_user ON calendar_accounts(user_id);
CREATE UNIQUE INDEX idx_cal_acc_uniq ON calendar_accounts(user_id, provider, provider_email);

-- Календари в аккаунте
CREATE TABLE calendar_connections (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    account_id UUID NOT NULL REFERENCES calendar_accounts(id) ON DELETE CASCADE,
    external_calendar_id TEXT NOT NULL,
    calendar_name TEXT NOT NULL,
    calendar_color TEXT,
    is_visible BOOLEAN NOT NULL DEFAULT TRUE,
    is_read_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    is_write_target BOOLEAN NOT NULL DEFAULT FALSE,
    sync_token TEXT,
    last_sync_at TIMESTAMPTZ,
    webhook_channel_id TEXT,
    webhook_resource_id TEXT,
    webhook_expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_cal_conn_acc ON calendar_connections(account_id);

-- Привязка к расписаниям
CREATE TABLE schedule_calendar_rules (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    schedule_id UUID NOT NULL REFERENCES schedules(id) ON DELETE CASCADE,
    connection_id UUID NOT NULL REFERENCES calendar_connections(id) ON DELETE CASCADE,
    use_for_blocking BOOLEAN NOT NULL DEFAULT TRUE,
    use_for_writing BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX idx_scr_uniq ON schedule_calendar_rules(schedule_id, connection_id);

-- Кэш busy-слотов
CREATE TABLE external_busy_slots (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    connection_id UUID NOT NULL REFERENCES calendar_connections(id) ON DELETE CASCADE,
    external_event_id TEXT NOT NULL,
    summary TEXT,
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ NOT NULL,
    is_all_day BOOLEAN NOT NULL DEFAULT FALSE,
    etag TEXT,
    raw_data JSONB,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_ebs_conn ON external_busy_slots(connection_id);
CREATE INDEX idx_ebs_time ON external_busy_slots(start_time, end_time);
CREATE UNIQUE INDEX idx_ebs_uniq ON external_busy_slots(connection_id, external_event_id);

-- Маппинг бронирований → внешние события
CREATE TABLE event_mapping (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    booking_id UUID NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,
    connection_id UUID NOT NULL REFERENCES calendar_connections(id) ON DELETE CASCADE,
    external_event_id TEXT NOT NULL,
    external_event_url TEXT,
    sync_status TEXT NOT NULL DEFAULT 'synced',   -- synced/pending/error/deleted
    sync_direction TEXT NOT NULL DEFAULT 'outbound',
    last_synced_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_error TEXT,
    etag TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX idx_em_uniq ON event_mapping(booking_id, connection_id);
CREATE INDEX idx_em_ext ON event_mapping(connection_id, external_event_id);

-- Логи
CREATE TABLE sync_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    account_id UUID REFERENCES calendar_accounts(id) ON DELETE SET NULL,
    connection_id UUID REFERENCES calendar_connections(id) ON DELETE SET NULL,
    action TEXT NOT NULL,
    status TEXT NOT NULL,
    details JSONB,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_sl_acc ON sync_log(account_id);
CREATE INDEX idx_sl_created ON sync_log(created_at);
```

ER: `users → calendar_accounts → calendar_connections → {schedule_calendar_rules ↔ schedules, external_busy_slots, event_mapping ↔ bookings}`

---

## 5. Стратегия синхронизации

**Hybrid:** Webhooks (Google/Outlook) + Polling fallback (все).

| Провайдер | Primary | Fallback |
|-----------|---------|----------|
| Google | Webhook | Polling 15 мин |
| Outlook | Webhook | Polling 15 мин |
| Yandex | Polling 10 мин | — |
| Apple | Polling 10 мин | — |

**Duplicate prevention:** UNIQUE constraints + idempotency checks + ETag comparison.

**Conflict resolution:** Internal = Source of Truth. Бронирования у нас overwrite внешний календарь.

---

## 6. Фазированный план

### Phase 1 — Google Calendar MVP (4-5 недель)
- SQL миграция (6 таблиц)
- Token encryption (Fernet)
- Calendar Abstraction Layer (base class)
- Google adapter
- OAuth flow (auth + callback endpoints)
- CRUD endpoints (accounts, connections)
- Modified available_slots (+ external busy)
- Modified create_booking (+ write to Google + mapping)
- Background sync (polling 15 мин)
- Webhook endpoint
- Frontend: экран календарей, OAuth popup, busy-слоты

### Phase 2 — Multi-calendar + Priority (2-3 недели)
- Per-schedule calendar config API
- Incremental sync (sync tokens)
- Google webhook renewal
- Modified cancel_booking (delete external)
- Frontend: per-schedule UI, priority selection

### Phase 3 — CalDAV: Yandex + Apple (3-4 недели)
- CalDAV adapter (`python-caldav` async)
- Yandex OAuth + Apple app-password flows
- CalDAV polling sync (sync-collection)
- ICS event creation
- Frontend: connect flows, instructions

### Phase 4 — Outlook + масштабирование (3-4 недели)
- Microsoft Graph adapter
- Azure AD OAuth
- Outlook webhooks
- Мониторинг и оптимизация

---

## 7. Технологии

| Компонент | Технология |
|-----------|-----------|
| Google | `google-api-python-client` + `google-auth-oauthlib` |
| CalDAV | `python-caldav[async]` v3.x |
| Outlook | `httpx` (прямые HTTP к Graph API) |
| Encryption | `cryptography` (Fernet) |
| Background | `asyncio.create_task()` + `aiocron` |
| iCal | `icalendar` (pip) |

---

## 8. Риски

| Риск | Митигация |
|------|-----------|
| Token expiration | Auto-refresh; уведомление при revoke |
| Yandex rate limits | Backoff; batch; FreeBusy API |
| Дубликаты | UNIQUE constraints; idempotency |
| Race conditions | Advisory locks; SELECT FOR UPDATE |
| Webhook failure | Polling fallback |
| 152-ФЗ | Все данные на Timeweb VPS |
| Apple auth UX | Подробные инструкции |
