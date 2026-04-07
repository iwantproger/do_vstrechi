# Текущее состояние проекта — 2026-04-07

## Что работает
- Telegram Mini App: авторизация, бронирование встреч, профиль, напоминания, changelog
- Бот: /start, FSM создания расписания, список встреч, подтверждение/отмена, push-уведомления, reminder_loop
- Admin-панель: дашборд, логи, kanban-доска задач, системная информация
- PostgreSQL: все таблицы, 5 миграций применены (002–005)
- CI/CD: GitHub Actions → SSH → git pull + docker compose up

## Структура проекта (текущая — после рефакторинга)
```
backend/
  main.py (~140 строк), config.py, database.py, auth.py, schemas.py, utils.py
  routers/ — users.py, schedules.py, bookings.py, meetings.py, stats.py, admin.py

bot/
  bot.py (~70 строк), config.py, api.py, states.py, keyboards.py, formatters.py
  handlers/ — start.py, navigation.py, schedules.py, bookings.py, create.py
  services/ — notifications.py, reminders.py

frontend/
  index.html, css/style.css
  js/ — api.js, state.js, config.js, utils.js, nav.js, bookings.js,
         schedules.js, calendar.js, quickadd.js, profile.js

admin/
  index.html, css/admin.css
  js/ — config.js, auth.js, dashboard.js, logs.js, tasks.js, settings.js
```

## Последние изменения (апрель 2026)
- **a48ef7c** — рефакторинг backend/main.py → модули (routers/, schemas.py, auth.py, utils.py)
- **39ca389** — рефакторинг bot/bot.py → handlers/, services/
- **ad30b5d** — рефакторинг admin → css/ + js/
- **47686e5** — fix aiogram DefaultBotProperties (устаревший parse_mode)
- Новые эндпоинты: GET /api/bookings/{id}, POST /api/meetings/quick
- Новые миграции: 004_quick_add_meeting.sql, 005_min_booking_advance.sql
- Deep link бота: /start notify_{booking_id}

## Миграции БД (применённые)
- 002_add_timezone.sql — users.timezone
- 003_add_reminder_flags.sql — bookings.reminder_24h_sent / reminder_1h_sent
- 004_admin_tables.sql — admin_sessions, admin_audit_log, app_events, admin_tasks
- 004_quick_add_meeting.sql — schedules.is_default, bookings.{title, end_time, is_manual, created_by}
- 005_min_booking_advance.sql — schedules.min_booking_advance

## Известные ограничения
- Нет тестов (pytest)
- Нет пагинации в API
- generate_meeting_link() всегда возвращает Jitsi даже для zoom/other
- Лимит 10 встреч в боте (bot/handlers/navigation.py)
- Пауза vs удаление расписания — отличие только в localStorage фронтенда (не в БД)
- MemoryStorage для FSM — потеря сессий при перезапуске бота

## Критические правила (не нарушать!)
- Бот не ходит в БД напрямую — только через Backend API (bot/api.py)
- Async/await везде — никаких синхронных I/O (requests, time.sleep)
- Секреты только в .env
- 152-ФЗ — данные только на российском VPS (Timeweb)
- SQL только с параметрами $1, $2 — никаких f-строк
- Все protected endpoints используют Depends(get_current_user), не telegram_id из query
- escHtml() для всего пользовательского ввода в DOM
- Не ставить :ro на родительский bind mount если внутрь вложен другой (INC-001)
- Не удалять CSS @keyframes _force-show и global error handlers (серый экран)
- Пароли с @ и ! в DATABASE_URL требуют URL-encode
