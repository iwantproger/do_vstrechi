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
| 12 | CORS allow_origins=["*"] | Упрощение разработки, Mini App открывается с разных origin'ов | Whitelist конкретных доменов |
| 13 | MemoryStorage для FSM | Достаточно для одного инстанса бота, нет зависимости от Redis | Redis storage (нужен при масштабировании) |
| 14 | Docker Compose 3.9 | Стандарт оркестрации для single-server deployment | Kubernetes (overkill), bare-metal |

## Известные технические ограничения

### Telegram Mini App

- **MainButton** недоступна в обычных браузерах — в коде есть fallback на HTML-кнопку `<div class="bottom-cta">`
- **Inline-режим** бота требует ручной активации в BotFather: Bot Settings → Inline Mode
- **BackButton** управляется через `tg.BackButton.show()/hide()` — при открытии вне Telegram недоступна
- **initDataUnsafe** не валидируется на backend — нет проверки HMAC-подписи
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
- **Нет таймзон** — `available_slots` использует `datetime.utcnow()` для фильтрации, но `scheduled_time` хранится как TIMESTAMPTZ. Пользователь видит время в UTC
- **Лимит 10 встреч** в боте — `bookings[:10]` в `cb_my_bookings()` (строка 437 `bot/bot.py`)
- **Нет пагинации** в API — все запросы возвращают полные списки
- **Нет rate limiting** — API открыт без ограничений
- **Нет валидации email** на backend — `guest_contact` принимает любую строку
- **Отфильтрованные cancelled** — GET `/api/bookings` по умолчанию исключает cancelled встречи из SQL, фронтенд видит их только если запрашивает специально

## Технический долг

| Приоритет | Проблема | Где в коде | Рекомендуемое решение |
|-----------|----------|-----------|----------------------|
| Высокий | Нет валидации Telegram InitData | `backend/main.py` — все роуты | Добавить middleware для проверки HMAC-подписи |
| Высокий | CORS allow_origins=["*"] | `backend/main.py:57-63` | Ограничить: `[MINI_APP_URL, "https://web.telegram.org"]` |
| Высокий | Секреты в .env.example | `.env.example` | Заменить реальные токены на плейсхолдеры |
| Средний | Всё в одном файле (backend) | `backend/main.py` (497 строк) | Разделить на routers/, schemas/, db/ |
| Средний | Всё в одном файле (bot) | `bot/bot.py` (573 строки) | Разделить на handlers/, keyboards/, states.py |
| Средний | Всё в одном файле (frontend) | `frontend/index.html` (~2200 строк) | Вынести JS в отдельные файлы |
| Средний | Нет миграций | `database/init.sql` | Внедрить alembic или ручные миграции |
| Средний | Нет тестов | весь проект | Добавить pytest (backend), pytest-aiogram (bot) |
| Средний | Нет таймзон | `backend/main.py:285` (`datetime.utcnow()`) | Использовать `datetime.now(UTC)`, передавать TZ пользователя |
| Средний | generate_meeting_link игнорирует platform | `backend/main.py:108-112` | Генерировать разные ссылки по platform |
| Низкий | Нет пагинации | GET `/api/bookings`, GET `/api/schedules` | Добавить `limit`/`offset` query params |
| Низкий | Нет rate limiting | весь backend | Добавить slowapi или middleware |
| Низкий | Нет логирования запросов | `backend/main.py` | Добавить access log middleware |
| Низкий | skip_updates=True при старте бота | `bot/bot.py:570` | Рассмотреть обработку пропущенных сообщений |

## Задокументированные workarounds

### Trailing slash в MINI_APP_URL

**Проблема:** двойной слеш в URL бронирования: `https://domain.ru/?schedule_id=...` или `https://domain.ru//?schedule_id=...`

**Решение:** не ставить `/` в конце `MINI_APP_URL` в .env. Бот конкатенирует через `f"{MINI_APP_URL}?schedule_id={id}"`.

### Фронтенд без билд-системы

**Проблема:** весь CSS + HTML + JS в одном файле ~2200 строк.

**Текущий подход:** один `index.html` раздаётся nginx как статика. Нет npm, нет Webpack/Vite, нет минификации.

**Почему:** нулевая сложность деплоя, нет зависимости от Node.js, мгновенная загрузка в Telegram Mini App.

### Jitsi как универсальная платформа

**Проблема:** пользователь может выбрать Zoom или «Другое» как платформу, но meeting_link всё равно генерируется для Jitsi Meet.

**Текущий код:** `backend/main.py:108-112` — функция `generate_meeting_link()` всегда возвращает Jitsi-ссылку.

**Решение на будущее:** интеграция с Zoom API (требует OAuth), добавление поля для пользовательской ссылки.

### FSM storage в памяти

**Проблема:** при перезапуске бота все незавершённые FSM-сессии (создание расписания) теряются.

**Текущий подход:** `MemoryStorage()` в `bot/bot.py:564`. Достаточно для одного инстанса.

**Решение при масштабировании:** перейти на `RedisStorage` из aiogram, добавить Redis в docker-compose.

### Отсутствие push-уведомлений

**Проблема:** организатор не получает push при новом бронировании. Бот только логирует событие.

**Текущий код:** `backend/main.py:343` — `log.info(f"New booking created: ...")`, но нет HTTP-вызова к боту.

**Решение на будущее:** webhook от backend к боту или polling новых бронирований в боте.
