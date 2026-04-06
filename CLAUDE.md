# CLAUDE.md

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
│   ├── main.py             # Весь backend в одном файле (роуты, модели, БД, auth)
│   ├── requirements.txt    # Python-зависимости backend
│   └── Dockerfile
├── bot/                    # Telegram-бот на aiogram 3.x
│   ├── bot.py              # Бот + внутренний HTTP-сервер уведомлений (:8080)
│   ├── requirements.txt    # Python-зависимости бота
│   └── Dockerfile
├── frontend/               # Telegram Mini App (SPA)
│   └── index.html          # Весь фронтенд в одном файле (HTML + CSS + JS)
├── admin/                  # Админ-панель (SPA)
│   └── index.html          # Весь фронтенд админки (HTML + CSS + JS)
├── database/               # Инициализация и миграции БД
│   ├── init.sql            # Схема: таблицы, индексы, триггеры, view
│   └── migrations/         # Инкрементальные SQL-миграции
│       ├── 002_add_timezone.sql
│       ├── 003_add_reminder_flags.sql
│       └── 004_admin_tables.sql
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
│   └── incidents/          # Разборы инцидентов (postmortem)
│       └── INC_001_NGINX_GRAY_SCREEN.md
├── .github/workflows/
│   └── deploy.yml          # CI/CD: автодеплой на VPS при push в main
├── docker-compose.yml      # Оркестрация всех сервисов
├── Makefile                # Команды управления проектом
├── .env.example            # Шаблон переменных окружения
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
| Database | PostgreSQL | 16 (Alpine) |
| Frontend | Vanilla JS | — |
| Proxy | nginx | 1.25 (Alpine) |
| Runtime | Python | 3.12 (slim) |
| Контейнеризация | Docker Compose | 3.9 |

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

**Примечание:** `DATABASE_URL` собирается автоматически в `docker-compose.yml` из `POSTGRES_USER`, `POSTGRES_PASSWORD` и `POSTGRES_DB`.

## API Backend — все эндпоинты

Все роуты определены в `backend/main.py`. Версия API: **2.0.0**.

| Метод | Путь | Auth | Описание |
|-------|------|------|----------|
| GET | `/` | — | Корневой healthcheck — возвращает имя, версию, статус |
| GET | `/health` | — | Проверка подключения к БД |
| POST | `/api/users/auth` | initData | Регистрация / обновление пользователя (upsert по telegram_id) |
| GET | `/api/users/{telegram_id}` | — | Получить пользователя по Telegram ID |
| POST | `/api/schedules` | initData | Создать расписание |
| GET | `/api/schedules` | initData | Список активных расписаний текущего пользователя |
| GET | `/api/schedules/{schedule_id}` | — | Детали расписания (публичный) |
| DELETE | `/api/schedules/{schedule_id}` | initData | Мягкое удаление расписания (is_active=FALSE) |
| GET | `/api/available-slots/{schedule_id}?date=&viewer_tz=` | — | Свободные слоты на дату (с учётом таймзон) |
| POST | `/api/bookings` | optional | Создать бронирование (автогенерация Jitsi-ссылки + push организатору) |
| GET | `/api/bookings?role=` | initData | Список бронирований (role: organizer / guest / all) |
| PATCH | `/api/bookings/{booking_id}/confirm` | initData | Подтвердить бронирование (только организатор) |
| PATCH | `/api/bookings/{booking_id}/cancel` | initData | Отменить бронирование (организатор или гость) |
| GET | `/api/bookings/pending-reminders?reminder_type=` | — | Список бронирований для напоминаний (24h/1h) |
| PATCH | `/api/bookings/{booking_id}/reminder-sent?reminder_type=` | — | Отметить напоминание как отправленное |
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

## Telegram Bot — команды и handlers

Весь код бота в `bot/bot.py`.

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
| `users` | id (UUID PK), telegram_id (BIGINT UNIQUE), username, first_name, last_name, **timezone** (TEXT, default 'UTC'), created_at, updated_at | Пользователи-организаторы |
| `schedules` | id (UUID PK), user_id (FK→users CASCADE), title, duration (INT, мин), buffer_time (INT, мин), work_days (INT[]), start_time (TIME), end_time (TIME), location_mode, platform, is_active (BOOL), created_at, updated_at | Расписания для бронирования |
| `bookings` | id (UUID PK), schedule_id (FK→schedules CASCADE), guest_name, guest_contact, guest_telegram_id, scheduled_time (TIMESTAMPTZ), status (CHECK: pending/confirmed/cancelled/completed), meeting_link, notes, **reminder_24h_sent** (BOOL), **reminder_1h_sent** (BOOL), created_at, updated_at | Бронирования встреч |
| `admin_sessions` | id (UUID PK), telegram_id (BIGINT), session_token (TEXT UNIQUE), ip_address (INET), user_agent, expires_at (TIMESTAMPTZ), is_active (BOOL) | Admin cookie-сессии |
| `admin_audit_log` | id (BIGSERIAL PK), action (TEXT CHECK), details (JSONB), ip_address (INET), created_at | Лог всех admin-действий |
| `app_events` | id (BIGSERIAL PK), event_type (TEXT), anonymous_id (TEXT, 12 chars), session_id, metadata (JSONB), severity (CHECK: info/warn/error/critical), created_at | Аналитика: события приложения с анонимизацией |
| `admin_tasks` | id (UUID PK), title, description, description_plain, status (CHECK: backlog/in_progress/done), priority (INT), source (CHECK), source_ref, tags (TEXT[]), created_at, updated_at | Kanban-задачи |

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

Сейчас весь backend — один файл `backend/main.py`. Новые эндпоинты добавляются туда же:

1. Определить Pydantic-модель (если нужна) с `Field(min_length=, max_length=)` — рядом с существующими
2. Добавить роут-функцию с декоратором `@app.get/post/patch/delete`
3. **Если эндпоинт требует авторизации** — добавить `auth_user: dict = Depends(get_current_user)` и извлекать `telegram_id = auth_user["id"]`
4. Если эндпоинт публичный (гостевой доступ) — использовать `Depends(get_optional_user)` или без auth
5. Использовать dependency `conn = Depends(db)` для доступа к asyncpg-соединению
6. SQL — только `$1, $2` параметры, никогда f-строки
7. Для конвертации результатов из asyncpg: `row_to_dict(row)` / `rows_to_list(rows)`

## Как добавить новый handler бота

Весь бот — один файл `bot/bot.py`. Новые handlers добавляются туда же:

1. Написать async-функцию handler
2. Зарегистрировать через `dp.message.register()` или `dp.callback_query.register()`
3. Если нужен FSM — добавить состояния в класс `CreateSchedule` (или создать новый `StatesGroup`)
4. Для API-вызовов использовать хелпер `api(method, path, **kwargs)`
5. Для клавиатур — `InlineKeyboardBuilder` из aiogram

## Инфраструктура

| Параметр | Значение |
|----------|---------|
| VPS | Timeweb (Россия, 152-ФЗ) |
| Домен | dovstrechiapp.ru |
| SSL | Let's Encrypt (certbot, `make ssl` / `make ssl-renew`) |
| CI/CD | GitHub Actions → SSH → `git pull` + `docker compose build` + `up -d` |
| Деплой-путь на сервере | `/opt/dovstrechi` |

### Сервисы в docker-compose

| Сервис | Контейнер | Порты |
|--------|----------|-------|
| postgres | dovstrechi_postgres | — (internal) |
| backend | dovstrechi_backend | 8000 (internal) |
| bot | dovstrechi_bot | 8080 (internal, уведомления) |
| nginx | dovstrechi_nginx | 80, 443 (external) |
| certbot | dovstrechi_certbot | — (профиль `ssl`) |

### GitHub Secrets для CI/CD

| Secret | Описание |
|--------|----------|
| `VPS_HOST` | IP-адрес VPS |
| `VPS_USER` | SSH-пользователь (обычно root) |
| `VPS_SSH_KEY` | Приватный SSH-ключ |

## Известные особенности и gotchas

- **Telegram MainButton** не рендерится в обычных браузерах — в Mini App есть fallback на HTML-кнопку
- **Inline-режим бота** требует активации в BotFather: Bot Settings → Inline Mode
- **Trailing slash** в URL вызывает двойной слеш — убирать `/` в конце `MINI_APP_URL`
- **Бот работает polling'ом** (не webhook) — `dp.start_polling(bot)` + aiohttp-сервер на :8080 для приёма уведомлений от backend
- **CORS** ограничен whitelist'ом (`dovstrechiapp.ru`) — менять в `backend/main.py` переменную `allow_origins`
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
