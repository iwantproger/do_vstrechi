# Технические решения и ограничения

## Принятые архитектурные решения

| # | Решение | Обоснование | Отклонённые альтернативы |
|---|---------|-------------|------------------------|
| 1 | Self-hosted PostgreSQL 16 | 152-ФЗ — персональные данные хранятся на российском VPS | Supabase, PlanetScale, Neon (зарубежные managed DB) |
| 21 | Модульный backend (`backend/routers/`) | Разделение ответственности, лёгкая навигация, unit-тестируемость каждого роутера | Монофайл `main.py` (был ранее, решение #9 устарело) |
| 22 | Модульный bot (`bot/handlers/`, `bot/services/`) | Изоляция FSM-логики, фоновых сервисов и обработчиков; независимое развитие каждого модуля | Монофайл `bot.py` (был ранее) |
| 2 | asyncpg без ORM | Максимальная производительность и контроль SQL, минимум абстракций | SQLAlchemy async, Tortoise ORM |
| 3 | aiogram 3.6 | Современный async API, FSM из коробки, активное русскоязычное сообщество | python-telegram-bot, Telethon |
| 4 | Vanilla JS (без фреймворка) | Нулевой размер бандла, не нужен этап сборки, быстрая загрузка в Mini App | React, Vue, Svelte, Solid |
| 5 | Jitsi Meet для видеозвонков | Self-hosted, бесплатный, не требует API-ключей — ссылка генерируется по UUID | Zoom API (платный), Google Meet API (OAuth) |
| 6 | Монорепо (один репозиторий) | Единый деплой, общие конфиги, атомарные изменения | Отдельные репо для bot/backend/frontend |
| 7 | Timeweb VPS | Российский хостинг для 152-ФЗ, SSH-деплой через GitHub Actions | AWS, GCP, DigitalOcean (зарубежные) |
| 8 | Polling вместо Webhook | Проще настройка, не нужен публичный URL для бота, не нужен SSL для бота | Webhook (выше производительность при нагрузке) |
| ~~9~~ | ~~Один файл на сервис~~ | ~~Быстрый старт, нет over-engineering на ранней стадии~~ | ~~Разделение на routers/, schemas/, db/~~ — **Устарело, см. решения #21, #22** |
| 10 | Мягкое удаление расписаний | Сохранение данных бронирований, привязанных к расписанию | Физическое удаление (CASCADE удалит bookings) |
| 11 | UUID как первичные ключи | Безопасность: нельзя перебирать ID; уникальность без sequence | SERIAL / BIGSERIAL (предсказуемые ID) |
| 12 | CORS whitelist (dovstrechiapp.ru) | Безопасность: ограничить origin, methods, headers | allow_origins=["*"] (использовалось ранее, убрано) |
| 13 | MemoryStorage для FSM | Достаточно для одного инстанса бота, нет зависимости от Redis | Redis storage (нужен при масштабировании) |
| 14 | Docker Compose 3.9 | Стандарт оркестрации для single-server deployment | Kubernetes (overkill), bare-metal |
| 15 | Telegram Login Widget для аутентификации в админке | Нет отдельной базы паролей, 2FA встроен в Telegram, один владелец — нет смысла в отдельном auth-сервисе | Email+password+2FA (нужен хеш паролей), Passkeys (сложная настройка), VPN-only (неудобен) |
| 16 | Cookie sessions вместо JWT для admin | Server-side invalidation при logout/компрометации, нет refresh token логики, `path=/api/admin` изолирует от основного сайта | JWT (stateless — нельзя инвалидировать без блэклиста), sessionStorage (утечка при XSS) |
| 17 | Structlog + JSON-логи | Machine-readable формат для Docker log aggregation, structured context через contextvars (request_id), легко парсить `docker logs | python -m json.tool` | Стандартный logging (text), ELK/Loki stack (overkill для VPS) |
| 18 | Chart.js + SortableJS через CDN | Нет npm/build step, нет Node.js зависимости, CDN-кеширование, Chart.js 4.4.7 (~200KB) и SortableJS (~30KB) — приемлемо | Recharts (требует React), D3 (overkill), локальные бандлы (нужен Webpack/Vite) |
| 19 | Event tracking в PostgreSQL (app_events) | Единая БД, SQL-аналитика, простая схема, нет внешних зависимостей | Elasticsearch (overkill), ClickHouse (отдельный сервис), Mixpanel/Amplitude (зарубежные, нарушают 152-ФЗ) |
| 20 | Анонимизация telegram_id через SHA256+salt | Необратимо — нельзя восстановить telegram_id из лога, консистентно — один пользователь всегда один anonymous_id, privacy-first | UUID random (нет consistency для аналитики), reversible encoding (раскрывает данные при утечке соли) |

## Известные технические ограничения

### Telegram Mini App

- **MainButton** недоступна в обычных браузерах — в коде есть fallback на HTML-кнопку `<div class="bottom-cta">`
- **Inline-режим** бота требует ручной активации в BotFather: Bot Settings → Inline Mode
- **BackButton** управляется через `tg.BackButton.show()/hide()` — при открытии вне Telegram недоступна
- **initData** валидируется на backend через HMAC-SHA256 (`validate_init_data()`) с проверкой auth_date (max 24ч)
- **WebApp SDK** подключается через CDN `https://telegram.org/js/telegram-web-app.js` — нет fallback при недоступности

### Инфраструктура

- **Домен:** `dovstrechiapp.ru` — захардкожен в nginx.conf
- **SSL-сертификат** нужно получить вручную при первом деплое (`make ssl`)
- **Нет автоскейлинга** — один инстанс каждого сервиса на VPS
- **CI/CD делает `git reset --hard`** — любые локальные изменения на сервере будут потеряны
- **Нет health-check мониторинга** — нет Grafana, Prometheus или аналогов
- **Нет автоматического backup** — `make backup` нужно запускать вручную или по cron

### Бизнес-логика

- **Генерация meeting_link** всегда создаёт Jitsi-ссылку, даже если `platform != 'jitsi'` (`backend/utils.py: generate_meeting_link()`)
- **Нет статуса `completed`** в БД — фронтенд определяет завершённые встречи по `scheduled_time < now()`
- **Таймзоны реализованы** — `users.timezone` (IANA), `available_slots` работает в зоне организатора, `viewer_tz` для гостя
- **Лимит 10 встреч** в боте — `bookings[:10]` в `cb_my_bookings()` (`bot/handlers/navigation.py`)
- **Нет пагинации** в API — все запросы возвращают полные списки
- **Rate limiting через nginx** — `/api/` 10 req/s burst=20, `/api/bookings` 5 req/min burst=3. На уровне backend ограничений нет
- **Нет валидации email** на backend — `guest_contact` принимает любую строку
- **Отфильтрованные cancelled** — GET `/api/bookings` по умолчанию исключает cancelled встречи из SQL, фронтенд видит их только если запрашивает специально

## Технический долг

| Приоритет | Проблема | Где в коде | Рекомендуемое решение | Статус |
|-----------|----------|-----------|----------------------|--------|
| ~~Высокий~~ | ~~Нет валидации Telegram InitData~~ | ~~`backend/main.py`~~ | ~~HMAC-подпись~~ | ✅ Решено |
| ~~Высокий~~ | ~~CORS allow_origins=["*"]~~ | ~~`backend/main.py`~~ | ~~Whitelist~~ | ✅ Решено |
| ~~Высокий~~ | ~~Секреты в .env.example~~ | ~~`.env.example`~~ | ~~Плейсхолдеры~~ | ✅ Решено |
| ~~Средний~~ | ~~Всё в одном файле (backend)~~ | ~~`backend/main.py` (~1785 строк)~~ | ~~Разделить на routers/, schemas/, db/~~ | ✅ Решено (коммит a48ef7c) |
| ~~Средний~~ | ~~Всё в одном файле (bot)~~ | ~~`bot/bot.py` (879 строк)~~ | ~~Разделить на handlers/, keyboards/, states.py~~ | ✅ Решено (коммит 39ca389) |
| ~~Средний~~ | ~~Всё в одном файле (frontend)~~ | ~~`frontend/index.html` (~3100 строк)~~ | ~~Вынести JS в отдельные файлы~~ | ✅ Решено |
| ~~Средний~~ | ~~Всё в одном файле (admin)~~ | ~~`admin/index.html` (~2260 строк)~~ | ~~Вынести JS/CSS в отдельные файлы~~ | ✅ Решено (коммит ad30b5d) |
| ~~Средний~~ | ~~Нет миграций~~ | ~~`database/init.sql`~~ | ~~Ручные миграции~~ | ✅ Частично (ручные SQL-файлы в `database/migrations/`) |
| Средний | Нет тестов | весь проект | Добавить pytest (backend), pytest-aiogram (bot) | Открыт |
| ~~Средний~~ | ~~Нет таймзон~~ | ~~`backend/main.py`~~ | ~~ZoneInfo~~ | ✅ Решено (users.timezone + viewer_tz) |
| Средний | generate_meeting_link игнорирует platform | `backend/utils.py: generate_meeting_link()` | Генерировать разные ссылки по platform | Открыт |
| Низкий | Нет пагинации | GET `/api/bookings`, GET `/api/schedules` | Добавить `limit`/`offset` query params | Открыт |
| ~~Низкий~~ | ~~Нет rate limiting~~ | ~~весь backend~~ | ~~nginx rate limiting~~ | ✅ Частично (nginx, не backend) |
| ~~Низкий~~ | ~~Нет логирования запросов~~ | ~~`backend/main.py`~~ | ~~Добавить access log middleware~~ | ✅ Решено (StructlogMiddleware) |
| Низкий | skip_updates=True при старте бота | `bot/bot.py` | Рассмотреть обработку пропущенных сообщений | Открыт |

## Задокументированные workarounds

### Trailing slash в MINI_APP_URL

**Проблема:** двойной слеш в URL бронирования: `https://domain.ru/?schedule_id=...` или `https://domain.ru//?schedule_id=...`

**Решение:** не ставить `/` в конце `MINI_APP_URL` в .env. Бот конкатенирует через `f"{MINI_APP_URL}?schedule_id={id}"`.

### Фронтенд без билд-системы

**Проблема:** ~~весь CSS + HTML + JS в одном файле ~3100 строк~~ — **решено рефакторингом**.

**Текущий подход:** `frontend/index.html` (HTML), `frontend/css/style.css`, `frontend/js/*.js` (10 модулей). Раздаётся nginx как статика. Нет npm, нет Webpack/Vite, нет минификации.

**Почему:** нулевая сложность деплоя, нет зависимости от Node.js, мгновенная загрузка в Telegram Mini App.

### Jitsi как универсальная платформа

**Проблема:** пользователь может выбрать Zoom или «Другое» как платформу, но meeting_link всё равно генерируется для Jitsi Meet.

**Текущий код:** `backend/utils.py: generate_meeting_link()` — всегда возвращает Jitsi-ссылку.

**Решение на будущее:** интеграция с Zoom API (требует OAuth), добавление поля для пользовательской ссылки.

### FSM storage в памяти

**Проблема:** при перезапуске бота все незавершённые FSM-сессии (создание расписания) теряются.

**Текущий подход:** `MemoryStorage()` в `bot/bot.py`. Достаточно для одного инстанса.

**Решение при масштабировании:** перейти на `RedisStorage` из aiogram, добавить Redis в docker-compose.

### Вложенные bind mounts в docker-compose (INC-001)

**Проблема:** коммит `6eb6181` добавил `./admin:/usr/share/nginx/html/admin:ro` внутрь уже существующего `./frontend:/usr/share/nginx/html:ro`. Docker не может создать mountpoint внутри read-only overlayfs — nginx перестал запускаться, **9 часов полного даунтайма**.

**Решение:** убран `:ro` с родительского маунта (`./frontend:/usr/share/nginx/html`). Дочерний admin остаётся `:ro`.

**Правило:** никогда не ставить `:ro` на родительский bind mount, если внутрь него вложен другой. Полный разбор: `docs/incidents/INC_001_NGINX_GRAY_SCREEN.md`.

### Frontend gray screen protection (INC-001)

**Проблема:** `#app` начинает с `opacity:0` и становится видимым только после `classList.add('ready')` в JS. Если JS падает — приложение навсегда остаётся прозрачным (серый экран).

**Решение:** три слоя защиты:
1. CSS `@keyframes _force-show` — автопоказ через 5 секунд без JS
2. Global `error`/`unhandledrejection` handlers → добавляют `.ready`
3. Весь TG SDK init обёрнут в try/catch

**Правило:** не удалять эти механизмы. Любой новый код инициализации, блокирующий видимость, должен быть обёрнут в try/catch.

### Пауза vs удаление расписания

**Проблема:** на backend оба действия выглядят одинаково — `PATCH is_active=false`. Нет способа различить «приостановлено» от «удалено» без дополнительного поля в БД.

**Решение:** фронтенд хранит `deleted_schedules` (Set UUID) в localStorage. При пуш удаления — ID добавляется в Set и расписание скрывается из UI. При паузе — ID не добавляется, расписание показывается с `opacity: 0.55`. Восстановление: `PATCH is_active=true` + удаление из localStorage.

**Ограничение:** при смене устройства «удалённые» расписания снова появятся в UI до следующего действия. Технический долг: добавить `is_deleted` поле в БД.

### Быстрое добавление встречи (Quick Add)

**Проблема:** организатор хочет добавить личную встречу без публичного расписания.

**Решение:** `POST /api/meetings/quick` — если `schedule_id` не передан, автоматически создаётся скрытое расписание (`is_default=TRUE`, `is_active=FALSE`). Такие расписания не отображаются в `/api/schedules`.

**Реализация:** `backend/routers/meetings.py: get_or_create_default_schedule()`, `frontend/js/quickadd.js`.

### ~~Отсутствие push-уведомлений~~ ✅ Решено

**Было:** организатор не получал push при новом бронировании.

**Решение:** реализован двусторонний канал уведомлений:
- Backend → `POST http://bot:8080/internal/notify` (fire-and-forget через httpx)
- Бот отправляет сообщение организатору (с InlineKeyboard ✅/❌) и гостю
- Дополнительно: фоновый reminder_loop — напоминания за 24ч и 1ч
