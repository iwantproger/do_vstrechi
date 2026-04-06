# Security Audit Log

Журнал аудитов безопасности проекта **"До встречи"**.
Каждый аудит фиксирует найденные уязвимости, принятые меры и оставшиеся риски.
Файл обновляется после каждого аудита или значимого изменения, связанного с безопасностью.

---

## Текущий статус защиты

| Компонент | Уровень | Последний аудит |
|-----------|---------|-----------------|
| Аутентификация | Telegram initData HMAC-SHA256 | 2026-04-04 |
| Авторизация | Серверная (dependency `get_current_user`) | 2026-04-04 |
| CORS | Whitelist (`dovstrechiapp.ru`) | 2026-04-04 |
| XSS-защита | `escHtml()` + CSP header | 2026-04-04 |
| SQL Injection | Параметризованные запросы ($1, $2) | 2026-04-04 |
| Rate Limiting | nginx `limit_req_zone` | 2026-04-04 |
| Security Headers | HSTS, X-Content-Type-Options, CSP, Referrer-Policy | 2026-04-04 |
| Контейнеры | Non-root user (`appuser`) | 2026-04-04 |
| Секреты | `.env` only, не в коде | 2026-04-04 |

---

## Открытые риски

| # | Severity | Описание | Статус | Ответственный |
|---|----------|----------|--------|---------------|
| R1 | HIGH | Секреты в git history (commit 98a3d39 и ранее) — `POSTGRES_PASSWORD`, `BOT_TOKEN`, `SECRET_KEY` | Требуется ротация на VPS + `git filter-repo` | DevOps |
| R2 | MEDIUM | Нет RLS (Row Level Security) в PostgreSQL — защита только на уровне приложения | Принятый риск (single-app access) | Backend |
| R3 | LOW | Inline `<style>` требует `'unsafe-inline'` в CSP для style-src | Принятый риск (single-file архитектура) | Frontend |

---

## Аудит #1 — 2026-04-04 (полный)

**Аудитор:** Claude Code (Security Engineer mode)
**Scope:** Все файлы репозитория — backend, bot, frontend, nginx, docker-compose, database, CI/CD
**Методология:** Ручной анализ кода, трассировка потоков данных, проверка конфигурации

### Найдено уязвимостей

| Severity | Кол-во | Исправлено | Осталось |
|----------|--------|------------|----------|
| CRITICAL | 3 | 3 | 0 |
| HIGH | 3 | 2 | 1 (R1) |
| MEDIUM | 6 | 6 | 0 |
| LOW | 5 | 4 | 1 (R3) |

### Находки и исправления

#### CRITICAL

| # | Категория | Файл | Проблема | Исправление | Коммит |
|---|-----------|------|----------|-------------|--------|
| C1 | Auth | `backend/main.py` | Нет валидации Telegram initData — любой мог представиться любым пользователем | Реализована HMAC-SHA256 валидация `initData` через dependency `get_current_user()`, заголовок `X-Init-Data` | 2026-04-04 |
| C2 | IDOR | `backend/main.py` | `telegram_id` принимался из query params — клиент контролировал identity | Убран `telegram_id` из всех query/body params; извлекается из валидированного токена | 2026-04-04 |
| C3 | XSS | `frontend/index.html` | `escHtml()` не экранировала `'` — Stored XSS через title расписания в onclick | Добавлен `.replace(/'/g,'&#39;')` в `escHtml()` | 2026-04-04 |

#### HIGH

| # | Категория | Файл | Проблема | Исправление |
|---|-----------|------|----------|-------------|
| H1 | CORS | `backend/main.py` | `allow_origins=["*"]` + `allow_credentials=True` | Ограничен до `dovstrechiapp.ru`, `allow_credentials=False` |
| H2 | Headers | `nginx/nginx.conf` | Нет security headers | Добавлены HSTS, X-Content-Type-Options, CSP, Referrer-Policy, Permissions-Policy, `server_tokens off` |
| H3 | Secrets | `.env.example` git history | Реальные пароли были закоммичены | `.env.example` очищен (commit 98a3d39). **Ротация на сервере ещё не выполнена — см. R1** |

#### MEDIUM

| # | Категория | Файл | Проблема | Исправление |
|---|-----------|------|----------|-------------|
| M1 | Info Leak | `backend/main.py` | `detail=f"DB error: {e}"` утекали внутренние ошибки | Ошибки логируются серверно, клиенту — generic message |
| M2 | Rate Limit | `nginx/nginx.conf` | Нет rate limiting | `limit_req_zone` — 10r/s для API, 5r/m для bookings |
| M3 | Container | `Dockerfile` (backend, bot) | Контейнеры работали как root | Добавлен `appuser` (UID 1000), `USER appuser` |
| M4 | Validation | `backend/main.py` | Pydantic модели без ограничений длины | Добавлены `min_length`, `max_length`, `ge`, `le`, `pattern` |
| M5 | DB | `database/init.sql` | `status TEXT` без CHECK | Добавлен `CHECK (status IN ('pending','confirmed','cancelled','completed'))` |
| M6 | Deprecated | `backend/main.py` | `datetime.utcnow()` deprecated в Python 3.12+ | Заменён на `datetime.now(timezone.utc)` |

#### LOW

| # | Категория | Файл | Проблема | Исправление |
|---|-----------|------|----------|-------------|
| L1 | CSP | `nginx/nginx.conf` | Нет CSP | Добавлен через nginx `add_header Content-Security-Policy` |
| L2 | SRI | `frontend/index.html` | Google Fonts без crossorigin | Добавлен `crossorigin="anonymous"` |
| L3 | Info | `nginx/nginx.conf` | `server_tokens` не отключён | `server_tokens off;` |
| L4 | Proxy | `nginx/nginx.conf` | Нет X-Forwarded-For/Proto | Добавлены `proxy_set_header` директивы |
| L5 | Error | `bot/bot.py` | `api()` без timeout — мог зависнуть | `aiohttp.ClientTimeout(total=15)` |

### Архитектура безопасности после аудита

```
Telegram Client
    │
    ▼ initData (HMAC-signed by Telegram)
Frontend (index.html)
    │ X-Init-Data header
    ▼
Nginx (reverse proxy)
    │ rate limiting, security headers, HTTPS
    ▼
FastAPI Backend
    │ get_current_user() — validates HMAC-SHA256
    │ Pydantic — validates input
    ▼
PostgreSQL (asyncpg, parameterized $1/$2)
    │ CHECK constraints
    ▼
Data

Bot (aiogram) ──X-Internal-Key──► Backend (trusted internal network)
```

### Два канала аутентификации

| Канал | Механизм | Заголовок |
|-------|----------|-----------|
| Mini App → Backend | Telegram initData HMAC-SHA256 | `X-Init-Data` |
| Bot → Backend | Shared secret (internal Docker network) | `X-Internal-Key` |

---

## Аудит #2 — 2026-04-06 (точечный — админ-панель)

**Аудитор:** Claude Code (Security Engineer mode)
**Scope:** Все новые файлы и изменения Фаз 1–3 (admin panel): `backend/main.py` (новые функции/эндпоинты), `admin/index.html`, `nginx/nginx.conf`, `database/migrations/004_admin_tables.sql`
**Триггер:** Завершение разработки полной функциональности админ-панели

### Найдено

| # | Severity | Категория | Файл | Проблема | Исправление |
|---|----------|-----------|------|----------|-------------|
| A2-L1 | LOW | Memory leak | `backend/main.py` | `_session_checked: set[str]` растёт неограниченно — никогда не очищается за всё время жизни процесса | Принятый риск: один admin-пользователь, перезапуск Docker очищает память. Нет реального threat при текущей нагрузке |
| A2-L2 | LOW | Token в лог | `backend/main.py:1281` | `session_prefix=session_token[:8]` — первые 8 символов session token в structured log | Принятый риск: 8 из 86 URL-safe символов (~6 бит из ~516 бит). Оставшаяся энтропия достаточна. Логи хранятся только на сервере |

Новых уязвимостей категории CRITICAL, HIGH, MEDIUM не найдено.

### Проверено без замечаний

| Категория | Что проверялось | Результат |
|-----------|----------------|-----------|
| Auth: Login Widget | `verify_telegram_login()` — SHA256(BOT_TOKEN) → HMAC, сортировка ключей, auth_date < 300s | ✅ Корректно |
| Auth: cookie | HttpOnly=True, Secure=True, SameSite="strict", path="/api/admin" — cookie не утекает на основной сайт | ✅ |
| Auth: ADMIN_TELEGRAM_ID | Сравнение как int: `data.id != ADMIN_TELEGRAM_ID` | ✅ |
| Auth: session token | `secrets.token_urlsafe(64)` — 64 байта = ~516 бит энтропии | ✅ |
| Auth: инвалидация | При новом логине все старые сессии деактивируются (`is_active = FALSE WHERE telegram_id`) | ✅ |
| Auth: rate limit | nginx 3r/min + backend `_login_attempts` (3 попытки / 5 мин) — два слоя | ✅ |
| Auth: generic errors | Все отказы возвращают `"Authentication failed"` без причины | ✅ |
| SQL: admin/logs | Динамический WHERE через `$idx` placeholders, значения в params list | ✅ |
| SQL: PATCH tasks | SET clause из Pydantic `model_dump()` — column names не пользовательский ввод | ✅ |
| SQL: cleanup-events | `$1` (severity), `$2` (days) — параметризовано | ✅ |
| XSS: admin frontend | `renderLogTable`, `renderTaskCard`, `renderAuditMini` — все поля через `escHtml()` или `textContent` | ✅ |
| XSS: event delegation | Кнопки task cards используют `data-id`/`data-title` через HTML entities (FIX 4) | ✅ |
| Data leak: system/info | CORS origins, IP allowlist, rate limits — без BOT_TOKEN, INTERNAL_API_KEY, POSTGRES_PASSWORD | ✅ |
| Data leak: structlog | `session_prefix=token[:8]`, никаких полных секретов в логах | ✅ |
| Data leak: error handler | Non-HTTP exceptions → `"Internal server error"`, traceback не возвращается | ✅ |
| Data leak: analytics | `anonymize_id()` — SHA256(id:salt)[:12], необратимо | ✅ |
| nginx: /admin/ headers | X-Robots-Tag, HSTS, X-Content-Type-Options, CSP, Referrer-Policy, Permissions-Policy, frame-ancestors 'none' | ✅ |
| nginx: CSP cdnjs | `script-src` включает `https://cdnjs.cloudflare.com` для Chart.js и SortableJS | ✅ |
| nginx: Cache-Control | `/admin/` возвращает `no-cache, must-revalidate` | ✅ |
| Logic: cleanup | `severity` pattern `^(info\|warn)$` — Pydantic отклоняет `error`/`critical` с 422 | ✅ |
| Logic: invalidate | `session_token != $1` — текущая сессия защищена от инвалидации | ✅ |
| Logic: admin endpoints | Все 18 `/api/admin/*` эндпоинтов имеют `Depends(get_admin_user)` | ✅ |

### Обновление статуса защиты

| Компонент | Было (Аудит #1) | Стало (Аудит #2) |
|-----------|-----------------|------------------|
| Admin Auth | Нет | Telegram Login Widget + cookie sessions (HttpOnly, Secure, SameSite=Strict) |
| Admin API | Нет | 18 эндпоинтов, все за `Depends(get_admin_user)` |
| Logging | `logging.basicConfig` | structlog JSON + contextvars (request_id, path, method, duration_ms) |
| Event tracking | Нет | `app_events` с SHA256-анонимизацией telegram_id |
| Rate Limits | api: 10r/s, booking: 5r/m | + admin: 5r/s burst=10, admin_auth: 3r/m burst=2 |
| CSP | `telegram.org` | + `oauth.telegram.org`, `cdnjs.cloudflare.com` |
| Audit trail | Нет | `admin_audit_log` — все admin-действия (login, logout, view_*, task_*, cleanup) |
| Cache-Control | Нет на /admin/ | `no-cache, must-revalidate` |

### Обновление открытых рисков

| # | Изменение |
|---|-----------|
| R1 | Без изменений — ротация секретов на сервере не подтверждена |
| R2 | Без изменений — нет RLS, принятый риск |
| R3 | Без изменений — `unsafe-inline` для style-src, принятый риск |
| R4 (новый) | LOW — `_session_checked` не очищается. Принятый риск, нет практического impact |

---

## Чеклист для будущих аудитов

При каждом новом аудите проверять:

- [ ] `get_current_user()` используется на всех защищённых эндпоинтах
- [ ] Новые эндпоинты не принимают `telegram_id` из query/body
- [ ] SQL-запросы используют `$1, $2` (не f-строки)
- [ ] Пользовательский ввод проходит через `escHtml()` перед вставкой в DOM
- [ ] CORS origins актуальны (только свои домены)
- [ ] Nginx security headers на месте
- [ ] Rate limiting покрывает новые эндпоинты
- [ ] Зависимости обновлены, нет CVE
- [ ] `.env.example` содержит только плейсхолдеры
- [ ] Docker контейнеры работают не от root
- [ ] Секреты не логируются (grep `log.*token\|log.*password\|log.*key`)

---

## Шаблон записи нового аудита

```markdown
## Аудит #N — YYYY-MM-DD (тип: полный / точечный / зависимости)

**Аудитор:** ...
**Scope:** ...
**Триггер:** (новая фича / инцидент / плановый / обновление зависимостей)

### Найдено

| # | Severity | Категория | Файл | Проблема | Исправление |
|---|----------|-----------|------|----------|-------------|

### Обновление открытых рисков

| # | Изменение |
|---|-----------|

### Обновление статуса защиты

| Компонент | Было | Стало |
|-----------|------|-------|
```

---

*Последнее обновление: 2026-04-06*
