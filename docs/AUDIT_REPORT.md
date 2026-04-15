# Аудит кодовой базы «До встречи»
> Дата: 2026-04-15 | Версия: v1.2.0 | Аудитор: AI Senior Architect (claude-sonnet-4-6)

---

## 1. Карта системы

### 1.1 Реальные модули (таблица)

| Файл | Строк (прибл.) | Ключевые зависимости | Внешние вызовы | Сложность |
|------|-----------------|----------------------|----------------|-----------|
| `backend/main.py` | 159 | structlog, FastAPI, calendars.sync | calendars.registry | Низкая |
| `backend/config.py` | 49 | os, hashlib | — | Низкая |
| `backend/database.py` | 110 | asyncpg | PostgreSQL | Низкая |
| `backend/auth.py` | 201 | hmac, hashlib, asyncpg | — | Средняя |
| `backend/schemas.py` | 127 | pydantic | — | Низкая |
| `backend/utils.py` | 94 | httpx, hashlib | bot:8080 (HTTP) | Низкая |
| `backend/routers/users.py` | 185 | httpx, asyncpg | Telegram Bot API (аватар) | Средняя |
| `backend/routers/schedules.py` | 372 | asyncpg, zoneinfo | calendars.db | Высокая |
| `backend/routers/bookings.py` | 753 | asyncpg, asyncio | bot:8080 (async), calendars.sync | Высокая |
| `backend/routers/meetings.py` | 145 | asyncpg | — | Средняя |
| `backend/routers/stats.py` | 34 | asyncpg | — | Низкая |
| `backend/routers/admin.py` | 628 | asyncpg, structlog | — | Высокая |
| `bot/bot.py` | 88 | aiogram, aiohttp, Redis (опционально) | Telegram API | Низкая |
| `bot/api.py` | 26 | aiohttp | backend:8000 | Низкая |
| `bot/handlers/start.py` | 435 | aiogram, api | backend (2 вызова при /start) | Высокая |
| `bot/handlers/navigation.py` | 101 | aiogram, api | backend (1 вызов/callback) | Средняя |
| `bot/handlers/bookings.py` | 109 | aiogram, api | backend (ALL + filter) | Средняя |
| `bot/handlers/schedules.py` | 70 | aiogram, api | backend | Низкая |
| `bot/handlers/create.py` | 161 | aiogram, api | backend (1 POST при финале) | Средняя |
| `bot/handlers/inline.py` | 124 | aiogram, api | backend | Средняя |
| `bot/services/notifications.py` | 225 | aiohttp, aiogram | Telegram API | Средняя |
| `bot/services/reminders.py` | 236 | aiogram, api | backend (5-7 вызовов/60с) | Высокая |
| `frontend/js/api.js` | 44 | — | backend (все /api/) | Низкая |
| `frontend/js/state.js` | 23 | — | — | Низкая |
| `frontend/js/nav.js` | 121 | — | — | Низкая |
| `frontend/js/utils.js` | 269 | — | backend (/api/users/*/avatar) | Средняя |
| `frontend/js/bookings.js` | 795 | — | backend (/api/bookings, /api/calendar/external-events) | Высокая |
| `frontend/js/schedules.js` | 997 | — | backend (/api/schedules, /api/calendar/*) | Высокая |
| `frontend/js/calendar.js` | 100+ | — | backend (/api/schedules, /api/available-slots) | Высокая |
| `database/init.sql` | 274 | PostgreSQL 16 | — | Средняя |
| `nginx/nginx.conf` | 314 | nginx 1.25 | — | Средняя |
| `docker-compose.yml` | 140 | Docker Compose 3.9 | — | Низкая |

### 1.2 Граф связности

**Наибольший coupling:**

- `bot/handlers/start.py` — наиболее перегруженный файл бота: обрабатывает /start, reply-кнопки профиля, встречи, расписания, deep links, callback-уведомления. Содержит 7 хендлеров вместо 1-2. Сложность затрудняет навигацию.
- `backend/routers/bookings.py` — 753 строки, 15+ роутов включая reminder-эндпоинты, confirmation flow, no_answer, morning summaries. Правильная точка декомпозиции — вынести reminder/confirmation в отдельный роутер.
- `backend/routers/admin.py` — 628 строк, смешивает auth, dashboard, tasks, logs, audit, maintenance, event tracking.
- `frontend/js/schedules.js` — 997 строк, содержит: список расписаний, детали, создание, редактирование, шаринг, удаление, preview, calendar config. Монолит.
- `backend/calendars/` — отдельный подмодуль (~14 файлов), слабо связан с основным кодом, интегрируется через `import` внутри роут-функций (lazy import pattern).

**Ключевые внешние зависимости:**
- Bot ↔ Backend: HTTP через `X-Internal-Key` (правильно)
- Backend ↔ Bot: HTTP POST к bot:8080 (fire-and-forget, без retry)
- Backend ↔ Telegram API: только для аватарок (httpx)
- Bot ↔ Telegram API: polling (aiogram)

### 1.3 Несоответствия документации

| Что в коде | Что в CLAUDE.md | Расхождение |
|------------|-----------------|-------------|
| `bot/config.py`: `REDIS_URL` переменная, Redis FSM если доступен | В CLAUDE.md нет REDIS_URL в таблице переменных | **Не задокументировано** |
| `database/migrations/013_morning_summary.sql` и `014_custom_link.sql` | В списке миграций в CLAUDE.md только до 012 | **Две миграции отсутствуют в документации** |
| `backend/calendars/` — целый подмодуль с 14 файлами | Упоминается только через `backend/routers/calendar.py` | Структура каталога не отражена |
| `GET /api/bookings/morning-organizer-summary`, `GET /api/bookings/morning-pending-guest-notice`, `PATCH /api/bookings/complete-past`, `PATCH /api/users/{telegram_id}/morning-summary-sent` | Отсутствуют в таблице API | **4 эндпоинта не задокументированы** |
| `bot/handlers/start.py` содержит reply-хендлеры 🏠 Главная, 📋 Встречи, 📅 Расписания, 👤 Профиль | В CLAUDE.md описаны другие текстовые кнопки: «📅 Создать расписание», «📋 Мои расписания» | Кнопки переименованы, документация устарела |
| `APP_VERSION = "1.2.0"` в config.py | Версия в CLAUDE.md: 1.2.0 — совпадает |

---

## 2. Критические проблемы (P0–P1)

### [P1] Бот передаёт telegram_id в query params — обходит авторизацию

**Файл:** `bot/handlers/bookings.py:47`, `bot/handlers/navigation.py:24`, `bot/handlers/schedules.py:64`, `bot/handlers/create.py:137`, и многие другие

**Факт — из кода:**
```python
bookings = await api("get", f"/api/bookings?telegram_id={cb.from_user.id}")
result = await api("post", f"/api/schedules?telegram_id={telegram_id}", json=data)
stats = await api("get", f"/api/stats?telegram_id={cb.from_user.id}")
```

**Факт — из backend/auth.py:69-72:**
```python
internal_key = request.headers.get("X-Internal-Key")
if internal_key and INTERNAL_API_KEY and hmac.compare_digest(internal_key, INTERNAL_API_KEY):
    tid = request.query_params.get("telegram_id")
    if tid:
        return {"id": int(tid)}
```

**Проблема:** Бот передаёт telegram_id как query param, который backend принимает при наличии X-Internal-Key. Это задокументировано как запрещённый паттерн в CLAUDE.md: «Принимать telegram_id из query params или тела запроса для авторизации». Однако это единственный способ, которым бот аутентифицируется — через X-Internal-Key + telegram_id. Де-факто это intentional design, но создаёт риск: если INTERNAL_API_KEY слаб или утечёт, любой может подделать telegram_id.

**Impact:** При компрометации INTERNAL_API_KEY — полная возможность действовать от имени любого пользователя.

**Fix complexity:** Medium. Нужен отдельный Bot-specific auth flow.

**ROI:** Высокий — это архитектурный риск, но приемлемый в рамках внутреннего Docker network (бот к backend только через internal сеть).

---

### [P1] N+1 запрос в cb_booking_detail бота

**Файл:** `bot/handlers/bookings.py:19-22`

**Факт — из кода:**
```python
async def cb_booking_detail(cb: CallbackQuery):
    booking_id = cb.data.split("_", 1)[1]
    bookings = await api("get", f"/api/bookings?telegram_id={cb.from_user.id}")
    booking = next((b for b in (bookings or []) if b["id"] == booking_id), None)
```

**Проблема:** При открытии деталей одной встречи загружаются ВСЕ встречи пользователя (до 50), чтобы найти одну. Существует эндпоинт `GET /api/bookings/{booking_id}` именно для этого.

**Impact:** 50x лишний трафик и 50x лишняя нагрузка на БД при каждом просмотре встречи в боте.

**Fix complexity:** Low (5 минут). Заменить на `api("get", f"/api/bookings/{booking_id}")`.

**ROI:** Высокий.

---

### [P1] list_bookings в backend: фильтрация на Python вместо SQL

**Файл:** `backend/routers/bookings.py:126-187`

**Факт — из кода:**
```python
rows = await conn.fetch("""SELECT ... FROM bookings b ... WHERE (u.telegram_id = $1 OR b.guest_telegram_id = $1) AND b.status != 'cancelled' ...""", telegram_id)
result = rows_to_list(rows)
if role == "organizer":
    result = [r for r in result if r["my_role"] == "organizer"]
if schedule_id:
    result = [r for r in result if str(r.get("schedule_id", "")) == schedule_id]
if future_only:
    now = datetime.now(timezone.utc)
    result = [r for r in result if ...]
total = len(result)
paginated = result[offset:offset + limit]
```

**Проблема:** SQL-запрос не применяет фильтры `role`, `schedule_id`, `future_only` — они фильтруются в Python. Это означает: пагинация работает на уже отфильтрованном Python-списке (правильно), но SQL тянет ВСЕ записи пользователя перед фильтрацией. При 1000+ бронированиях — серьёзная проблема. Поле `status != 'cancelled'` захардкожено в SQL, тогда как filter='archive' в frontend ожидает отменённые.

**Impact:** При активном использовании (100+ встреч) — избыточный fetch всего списка в память Python.

**Fix complexity:** Medium. Добавить условия в WHERE clause.

**ROI:** Средний (актуально при росте пользователей).

---

### [P1] Динамический SQL без валидации имён колонок (SQL injection risk)

**Файл:** `backend/routers/schedules.py:190-210`, `backend/routers/admin.py:422-434`

**Факт — из кода (schedules.py:192-208):**
```python
updates = data.model_dump(exclude_none=True)
set_parts = []
values = []
for i, (col, val) in enumerate(updates.items(), start=1):
    set_parts.append(f"{col} = ${i}")
    values.append(val)
row = await conn.fetchrow(
    f"""UPDATE schedules SET {', '.join(set_parts)} WHERE id = ${n - 1} ...""",
    *values,
)
```

**Проблема:** Имена колонок берутся напрямую из `data.model_dump()` — то есть из имён полей Pydantic-схемы. Pydantic гарантирует, что поля только из `ScheduleUpdate`, поэтому произвольная инъекция невозможна. **Однако:** если к схеме когда-либо добавят поле с именем типа `"; DROP TABLE users --"` или если схема расширится некорректно — риск возрастёт. Это архитектурный антипаттерн: whitelist колонок должен быть явным.

**Impact:** [ПОТЕНЦИАЛЬНЫЙ РИСК] — сейчас не эксплуатируется за счёт Pydantic, но паттерн опасен при расширении.

**Fix complexity:** Low. Добавить явный ALLOWED_COLUMNS whitelist.

**ROI:** Средний (профилактика).

---

### [P1] in-memory rate limiter и session cache — не работают при горизонтальном масштабировании

**Файл:** `backend/auth.py:26-28`

**Факт — из кода:**
```python
_login_attempts: dict[str, list[float]] = {}
_session_checked: set[str] = set()
```

**Проблема:** Оба объекта хранятся в памяти процесса uvicorn. При:
- Перезапуске бэкенда — rate limit сбрасывается (атакующий может перезапустить через DoS)
- Нескольких воркерах uvicorn (`--workers 2`) — каждый воркер имеет свой словарь, rate limit обходится

При текущем деплое (1 воркер uvicorn в Docker) — некритично. Но `_session_checked` может вырасти неограниченно до `len(_session_checked) > 10000` (есть защита, но `_login_attempts` — нет).

**Impact:** При многоворкерном деплое — rate limit не работает совсем.

**Fix complexity:** Low (добавить TTL-cleanup для `_login_attempts`). Medium для Redis-backend.

**ROI:** Средний.

---

### [P1] MemoryStorage FSM бота — потеря состояния при перезапуске

**Файл:** `bot/bot.py:56`

**Факт — из кода:**
```python
storage = MemoryStorage()
```

**Проблема:** При перезапуске бота (деплой, краш) все незавершённые FSM-сессии создания расписания теряются. Пользователь, находящийся в процессе создания расписания (7-шаговый wizard), потеряет прогресс без предупреждения.

**Частичное решение:** Redis FSM задан условно через `REDIS_URL`, но `REDIS_URL` не указан в .env.example (судя по доступным данным).

**Impact:** UX деградация при каждом деплое. При активном использовании — потеря данных пользователей в процессе создания.

**Fix complexity:** Low — задать REDIS_URL в .env.

**ROI:** Высокий (простое исправление с большим эффектом).

---

### [P1] console.log с отладочными данными в production frontend

**Файл:** `frontend/js/bookings.js:764-768`

**Факт — из кода:**
```javascript
console.log('[cancel] id=', id, 'hasInitData=', !!tg?.initData, 'url=', '/api/bookings/' + id + '/cancel');
// ...
console.log('[cancel] response data=', data, 'error=', error);
```

**Проблема:** Отладочные логи в продакшн коде раскрывают структуру API и данные ответов в DevTools. Незначительно, но нарушает security best practices.

**Impact:** Низкий (только в браузере пользователя).

**Fix complexity:** Low (удалить строки).

**ROI:** Низкий, но быстро.

---

### [P1] Небезопасная дефолтная соль анонимизации

**Файл:** `backend/config.py:15`

**Факт — из кода:**
```python
ANONYMIZE_SALT = os.environ.get("ANONYMIZE_SALT", "do-vstrechi-2026")
```

**Проблема:** Если `ANONYMIZE_SALT` не задан в .env, используется публично известная строка "do-vstrechi-2026". Это делает анонимизацию через SHA256(telegram_id:"do-vstrechi-2026") тривиально обратимой для известных telegram_id (перебором).

**Impact:** Нарушение принципа анонимизации аналитики (152-ФЗ).

**Fix complexity:** Low. Сделать переменную обязательной или генерировать случайную при первом запуске.

**ROI:** Высокий.

---

## 3. Производительность (P2)

### [P2] Два HTTP-запроса при каждом /start

**Файл:** `bot/handlers/start.py:66-74`

**Факт — из кода:**
```python
await api("post", f"/api/users/auth?telegram_id={user.id}", json={...})
stats = await api("get", f"/api/stats?telegram_id={user.id}")
```

Два последовательных HTTP-вызова при каждом `/start`. Можно объединить в один ответ от `/api/users/auth` (вернуть stats вместе с профилем), или выполнять параллельно через `asyncio.gather`.

**Impact:** +50-100ms latency на каждый /start.

**Fix complexity:** Low (asyncio.gather).

---

### [P2] loadHome во фронтенде: два параллельных fetch + external calendar

**Файл:** `frontend/js/bookings.js:63-87`

**Факт — из кода:**
```javascript
var { data, error } = await apiFetch('GET', '/api/bookings?role=all');
// ...
var extRes = await apiFetch('GET', '/api/calendar/external-events?from_date=' + todayStr + '&to_date=' + todayStr);
```

Два последовательных fetch. Второй (`external-events`) — необязательный, но выполняется последовательно. Можно запускать параллельно через `Promise.all`.

**Impact:** +200-500ms при открытии Home screen.

**Fix complexity:** Low.

---

### [P2] Открытие расписания (s-schedule-view) делает 3 последовательных запроса

**Файл:** `frontend/js/schedules.js:447`, `863-876`

При открытии детали расписания (`openScheduleView`):
1. Данные уже есть в `state.schedules` — ОК
2. `loadScheduleCalConfig` делает параллельно 2 fetch (`Promise.all`) — ОК

Но на экране `loadMeetings` делает 2 fetch последовательно: bookings + external-events.

---

### [P2] Новая aiohttp.ClientSession на каждый API-вызов из бота

**Файл:** `bot/api.py:16-23`

**Факт — из кода:**
```python
async with aiohttp.ClientSession(timeout=timeout) as session:
    async with getattr(session, method)(url, headers=headers, **kwargs) as r:
```

При reminder_loop (60 вызовов/мин) создаётся новая ClientSession на каждый запрос. Это накладные расходы на TCP handshake и DNS resolution. Правильный паттерн — singleton session.

**Impact:** При большом количестве запросов — лишний overhead на TCP. При текущих масштабах — незначительно.

**Fix complexity:** Medium (требует инициализации session в lifespan).

**ROI:** Средний.

---

### [P2] available-slots: дополнительный запрос к external calendar на каждый GET

**Файл:** `backend/routers/schedules.py:298-325`

При каждом запросе доступных слотов выполняются дополнительные запросы:
1. `get_schedule_calendar_rules` — SELECT из schedule_calendar_rules
2. Если нет правил — SELECT всех calendar_connections пользователя
3. `get_external_busy_slots` — SELECT из external_busy_slots

Итого: основной запрос расписания + 2-3 дополнительных SELECT. Для популярного расписания при просмотре каждого дня — 3-4 SQL-запроса на вызов.

**Impact:** Задержка 30-100ms при наличии подключённых календарей.

**Fix complexity:** Medium (кэш на 1-5 минут).

---

### [P2] Fire-and-forget без retry — потеря уведомлений

**Файл:** `backend/utils.py:65-80`, `backend/routers/bookings.py:77`, `backend/routers/schedules.py:148`

**Факт — из кода:**
```python
asyncio.create_task(_notify_bot_new_booking(...))
# и в utils.py:
except Exception as e:
    log.warning("bot_notification_error", error=str(e))
```

При недоступности бота (перезапуск) уведомление теряется навсегда. Организатор не узнает о новом бронировании.

**Impact:** Бизнес-критично: пропущенные уведомления = потерянные клиенты.

**Fix complexity:** Medium (очередь + retry). High (полноценная message queue).

**ROI:** Очень высокий.

---

### [P2] reminder_loop: 5-7 HTTP-запросов каждую минуту к backend

**Файл:** `bot/services/reminders.py:173-235`

Каждые 60 секунд:
1. GET `/api/bookings/pending-reminders-v2`
2. Каждые 5 тиков (5 мин): + 4 дополнительных GET
3. Каждые 15 тиков (15 мин): + 1 POST

При каждом шаге reminder_loop — минимум 1-6 HTTP-запросов. При 0 активных напоминаний — всё равно 1 запрос в минуту (пустой ответ).

**Impact:** Минимальный при текущих масштабах. При тысячах пользователей — стоит добавить long-polling или SSE.

---

### [P2] admin.py: лог действий на КАЖДОМ запросе dashboard

**Файл:** `backend/routers/admin.py:130-131`

```python
await log_admin_action("view_dashboard", client_ip, {"path": "/api/admin/dashboard/summary"}, conn)
await log_admin_action("view_logs", client_ip, {"path": "/api/admin/logs"}, conn)
```

Каждый просмотр dashboard и logs записывает строку в `admin_audit_log`. При авто-обновлении каждые 30 секунд — 120 записей/час в audit_log. Таблица будет расти.

**Impact:** Раздувание `admin_audit_log`. Имеет смысл логировать только реальные действия (login, task_create/update/delete), не просмотры.

**Fix complexity:** Low.

---

## 4. Качество кода (P3)

### [P3] TODO без реализации: remind_30m/15m_BOOKING_ID

**Файл:** `bot/handlers/start.py:434`

**Факт — из кода:**
```python
await callback.answer(f"✅ Напоминание за {interval_text} добавлено!")
# TODO: сохранить в БД через API
```

Пользователь получает сообщение «добавлено», но ничего не сохраняется. Это ложная обратная связь.

**Impact:** P1 с точки зрения пользователя (обман), P3 с точки зрения кода.

**Fix complexity:** Low — есть `/api/users/notification-settings`.

---

### [P3] Дублирование logic сбора данных формы расписания

**Файл:** `frontend/js/schedules.js`

Функции `getFormScheduleData()` (создание) и `collectScheduleForm()` (редактирование) — практически идентичны по структуре (собирают те же поля из разных DOM-элементов с разными ID: `nw-*` vs `sl-*`). Логика валидации и сборки дублируется.

**Impact:** Рассинхрон: добавление нового поля требует изменений в двух местах.

**Fix complexity:** Medium (единая функция с параметром prefix).

---

### [P3] pickPlatNew и pickPlatEdit — дублирующая логика

**Файл:** `frontend/js/schedules.js:493-512` и `794-812`

Обе функции делают одно и то же: переключают выбранную платформу и показывают/скрывают поля link/address. Отличаются только DOM-контейнерами (`nw-*` vs `sl-*`).

**Fix complexity:** Low.

---

### [P3] bot/handlers/navigation.py: cb_my_bookings ожидает list, но API возвращает dict

**Файл:** `bot/handlers/navigation.py:56-58`

**Факт — из кода:**
```python
bookings = await api("get", f"/api/bookings?telegram_id={cb.from_user.id}")
if not bookings:
    await cb.message.edit_text("У тебя пока нет встреч.", reply_markup=kb_back_main())
```

API `/api/bookings` возвращает `{"bookings": [...], "total": N, ...}` — dict, а не list. `not bookings` всегда будет False (dict непуст). Код не падает, но логика "нет встреч" никогда не срабатывает корректно в боте. Аналогичная проблема в `cb_my_schedules`:
```python
schedules = await api("get", f"/api/schedules?telegram_id={cb.from_user.id}")
if not schedules:  # schedules — это dict {"schedules": [], "total": 0}
```

**Impact:** Пользователь с 0 встречами видит пустой список, а не сообщение "нет встреч".

**Fix complexity:** Low. Надо `bookings_list = (bookings or {}).get("bookings", [])`.

---

### [P3] Мёртвая переменная state._previewReturnScreen

**Файл:** `frontend/js/schedules.js:456-460`

```javascript
state._previewReturnScreen = 's-schedule-view';
```

Устанавливается, но нигде не используется (в `nav.js` не задействована для возврата).

---

### [P3] Несогласованное именование в CLAUDE.md: custom_link

`custom_link` упоминается в `ScheduleCreate`, есть в `init.sql`, есть в `014_custom_link.sql` — но в CLAUDE.md в разделе схемы БД поле не перечислено.

---

### [P3] admin_sessions не очищаются автоматически

**Файл:** `database/init.sql` — нет CRON/TTL для очистки старых сессий.

Старые записи `admin_sessions` (is_active=FALSE, expired) накапливаются. Нет periodic cleanup. При активном использовании за год — тысячи строк.

**Fix complexity:** Low. Добавить задачу `DELETE FROM admin_sessions WHERE expires_at < NOW() - INTERVAL '30 days'`.

---

## 5. Аудит зависимостей

### row_to_dict() и rows_to_list()

**Файл:** `backend/utils.py:17-25`

Самописные, однострочные обёртки над `dict(row)`. Не нужно заменять на внешние библиотеки — минимальная и правильная реализация.

### Rate limiter (auth.py)

Самописный in-memory rate limiter (`_login_attempts`). Альтернатива — `slowapi` (Redis-backed). При текущем масштабе самописный приемлем, но имеет проблему утечки памяти (нет TTL-cleanup для старых IP без попыток).

**Факт:** `_login_attempts` растёт вечно — каждый новый IP добавляется в dict, старые записи удаляются только при новом запросе с этого же IP (`[t for t in attempts if now - t < 300]`). IP без повторных запросов остаются навсегда.

### MemoryStorage FSM

Обсуждено в P1. Риск потери состояния при перезапуске. Redis Storage уже подготовлен в коде — нужно только задать REDIS_URL.

### Dynamic SQL builder (schedules.py, admin.py)

Обсуждён в P1. Приемлем при строгом контроле имён полей через Pydantic, но является антипаттерном.

### OSS-альтернативы

| Компонент | Текущее решение | Альтернатива | Стоит ли менять? |
|-----------|-----------------|--------------|------------------|
| HTTP клиент (бот) | aiohttp per-request session | aiohttp с singleton session | Да, minor |
| Rate limiting | self-made dict | slowapi | При масштабировании |
| Напоминания | polling loop | celery beat / APScheduler | При масштабировании |
| FSM storage | MemoryStorage | RedisStorage | Да, просто |

---

## 6. Аудит SQL

### Используются ли индексы?

| Запрос | Индексы | Оценка |
|--------|---------|--------|
| `WHERE u.telegram_id = $1` (users.py) | ✅ idx_users_telegram_id | OK |
| `WHERE s.user_id = $1` (schedules.py) | ✅ idx_schedules_user_id | OK |
| `WHERE b.schedule_id = $1` | ✅ idx_bookings_schedule_id | OK |
| `WHERE b.guest_telegram_id = $1` | ✅ idx_bookings_guest_telegram_id | OK |
| `WHERE b.status = 'confirmed'` (reminders) | ✅ idx_bookings_status | OK |
| `WHERE b.scheduled_time > NOW()` (reminders) | ✅ idx_bookings_scheduled_time | OK |

### Потенциально неэффективные запросы

**Запрос pending-reminders-v2 (bookings.py:245-283):**

```sql
WITH user_reminder_mins AS (
    SELECT u.telegram_id,
           jsonb_array_elements_text(
               COALESCE(u.reminder_settings->'reminders', '["1440","60"]'::jsonb)
           )::int AS reminder_min
    FROM users u
)
SELECT DISTINCT ... FROM bookings b
JOIN ... JOIN ...
JOIN user_reminder_mins rm ON rm.telegram_id = u.telegram_id
WHERE b.status IN ('confirmed', 'pending', 'no_answer')
  AND b.scheduled_time <= NOW() + (rm.reminder_min || ' minutes')::interval
  AND b.scheduled_time > NOW() + ((rm.reminder_min - 2) || ' minutes')::interval
  AND NOT EXISTS (SELECT 1 FROM sent_reminders ...)
```

[ВЫВОД] Этот запрос выполняет `jsonb_array_elements_text` на ВСЕ строки таблицы users, затем JOIN с bookings. При тысячах пользователей — дорогостоящий CTE. Отсутствует индекс на `reminder_settings` (JSONB). При текущих масштабах OK, при росте — нужен partial index.

**Запрос admin dashboard (admin.py:133-161):**

5 вложенных SELECT COUNT(*) с JOIN в одном запросе. Каждый из них полностью сканирует bookings + schedules + users. При миллионах событий — медленно. Сейчас приемлемо.

### VIEW bookings_detail

[ФАКТ] Определён в `init.sql` (строки 106-118). Однако в коде НИГДЕ не используется — все JOIN пишутся вручную в каждом роуте. VIEW является dead code в production.

**Fix complexity:** Low — либо использовать, либо удалить.

---

## 7. Аудит фронтенда

### HTTP-запросы при загрузке экранов

| Экран | Запросы | Параллельность |
|-------|---------|----------------|
| Home (loadHome) | 2 (bookings + ext-events) | ❌ Последовательно |
| Meetings (loadMeetings) | 2 (bookings + ext-events) | ❌ Последовательно |
| Schedules (loadSchedules) | 1 (schedules) | OK |
| Schedule view (openScheduleView) | 3 (data из state + 2×calendar) | ✅ calendar через Promise.all |
| Profile (loadProfile) | 1 (user) | OK |
| Calendar/booking (loadCalendar) | 1 (schedule) + N (slots per month) | Пошаговая загрузка |

### Дублирующий код

- `getFormScheduleData()` vs `collectScheduleForm()` — 95% идентичных строк (описано в P3)
- `pickPlatNew()` vs `pickPlatEdit()` — идентичная логика
- `updateSlider()` vs `updateSliderSmart()` — почти идентичны

### Event listeners без cleanup

`document.addEventListener('click', ...)` в `bookings.js:363-370` — глобальный listener добавляется при загрузке файла, не удаляется. Это нормально для SPA без полного перезапуска.

`window._homeRefreshTimer = setInterval(...)` в `bookings.js:59-61` — очищается через `clearInterval` при повторном вызове loadHome. Корректно.

### Оценка размера бандла

- Нет bundler/minifier: JS-файлы загружаются по отдельности (~10 файлов).
- Отсутствует gzip для JS (nginx имеет `gzip on`, но без `gzip_types text/javascript`)
- Нет cache-busting (версионирования файлов)
- Суммарный JS: ориентировочно ~8000 строк, ~250KB raw, ~80KB gzip

**Impact:** При первой загрузке ~250KB некэшированного JS. Для мобильного Telegram — приемлемо, но можно улучшить.

---

## 8. Quick Wins (можно сделать за 15–30 мин каждый)

1. **Исправить N+1 в боте** — `bot/handlers/bookings.py:19` — заменить fetch всех встреч на `GET /api/bookings/{booking_id}` — **Impact: -50x запросов к БД**

2. **Исправить парсинг ответа API в боте** — `bot/handlers/navigation.py:24,56` — `(bookings or {}).get("bookings", [])` — **Impact: корректное отображение "нет встреч"**

3. **Включить REDIS_URL** — добавить в `.env.example` и `.env.beta.example`, задать на сервере — **Impact: FSM не теряется при перезапусте**

4. **Сделать ANONYMIZE_SALT обязательным** — `backend/config.py:15` — убрать default "do-vstrechi-2026" — **Impact: реальная анонимизация**

5. **Параллельные fetch в loadHome** — `frontend/js/bookings.js:63-87` — `Promise.all([bookings, extEvents])` — **Impact: -200-500ms загрузка главной**

6. **Удалить console.log** — `frontend/js/bookings.js:764-768` — **Impact: security hygiene**

7. **Реализовать remind_30m/15m** — `bot/handlers/start.py:434` — вызвать `/api/users/notification-settings` — **Impact: устранить ложную обратную связь**

8. **Добавить TTL-cleanup для _login_attempts** — `backend/auth.py:26` — периодически чистить старые IP — **Impact: предотвратить утечку памяти**

9. **Убрать логирование view_dashboard в audit_log** — `backend/routers/admin.py:130` — логировать только изменяющие действия — **Impact: уменьшить рост таблицы**

10. **Добавить gzip_types для JS** в `nginx/nginx.conf` — `gzip_types text/javascript application/javascript` — **Impact: -70% трафик JS**

---

## 9. План оптимизации

### Фаза 1: Быстро + важно (1-2 дня)

| # | Задача | Файл | Effort | Impact |
|---|--------|------|--------|--------|
| 1 | Исправить N+1 в cb_booking_detail | bot/handlers/bookings.py:19 | 5 мин | Высокий |
| 2 | Исправить парсинг dict/list из API | bot/handlers/navigation.py:24,56 | 10 мин | Высокий |
| 3 | Задать REDIS_URL для FSM | bot/config.py + .env | 15 мин | Высокий |
| 4 | Сделать ANONYMIZE_SALT обязательным | backend/config.py:15 | 5 мин | Высокий |
| 5 | Удалить console.log | frontend/js/bookings.js:764 | 2 мин | Средний |
| 6 | Реализовать remind setup (TODO) | bot/handlers/start.py:434 | 30 мин | Высокий |
| 7 | Параллельные fetch в loadHome и loadMeetings | frontend/js/bookings.js | 20 мин | Средний |
| 8 | gzip_types для JS в nginx | nginx/nginx.conf | 5 мин | Средний |

### Фаза 2: Важно + средняя сложность (1-2 недели)

| # | Задача | Файл | Effort | Impact |
|---|--------|------|--------|--------|
| 1 | Добавить whitelist колонок в dynamic SQL | backend/routers/schedules.py:192 | 30 мин | Средний |
| 2 | Фильтрация в SQL (не в Python) для list_bookings | backend/routers/bookings.py:126 | 2ч | Высокий |
| 3 | Singleton aiohttp session в боте | bot/api.py | 1ч | Средний |
| 4 | TTL-cleanup для _login_attempts | backend/auth.py:26 | 30 мин | Средний |
| 5 | Вынести reminder-эндпоинты в отдельный роутер | backend/routers/bookings.py | 2ч | Низкий (порядок) |
| 6 | Объединить getFormScheduleData/collectScheduleForm | frontend/js/schedules.js | 1ч | Средний |
| 7 | Использовать или удалить VIEW bookings_detail | database/init.sql | 30 мин | Низкий |
| 8 | Обновить документацию в CLAUDE.md (REDIS_URL, 4 эндпоинта, миграции 013-014) | CLAUDE.md | 30 мин | Низкий |

### Фаза 3: Низкий приоритет (backlog)

| # | Задача | Effort | Impact |
|---|--------|--------|--------|
| 1 | Retry mechanism для bot notifications | High | Высокий при масштабе |
| 2 | Cleanup admin_audit_log (view_dashboard) | Low | Средний |
| 3 | Кэш results available-slots с external calendar | Medium | Средний |
| 4 | Bundelr/minifier для frontend JS | High | Низкий при текущем трафике |
| 5 | Periodic cleanup admin_sessions таблицы | Low | Низкий |
| 6 | Индекс на reminder_settings JSONB для v2 reminders | Low | Средний при масштабе |
| 7 | Декомпозиция bot/handlers/start.py (7 хендлеров → отдельные файлы) | Medium | Качество |
| 8 | Декомпозиция frontend/js/schedules.js (~997 строк) | High | Качество |

---

## Итоговая оценка

| Категория | Найдено | Критичность |
|-----------|---------|-------------|
| P0 (data loss) | 0 | — |
| P1 (bug/security) | 6 | Средняя (никаких активных эксплойтов, но есть риски) |
| P2 (performance) | 6 | Низкая при текущем масштабе |
| P3 (quality) | 6 | Накопительный техдолг |

**Общее впечатление:** Кодовая база хорошего качества для проекта этого масштаба. Архитектура правильная (разделение bot/backend/frontend, параметризованный SQL, Pydantic-валидация, async/await везде). Основные проблемы — технический долг от быстрого роста функциональности (FSM в памяти, in-memory rate limit, дублирование кода во фронтенде, TODO без реализации). Критических уязвимостей нет, но несколько P1-проблем требуют внимания в ближайший спринт.

---

## Замена зависимостей (Промт #7, 2026-04-16)

Оценка самописных решений на предмет замены проверенными OSS-библиотеками.
Критерии: меньше кода, выше надёжность/производительность, лицензия MIT/BSD/Apache-2.0,
без зарубежных managed-сервисов (152-ФЗ).

| # | Текущее | Файл | Строк | Замена (кандидат) | Плюсы | Минусы | Вердикт |
|---|---------|------|-------|-------------------|-------|--------|---------|
| A | `row_to_dict` / `rows_to_list` | `backend/utils.py` | ~15 | `dict(row)` встроенный | −1 хелпер | теряется None-guard, 66 call sites, в коде явный комментарий «Do NOT inline» | **НЕ МЕНЯТЬ** |
| B | FastAPI default `JSONResponse` (std `json`) | `backend/main.py` | 2 | `orjson` + `ORJSONResponse` | 3–10× быстрее, нативная сериализация UUID/datetime (asyncpg возвращает именно их), pre-built wheels под linux/amd64, Apache-2.0 | новая зависимость ~0.9 MB | **ЗАМЕНИТЬ** |
| C | In-memory rate limiter login | `backend/auth.py` | ~15 | `slowapi` / `limits` | стандарт, поддержка Redis | +зависимость ради 15 строк, только один endpoint | **НЕ МЕНЯТЬ** |
| D | `MemoryStorage` FSM | `bot/bot.py` | — | `RedisStorage` (aiogram) | persistent между рестартами | требует Redis | **УЖЕ СДЕЛАНО** (Track B, fallback на memory) |
| E | `structlog` с `StackInfoRenderer` | `backend/main.py` | 1 | убрать processor | минус процессор | renderer no-op без `stack_info=True`, дешёвый, полезен при отладке | **НЕ МЕНЯТЬ** |
| F | Динамический SQL в `/api/admin/logs` | `backend/routers/admin.py` | ~40 | `asyncpg` параметризация | — | уже параметризовано (`$1…$N`), имена колонок захардкожены, SQL-инъекция невозможна | **НЕ МЕНЯТЬ** |

### Реализованные замены

**B) orjson** — `backend/requirements.txt`: `orjson==3.10.12` (Apache-2.0). `backend/main.py`: `default_response_class=ORJSONResponse`, глобальный exception handler возвращает `ORJSONResponse`. Dockerfile не требует изменений — orjson имеет pre-built manylinux wheels для python 3.12.

### Отклонённые замены — обоснование

- **A, C, E, F** — выигрыш минимальный, риск регрессии выше пользы. Текущий код ≤ 40 строк на каждый случай, покрыт комментариями и безопасен.
- **D** — уже выполнено в Track B (Redis FSM с graceful fallback на MemoryStorage).
