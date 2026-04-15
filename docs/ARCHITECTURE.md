# Архитектура системы «До встречи»

> Последнее обновление: 15.04.2026

## Обзор

«До встречи» — Telegram Mini App для бронирования встреч, аналог Calendly.
Система обслуживает два типа пользователей: **организатор** создаёт расписания
через Telegram-бота и делится ссылкой, **гость** открывает Mini App, выбирает
свободный слот и бронирует встречу. Оба получают ссылку на видеозвонок (Jitsi Meet).

Архитектура — классический монолит из четырёх Docker-контейнеров: бот (aiogram),
API-сервер (FastAPI), фронтенд (Vanilla JS, раздаётся nginx), база данных (PostgreSQL).
Все сервисы развёрнуты на российском VPS (Timeweb) для соответствия 152-ФЗ.

## Высокоуровневая схема

```mermaid
graph LR
    TU[Telegram User] -->|команды| BOT["Bot<br/>aiogram 3.6"]
    TU -->|Mini App| FE["Frontend<br/>Vanilla JS"]
    BOT -->|HTTP + X-Internal-Key| API["Backend API<br/>FastAPI 0.111"]
    API -->|POST /internal/notify| BOT
    FE -->|fetch /api/ + X-Init-Data| NGX["nginx 1.25"]
    NGX -->|proxy_pass| API
    NGX -->|static| FE
    API -->|asyncpg| DB["PostgreSQL 16"]
    API -->|generate link| JIT["Jitsi Meet"]
    BOT -->|Telegram Bot API| TG_API["Telegram API"]
```

## Компоненты

### Bot (`bot/`)

**Назначение:** Telegram-интерфейс для организатора — создание расписаний, управление
бронированиями, просмотр статистики. Единая точка входа для пользователей.

**Технологии:** aiogram 3.6.0, aiohttp 3.9.5, Python 3.12

**Модули:** `bot.py` (инициализация), `handlers/` (команды, callbacks, FSM, `inline.py` — inline query handler для шаринга расписаний),
`services/` (notifications.py — aiohttp сервер :8080, reminders.py — фоновые напоминания),
`keyboards.py`, `formatters.py`, `states.py`, `api.py`, `config.py`

**Команды бота:**

| Команда | Описание |
|---------|----------|
| `/start` | Регистрация пользователя + главное меню |
| `/help` | Справка по использованию |

**FSM: создание расписания (CreateSchedule)**

```mermaid
stateDiagram-v2
    [*] --> title: create_schedule callback
    title --> duration: ввод названия
    duration --> buffer_time: dur_* callback
    buffer_time --> work_days: buf_* callback
    work_days --> start_time: числа 0-6
    start_time --> end_time: HH:MM
    end_time --> platform: HH:MM
    platform --> [*]: plat_* → POST /api/schedules
```

**Menu Button:** кнопка «Открыть» в чате — открывает Mini App через `MenuButtonWebApp`.
Устанавливается глобально при старте бота и per-user при `/start`.

**Уведомления:** бот принимает push-уведомления о новых бронированиях через внутренний
HTTP-сервер (aiohttp на порту 8080, endpoint `/internal/notify`). Backend отправляет
fire-and-forget POST при создании бронирования. Бот уведомляет и организатора, и гостя.

**FSM Storage:** Redis (`RedisStorage` из aiogram) с graceful fallback на `MemoryStorage` если Redis недоступен. FSM-состояния сохраняются при перезапуске бота.

**Напоминания:** фоновый цикл `reminder_loop()` каждые 5 минут проверяет
`GET /api/bookings/pending-reminders` и рассылает напоминания за 24ч и 1ч до встречи.
Каждые 15 мин вызывает `POST /api/bookings/complete-past` — переводит подтверждённые встречи в статус `completed` через 30 мин после окончания.

**ReplyKeyboard:** при `/start` бот устанавливает постоянную нижнюю панель (4 кнопки:
Создать расписание, Мои расписания, Мои встречи, Помощь).

### Backend API (`backend/`)

**Назначение:** REST API — единственный компонент с доступом к БД. Обрабатывает
CRUD расписаний и бронирований, рассчитывает свободные слоты, генерирует ссылки на встречи.

**Технологии:** FastAPI 0.111.0, asyncpg 0.29.0, pydantic 2.7.1, Python 3.12

**Модули:** `main.py` (app, lifespan, middleware), `routers/` (users, schedules, bookings,
meetings, stats, admin, `calendar.py` — 12 эндпоинтов календарной интеграции: OAuth, accounts, connections, sync, webhooks, CalDAV),
`auth.py` (initData HMAC + admin sessions), `database.py` (pool),
`schemas.py` (Pydantic-модели), `utils.py` (row_to_dict, generate_meeting_link, _notify_bot), `config.py`

**Все эндпоинты:**

| Метод | Путь | Auth | Описание | Параметры |
|-------|------|------|----------|-----------|
| GET | `/` | — | Healthcheck | — |
| GET | `/health` | — | Проверка подключения к БД | — |
| POST | `/api/users/auth` | initData | Upsert пользователя | body: `UserAuth` |
| PATCH | `/api/users/notification-settings` | initData | Обновить настройки напоминаний | body: `{settings}` |
| GET | `/api/users/{telegram_id}/avatar` | — | Проксирование аватарки из Telegram | path: telegram_id |
| GET | `/api/users/{telegram_id}` | — | Получить пользователя | path: telegram_id |
| POST | `/api/schedules` | initData | Создать расписание | body: `ScheduleCreate` |
| GET | `/api/schedules` | initData | Список расписаний пользователя | — |
| GET | `/api/schedules/{schedule_id}` | — | Детали расписания (публичный) | path: schedule_id (UUID) |
| PATCH | `/api/schedules/{schedule_id}` | initData | Обновить расписание | path: schedule_id, body: `ScheduleUpdate` |
| DELETE | `/api/schedules/{schedule_id}` | initData | Мягкое удаление (is_active=FALSE) | path: schedule_id |
| GET | `/api/available-slots/{schedule_id}` | — | Свободные слоты на дату | query: date, viewer_tz |
| POST | `/api/bookings` | optional | Создать бронирование + push | body: `BookingCreate` |
| GET | `/api/bookings` | initData | Список бронирований | query: role (organizer/guest/all) |
| GET | `/api/bookings/{booking_id}` | optional | Детали бронирования + my_role | path: booking_id |
| POST | `/api/meetings/quick` | initData | Создать встречу вручную (личная или в расписание) | body: `QuickMeetingCreate` |
| PATCH | `/api/bookings/{booking_id}/confirm` | initData | Подтвердить (организатор) | path: booking_id |
| PATCH | `/api/bookings/{booking_id}/guest-confirm` | initData | Гость подтверждает присутствие | path: booking_id |
| PATCH | `/api/bookings/{booking_id}/cancel` | initData | Отменить | path: booking_id |
| GET | `/api/bookings/confirmation-requests` | — | Встречи на сегодня для утреннего подтверждения | — |
| GET | `/api/bookings/no-answer-candidates` | — | Бронирования без ответа (>1ч после запроса) | — |
| PATCH | `/api/bookings/{booking_id}/set-no-answer` | — | Перевести в статус no_answer | path: booking_id |
| PATCH | `/api/bookings/{booking_id}/confirmation-asked` | — | Отметить что запрос подтверждения отправлен | path: booking_id |
| GET | `/api/bookings/pending-reminders` | — | Бронирования для напоминаний | query: reminder_type (24h/1h/15m/5m/morning) |
| GET | `/api/bookings/pending-reminders-v2` | — | Напоминания v2 (по настройкам пользователя) | — |
| PATCH | `/api/bookings/{booking_id}/reminder-sent` | — | Пометить напоминание отправленным | query: reminder_type |
| POST | `/api/sent-reminders` | — | Записать отправленное напоминание (v2) | body: `{booking_id, reminder_type}` |
| GET | `/api/stats` | initData | Статистика пользователя | — |
| GET | `/api/calendar/google/auth-url` | initData | URL для Google OAuth | — |
| GET | `/api/calendar/google/callback` | — | OAuth callback от Google (redirect) | query: code, state |
| GET | `/api/calendar/accounts` | initData | Список подключённых календарных аккаунтов | — |
| DELETE | `/api/calendar/accounts/{account_id}` | initData | Отключить календарный аккаунт | path: account_id |
| POST | `/api/calendar/connections/{id}/toggle` | initData | Переключить read/write для календаря | path: id, body: `CalendarConnectionToggle` |
| GET | `/api/calendar/schedules/{id}/calendar-config` | initData | Привязки календарей к расписанию | path: id |
| PUT | `/api/calendar/schedules/{id}/calendar-config` | initData | Заменить привязки календарей | path: id, body: `ScheduleCalendarConfig` |
| POST | `/api/calendar/accounts/{id}/sync` | initData | Принудительная синхронизация аккаунта | path: id |
| POST | `/api/calendar/webhook/google` | — | Webhook от Google Calendar push notifications | headers: X-Goog-* |
| POST | `/api/calendar/caldav/connect` | initData | Подключить CalDAV-провайдер (Yandex/Apple) | body: `CalDAVConnectRequest` |
| GET | `/api/calendar/external-events` | initData | Внешние события для отображения | query: from_date, to_date |

**Аутентификация:** двухканальная.
- **Mini App → Backend:** заголовок `X-Init-Data` с Telegram initData. Backend валидирует HMAC-SHA256 подпись
  через `validate_init_data()` и извлекает `user.id`. Dependency: `Depends(get_current_user)`.
- **Bot → Backend:** заголовок `X-Internal-Key` с `INTERNAL_API_KEY`. `telegram_id` передаётся в query params.
- **Публичные эндпоинты:** `get_schedule`, `available_slots`, `get_user` — без auth.
- **Опциональная auth:** `create_booking` — `Depends(get_optional_user)`, гость может быть не авторизован.

**Connection pool:** asyncpg, min_size=2, max_size=10. Создаётся при старте через lifespan,
закрывается при остановке. Dependency `db()` выдаёт соединение из пула на каждый запрос.

### Support Bot (`support-bot/`)

**Назначение:** Отдельный aiogram-бот для обратной связи — пересылка сообщений пользователей
администратору и ответов обратно. Работает как relay: пользователь пишет боту, сообщение
пересылается в admin-чат, admin отвечает reply на forward — ответ уходит пользователю.

**Технологии:** aiogram 3.x, Python 3.12

**Модули:** `bot.py` (инициализация, handlers), `config.py` (BOT_TOKEN, ADMIN_CHAT_ID, ADMIN_IDS)

**Команды:** `/start` (приветствие или admin-панель), `/stats` (статистика обращений, только admin),
`/broadcast` (рассылка всем пользователям, только admin)

**Деплой:** только в beta-стеке (`docker-compose.beta.yml`, сервис `support_bot_beta`).

### Frontend Mini App (`frontend/`)

**Назначение:** SPA для гостей (бронирование) и организаторов (просмотр встреч, расписаний).
Открывается внутри Telegram как Mini App или по прямой ссылке.

**Модули:** `index.html` (разметка), `css/style.css` (все стили),
`js/` — api.js, state.js, config.js, utils.js, nav.js, bookings.js, schedules.js,
calendar.js, quickadd.js, profile.js

**Telegram WebApp SDK — используемые методы:**

| Метод | Назначение |
|-------|-----------|
| `tg.ready()` | Сигнал готовности приложения |
| `tg.expand()` | Развернуть на весь экран |
| `tg.enableClosingConfirmation()` | Предупреждение при закрытии |
| `tg.initDataUnsafe.user` | Данные пользователя Telegram |
| `tg.BackButton.show/hide/onClick` | Нативная кнопка «Назад» |
| `tg.HapticFeedback.impactOccurred` | Вибрация при действиях |
| `tg.HapticFeedback.notificationOccurred` | Вибрация success/error |
| `tg.MainButton.*` | Кнопка действия внизу экрана |
| `tg.openLink(url)` | Открыть внешнюю ссылку |

**Экраны:**

| Экран | ID | Назначение |
|-------|----|-----------|
| Главная | `screen-home` | Приветствие, статистика, меню |
| Календарь | `screen-calendar` | Выбор даты и времени для бронирования |
| Форма | `screen-form` | Ввод данных гостя (имя, контакт, заметки) |
| Успех | `screen-success` | Подтверждение бронирования, ссылка на встречу |
| Встречи | `screen-meetings` | Список встреч (предстоящие / история) |
| Детали | `screen-detail` | Детали конкретной встречи |
| Расписания | `screen-schedules` | Список расписаний организатора |
| Настройки | `screen-settings` | Профиль, уведомления |

**Навигация между экранами:**

```mermaid
flowchart TD
    HOME[home] -->|Мои встречи| MEETINGS[meetings]
    HOME -->|Мои расписания| SCHEDULES[schedules]
    HOME -->|Настройки| SETTINGS[settings]
    HOME -->|schedule_id в URL| CALENDAR[calendar]
    CALENDAR -->|выбор даты/времени| FORM[form]
    FORM -->|бронирование| SUCCESS[success]
    SUCCESS -->|Главная| HOME
    MEETINGS -->|Подробнее| DETAIL[detail]
    DETAIL -->|Назад| MEETINGS
```

**Взаимодействие с API:**

| Экран | Эндпоинт | Действие |
|-------|----------|----------|
| home | GET `/api/stats` | Загрузка статистики |
| home | POST `/api/users/auth` | Аутентификация |
| calendar | GET `/api/schedules/{id}` | Загрузка расписания |
| calendar | GET `/api/available-slots/{id}` | Слоты на дату (батчами по 8) |
| form | POST `/api/bookings` | Создание бронирования |
| meetings | GET `/api/bookings` | Список встреч |
| meetings | PATCH `/api/bookings/{id}/cancel` | Отмена встречи |
| schedules | GET `/api/schedules` | Список расписаний |
| schedules | DELETE `/api/schedules/{id}` | Удаление расписания |

### База данных (PostgreSQL 16)

```mermaid
erDiagram
    users ||--o{ schedules : "has"
    users ||--o{ calendar_accounts : "connects"
    schedules ||--o{ bookings : "receives"
    schedules ||--o{ schedule_calendar_rules : "configured"
    calendar_accounts ||--o{ calendar_connections : "contains"
    calendar_connections ||--o{ schedule_calendar_rules : "linked"
    calendar_connections ||--o{ external_busy_slots : "caches"
    calendar_connections ||--o{ event_mapping : "maps"
    bookings ||--o{ event_mapping : "synced"
    bookings ||--o{ sent_reminders : "tracked"

    users {
        UUID id PK
        BIGINT telegram_id UK
        TEXT username
        TEXT first_name
        TEXT last_name
        TEXT timezone
        TIMESTAMPTZ created_at
        TIMESTAMPTZ updated_at
    }

    schedules {
        UUID id PK
        UUID user_id FK
        TEXT title
        TEXT description
        INTEGER duration
        INTEGER buffer_time
        INTEGER_ARRAY work_days
        TIME start_time
        TIME end_time
        TEXT location_mode
        TEXT platform
        TEXT location_address
        BOOLEAN requires_confirmation
        BOOLEAN is_active
        BOOLEAN is_default
        INTEGER min_booking_advance
        TIMESTAMPTZ created_at
        TIMESTAMPTZ updated_at
    }

    bookings {
        UUID id PK
        UUID schedule_id FK
        TEXT guest_name
        TEXT guest_contact
        BIGINT guest_telegram_id
        TIMESTAMPTZ scheduled_time
        TEXT status "pending|confirmed|cancelled|completed|no_answer"
        TEXT meeting_link
        TEXT notes
        TEXT platform
        TEXT location_address
        BOOLEAN blocks_slots
        BOOLEAN confirmation_asked
        TIMESTAMPTZ confirmation_asked_at
        BOOLEAN reminder_24h_sent
        BOOLEAN reminder_1h_sent
        BOOLEAN reminder_15m_sent
        BOOLEAN reminder_5m_sent
        BOOLEAN morning_reminder_sent
        TEXT title
        TIMESTAMPTZ end_time
        BOOLEAN is_manual
        BIGINT created_by
        TIMESTAMPTZ created_at
        TIMESTAMPTZ updated_at
    }

    calendar_accounts {
        UUID id PK
        UUID user_id FK
        TEXT provider "google|yandex|apple|outlook"
        TEXT provider_email
        TEXT access_token_encrypted
        TEXT refresh_token_encrypted
        TIMESTAMPTZ token_expires_at
        TEXT caldav_url
        TEXT caldav_username
        TEXT caldav_password_encrypted
        TEXT status "active|expired|revoked|error"
        TEXT last_error
        TIMESTAMPTZ last_sync_at
        TIMESTAMPTZ created_at
        TIMESTAMPTZ updated_at
    }

    calendar_connections {
        UUID id PK
        UUID account_id FK
        TEXT external_calendar_id
        TEXT calendar_name
        TEXT calendar_color
        BOOLEAN is_visible
        BOOLEAN is_read_enabled
        BOOLEAN is_write_target
        BOOLEAN is_display_enabled
        TEXT sync_token
        TIMESTAMPTZ last_sync_at
        TEXT webhook_channel_id
        TEXT webhook_resource_id
        TIMESTAMPTZ webhook_expires_at
        TIMESTAMPTZ created_at
        TIMESTAMPTZ updated_at
    }

    schedule_calendar_rules {
        UUID id PK
        UUID schedule_id FK
        UUID connection_id FK
        BOOLEAN use_for_blocking
        BOOLEAN use_for_writing
        TIMESTAMPTZ created_at
    }

    external_busy_slots {
        UUID id PK
        UUID connection_id FK
        TEXT external_event_id
        TEXT summary
        TIMESTAMPTZ start_time
        TIMESTAMPTZ end_time
        BOOLEAN is_all_day
        TEXT etag
        JSONB raw_data
        TIMESTAMPTZ fetched_at
        TIMESTAMPTZ updated_at
    }

    event_mapping {
        UUID id PK
        UUID booking_id FK
        UUID connection_id FK
        TEXT external_event_id
        TEXT external_event_url
        TEXT sync_status "synced|pending|error|deleted"
        TEXT sync_direction "outbound|inbound"
        TIMESTAMPTZ last_synced_at
        TEXT last_error
        TEXT etag
        TIMESTAMPTZ created_at
        TIMESTAMPTZ updated_at
    }

    sync_log {
        UUID id PK
        UUID account_id FK
        UUID connection_id FK
        TEXT action
        TEXT status
        JSONB details
        TEXT error_message
        TIMESTAMPTZ created_at
    }

    sent_reminders {
        UUID id PK
        UUID booking_id FK
        TEXT reminder_type
        TIMESTAMPTZ sent_at
    }
```

**Индексы:** 7 B-tree индексов на FK и часто фильтруемые поля (telegram_id, schedule_id, status, scheduled_time).

**View:** `bookings_detail` — JOIN bookings + schedules + users для денормализованного чтения.

**Триггеры:** `trigger_set_updated_at()` — автообновление `updated_at` на всех таблицах.

### Инфраструктура

**Docker-compose сервисы:**

| Сервис | Образ | Порты | Volumes |
|--------|-------|-------|---------|
| postgres | postgres:16-alpine | — (internal) | postgres_data, init.sql, migrations/ |
| redis | redis:7-alpine (ECR Public) | — (internal) | redis_data |
| backend | python:3.12-slim (custom, non-root) | 8000 (internal) | — |
| bot | python:3.12-slim (custom, non-root) | 8080 (internal) | — |
| nginx | nginx:1.25-alpine (custom) | 80, 443 | nginx.conf, frontend/, admin/, certbot certs |
| certbot | certbot/certbot:latest | — (профиль ssl) | certbot_www, certbot_certs |
| support_bot_beta | python:3.12-slim (custom) | — | — (только в beta docker-compose) |

**nginx routing:**

| Путь | Upstream | Rate limit | Описание |
|------|---------|------------|----------|
| `/` | filesystem | — | Статика из `/usr/share/nginx/html` (frontend) |
| `/admin/` | filesystem | — | Админ-панель SPA, `X-Robots-Tag: noindex` |
| `/api/admin/auth/` | `http://backend:8000` | 3 req/min, burst=2 | Auth-эндпоинты с жёстким лимитом |
| `/api/admin/` | `http://backend:8000` | 5 req/s, burst=10 | Все admin API-эндпоинты |
| `/api/events` | `http://backend:8000` | 10 req/s, burst=20 | Event tracking из Mini App |
| `/api/*` | `http://backend:8000` | 10 req/s, burst=20 | Проксирование API-запросов |
| `/api/bookings` | `http://backend:8000` | 5 req/min, burst=3 | Отдельный лимит на бронирование |
| `/health` | `http://backend:8000/health` | — | Healthcheck |
| `/.well-known/acme-challenge/` | filesystem | — | Let's Encrypt challenge |

**SSL:** Let's Encrypt через certbot. HTTP (80) → редирект на HTTPS (443). TLS 1.2 + 1.3.

**Security headers:** HSTS (max-age=31536000), CSP (default-src 'self', script-src telegram.org),
X-Content-Type-Options: nosniff, Referrer-Policy: strict-origin-when-cross-origin,
Permissions-Policy (camera, microphone, geolocation disabled). `server_tokens off`.

**Переменные окружения:**

| Переменная | Сервис | Описание |
|-----------|--------|----------|
| `BOT_TOKEN` | backend, bot | Токен Telegram-бота (нужен обоим для HMAC валидации) |
| `MINI_APP_URL` | backend, bot | URL фронтенда Mini App |
| `INTERNAL_API_KEY` | backend, bot | Ключ для аутентификации бот↔backend |
| `BOT_INTERNAL_URL` | backend | URL HTTP-сервера бота (default: `http://bot:8080`) |
| `BACKEND_API_URL` | bot | URL backend (default: `http://backend:8000`) |
| `DATABASE_URL` | backend | PostgreSQL connection string |
| `SECRET_KEY` | backend | Секретный ключ |
| `POSTGRES_DB` | postgres | Имя БД (default: `dovstrechi`) |
| `POSTGRES_USER` | postgres | Пользователь (default: `dovstrechi`) |
| `POSTGRES_PASSWORD` | postgres | Пароль PostgreSQL |
| `ADMIN_TELEGRAM_ID` | backend | Telegram ID администратора (единственный допустимый) |
| `ADMIN_SESSION_TTL_HOURS` | backend | Время жизни admin-сессии (default: 2) |
| `ADMIN_IP_ALLOWLIST` | backend | Белый список IP (через запятую, пусто = любой) |
| `ANONYMIZE_SALT` | backend | Соль для SHA256-анонимизации telegram_id |

## Admin API

Внутренняя админ-панель. Все `/api/admin/*` эндпоинты (кроме login) защищены cookie-based сессией через `Depends(get_admin_user)`. Доступ только для `ADMIN_TELEGRAM_ID`.

### Аутентификация

| Метод | Путь | Auth | Описание |
|-------|------|------|----------|
| POST | `/api/admin/auth/login` | Telegram Login Widget | Вход: HMAC-SHA256 верификация → cookie `admin_session` |
| POST | `/api/admin/auth/logout` | cookie | Деактивация сессии, удаление cookie |
| GET | `/api/admin/auth/me` | cookie | Данные текущей сессии |

### Dashboard

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/admin/dashboard/summary` | 6 метрик: users, active_7d, bookings, today, errors_24h, pending |
| GET | `/api/admin/dashboard/bookings-trend?days=30` | Бронирования по дням за N дней |
| GET | `/api/admin/dashboard/platforms` | Распределение расписаний по платформам |

### Logs (app_events)

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/admin/logs` | Пагинированный список событий с фильтрами (event_type, severity, date, search) |
| GET | `/api/admin/logs/stats` | Агрегация за 24ч: by_severity, by_type, unique_users |

### Tasks (Kanban)

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/admin/tasks` | Все задачи, сгруппированные по статусу (backlog/in_progress/done) |
| POST | `/api/admin/tasks` | Создать задачу |
| PATCH | `/api/admin/tasks/reorder` | Перестановка задач в колонке |
| PATCH | `/api/admin/tasks/{id}` | Обновить задачу (при смене status — пересчёт priority) |
| DELETE | `/api/admin/tasks/{id}` | Физическое удаление задачи |

### Audit Log

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/admin/audit-log` | Пагинированный лог действий администратора |

### System & Maintenance

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/admin/system/info` | Версия, uptime, pool stats, счётчики, окружение (без секретов) |
| POST | `/api/admin/sessions/invalidate-all` | Деактивировать все сессии кроме текущей |
| POST | `/api/admin/maintenance/cleanup-events` | Удалить info/warn события старше N дней (error/critical защищены) |

### Event Tracking (публичный)

| Метод | Путь | Auth | Описание |
|-------|------|------|----------|
| POST | `/api/events` | optional initData | Трекинг событий из Mini App (анонимизированный) |

### Admin Panel (Frontend)

**Расположение:** `admin/` — SPA, раздаётся nginx с `/admin/`. Модули: `index.html` (разметка),
`css/admin.css` (стили), `js/` — config.js, auth.js, dashboard.js, logs.js, tasks.js, settings.js.

**Auth flow:**
1. Пользователь открывает `/admin/` → JS проверяет `GET /api/admin/auth/me`
2. Если 401 → экран логина с Telegram Login Widget
3. Нажатие "Log in with Telegram" → Telegram OAuth → `onTelegramAuth(user)`
4. JS отправляет `POST /api/admin/auth/login` с данными от Telegram
5. Backend верифицирует HMAC, проверяет `telegram_id == ADMIN_TELEGRAM_ID`, создаёт сессию
6. Cookie `admin_session` устанавливается (HttpOnly, Secure, SameSite=Strict, path=/api/admin)
7. JS переключает на экран дашборда

**SPA-навигация:** hash-роутинг (#dashboard, #logs, #tasks, #settings).

**Rate limiting:** auth — 3 req/min (nginx) + 3 attempts/5min (backend in-memory), прочие admin — 5 req/s.

## Основные потоки данных

### Создание расписания (организатор)

```mermaid
sequenceDiagram
    participant O as Организатор
    participant B as Bot (aiogram)
    participant API as Backend (FastAPI)
    participant DB as PostgreSQL

    O->>B: /start
    B->>API: POST /api/users/auth
    API->>DB: INSERT users ON CONFLICT UPDATE
    DB-->>API: user record
    API-->>B: user JSON
    B-->>O: Главное меню

    O->>B: callback "create_schedule"
    B-->>O: FSM: title → duration → buffer → days → time → platform
    O->>B: вводит данные по шагам

    B->>API: POST /api/schedules
    API->>DB: INSERT schedules
    DB-->>API: schedule record
    API-->>B: schedule JSON
    B-->>O: Расписание создано + ссылка для клиентов
```

### Бронирование встречи (гость)

```mermaid
sequenceDiagram
    participant G as Гость
    participant FE as Mini App (Frontend)
    participant NGX as nginx
    participant API as Backend (FastAPI)
    participant DB as PostgreSQL
    participant BOT2 as Bot (aiogram)
    participant TG2 as Telegram API

    G->>FE: Открывает ссылку ?schedule_id=UUID
    FE->>NGX: GET /api/schedules/{id}
    NGX->>API: proxy
    API->>DB: SELECT schedules
    DB-->>API: schedule
    API-->>FE: schedule JSON

    FE->>NGX: GET /api/available-slots/{id}?date=...
    NGX->>API: proxy
    API->>DB: SELECT bookings WHERE date
    DB-->>API: booked times
    API-->>FE: available_slots JSON

    G->>FE: Выбирает дату и время
    G->>FE: Заполняет форму (имя, контакт)
    FE->>NGX: POST /api/bookings (X-Init-Data)
    NGX->>API: proxy
    API->>DB: CHECK conflict → INSERT bookings
    Note over API: generate_meeting_link (Jitsi)
    DB-->>API: booking record
    API-->>FE: booking JSON + meeting_link
    FE-->>G: Экран успеха + ссылка на встречу

    Note over API: fire-and-forget
    API->>BOT2: POST /internal/notify
    BOT2->>TG2: Уведомление организатору
    BOT2->>TG2: Уведомление гостю
```

> **Примечание:** BOT2/TG2 в диаграмме — это бот-сервис и Telegram API,
> показаны отдельно для наглядности потока уведомлений.

### Утреннее подтверждение (Morning Confirmation Flow)

```mermaid
sequenceDiagram
    participant BOT as Bot (reminder_loop)
    participant API as Backend (FastAPI)
    participant DB as PostgreSQL
    participant G as Гость
    participant O as Организатор

    Note over BOT: Каждые 5 мин, после 09:00 в TZ организатора

    BOT->>API: GET /api/bookings/confirmation-requests
    API->>DB: SELECT confirmed bookings на сегодня<br/>WHERE confirmation_asked = FALSE
    DB-->>API: bookings list
    API-->>BOT: {bookings: [...]}

    loop Для каждого бронирования
        BOT->>G: "Вы придёте на встречу?" (кнопки: Да / Отменить)
        BOT->>API: PATCH /api/bookings/{id}/confirmation-asked
    end

    alt Гость подтверждает
        G->>BOT: callback "Да, приду"
        BOT->>API: PATCH /api/bookings/{id}/guest-confirm
        API->>DB: UPDATE status = 'confirmed'
        BOT->>O: "Гость подтвердил присутствие"
    else Гость отменяет
        G->>BOT: callback "Отменить"
        BOT->>API: PATCH /api/bookings/{id}/cancel
        BOT->>O: "Гость отменил встречу"
    else Нет ответа >1ч
        BOT->>API: GET /api/bookings/no-answer-candidates
        API-->>BOT: bookings без ответа
        BOT->>API: PATCH /api/bookings/{id}/set-no-answer
        API->>DB: UPDATE status = 'no_answer'
        BOT->>O: "Гость не ответил на подтверждение"
    end
```

### Подтверждение / отмена встречи

```mermaid
sequenceDiagram
    participant O as Организатор
    participant B as Bot / Mini App
    participant API as Backend (FastAPI)
    participant DB as PostgreSQL

    O->>B: callback "confirm_{id}" или "cancel_{id}"
    B->>API: PATCH /api/bookings/{id}/confirm или /cancel
    API->>DB: UPDATE bookings SET status
    Note over API: Проверка: организатор — свои,<br/>гость — только свои
    DB-->>API: updated booking
    API-->>B: booking JSON
    B-->>O: Статус обновлён
```

### Уведомления

**Push-уведомления о новых бронированиях:**
1. Гость создаёт бронирование → backend POST `/api/bookings`
2. Backend отправляет fire-and-forget `POST http://bot:8080/internal/notify` с данными бронирования
3. Бот (`handle_new_booking`) отправляет сообщение организатору (с кнопками ✅/❌) и гостю

**Напоминания о предстоящих встречах:**
1. Фоновый цикл `reminder_loop()` в боте — каждые 5 минут
2. Запрашивает `GET /api/bookings/pending-reminders?reminder_type=24h|1h`
3. Backend возвращает confirmed бронирования с `reminder_*_sent = FALSE` в нужном временном окне
4. Бот отправляет напоминание организатору и гостю
5. Помечает отправленным: `PATCH /api/bookings/{id}/reminder-sent?reminder_type=24h|1h`

**Таймзоны:** все даты/времена в уведомлениях форматируются в таймзоне организатора
(`users.timezone`, default 'UTC') через `format_dt(dt_str, tz=...)`.
