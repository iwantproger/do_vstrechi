# Отчёт о чистке кода
> Дата: 2026-04-15
> Ветка: main (HEAD), выполнено из рабочей копии dev-задач
> Стратегия: минимально-инвазивная — удалены только DEFINITELY unused элементы

## Методология

1. Прочитан `docs/AUDIT_REPORT.md` для контекста уже известных проблем.
2. Для каждого Python-модуля проверялось использование каждого имени из `import X` / `from X import Y` через grep внутри файла.
3. Функции/классы проверялись на внешние вызовы через grep по `backend/`, `bot/`, `frontend/`, `admin/`.
4. Сомнительные случаи (потенциально вызываемые через строки, dynamic dispatch, onclick) — ОСТАВЛЕНЫ без изменений.
5. `.cleanup.bak` создан для каждого изменённого файла.
6. Защитные обёртки (`_force-show`, `@keyframes`, `.ready`, `escHtml`, global error handlers, try/catch Telegram SDK init, health endpoints) НЕ тронуты по требованию ТЗ.

## Удалено

### Backend

| Файл | Строки | Что удалено | Причина |
|------|--------|-------------|---------|
| `backend/utils.py` | 3, 5, 6 | `import json`, `import asyncio`, `import logging` | Ни одно имя не используется в файле (grep подтвердил 0 упоминаний) |
| `backend/auth.py` | 8 | `from typing import Optional` | 0 упоминаний — сигнатуры используют PEP 604 (`dict \| None`, `str \| None`) |
| `backend/routers/users.py` | 5 | `import hashlib` | 0 упоминаний — вся хеш-логика вынесена в `utils.anonymize_id` и `event_buffer` |
| `backend/routers/admin.py` | 3 | `import json` | 0 упоминаний — сериализация выполняется в `auth.log_admin_action` / `event_buffer` |
| `backend/routers/admin.py` | 18 | `anonymize_id` (в импорте из utils) | 0 упоминаний — анонимизация делается в `event_buffer` |
| `backend/routers/admin.py` | 35 | Константа `ALLOWED_EVENT_FILTERS = {...}` | Определена, но нигде не используется. Фильтры event_type/severity/anonymous_id проверяются через Pydantic/Query параметры |

### Bot

| Файл | Строки | Что удалено | Причина |
|------|--------|-------------|---------|
| — | — | — | Явных dead-imports или unused handler-функций не найдено. Все `router.message` / `router.callback_query` обработчики реально вызываются из соответствующих entry points. Debug-print'ов нет |

### Frontend

| Файл | Строки | Что удалено | Причина |
|------|--------|-------------|---------|
| `frontend/js/calendar.js` | 517 | `// TODO: ждём backend — organizer fields in GET /api/schedules/{id}` | TODO выполнен — `backend/routers/schedules.py:116-124` GET `/api/schedules/{id}` уже возвращает `organizer_first_name`, `organizer_last_name`, `organizer_username` (JOIN с users). Фронтенд уже их использует в соседних строках |

### Admin

| Файл | Строки | Что удалено | Причина |
|------|--------|-------------|---------|
| `admin/js/auth.js` | 14 | `console.log('[ADMIN AUTH] Telegram callback received, id=' + ...)` | Отладочный лог, раскрывает данные Telegram-коллбэка в DevTools. `console.error` на line 30 намеренно ОСТАВЛЕН (нужен для диагностики production-проблем) |
| `admin/js/auth.js` | 22 | `console.log('[ADMIN AUTH] Login success')` | То же |

## Не удалено (требует подтверждения)

| Файл | Строки | Что | Почему сомнение |
|------|--------|-----|-----------------|
| `backend/routers/bookings.py` | 212-230 | Константы `_REMINDER_CFG`, `_REMINDER_SELECT` и эндпоинт `GET /api/bookings/pending-reminders` | Используются только в legacy-эндпоинте `/pending-reminders` (v1). Бот (`reminders.py`) использует `/pending-reminders-v2`. Эндпоинт v1, вероятно, deprecated, но ещё может вызываться внешними инструментами. **TODO: verify if used** |
| `backend/routers/admin.py` | 15 | `_session_checked` импорт | Используется в `admin_me` и `admin_logout`. Не удалено |
| `backend/utils.py:27-31` | `rows_to_list` | Функция-обёртка | Используется в roouters (stats/admin/schedules/bookings). Оставлена |
| `database/init.sql` | VIEW `bookings_detail` | SQL view | Аудит (AUDIT_REPORT.md:580) отметил как dead code. Не тронут — влияние на БД требует отдельной миграции, scope этой чистки ограничен кодом |
| `bot/formatters.py` | `format_booking` | Функция | Используется в `bot/handlers/bookings.py:25`. Оставлена |
| `backend/auth.py` | `verify_telegram_login` | Функция | Используется в `admin.py:75`. Оставлена |
| `frontend/js/utils.js` | `updateSlider` vs `updateSliderSmart` | Почти идентичные функции | AUDIT_REPORT.md указал как дублирующие (P3), но обе активно вызываются в разных местах. Рефакторинг выходит за рамки dead-code cleanup |
| `frontend/js/schedules.js` | `getFormScheduleData` / `collectScheduleForm` | Дублирующие 95% логики | Обе вызываются (создание vs редактирование). Рефакторинг нужен, но это не dead code |
| `frontend//admin/ CSS selectors` | — | Классы и ID из style.css / admin.css | Полный cross-check 500+ селекторов против HTML + JS (в т.ч. динамически добавляемых через `classList.add(...)` + string literals) выходит за безопасный scope автоматической чистки. Риск false-positive слишком высок. **TODO: separate CSS audit pass** |
| `bot/services/reminders.py` | `_REMINDER_LABEL` / `send_confirmation_request` / `send_pending_guest_notice` / `send_morning_organizer_summary` | Все реально вызываются из `_reminder_tick`. Не тронуты |

## Защитные обёртки — ПОДТВЕРЖДЕНО сохранены

- `escHtml()` в `frontend/js/utils.js:51-53` и `frontend/index.html` — не тронут
- `@keyframes _force-show` в CSS — не искал/не удалял (по ТЗ запрещено)
- Global error handlers — не тронуты
- `try/catch` вокруг Telegram SDK init (`bot.set_chat_menu_button` в `start.py:53-64`) — не тронут
- Health endpoints (`/`, `/health` в `backend/main.py:154-176`) — не тронуты

## Статистика

- **Удалено строк:** 11 (чистая дельта)
- **Затронуто файлов:** 6
- **Backup-файлов создано:** 6 (с суффиксом `.cleanup.bak`, чтобы не путать с существующими `.bak` от предыдущих чисток)
- **Снижение размера кодовой базы:** ~0.01% (кодовая база >10000 строк)
- **Риск регрессии:** минимальный (удалены только 100% подтверждённо неиспользуемые imports / const / console.log / TODO-комментарий)

## Проверка

Все изменённые файлы прошли AST-синтаксис-чек (Python) и `node -c` (JS).
Импорт `backend.main:app` не проверен на этом хосте (отсутствует `structlog` в `python3` по умолчанию),
но AST подтвердил корректность Python-синтаксиса во всех модулях backend/ и bot/.

## Backup-файлы

```
backend/utils.py.cleanup.bak
backend/auth.py.cleanup.bak
backend/routers/users.py.cleanup.bak
backend/routers/admin.py.cleanup.bak
admin/js/auth.js.cleanup.bak
frontend/js/calendar.js.cleanup.bak
```

## Рекомендации на будущее

1. **CSS audit** — требует отдельного прохода с ручной проверкой каждого селектора. Автоматический grep даёт слишком много false-positives (классы добавляются динамически, имена генерируются шаблонно).
2. **VIEW `bookings_detail`** — реально dead code (по AUDIT_REPORT.md). Удалить через отдельную миграцию, например `016_drop_unused_view.sql`.
3. **Legacy reminder endpoints** — `/pending-reminders` (v1) и поля `reminder_24h_sent` etc. — если переход на v2 завершён, можно удалить. Требует grep по deploy/infra скриптам.
4. **`.bak` файлы прежних чисток** (`backend/*.py.bak`, `bot/*.py.bak*`, `frontend/js/*.js.bak`, `admin/js/*.js.bak`) — накопились, стоит удалить через `find . -name '*.bak*' -delete` после ревью текущего PR.
