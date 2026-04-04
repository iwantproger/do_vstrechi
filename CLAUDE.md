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
│   ├── main.py             # Весь backend в одном файле (роуты, модели, БД)
│   ├── requirements.txt    # Python-зависимости backend
│   └── Dockerfile
├── bot/                    # Telegram-бот на aiogram 3.x
│   ├── bot.py              # Весь бот в одном файле (handlers, FSM, клавиатуры)
│   ├── requirements.txt    # Python-зависимости бота
│   └── Dockerfile
├── frontend/               # Telegram Mini App (SPA)
│   └── index.html          # Весь фронтенд в одном файле (HTML + CSS + JS)
├── database/               # Инициализация БД
│   └── init.sql            # Схема: таблицы, индексы, триггеры, view
├── nginx/                  # Reverse proxy
│   ├── nginx.conf          # Конфиг: SSL, проксирование /api/ → backend
│   └── Dockerfile
├── design/                 # Дизайн-макеты и прототипы (HTML, SVG, PDF)
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
| `BOT_TOKEN` | bot | Токен Telegram-бота от BotFather | ✅ |
| `MINI_APP_URL` | bot | URL фронтенда Mini App (без `/` на конце) | ✅ |
| `BACKEND_API_URL` | bot | URL backend API (default: `http://backend:8000`) | — |
| `DATABASE_URL` | backend | PostgreSQL connection string (формируется в docker-compose) | ✅ |
| `SECRET_KEY` | backend | Секретный ключ приложения | ✅ |
| `BOT_TOKEN` | backend, bot | Токен бота (нужен backend для валидации initData) | ✅ |
| `INTERNAL_API_KEY` | backend, bot | Ключ для аутентификации бот→backend | ✅ |
| `POSTGRES_DB` | postgres | Имя базы данных (default: `dovstrechi`) | — |
| `POSTGRES_USER` | postgres | Пользователь PostgreSQL (default: `dovstrechi`) | — |
| `POSTGRES_PASSWORD` | postgres | Пароль PostgreSQL | ✅ |

**Примечание:** `DATABASE_URL` собирается автоматически в `docker-compose.yml` из `POSTGRES_USER`, `POSTGRES_PASSWORD` и `POSTGRES_DB`.

## API Backend — все эндпоинты

Все роуты определены в `backend/main.py`. Версия API: **2.0.0**.

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/` | Корневой healthcheck — возвращает имя, версию, статус |
| GET | `/health` | Проверка подключения к БД |
| POST | `/api/users/auth` | Регистрация / обновление пользователя (upsert по telegram_id) |
| GET | `/api/users/{telegram_id}` | Получить пользователя по Telegram ID |
| POST | `/api/schedules` | Создать расписание |
| GET | `/api/schedules?telegram_id=` | Список активных расписаний пользователя |
| GET | `/api/schedules/{schedule_id}` | Детали расписания |
| DELETE | `/api/schedules/{schedule_id}?telegram_id=` | Мягкое удаление расписания (is_active=FALSE) |
| GET | `/api/available-slots/{schedule_id}?date=` | Свободные слоты на дату (с учётом duration, buffer, занятых) |
| POST | `/api/bookings` | Создать бронирование (автогенерация Jitsi-ссылки) |
| GET | `/api/bookings?telegram_id=&role=` | Список бронирований (role: organizer / guest / all) |
| PATCH | `/api/bookings/{booking_id}/confirm?telegram_id=` | Подтвердить бронирование (только организатор) |
| PATCH | `/api/bookings/{booking_id}/cancel?telegram_id=` | Отменить бронирование (организатор или гость) |
| GET | `/api/stats?telegram_id=` | Статистика: кол-во расписаний, бронирований, pending, confirmed, upcoming |

## Telegram Bot — команды и handlers

Весь код бота в `bot/bot.py`.

### Команды

| Команда | Описание |
|---------|----------|
| `/start` | Регистрация через API + главное меню (5 кнопок) |
| `/help` | Справка по использованию |

### Главное меню (InlineKeyboard)

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

Определена в `database/init.sql`. PostgreSQL 16, расширение `uuid-ossp`.

### Таблицы

| Таблица | Ключевые поля | Назначение |
|---------|--------------|-----------|
| `users` | id (UUID PK), telegram_id (BIGINT UNIQUE), username, first_name, last_name, created_at, updated_at | Пользователи-организаторы |
| `schedules` | id (UUID PK), user_id (FK→users CASCADE), title, duration (INT, мин), buffer_time (INT, мин), work_days (INT[]), start_time (TIME), end_time (TIME), location_mode, platform, is_active (BOOL), created_at, updated_at | Расписания для бронирования |
| `bookings` | id (UUID PK), schedule_id (FK→schedules CASCADE), guest_name, guest_contact, guest_telegram_id, scheduled_time (TIMESTAMPTZ), status (pending/confirmed/cancelled), meeting_link, notes, created_at, updated_at | Бронирования встреч |

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
- **Изменения схемы БД** — только через `database/init.sql` (миграции пока не выделены)
- **UUID** как первичные ключи во всех таблицах
- **CORS** ограничен whitelist'ом доменов (`dovstrechiapp.ru`)
- **Аутентификация** — все защищённые эндпоинты используют `Depends(get_current_user)`, **не** `telegram_id` из query/body
- **SQL** — только параметризованные запросы (`$1, $2`), **никогда** f-строки
- **XSS** — весь пользовательский ввод проходит через `escHtml()` перед вставкой в DOM
- **Security audit log** — при любом изменении, связанном с безопасностью, обновлять `docs/SECURITY.md`

### Запрещено
- Хардкодить токены, пароли, ключи
- Синхронные библиотеки (requests, psycopg2, time.sleep)
- Прямые запросы из бота в PostgreSQL
- Менять схему БД без обновления `database/init.sql`
- Зарубежные managed-сервисы для хранения данных (требование 152-ФЗ — данные только на российском VPS)
- Принимать `telegram_id` из query params или тела запроса для авторизации
- Использовать `innerHTML` с непроверенными данными без `escHtml()`
- Добавлять `allow_origins=["*"]` в CORS

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
| bot | dovstrechi_bot | — (polling) |
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
- **Бот работает polling'ом** (не webhook) — `dp.start_polling(bot)`
- **CORS** ограничен whitelist'ом — менять в `backend/main.py` переменную `allow_origins`
- **Аутентификация** двухканальная: Mini App через `X-Init-Data` (HMAC-SHA256), бот через `X-Internal-Key`
- **Security audit log** ведётся в `docs/SECURITY.md` — обновлять при каждом изменении безопасности
- **Нет миграций** — схема БД применяется только при первой инициализации через `init.sql`
- **Meeting link** генерируется как Jitsi-ссылка по UUID: `https://meet.jit.si/dovstrechi-{uuid4}`
- **Расписание удаляется мягко** — `is_active=FALSE`, данные остаются в БД
- **Фронтенд определяет API-URL как пустую строку** (`const BACKEND = ''`) — запросы идут на тот же origin через nginx proxy `/api/`
- **work_days** хранятся как массив int: 0=Понедельник, 6=Воскресенье
- **Connection pool** asyncpg: min_size=2, max_size=10
