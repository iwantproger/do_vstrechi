# CLAUDE.md

> Последнее обновление: 15.04.2026

## Что это за проект

«До встречи» — Telegram Mini App для бронирования встреч (аналог Calendly).
Два типа пользователей: **организатор** (создаёт расписания и делится ссылкой)
и **гость** (открывает ссылку, выбирает слот и бронирует встречу).
Основной флоу: организатор создаёт расписание через бота → получает ссылку →
гость открывает Mini App → выбирает дату/время → бронирует → оба получают ссылку на звонок.

## Структура репозитория

```
do_vstrechi/
├── backend/                # FastAPI-приложение (API + БД)
│   ├── main.py             # ~140 строк: app, lifespan, middleware, healthcheck
│   ├── config.py           # Переменные окружения
│   ├── database.py         # Connection pool asyncpg + dependency db()
│   ├── auth.py             # Telegram initData validation + admin session auth
│   ├── schemas.py          # Pydantic-модели запросов/ответов
│   ├── utils.py            # row_to_dict, generate_meeting_link, _notify_bot
│   ├── routers/            # API-эндпоинты по модулям
│   │   ├── users.py        # /api/users/*
│   │   ├── schedules.py    # /api/schedules/*, /api/available-slots/*
│   │   ├── bookings.py     # /api/bookings/*
│   │   ├── meetings.py     # /api/meetings/quick
│   │   ├── calendar.py     # /calendar/* (Google OAuth, CalDAV, sync, webhooks)
│   │   ├── stats.py        # /api/stats
│   │   └── admin.py        # /api/admin/*, /api/events
│   ├── requirements.txt    # Python-зависимости backend
│   └── Dockerfile
├── bot/                    # Telegram-бот на aiogram 3.x
│   ├── bot.py              # ~70 строк: Bot init, router includes, lifespan
│   ├── config.py           # BOT_TOKEN, BACKEND_API_URL, INTERNAL_API_KEY
│   ├── api.py              # HTTP helper (auto X-Internal-Key)
│   ├── states.py           # CreateSchedule FSM StatesGroup
│   ├── keyboards.py        # Все клавиатуры (Reply + Inline)
│   ├── formatters.py       # format_dt, STATUS_EMOJI, format_booking
│   ├── handlers/           # Обработчики команд и callback
│   │   ├── start.py        # /start, /help, deep link notify_*
│   │   ├── navigation.py   # main_menu, my_schedules, my_bookings, stats
│   │   ├── schedules.py    # Детали, шаринг, удаление расписания
│   │   ├── bookings.py     # Детали, подтверждение, отмена, guest_confirm/cancel
│   │   ├── create.py       # FSM: создание расписания
│   │   └── inline.py       # Inline-режим: поиск расписаний через @bot
│   ├── services/           # Фоновые сервисы
│   │   ├── notifications.py # aiohttp сервер :8080, handle_new_booking
│   │   └── reminders.py    # reminder_loop, send_reminder
│   ├── requirements.txt    # Python-зависимости бота
│   └── Dockerfile
├── frontend/               # Telegram Mini App (SPA)
│   ├── index.html          # HTML-разметка
│   ├── css/style.css       # Все стили
│   └── js/                 # JS-модули
│       ├── api.js, state.js, config.js, utils.js, nav.js
│       ├── bookings.js, schedules.js, calendar.js
│       ├── quickadd.js, profile.js
├── admin/                  # Админ-панель (SPA)
│   ├── index.html          # HTML-разметка
│   ├── css/admin.css       # Все стили
│   └── js/                 # JS-модули
│       ├── config.js, auth.js, dashboard.js
│       ├── logs.js, tasks.js, settings.js
├── database/               # Инициализация и миграции БД
│   ├── init.sql            # Схема: таблицы, индексы, триггеры, view
│   └── migrations/         # Инкрементальные SQL-миграции
│       ├── 002_add_timezone.sql
│       ├── 003_add_reminder_flags.sql
│       ├── 004_admin_tables.sql
│       ├── 004_quick_add_meeting.sql
│       ├── 005_min_booking_advance.sql
│       ├── 006_requires_confirmation.sql
│       ├── 007_more_reminder_flags.sql
│       ├── 008_calendar_integration.sql
│       ├── 008_no_answer_status.sql
│       ├── 009_display_enabled.sql
│       ├── 010_notifications_v2.sql
│       ├── 011_offline_platform.sql
│       └── 012_blocks_slots.sql
├── nginx/                  # Reverse proxy
│   ├── nginx.conf          # Конфиг: SSL, rate limiting, security headers
│   └── Dockerfile
├── design/                 # Дизайн-макеты и прототипы (HTML, SVG, PDF)
├── docs/                   # Техническая документация
│   ├── ARCHITECTURE.md     # Архитектура и диаграммы
│   ├── DATA_MODELS.md      # ER-диаграммы, схема БД, Pydantic-модели
│   ├── MODULES.md          # Описание модулей и функций
│   ├── DECISIONS.md        # Архитектурные решения, техдолг
│   ├── SECURITY.md         # Аудит безопасности
│   ├── DEPLOYMENT.md       # Правила деплоя (beta-first, подробно)
│   ├── AGENTS.md           # Обязательные правила для AI-агентов
│   └── incidents/          # Разборы инцидентов (postmortem)
│       └── INC_001_NGINX_GRAY_SCREEN.md
├── support-bot/            # Бот поддержки (пересылка сообщений админу)
│   ├── bot.py              # Основная логика (aiogram 3.x)
│   ├── config.py           # SUPPORT_BOT_TOKEN, ADMIN_CHAT_ID, ADMIN_IDS
│   ├── requirements.txt    # Python-зависимости
│   └── Dockerfile
├── .github/workflows/
│   ├── deploy-prod.yml     # CI/CD: деплой в production при push в main
│   └── deploy-beta.yml     # CI/CD: автодеплой на beta при push в dev
├── docker-compose.yml      # Оркестрация prod-сервисов
├── docker-compose.beta.yml # Beta-стек (отдельная БД, отдельный бот)
├── Makefile                # Команды управления проектом
├── .env.example            # Шаблон переменных окружения (prod)
├── .env.beta.example       # Шаблон переменных для beta
├── CHANGELOG.md            # История релизов (semver)
├── CHANGELOG_USER.md       # История обновлений для пользователей приложения
└── .gitignore
```

## Быстрый старт

```bash
cp .env.example .env
# Заполни .env реальными значениями (см. раздел «Переменные окружения»)
make up          # Запустить все сервисы
make logs        # Посмотреть логи
```

## Все команды

| Команда | Что делает |
|---------|-----------|
| `make up` | Запустить все сервисы (`docker compose up -d`) |
| `make down` | Остановить все сервисы |
| `make restart` | Остановить, пересобрать без кеша, запустить |
| `make logs` | Логи всех сервисов (follow) |
| `make logs-backend` | Логи конкретного сервиса (backend/bot/postgres/nginx) |
| `make ps` | Статус контейнеров |
| `make build` | Пересобрать образы без кеша |
| `make backup` | Дамп PostgreSQL в файл `backup_YYYYMMDD_HHMMSS.sql` |
| `make restore FILE=backup_xxx.sql` | Восстановить БД из дампа |
| `make migrate FILE=004_admin_tables.sql` | Применить конкретную SQL-миграцию |
| `make migrate-all` | Применить все миграции по порядку |
| `make admin` | Открыть `/admin/` в браузере |
| `make health` | Проверить здоровье backend, admin, postgres |
| `make cleanup` | Очистить старые Docker-образы и тома |
| `make ssl` | Получить SSL-сертификат Let's Encrypt (первый раз) |
| `make ssl-renew` | Обновить SSL и перезагрузить nginx |
| `make psql` | Открыть psql-консоль в контейнере postgres |
| `make help` | Показать список доступных команд |
| `make beta-up` | Поднять beta-стек |
| `make beta-down` | Остановить beta-стек |
| `make beta-logs` | Логи beta-сервисов |
| `make beta-deploy` | Деплой на beta (pull dev + rebuild + up) |
| `make beta-health` | Health-check beta окружения |
| `make beta-migrate FILE=...` | Применить миграцию в beta |
| `make beta-psql` | Открыть psql-консоль в beta postgres |
| `make status` | Статус обоих окружений (prod + beta) |

## Стек и версии

| Компонент | Технология | Версия |
|-----------|-----------|--------|
| Bot | aiogram | 3.6.0 |
| Bot HTTP | aiohttp | 3.9.5 |
| Backend | FastAPI | 0.111.0 |
| ASGI-сервер | uvicorn | 0.29.0 |
| DB driver | asyncpg | 0.29.0 |
| Валидация | pydantic | 2.7.1 |
| HTTP-клиент | httpx | 0.27.0 |
| Encryption | cryptography (Fernet) | 42.0+ |
| Google API | google-api-python-client | 2.100+ |
| Google Auth | google-auth-oauthlib | 1.0+ |
| CalDAV | caldav | 1.3+ |
| iCalendar | icalendar | 5.0+ |
| Database | PostgreSQL | 16 (Alpine) |
| Frontend | Vanilla JS | — |
| Proxy | nginx | 1.25 (Alpine) |
| Runtime | Python | 3.12 (slim) |
| Контейнеризация | Docker Compose | 3.9 |

## Окружения

| Параметр | Beta | Production |
|----------|------|------------|
| Домен | beta.dovstrechiapp.ru | dovstrechiapp.ru |
| Ветка | `dev` | `main` |
| Бот | @beta_do_vstrechi_bot | @do_vstrechi_bot |
| БД | dovstrechi_beta | dovstrechi |
| Путь на VPS | `/opt/dovstrechi-beta` (worktree) | `/opt/dovstrechi` |
| Compose файл | docker-compose.beta.yml | docker-compose.yml |
| Деплой | Автоматически при push в `dev` | Только через процедуру |
| CI/CD workflow | `deploy-beta.yml` | `deploy-prod.yml` |

## ⚠️ Правила деплоя (читать обязательно)

### Beta-First: главное правило

> **Любой деплой по умолчанию = beta.
> В production — только по явному запросу с подтверждением.**

### Как деплоить на beta (обычная работа)

```bash
git push origin dev
# GitHub Actions автоматически деплоит на beta.dovstrechiapp.ru
```

### Как деплоить в production

Напиши в Claude Code:

```
deploy to production
```
или
```
задеплой в прод
```

Что произойдёт (полная церемония из `docs/DEPLOYMENT.md`):
1. Покажет все изменения с последнего прод-деплоя
2. Сгенерирует changelog (технический + для пользователей)
3. Два этапа подтверждения
4. Health-check beta перед деплоем
5. Деплой → health-check prod
6. Обновление CHANGELOG.md

### Git workflow

```
feature/* → merge в dev → push → beta (авто)
dev → (ceremony) → PR → main → production
```

| Ветка | Назначение | Куда деплоит |
|-------|-----------|-------------|
| `main` | Production-ready | → dovstrechiapp.ru |
| `dev` | Текущая разработка | → beta.dovstrechiapp.ru |
| `feature/*` | Новые фичи | merge в `dev` |
| `hotfix/*` | Срочные фиксы | `dev` → beta → prod |

### ❌ Запрещено

- `git push origin main` напрямую из feature/dev ветки без процедуры
- Деплой в prod если beta unhealthy
- Пропускать этапы подтверждения
- Деплоить в прод без явного запроса пользователя

### Признаки явного запроса в прод (для агентов)

✅ Явный запрос: «задеплой в прод», «deploy to production», «релиз в прод»
❌ НЕ явный (деплоить только на beta): «задеплой», «обнови сервер», «примени изменения»

**При любом сомнении — спрашивай: «Деплоить на beta или production?»**

### Git hooks

После `git clone` выполнить **один раз**:

```bash
make setup-hooks
```

Это установит `pre-commit` и `pre-push` из `.githooks/` в `.git/hooks/` — защита от случайных коммитов/push в `main`. Деплой в prod идёт только через PR `dev → main` + `make deploy`.

Обход однократно (не рекомендуется): `git commit --no-verify` / `git push --no-verify`.

## Переменные окружения

| Переменная | Сервис | Описание | Обязательная |
|-----------|--------|----------|-------------|
| `BOT_TOKEN` | backend, bot | Токен Telegram-бота от BotFather (нужен обоим для валидации initData) | ✅ |
| `MINI_APP_URL` | backend, bot | URL фронтенда Mini App (без `/` на конце) | ✅ |
| `INTERNAL_API_KEY` | backend, bot | Ключ для аутентификации бот↔backend (HMAC) | ✅ |
| `BACKEND_API_URL` | bot | URL backend API (default: `http://backend:8000`) | — |
| `BOT_INTERNAL_URL` | backend | URL внутреннего HTTP-сервера бота (default: `http://bot:8080`) | — |
| `DATABASE_URL` | backend | PostgreSQL connection string (формируется в docker-compose) | ✅ |
| `SECRET_KEY` | backend | Секретный ключ приложения | ✅ |
| `POSTGRES_DB` | postgres | Имя базы данных (default: `dovstrechi`) | — |
| `POSTGRES_USER` | postgres | Пользователь PostgreSQL (default: `dovstrechi`) | — |
| `POSTGRES_PASSWORD` | postgres | Пароль PostgreSQL | ✅ |
| `ADMIN_TELEGRAM_ID` | backend | Telegram ID администратора — единственный допустимый для входа в админку | ✅ |
| `ADMIN_SESSION_TTL_HOURS` | backend | Время жизни admin-сессии в часах (default: 2) | — |
| `ADMIN_IP_ALLOWLIST` | backend | IP-whitelist для /admin/ через запятую (пусто = любой IP) | — |
| `ANONYMIZE_SALT` | backend | Соль для SHA256-анонимизации telegram_id в app_events | — |
| `ENCRYPTION_KEY` | backend | Fernet-ключ для шифрования OAuth-токенов внешних календарей | — |
| `GOOGLE_CLIENT_ID` | backend | Google Calendar OAuth client ID | — |
| `GOOGLE_CLIENT_SECRET` | backend | Google Calendar OAuth client secret | — |
| `GOOGLE_REDIRECT_URI` | backend | Google Calendar OAuth redirect URI | — |
| `CALENDAR_WEBHOOK_URL` | backend | HTTPS base URL для Google Calendar webhooks | — |
| `BOT_USERNAME` | backend | Username бота без @ (для OAuth-редиректа обратно в бот) | — |
| `ALLOWED_ORIGINS` | backend | CORS-домены через запятую (default: dovstrechiapp.ru) | — |
| `SUPPORT_BOT_TOKEN` | support-bot | Токен отдельного Telegram-бота поддержки | — |
| `ADMIN_CHAT_ID` | support-bot | Telegram chat ID админа для пересылки сообщений | — |
| `ADMIN_IDS` | support-bot | Telegram ID админов через запятую (default: ADMIN_CHAT_ID) | — |

**Примечание:** `DATABASE_URL` собирается автоматически в `docker-compose.yml` из `POSTGRES_USER`, `POSTGRES_PASSWORD` и `POSTGRES_DB`.

### Beta-переменные (`.env.beta`)

Аналогичны prod-переменным, но с отдельными значениями для изоляции окружений:

| Переменная | Описание |
|-----------|----------|
| `BOT_TOKEN` | Токен @beta_do_vstrechi_bot (отдельный от прода!) |
| `SECRET_KEY` | FastAPI secret key для beta |
| `INTERNAL_API_KEY` | Ключ бот↔backend для beta |
| `POSTGRES_DB` | `dovstrechi_beta` (отдельная БД) |
| `POSTGRES_PASSWORD` | Пароль БД beta |
| `MINI_APP_URL` | `https://beta.dovstrechiapp.ru` |
| `ALLOWED_ORIGINS` | CORS для beta домена |
| `ANONYMIZE_SALT` | Отдельная соль (не как в проде) |
| `BETA_DIR` | Путь к worktree (default: `/opt/dovstrechi-beta`) |

## API Backend — все эндпоинты

Роуты определены в `backend/routers/`. Версия API: **1.2.0**.

| Метод | Путь | Auth | Описание |
|-------|------|------|----------|
| GET | `/` | — | Корневой healthcheck — возвращает имя, версию, статус |
| GET | `/health` | — | Проверка подключения к БД |
| POST | `/api/users/auth` | initData | Регистрация / обновление пользователя (upsert по telegram_id) |
| PATCH | `/api/users/notification-settings` | initData | Обновить настройки напоминаний пользователя |
| GET | `/api/users/{telegram_id}/avatar` | — | Получить аватар пользователя |
| GET | `/api/users/{telegram_id}` | — | Получить пользователя по Telegram ID |
| POST | `/api/schedules` | initData | Создать расписание |
| GET | `/api/schedules` | initData | Список активных расписаний текущего пользователя |
| GET | `/api/schedules/{schedule_id}` | — | Детали расписания (публичный) |
| PATCH | `/api/schedules/{schedule_id}` | initData | Обновить расписание (частичное обновление) |
| DELETE | `/api/schedules/{schedule_id}` | initData | Мягкое удаление расписания (is_active=FALSE) |
| GET | `/api/available-slots/{schedule_id}?date=&viewer_tz=` | — | Свободные слоты на дату (с учётом таймзон) |
| POST | `/api/bookings` | optional | Создать бронирование (автогенерация Jitsi-ссылки + push организатору) |
| GET | `/api/bookings?role=` | initData | Список бронирований (role: organizer / guest / all) |
| GET | `/api/bookings/{booking_id}` | optional | Детали бронирования + my_role (organizer/guest/viewer) |
| POST | `/api/meetings/quick` | initData | Создать встречу вручную (личная или в расписание) |
| PATCH | `/api/bookings/{booking_id}/confirm` | initData | Подтвердить бронирование (только организатор) |
| PATCH | `/api/bookings/{booking_id}/guest-confirm` | initData | Гость подтверждает что встреча в силе (morning confirmation) |
| PATCH | `/api/bookings/{booking_id}/cancel` | initData | Отменить бронирование (организатор или гость) |
| GET | `/api/bookings/pending-reminders?reminder_type=` | — | Список бронирований для напоминаний (24h/1h/15m/5m/morning) |
| GET | `/api/bookings/pending-reminders-v2` | — | Напоминания v2 (по user.reminder_settings + sent_reminders) |
| GET | `/api/bookings/confirmation-requests` | — | Встречи сегодня, требующие утреннего подтверждения |
| GET | `/api/bookings/no-answer-candidates` | — | Бронирования без ответа на подтверждение (>1ч) |
| PATCH | `/api/bookings/{booking_id}/confirmation-asked` | — | Отметить что запрос подтверждения отправлен |
| PATCH | `/api/bookings/{booking_id}/set-no-answer` | — | Перевести бронирование в статус no_answer |
| PATCH | `/api/bookings/{booking_id}/reminder-sent?reminder_type=` | — | Отметить напоминание как отправленное |
| POST | `/api/sent-reminders` | — | Записать отправленное напоминание (v2, idempotent) |
| GET | `/api/stats` | initData | Статистика: кол-во расписаний, бронирований, pending, confirmed, upcoming |
| POST | `/api/events` | optional | Трекинг событий из Mini App (анонимизированный, пишет в app_events) |
| POST | `/api/admin/auth/login` | Telegram Login Widget | Вход в админку — HMAC верификация → cookie `admin_session` |
| POST | `/api/admin/auth/logout` | admin cookie | Деактивация сессии + удаление cookie |
| GET | `/api/admin/auth/me` | admin cookie | Данные текущей сессии (telegram_id, expires_at) |
| GET | `/api/admin/dashboard/summary` | admin cookie | 6 метрик: users, active_7d, bookings_today, pending, errors_24h |
| GET | `/api/admin/dashboard/bookings-trend` | admin cookie | Бронирования по дням за N дней (query: days=30) |
| GET | `/api/admin/dashboard/platforms` | admin cookie | Распределение расписаний по платформам |
| GET | `/api/admin/logs` | admin cookie | Пагинированные app_events с фильтрами (severity, event_type, search, date) |
| GET | `/api/admin/logs/stats` | admin cookie | Агрегация за 24ч: by_severity, by_type, unique_users |
| GET | `/api/admin/tasks` | admin cookie | Задачи, сгруппированные по статусу (backlog/in_progress/done) |
| POST | `/api/admin/tasks` | admin cookie | Создать задачу (priority auto-increment) |
| PATCH | `/api/admin/tasks/reorder` | admin cookie | Переставить задачи в колонке (mass priority update) |
| PATCH | `/api/admin/tasks/{id}` | admin cookie | Обновить задачу (при смене status — пересчёт priority) |
| DELETE | `/api/admin/tasks/{id}` | admin cookie | Физическое удаление задачи |
| GET | `/api/admin/audit-log` | admin cookie | Пагинированный лог admin-действий |
| GET | `/api/admin/system/info` | admin cookie | Версия, uptime, pool stats, counts, окружение (без секретов) |
| POST | `/api/admin/sessions/invalidate-all` | admin cookie | Деактивировать все сессии кроме текущей |
| POST | `/api/admin/maintenance/cleanup-events` | admin cookie | Удалить info/warn события старше N дней |
| GET | `/calendar/google/auth-url` | initData | URL для Google OAuth авторизации |
| GET | `/calendar/google/callback` | — | Google OAuth callback (redirect) |
| GET | `/calendar/accounts` | initData | Список подключённых внешних календарей |
| DELETE | `/calendar/accounts/{account_id}` | initData | Удалить аккаунт календаря (+ отписка webhook) |
| POST | `/calendar/connections/{id}/toggle` | initData | Включить/выключить чтение/запись календаря |
| GET | `/calendar/schedules/{id}/calendar-config` | initData | Правила привязки календарей к расписанию |
| PUT | `/calendar/schedules/{id}/calendar-config` | initData | Установить правила привязки |
| POST | `/calendar/accounts/{id}/sync` | initData | Ручная синхронизация аккаунта |
| POST | `/calendar/webhook/google` | — | Google Calendar push-уведомление (webhook) |
| POST | `/calendar/caldav/connect` | initData | Подключить CalDAV-провайдер (Яндекс, Apple) |
| GET | `/calendar/external-events` | initData | События из внешних календарей для отображения |

## Telegram Bot — команды и handlers

Код бота в `bot/handlers/` (команды, callbacks), `bot/services/` (уведомления, напоминания).

### Команды

| Команда | Описание |
|---------|----------|
| `/start` | Регистрация через API + главное меню (ReplyKeyboard + InlineKeyboard) |
| `/help` | Справка по использованию |

### Главное меню

При `/start` бот отправляет два типа клавиатур:

**ReplyKeyboard (постоянная нижняя панель):**

| Кнопка | Handler | Действие |
|--------|---------|----------|
| 📅 Создать расписание | `reply_create_schedule` | Запуск FSM |
| 📋 Мои расписания | `reply_my_schedules` | Список расписаний |
| 👥 Мои встречи | `reply_my_bookings` | Список встреч |
| ❓ Помощь | `reply_help` | Справка |

**InlineKeyboard (в сообщении):**

| Кнопка | Callback / Тип | Действие |
|--------|---------------|----------|
| 🌐 Открыть приложение | WebApp | Открывает Mini App в Telegram |
| 📅 Мои расписания | `my_schedules` | Список расписаний с действиями |
| ➕ Создать расписание | `create_schedule` | Запуск FSM создания расписания |
| 📋 Мои встречи | `my_bookings` | Список бронирований |
| 📊 Статистика | `stats` | Карточка статистики |

### Callback-handlers

| Callback | Описание |
|----------|----------|
| `main_menu` | Возврат в главное меню |
| `my_schedules` | Список расписаний |
| `create_schedule` | Начало FSM |
| `my_bookings` | Список встреч |
| `stats` | Статистика |
| `schedule_{id}` | Детали расписания |
| `share_{id}` | Ссылка для бронирования |
| `del_{id}` | Удаление расписания |
| `booking_{id}` | Детали бронирования |
| `confirm_{id}` | Подтвердить встречу |
| `cancel_{id}` | Отменить встречу |
| `guest_confirm_{id}` | Гость подтверждает встречу (morning confirmation) |
| `guest_cancel_{id}` | Гость отменяет из morning confirmation |
| `how_it_works` | Как это работает (для новых пользователей) |
| `profile_help` | Помощь в профиле |
| `profile_notifications` | Настройки уведомлений |
| `remind_{option}` | Выбор настроек напоминания |
| `meetings_{type}` | Фильтр встреч (upcoming/past) |
| Inline query | Поиск и шаринг расписаний через @bot в любом чате |

### Deep Link: настройка напоминаний

| Ссылка | Обработчик | Действие |
|--------|-----------|----------|
| `/start notify_{booking_id}` | `start.py` | Кнопки выбора напоминания: за 30 мин, за 15 мин, не напоминать |

### FSM: создание расписания (CreateSchedule)

| Состояние | Ввод | Следующее |
|-----------|------|-----------|
| `title` | Текстовое сообщение (название) | `duration` |
| `duration` | Callback `dur_*` (15/30/45/60/90/120 мин) | `buffer_time` |
| `buffer_time` | Callback `buf_*` (0/10/15/30 мин) | `work_days` |
| `work_days` | Текст: числа 0-6 через пробел (Пн=0, Вс=6) | `start_time` |
| `start_time` | Текст в формате HH:MM | `end_time` |
| `end_time` | Текст в формате HH:MM | `platform` |
| `platform` | Callback `plat_*` (jitsi/zoom/other) | → POST `/api/schedules` → готово |

## Схема базы данных

Определена в `database/init.sql`. PostgreSQL 16, расширение `uuid-ossp`. Миграции: `database/migrations/*.sql`.

### Таблицы

| Таблица | Ключевые поля | Назначение |
|---------|--------------|-----------|
| `users` | id (UUID PK), telegram_id (BIGINT UNIQUE), username, first_name, last_name, **timezone** (TEXT, default 'UTC'), **reminder_settings** (JSONB), created_at, updated_at | Пользователи-организаторы |
| `schedules` | id (UUID PK), user_id (FK→users CASCADE), title, **description** (TEXT), duration (INT, мин), buffer_time (INT, мин), work_days (INT[]), start_time (TIME), end_time (TIME), location_mode, platform, **location_address** (TEXT, для offline), is_active (BOOL), **is_default** (BOOL, скрытое расписание для личных встреч), **min_booking_advance** (INT, мин, default 0), **requires_confirmation** (BOOL, default TRUE), created_at, updated_at | Расписания для бронирования |
| `bookings` | id (UUID PK), schedule_id (FK→schedules CASCADE), guest_name, guest_contact, guest_telegram_id, scheduled_time (TIMESTAMPTZ), status (CHECK: pending/confirmed/cancelled/completed/**no_answer**), meeting_link, notes, **title** (TEXT), **end_time** (TIMESTAMPTZ), **is_manual** (BOOL), **created_by** (BIGINT), **platform** (TEXT, snapshot), **location_address** (TEXT, snapshot), **blocks_slots** (BOOL, default TRUE), reminder_24h/1h/15m/5m_sent (BOOL), **morning_reminder_sent** (BOOL), **confirmation_asked** (BOOL), **confirmation_asked_at** (TIMESTAMPTZ), created_at, updated_at | Бронирования встреч |
| `admin_sessions` | id (UUID PK), telegram_id (BIGINT), session_token (TEXT UNIQUE), ip_address (INET), user_agent, expires_at (TIMESTAMPTZ), is_active (BOOL) | Admin cookie-сессии |
| `admin_audit_log` | id (BIGSERIAL PK), action (TEXT CHECK), details (JSONB), ip_address (INET), created_at | Лог всех admin-действий |
| `app_events` | id (BIGSERIAL PK), event_type (TEXT), anonymous_id (TEXT, 12 chars), session_id, metadata (JSONB), severity (CHECK: info/warn/error/critical), created_at | Аналитика: события приложения с анонимизацией |
| `admin_tasks` | id (UUID PK), title, description, description_plain, status (CHECK: backlog/in_progress/done), priority (INT), source (CHECK), source_ref, tags (TEXT[]), created_at, updated_at | Kanban-задачи |
| `calendar_accounts` | id (UUID PK), user_id (FK→users), provider (google/yandex/apple/outlook), provider_email, access_token_encrypted, refresh_token_encrypted, token_expires_at, caldav_url, status (active/expired/revoked/error), last_sync_at | Внешние календарные аккаунты |
| `calendar_connections` | id (UUID PK), account_id (FK→calendar_accounts), external_calendar_id, calendar_name, calendar_color, is_visible, is_read_enabled, is_write_target, **is_display_enabled** (BOOL), sync_token, webhook_channel_id, webhook_resource_id | Конкретные календари внутри аккаунта |
| `schedule_calendar_rules` | id (UUID PK), schedule_id (FK→schedules), connection_id (FK→calendar_connections), use_for_blocking (BOOL), use_for_writing (BOOL) | Привязка календарей к расписаниям |
| `external_busy_slots` | id (UUID PK), connection_id (FK→calendar_connections), external_event_id, summary, start_time, end_time, is_all_day, etag, raw_data (JSONB) | Кеш занятых слотов из внешних календарей |
| `event_mapping` | id (UUID PK), booking_id (FK→bookings), connection_id (FK→calendar_connections), external_event_id, sync_status (synced/pending/error/deleted), sync_direction (outbound/inbound) | Маппинг бронирование↔событие внешнего календаря |
| `sync_log` | id (UUID PK), account_id, connection_id, action, status, details (JSONB), error_message | Лог синхронизации календарей |
| `sent_reminders` | id (UUID PK), booking_id (FK→bookings), reminder_type (TEXT), sent_at (TIMESTAMPTZ). UNIQUE (booking_id, reminder_type) | Лог отправленных напоминаний (v2, idempotent) |

### View

| View | Описание |
|------|----------|
| `bookings_detail` | JOIN bookings + schedules + users — добавляет schedule_title, schedule_duration, schedule_platform, organizer_telegram_id, organizer_first_name, organizer_username |

### Индексы

- `idx_users_telegram_id` — users(telegram_id)
- `idx_schedules_user_id` — schedules(user_id)
- `idx_schedules_is_active` — schedules(is_active)
- `idx_bookings_schedule_id` — bookings(schedule_id)
- `idx_bookings_guest_telegram_id` — bookings(guest_telegram_id)
- `idx_bookings_scheduled_time` — bookings(scheduled_time)
- `idx_bookings_status` — bookings(status)

### Триггеры

На каждой таблице — `BEFORE UPDATE` триггер `trigger_set_updated_at()` для автообновления `updated_at`.

## Правила работы с кодом

### Обязательно
- **Async/await везде** — никаких синхронных I/O
- **Секреты только в .env** — никакого хардкода
- **Бот → Backend → БД** — бот не ходит в БД напрямую, только через HTTP API
- **Изменения схемы БД** — через `database/init.sql` (начальная схема) + `database/migrations/*.sql` (инкрементальные)
- **UUID** как первичные ключи во всех таблицах
- **CORS** ограничен whitelist'ом доменов (`dovstrechiapp.ru`)
- **Аутентификация** — все защищённые эндпоинты используют `Depends(get_current_user)`, **не** `telegram_id` из query/body
- **SQL** — только параметризованные запросы (`$1, $2`), **никогда** f-строки
- **XSS** — весь пользовательский ввод проходит через `escHtml()` перед вставкой в DOM
- **Security audit log** — при любом изменении, связанном с безопасностью, обновлять `docs/SECURITY.md`
- **Docker volumes: вложенные bind mounts** — если один bind mount вложен в другой (например `admin` внутри `frontend`), родительский маунт **НЕ** должен быть `:ro`. Docker не может создать mountpoint внутри read-only overlayfs. См. `docs/incidents/INC_001_NGINX_GRAY_SCREEN.md`
- **Frontend: блокирующая инициализация** — любой код, управляющий видимостью приложения (opacity, .ready, display), должен быть обёрнут в try/catch + иметь CSS fallback. Серый экран = P0 инцидент
- **docker-compose.yml: после изменения volumes** — обязательно проверить `docker compose up -d` локально и убедиться что ВСЕ контейнеры в статусе Up. `docker compose ps` должен показывать все 4 сервиса (postgres, backend, bot, nginx)

### Запрещено
- Хардкодить токены, пароли, ключи
- Синхронные библиотеки (requests, psycopg2, time.sleep)
- Прямые запросы из бота в PostgreSQL
- Менять схему БД без обновления `database/init.sql` и создания миграции в `database/migrations/`
- Зарубежные managed-сервисы для хранения данных (требование 152-ФЗ — данные только на российском VPS)
- Принимать `telegram_id` из query params или тела запроса для авторизации
- Использовать `innerHTML` с непроверенными данными без `escHtml()`
- Добавлять `allow_origins=["*"]` в CORS
- **Ставить `:ro` на родительский bind mount, если внутрь него вложен другой mount** — это сломает контейнер (INC-001, 9 часов даунтайма). Безопасные паттерны см. в `docs/incidents/INC_001_NGINX_GRAY_SCREEN.md`
- **Удалять или модифицировать защитные обёртки фронтенда** — global error handlers, CSS `@keyframes _force-show`, try/catch вокруг TG SDK init. Эти механизмы предотвращают серый экран

## Как добавить новый API-эндпоинт

Backend разделён на модули в `backend/routers/`. Новые эндпоинты добавляются в подходящий файл роутера (или создаётся новый):

1. Определить Pydantic-модель (если нужна) в `backend/schemas.py` с `Field(min_length=, max_length=)`
2. Добавить роут-функцию в `backend/routers/<модуль>.py` с декоратором `@router.get/post/patch/delete`
3. **Если эндпоинт требует авторизации** — добавить `auth_user: dict = Depends(get_current_user)` (импорт из `backend.auth`) и извлекать `telegram_id = auth_user["id"]`
4. Если эндпоинт публичный (гостевой доступ) — использовать `Depends(get_optional_user)` или без auth
5. Использовать dependency `conn = Depends(db)` для доступа к asyncpg-соединению (импорт из `backend.database`)
6. SQL — только `$1, $2` параметры, никогда f-строки
7. Для конвертации результатов из asyncpg: `row_to_dict(row)` / `rows_to_list(rows)` из `backend.utils`
8. Если новый роутер — подключить в `backend/main.py` через `app.include_router()`

## Как добавить новый handler бота

Бот разделён на модули. Handlers в `bot/handlers/`, фоновые сервисы в `bot/services/`:

1. Написать async-функцию handler в подходящем файле `bot/handlers/<модуль>.py`
2. Зарегистрировать через `router.message()`, `router.callback_query()` (используется `Router` из aiogram)
3. Если нужен FSM — добавить состояния в `bot/states.py` в класс `CreateSchedule` (или создать новый `StatesGroup`)
4. Для API-вызовов использовать хелпер `api(method, path, **kwargs)` из `bot.api`
5. Для клавиатур — `InlineKeyboardBuilder` из aiogram, готовые клавиатуры в `bot/keyboards.py`
6. Если новый файл handler — подключить router в `bot/bot.py` через `dp.include_router()`

## Инфраструктура

| Параметр | Значение |
|----------|---------|
| VPS | Timeweb (Россия, 152-ФЗ) |
| Домен (prod) | dovstrechiapp.ru |
| Домен (beta) | beta.dovstrechiapp.ru |
| SSL | Let's Encrypt (certbot, `make ssl` / `make ssl-renew` / `make ssl-beta`) |
| CI/CD | GitHub Actions → SSH → git worktree + docker compose |
| Деплой-путь (prod) | `/opt/dovstrechi` |
| Деплой-путь (beta) | `/opt/dovstrechi-beta` (git worktree ветки `dev`) |

### Сервисы в docker-compose

| Сервис | Контейнер | Порты |
|--------|----------|-------|
| postgres | dovstrechi_postgres | — (internal) |
| backend | dovstrechi_backend | 8000 (internal) |
| bot | dovstrechi_bot | 8080 (internal, уведомления) |
| nginx | dovstrechi_nginx | 80, 443 (external) |
| certbot | dovstrechi_certbot | — (профиль `ssl`) |
| support-bot | dovstrechi_support_bot | — (internal, только в beta) |

### GitHub Secrets для CI/CD

> Secrets используются обоими workflows (`deploy-prod.yml` и `deploy-beta.yml`).

| Secret | Описание |
|--------|----------|
| `VPS_HOST` | IP-адрес VPS |
| `VPS_USER` | SSH-пользователь (обычно root) |
| `VPS_SSH_KEY` | Приватный SSH-ключ |
| `DOCKERHUB_USER` | Docker Hub username (для избежания 429 rate limit при `docker pull`) |
| `DOCKERHUB_TOKEN` | Docker Hub Personal Access Token (read-only scope) |

## Известные особенности и gotchas

- **Telegram MainButton** не рендерится в обычных браузерах — в Mini App есть fallback на HTML-кнопку
- **Inline-режим бота** требует активации в BotFather: Bot Settings → Inline Mode
- **Trailing slash** в URL вызывает двойной слеш — убирать `/` в конце `MINI_APP_URL`
- **Бот работает polling'ом** (не webhook) — `dp.start_polling(bot)` + aiohttp-сервер на :8080 для приёма уведомлений от backend
- **CORS** ограничен whitelist'ом (`dovstrechiapp.ru`) — менять в `backend/main.py` переменную `allow_origins`
- **Пауза vs удаление расписания** — оба действия ставят `is_active=FALSE` на backend. Фронтенд отличает их через localStorage (`deleted_schedules`): удалённые не показываются, приостановленные — с opacity 0.55
- **Быстрое добавление встречи** — `POST /api/meetings/quick` автосоздаёт скрытое расписание (`is_default=TRUE`) если `schedule_id` не передан. Такие расписания не отображаются в списке расписаний организатора
- **min_booking_advance** — минимальное время бронирования заранее (в минутах), default 0. Слоты ближе этого порога к текущему времени отфильтровываются в `/api/available-slots`
- **Аутентификация** двухканальная: Mini App через `X-Init-Data` (HMAC-SHA256), бот через `X-Internal-Key`
- **Security audit log** ведётся в `docs/SECURITY.md` — обновлять при каждом изменении безопасности
- **Миграции** — ручные SQL-файлы в `database/migrations/`, применяются через `docker-compose exec postgres psql`
- **Meeting link** генерируется как Jitsi-ссылка по UUID: `https://meet.jit.si/dovstrechi-{uuid4}`
- **Расписание удаляется мягко** — `is_active=FALSE`, данные остаются в БД
- **Фронтенд определяет API-URL как пустую строку** (`const BACKEND = ''`) — запросы идут на тот же origin через nginx proxy `/api/`
- **work_days** хранятся как массив int: 0=Понедельник, 6=Воскресенье
- **Connection pool** asyncpg: min_size=2, max_size=10
- **Напоминания** — фоновый цикл в боте (каждые 5 мин) проверяет pending-reminders через API и рассылает за 24ч и 1ч до встречи
- **Push-уведомления** — backend → POST `http://bot:8080/internal/notify` при новом бронировании (fire-and-forget)
- **Docker: non-root** — backend и bot контейнеры работают под пользователем `appuser` (uid 1000)
- **nginx rate limiting** — `/api/` 10 req/s burst=20, `/api/bookings` 5 req/min burst=3
- **Security headers** — HSTS, CSP, X-Content-Type-Options, Referrer-Policy, Permissions-Policy
- **Telegram Login Widget** требует домен, зарегистрированный в BotFather: `/setdomain` → `dovstrechiapp.ru`
- **Админка** доступна по `/admin/`, rate limit 5 req/s (auth: 3 req/min), cookie-based сессии
- **Admin cookie path=/api/admin** — cookie не утекает на основной сайт (`/`), отправляется только с `/api/admin/*` запросами
- **CSP** включает `https://telegram.org` и `https://oauth.telegram.org` для Telegram Login Widget
- **CSP /admin/** дополнительно включает `https://cdnjs.cloudflare.com` для Chart.js и SortableJS
- **Structlog JSON-логи** — для просмотра: `docker compose logs backend | python3 -m json.tool` или `jq '.'`
- **structlog не логирует health** — `StructlogMiddleware` пропускает `/` и `/health` чтобы не засорять логи healthcheck-запросами
- **app_events anonymous_id** — 12-символьный хеш SHA256(telegram_id:ANONYMIZE_SALT). Нельзя восстановить telegram_id без знания соли
- **Docker nested bind mounts** — `./admin` монтируется ВНУТРЬ `./frontend` (оба в `/usr/share/nginx/html`). Родительский маунт frontend **без** `:ro`, иначе nginx не запустится. Подробности: `docs/incidents/INC_001_NGINX_GRAY_SCREEN.md`
- **Frontend gray screen protection** — три слоя: CSS `_force-show` (5s fallback), global error handlers → `.ready`, try/catch на TG SDK init. Не удалять!
- **no_answer статус бронирования** — утренний запрос гостю «Встреча в силе?», auto-transition в `no_answer` через 1ч без ответа. Эндпоинты: `/confirmation-requests`, `/confirmation-asked`, `/no-answer-candidates`, `/set-no-answer`
- **blocks_slots** — булевое поле бронирования (default TRUE). Если FALSE — бронирование не блокирует слоты в `/available-slots`. Для ручных встреч, которые не влияют на публичную доступность
- **Support bot** — отдельный бот `@dovstrechi_support_bot` для обратной связи. Пересылает сообщения пользователей админу. Пока только в beta docker-compose
- **Интеграция внешних календарей** — Google Calendar (OAuth 2.0 + webhooks) и CalDAV (Яндекс, Apple). Токены шифруются Fernet (ENCRYPTION_KEY). 6 таблиц: calendar_accounts, calendar_connections, schedule_calendar_rules, external_busy_slots, event_mapping, sync_log
- **Два файла с номером 008** — `008_calendar_integration.sql` и `008_no_answer_status.sql` (аналогично двум 004). Оба используют IF NOT EXISTS/IF EXISTS — идемпотентны
- **Напоминания v2** — таблица `sent_reminders` + JSONB `users.reminder_settings`. Позволяет произвольные интервалы напоминаний вместо фиксированных 24h/1h
- **Offline-встречи** — platform='offline' + location_address в schedules и bookings (snapshot при бронировании)
- **CORS** настраивается через переменную `ALLOWED_ORIGINS` (через запятую). `MINI_APP_URL` автоматически добавляется в whitelist
