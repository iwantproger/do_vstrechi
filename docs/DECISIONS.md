# Технические решения и ограничения

## Принятые архитектурные решения

| # | Решение | Обоснование | Отклонённые альтернативы |
|---|---------|-------------|------------------------|
| 1 | Self-hosted PostgreSQL 16 | 152-ФЗ — персональные данные хранятся на российском VPS | Supabase, PlanetScale, Neon (зарубежные managed DB) |
| 2 | asyncpg без ORM | Максимальная производительность и контроль SQL, минимум абстракций | SQLAlchemy async, Tortoise ORM |
| 3 | aiogram 3.6 | Современный async API, FSM из коробки, активное русскоязычное сообщество | python-telegram-bot, Telethon |
| 4 | Vanilla JS (без фреймворка) | Нулевой размер бандла, не нужен этап сборки, быстрая загрузка в Mini App | React, Vue, Svelte, Solid |
| 5 | Jitsi Meet для видеозвонков | Self-hosted, бесплатный, не требует API-ключей — ссылка генерируется по UUID | Zoom API (платный), Google Meet API (OAuth) |
| 6 | Монорепо (один репозиторий) | Единый деплой, общие конфиги, атомарные изменения | Отдельные репо для bot/backend/frontend |
| 7 | Timeweb VPS | Российский хостинг для 152-ФЗ, SSH-деплой через GitHub Actions | AWS, GCP, DigitalOcean (зарубежные) |
| 8 | Polling вместо Webhook | Проще настройка, не нужен публичный URL для бота, не нужен SSL для бота | Webhook (выше производительность при нагрузке) |
| 9 | Один файл на сервис | Быстрый старт, нет over-engineering на ранней стадии | Разделение на routers/, schemas/, db/ |
| 10 | Мягкое удаление расписаний | Сохранение данных бронирований, привязанных к расписанию | Физическое удаление (CASCADE удалит bookings) |
| 11 | UUID как первичные ключи | Безопасность: нельзя перебирать ID; уникальность без sequence | SERIAL / BIGSERIAL (предсказуемые ID) |
| 12 | CORS whitelist (dovstrechiapp.ru) | Безопасность: ограничить origin, methods, headers | allow_origins=["*"] (использовалось ранее, убрано) |
| 13 | MemoryStorage для FSM | Достаточно для одного инстанса бота, нет зависимости от Redis | Redis storage (нужен при масштабировании) |
| 14 | Docker Compose 3.9 | Стандарт оркестрации для single-server deployment | Kubernetes (overkill), bare-metal |

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

- **Генерация meeting_link** всегда создаёт Jitsi-ссылку, даже если `platform != 'jitsi'` (строка 108–112 `backend/main.py`)
- **Нет статуса `completed`** в БД — фронтенд определяет завершённые встречи по `scheduled_time < now()`
- **Таймзоны реализованы** — `users.timezone` (IANA), `available_slots` работает в зоне организатора, `viewer_tz` для гостя
- **Лимит 10 встреч** в боте — `bookings[:10]` в `cb_my_bookings()` (строка 437 `bot/bot.py`)
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
| Средний | Всё в одном файле (backend) | `backend/main.py` (714 строк) | Разделить на routers/, schemas/, db/ | Открыт |
| Средний | Всё в одном файле (bot) | `bot/bot.py` (879 строк) | Разделить на handlers/, keyboards/, states.py | Открыт |
| Средний | Всё в одном файле (frontend) | `frontend/index.html` (~3100 строк) | Вынести JS в отдельные файлы | Открыт |
| ~~Средний~~ | ~~Нет миграций~~ | ~~`database/init.sql`~~ | ~~Ручные миграции~~ | ✅ Частично (ручные SQL-файлы в `database/migrations/`) |
| Средний | Нет тестов | весь проект | Добавить pytest (backend), pytest-aiogram (bot) | Открыт |
| ~~Средний~~ | ~~Нет таймзон~~ | ~~`backend/main.py`~~ | ~~ZoneInfo~~ | ✅ Решено (users.timezone + viewer_tz) |
| Средний | generate_meeting_link игнорирует platform | `backend/main.py:188-193` | Генерировать разные ссылки по platform | Открыт |
| Низкий | Нет пагинации | GET `/api/bookings`, GET `/api/schedules` | Добавить `limit`/`offset` query params | Открыт |
| ~~Низкий~~ | ~~Нет rate limiting~~ | ~~весь backend~~ | ~~nginx rate limiting~~ | ✅ Частично (nginx, не backend) |
| Низкий | Нет логирования запросов | `backend/main.py` | Добавить access log middleware | Открыт |
| Низкий | skip_updates=True при старте бота | `bot/bot.py:866` | Рассмотреть обработку пропущенных сообщений | Открыт |

## Задокументированные workarounds

### Trailing slash в MINI_APP_URL

**Проблема:** двойной слеш в URL бронирования: `https://domain.ru/?schedule_id=...` или `https://domain.ru//?schedule_id=...`

**Решение:** не ставить `/` в конце `MINI_APP_URL` в .env. Бот конкатенирует через `f"{MINI_APP_URL}?schedule_id={id}"`.

### Фронтенд без билд-системы

**Проблема:** весь CSS + HTML + JS в одном файле ~3100 строк.

**Текущий подход:** один `index.html` раздаётся nginx как статика. Нет npm, нет Webpack/Vite, нет минификации.

**Почему:** нулевая сложность деплоя, нет зависимости от Node.js, мгновенная загрузка в Telegram Mini App.

### Jitsi как универсальная платформа

**Проблема:** пользователь может выбрать Zoom или «Другое» как платформу, но meeting_link всё равно генерируется для Jitsi Meet.

**Текущий код:** `backend/main.py:188-193` — функция `generate_meeting_link()` всегда возвращает Jitsi-ссылку.

**Решение на будущее:** интеграция с Zoom API (требует OAuth), добавление поля для пользовательской ссылки.

### FSM storage в памяти

**Проблема:** при перезапуске бота все незавершённые FSM-сессии (создание расписания) теряются.

**Текущий подход:** `MemoryStorage()` в `bot/bot.py:858`. Достаточно для одного инстанса.

**Решение при масштабировании:** перейти на `RedisStorage` из aiogram, добавить Redis в docker-compose.

### ~~Отсутствие push-уведомлений~~ ✅ Решено

**Было:** организатор не получал push при новом бронировании.

**Решение:** реализован двусторонний канал уведомлений:
- Backend → `POST http://bot:8080/internal/notify` (fire-and-forget через httpx)
- Бот отправляет сообщение организатору (с InlineKeyboard ✅/❌) и гостю
- Дополнительно: фоновый reminder_loop — напоминания за 24ч и 1ч
