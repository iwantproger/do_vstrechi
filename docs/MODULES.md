# Описание модулей

## Общая структура

Проект состоит из трёх сервисов, каждый представлен **одним файлом**:

| Сервис | Файл | Строк | Назначение |
|--------|------|-------|-----------|
| Backend | `backend/main.py` | ~714 | FastAPI app: auth, роуты, модели, БД-запросы, напоминания |
| Bot | `bot/bot.py` | ~879 | aiogram: handlers, FSM, клавиатуры, HTTP-сервер уведомлений, напоминания |
| Frontend | `frontend/index.html` | ~3100 | HTML + CSS + JS: SPA Mini App |

---

## Backend (`backend/main.py`)

### Инициализация и конфигурация (строки 1–145)

- **Logging:** `logging.basicConfig`, уровень INFO
- **Env:** `DATABASE_URL`, `BOT_TOKEN`, `INTERNAL_API_KEY`, `BOT_INTERNAL_URL`, `MINI_APP_URL`
- **Auth:** `validate_init_data()` (HMAC-SHA256), `get_current_user()`, `get_optional_user()` — строки 37–96
- **Connection pool:** `asyncpg.create_pool(min_size=2, max_size=10)` в `lifespan()`
- **CORS:** whitelist `dovstrechiapp.ru`, methods GET/POST/PATCH/DELETE, headers Content-Type + X-Init-Data
- **App:** `FastAPI(title="До встречи API", version="2.0.0")`

### Pydantic-модели (строки 150–177)

| Модель | Назначение |
|--------|-----------|
| `UserAuth` | Запрос: POST `/api/users/auth` |
| `ScheduleCreate` | Запрос: POST `/api/schedules` |
| `BookingCreate` | Запрос: POST `/api/bookings` |

### Утилиты (строки 175–213)

| Функция | Описание |
|---------|----------|
| `row_to_dict(row)` | asyncpg Record → Python dict |
| `rows_to_list(rows)` | Список Records → список dict |
| `generate_meeting_link(platform)` | Генерация Jitsi URL: `https://meet.jit.si/dovstrechi-{uuid[:12]}` |
| `_notify_bot_new_booking(**kwargs)` | Fire-and-forget POST в бот (httpx) — уведомление о новом бронировании |

### Роуты: Health (строки 216–231)

| Функция | Роут | Описание |
|---------|------|----------|
| `root()` | GET `/` | Возвращает JSON с названием, версией, статусом |
| `health()` | GET `/health` | `SELECT 1` для проверки подключения к БД |

### Роуты: Users (строки 233–265)

| Функция | Роут | Auth | SQL | Описание |
|---------|------|------|-----|----------|
| `auth_user()` | POST `/api/users/auth` | `get_current_user` | INSERT ON CONFLICT UPDATE (+ timezone) | Upsert пользователя |
| `get_user()` | GET `/api/users/{telegram_id}` | — | SELECT WHERE telegram_id | Получить пользователя |

### Роуты: Schedules (строки 268–349)

| Функция | Роут | Auth | SQL | Описание |
|---------|------|------|-----|----------|
| `create_schedule()` | POST `/api/schedules` | `get_current_user` | SELECT user → INSERT schedules | Создать расписание |
| `list_schedules()` | GET `/api/schedules` | `get_current_user` | SELECT JOIN users WHERE telegram_id, is_active | Список расписаний |
| `get_schedule()` | GET `/api/schedules/{id}` | — | SELECT WHERE id, is_active | Детали расписания |
| `delete_schedule()` | DELETE `/api/schedules/{id}` | `get_current_user` | UPDATE SET is_active=FALSE | Мягкое удаление |

### Роуты: Available slots (строки 354–433)

| Функция | Роут | Описание |
|---------|------|----------|
| `available_slots()` | GET `/api/available-slots/{id}` | Вычисляет свободные слоты на дату |

**Алгоритм расчёта слотов (с поддержкой таймзон):**
1. Загрузить расписание + таймзону организатора (`users.timezone`)
2. Проверить, что дата — рабочий день (`work_days`)
3. Сгенерировать слоты в зоне организатора (`org_tz`), перевести в UTC для сравнения
4. Загрузить бронирования в UTC-диапазоне рабочего дня (status != cancelled)
5. Отфильтровать: прошедшие и забронированные
6. Вернуть массив `{time, datetime, datetime_utc, datetime_local}` — `datetime_local` в `viewer_tz`

### Роуты: Bookings (строки 436–635)

| Функция | Роут | Auth | SQL | Описание |
|---------|------|------|-----|----------|
| `create_booking()` | POST `/api/bookings` | `get_optional_user` | CHECK conflict → INSERT | Создать бронирование + push уведомление |
| `list_bookings()` | GET `/api/bookings` | `get_current_user` | SELECT JOIN + CASE my_role | Список бронирований с фильтром role |
| `confirm_booking()` | PATCH `/api/bookings/{id}/confirm` | `get_current_user` | UPDATE status='confirmed' | Подтвердить (только организатор) |
| `cancel_booking()` | PATCH `/api/bookings/{id}/cancel` | `get_current_user` | UPDATE status='cancelled' | Отменить (организатор или гость) |

### Роуты: Reminders (строки 637–689)

| Функция | Роут | Описание |
|---------|------|----------|
| `get_pending_reminders()` | GET `/api/bookings/pending-reminders` | Confirmed бронирования в окне reminder_type (24h/1h) с `reminder_*_sent=FALSE` |
| `mark_reminder_sent()` | PATCH `/api/bookings/{id}/reminder-sent` | Пометить reminder как отправленный |

### Роуты: Stats (строки 693–714)

| Функция | Роут | Описание |
|---------|------|----------|
| `get_stats()` | GET `/api/stats` | Агрегация: active_schedules, total/pending/confirmed/upcoming bookings |

### Dependency Injection

- `db()` — async generator, выдаёт `asyncpg.Connection` из пула через `Depends(db)`
- `get_current_user(request)` — извлекает пользователя из `X-Init-Data` (HMAC) или `X-Internal-Key`
- `get_optional_user(request)` — то же, но возвращает None при отсутствии auth

---

## Bot (`bot/bot.py`)

### Конфигурация (строки 1–35)

- **BOT_TOKEN:** из `os.environ["BOT_TOKEN"]`
- **BACKEND_URL:** из `BACKEND_API_URL` (default: `http://backend:8000`)
- **MINI_APP_URL:** из env (default: `https://YOUR_DOMAIN.ru`)
- **INTERNAL_API_KEY:** из env — ключ для бот↔backend аутентификации
- **_bot:** глобальная ссылка на `Bot` инстанс (для отправки уведомлений из aiohttp handlers)

### FSM States (строки 42–52)

```
CreateSchedule (StatesGroup):
    title → duration → buffer_time → work_days → start_time → end_time → platform
```

### API-хелпер (строки 55–71)

| Функция | Описание |
|---------|----------|
| `api(method, path, **kwargs)` | Универсальный HTTP-клиент (aiohttp, timeout=15s). Автоматически добавляет `X-Internal-Key`. Возвращает JSON на 200/201, None на ошибке |

### Клавиатуры (строки 77–151)

| Функция | Описание |
|---------|----------|
| `get_main_keyboard()` | **ReplyKeyboard** — постоянная нижняя панель: 4 кнопки (Создать, Расписания, Встречи, Помощь) |
| `kb_main(mini_app_url)` | InlineKeyboard: главное меню 5 кнопок (WebApp + 4 callback) |
| `kb_back_main()` | Кнопка «Главное меню» |
| `kb_duration()` | 6 вариантов длительности (15/30/45/60/90/120 мин) |
| `kb_buffer()` | 4 варианта буфера (0/10/15/30 мин) |
| `kb_platform()` | 3 платформы (Jitsi/Zoom/Офлайн) |
| `kb_schedule_actions(schedule_id, url)` | Действия с расписанием (открыть/поделиться/удалить) |
| `kb_booking_actions(booking_id, status)` | Действия с бронированием (подтвердить/отменить, зависят от status) |

### Хелперы форматирования (строки 153–185)

| Функция / Константа | Описание |
|---------------------|----------|
| `STATUS_EMOJI` | dict: pending→⏳, confirmed→✅, cancelled→❌, completed→✓ |
| `STATUS_TEXT` | dict: pending→Ожидает, confirmed→Подтверждена и т.д. |
| `DAYS_RU` | ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"] |
| `format_dt(dt_str, tz="UTC")` | ISO datetime → "DD.MM.YYYY HH:MM" в указанной таймзоне (ZoneInfo) |
| `format_booking(b, show_role)` | Форматирование карточки бронирования (HTML), использует organizer_timezone |

### Handlers (строки 189–672)

#### Команды

| Handler | Фильтр | API-вызовы | Описание |
|---------|--------|-----------|----------|
| `cmd_start()` | `CommandStart()` | POST `/api/users/auth` | Очистка FSM, установка MenuButton per-user, ReplyKeyboard + InlineKeyboard |
| `cmd_help()` | `Command("help")` | — | Справка |

#### Callbacks: навигация

| Handler | Фильтр | API-вызовы | Описание |
|---------|--------|-----------|----------|
| `cb_main_menu()` | `F.data == "main_menu"` | — | Возврат в главное меню |
| `cb_my_schedules()` | `F.data == "my_schedules"` | GET `/api/schedules` | Список расписаний |
| `cb_my_bookings()` | `F.data == "my_bookings"` | GET `/api/bookings` | Список встреч (лимит 10) |
| `cb_stats()` | `F.data == "stats"` | GET `/api/stats` | Статистика |

#### Callbacks: расписания

| Handler | Фильтр | API-вызовы | Описание |
|---------|--------|-----------|----------|
| `cb_schedule_detail()` | `F.data.startswith("schedule_")` | GET `/api/schedules/{id}` | Детали расписания |
| `cb_share_schedule()` | `F.data.startswith("share_")` | — | Отправка ссылки для бронирования |
| `cb_delete_schedule()` | `F.data.startswith("del_")` | DELETE `/api/schedules/{id}` | Удаление расписания |

#### Callbacks: бронирования

| Handler | Фильтр | API-вызовы | Описание |
|---------|--------|-----------|----------|
| `cb_booking_detail()` | `F.data.startswith("booking_")` | GET `/api/bookings` | Детали бронирования |
| `cb_confirm_booking()` | `F.data.startswith("confirm_")` | PATCH `.../confirm` | Подтвердить встречу |
| `cb_cancel_booking()` | `F.data.startswith("cancel_")` | PATCH `.../cancel` | Отменить встречу |

#### FSM: создание расписания

| Handler | Состояние | Ввод | API-вызовы |
|---------|----------|------|-----------|
| `cb_create_schedule()` | → title | callback | — |
| `fsm_title()` | title → duration | текст | — |
| `fsm_duration()` | duration → buffer_time | `dur_*` callback | — |
| `fsm_buffer()` | buffer_time → work_days | `buf_*` callback | — |
| `fsm_work_days()` | work_days → start_time | текст (числа) | — |
| `fsm_start_time()` | start_time → end_time | текст (HH:MM) | — |
| `fsm_end_time()` | end_time → platform | текст (HH:MM) | — |
| `fsm_platform()` | platform → done | `plat_*` callback | POST `/api/schedules` |

#### Reply-кнопки (строки 601–672)

| Handler | Фильтр | API-вызовы | Описание |
|---------|--------|-----------|----------|
| `reply_create_schedule()` | `F.text == "📅 Создать расписание"` | — | Запуск FSM |
| `reply_my_schedules()` | `F.text == "📋 Мои расписания"` | GET `/api/schedules` | Список расписаний |
| `reply_my_bookings()` | `F.text == "👥 Мои встречи"` | GET `/api/bookings` | Список встреч |
| `reply_help()` | `F.text == "❓ Помощь"` | — | Вызов cmd_help |

### Notification server + Reminders (строки 679–849)

| Функция | Описание |
|---------|----------|
| `setup_bot_commands(bot)` | Регистрация /start, /help + глобальный MenuButtonWebApp (try/except) |
| `handle_new_booking(request)` | aiohttp handler для POST `/internal/notify` — проверка X-Internal-Key, отправка сообщений организатору (с кнопками ✅/❌) и гостю |
| `send_reminder(booking, type)` | Отправка напоминания (24h/1h) организатору и гостю + mark as sent через API |
| `reminder_loop()` | Фоновый цикл (каждые 5 мин) — опрашивает pending-reminders и вызывает send_reminder |

### Main (строки 852–879)

| Функция | Описание |
|---------|----------|
| `main()` | Создание Bot (глобальный `_bot`) + Dispatcher(MemoryStorage) + setup_bot_commands + `asyncio.create_task(reminder_loop)` + aiohttp web server :8080 + start_polling(skip_updates=True) |

---

## Frontend (`frontend/index.html`)

### Структура файла

Фронтенд был существенно переработан (v3). Примерные диапазоны строк:

| Секция | Строки (прибл.) | Описание |
|--------|-----------------|----------|
| CSS | 1–1300 | Стили: CSS variables, компоненты, анимации, адаптив |
| HTML | 1300–1700 | 8 экранов, модалки, bottom nav, toast |
| JS: константы | 1700–1800 | BACKEND URL, PLATFORMS, месяцы, дни, state |
| JS: init | 1800–1900 | Инициализация: Telegram SDK, auth, роутинг |
| JS: навигация | 1900–2050 | showScreen, goBack, switchNav, navigateRoot |
| JS: API | 2050–2080 | apiFetch(method, path, body) с X-Init-Data |
| JS: календарь | 2080–2400 | loadSchedule, renderCalendar, slots loading |
| JS: форма | 2400–2600 | setupForm, валидация, submitBooking |
| JS: успех | 2600–2700 | renderSuccess, копирование ссылки |
| JS: встречи | 2700–2900 | loadMeetings, renderMeetingsList, табы |
| JS: детали | 2900–2970 | renderDetail |
| JS: расписания | 2970–3040 | loadSchedules, удаление |
| JS: настройки | 3040–3100 | toggleSetting, localStorage |

### Ключевые функции

#### Навигация

| Функция | Описание |
|---------|----------|
| `showScreen(screenId, push)` | Переход на экран с анимацией, управление BackButton |
| `goBack()` | Возврат по стеку `screenStack` |
| `switchNav(tab)` | Переключение tab в bottom nav (home/meetings/schedules/settings) |
| `navigateRoot()` | Сброс на home, очистка стека |

#### API

| Функция | Описание |
|---------|----------|
| `apiFetch(method, path, body)` | fetch() обёртка: JSON body, parse response, throw on error |
| `authUser()` | POST `/api/users/auth` с данными из Telegram SDK |

#### Календарь и слоты

| Функция | Вызывает API | Описание |
|---------|-------------|----------|
| `loadSchedule(id)` | GET `/api/schedules/{id}` | Загрузка расписания, переход на экран calendar |
| `loadMonthSlots()` | GET `/api/available-slots/{id}` | Загрузка слотов на все рабочие дни месяца (батчами по 8) |
| `renderCalendar()` | — | Рендер месячной сетки с цветовой разметкой дней |
| `selectDay(dateStr)` | GET `/api/available-slots/{id}` | Загрузка слотов на выбранный день |
| `selectTime(time)` | — | Выбор конкретного времени |
| `changeMonth(dir)` | — | Переключение месяца ±1 |
| `calcTotalSlots(schedule)` | — | Расчёт теоретического кол-ва слотов за день |

#### Форма бронирования

| Функция | Вызывает API | Описание |
|---------|-------------|----------|
| `setupForm()` | — | Настройка формы: валидация, платформы |
| `submitBooking()` | POST `/api/bookings` | Отправка бронирования |
| `renderSuccess(booking)` | — | Экран подтверждения с meeting_link |

#### Встречи и расписания

| Функция | Вызывает API | Описание |
|---------|-------------|----------|
| `loadMeetings()` | GET `/api/bookings` | Загрузка встреч пользователя |
| `renderMeetingsList()` | — | Рендер списка с табами (upcoming/history/all) |
| `renderDetail(meetingId)` | — | Детали встречи |
| `loadSchedules()` | GET `/api/schedules` | Загрузка расписаний организатора |
| `confirmCancel(id)` | PATCH `.../cancel` | Отмена встречи |
| `confirmDeleteSchedule(id)` | DELETE `/api/schedules/{id}` | Удаление расписания |

#### Утилиты

| Функция | Описание |
|---------|----------|
| `formatDate(date)` | Date → "YYYY-MM-DD" |
| `formatDateTime(date)` | Date → "D MONTH, HH:MM" |
| `getPlatformName(id)` | ID платформы → человекочитаемое имя |
| `escHtml(str)` | Экранирование HTML-спецсимволов |
| `copyText(text)` | Копирование в буфер обмена |
| `showToast(msg, type)` | Уведомление (3 сек, auto-hide) |

### Глобальное состояние (`state`)

| Поле | Тип | Описание |
|------|-----|---------|
| currentScreen | string | Текущий экран |
| screenStack | string[] | История навигации |
| schedule | object | Загруженное расписание |
| selectedDate | string | Выбранная дата (YYYY-MM-DD) |
| selectedTime | string | Выбранное время (HH:MM) |
| selectedPlatform | string | Выбранная платформа |
| currentMonth | Date | Текущий месяц в календаре |
| monthSlots | object | Кеш слотов: dateStr → {free, total} |
| allMeetings | array | Загруженные встречи |
| allSchedules | array | Загруженные расписания |
| currentTab | string | Текущий таб встреч (upcoming/history/all) |
| pendingCancelId | string | ID для модалки отмены |
| pendingDeleteId | string | ID для модалки удаления |
| meetingLink | string | Ссылка на встречу для копирования |
| settings | object | Настройки уведомлений |

### LocalStorage

| Ключ | Описание |
|------|----------|
| `sb_settings` | JSON: `{notif: bool, '24h': bool, '1h': bool}` — настройки уведомлений |

---

## Граф зависимостей

```mermaid
graph TD
    USER[Telegram User]

    USER -->|polling| BOT["bot/bot.py<br/>(aiogram 3.6)"]
    USER -->|WebApp| FE["frontend/index.html<br/>(Vanilla JS)"]

    BOT -->|aiohttp + X-Internal-Key| API["backend/main.py<br/>(FastAPI 0.111)"]
    API -->|POST /internal/notify| BOT
    FE -->|fetch via nginx + X-Init-Data| API

    API -->|asyncpg| DB["PostgreSQL 16<br/>database/init.sql"]
    API -->|uuid| JITSI["Jitsi Meet<br/>(ссылка)"]

    subgraph Docker Compose
        BOT
        API
        FE
        DB
        NGX["nginx 1.25<br/>nginx/nginx.conf"]
    end

    NGX -->|/api/| API
    NGX -->|static| FE
```
