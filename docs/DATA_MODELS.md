# Модели данных

## ER-диаграмма

```mermaid
erDiagram
    users ||--o{ schedules : "создаёт"
    schedules ||--o{ bookings : "принимает"

    users {
        UUID id PK "uuid_generate_v4()"
        BIGINT telegram_id UK "NOT NULL"
        TEXT username "NULL"
        TEXT first_name "NULL"
        TEXT last_name "NULL"
        TIMESTAMPTZ created_at "DEFAULT NOW()"
        TIMESTAMPTZ updated_at "DEFAULT NOW()"
    }

    schedules {
        UUID id PK "uuid_generate_v4()"
        UUID user_id FK "NOT NULL, CASCADE"
        TEXT title "NOT NULL"
        TEXT description "NULL"
        INTEGER duration "DEFAULT 60 (минуты)"
        INTEGER buffer_time "DEFAULT 0 (минуты)"
        INTEGER_ARRAY work_days "DEFAULT {0,1,2,3,4}"
        TIME start_time "DEFAULT 09:00"
        TIME end_time "DEFAULT 18:00"
        TEXT location_mode "DEFAULT fixed"
        TEXT platform "DEFAULT jitsi"
        BOOLEAN is_active "DEFAULT TRUE"
        TIMESTAMPTZ created_at "DEFAULT NOW()"
        TIMESTAMPTZ updated_at "DEFAULT NOW()"
    }

    bookings {
        UUID id PK "uuid_generate_v4()"
        UUID schedule_id FK "NOT NULL, CASCADE"
        TEXT guest_name "NOT NULL"
        TEXT guest_contact "NOT NULL"
        BIGINT guest_telegram_id "NULL"
        TIMESTAMPTZ scheduled_time "NOT NULL"
        TEXT status "DEFAULT pending"
        TEXT meeting_link "NULL"
        TEXT notes "NULL"
        TIMESTAMPTZ created_at "DEFAULT NOW()"
        TIMESTAMPTZ updated_at "DEFAULT NOW()"
    }
```

## Таблицы базы данных

Определены в `database/init.sql`. Расширение: `uuid-ossp`.

### users

Пользователи-организаторы. Создаются при первом `/start` или открытии Mini App.

| Поле | Тип | Ограничение | Описание |
|------|-----|-------------|---------|
| id | UUID | PK, DEFAULT uuid_generate_v4() | Внутренний идентификатор |
| telegram_id | BIGINT | UNIQUE NOT NULL | Telegram user ID |
| username | TEXT | NULL | Username в Telegram (@handle) |
| first_name | TEXT | NULL | Имя из Telegram |
| last_name | TEXT | NULL | Фамилия из Telegram |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | Время регистрации |
| updated_at | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | Время последнего обновления |

**Индексы:** `idx_users_telegram_id` ON (telegram_id)

**Особенности:** при повторной авторизации (POST `/api/users/auth`) — UPSERT: обновляет username, first_name, last_name.

### schedules

Расписания для бронирования. Организатор может создать несколько расписаний.

| Поле | Тип | Ограничение | Описание |
|------|-----|-------------|---------|
| id | UUID | PK, DEFAULT uuid_generate_v4() | Идентификатор расписания |
| user_id | UUID | FK → users(id) ON DELETE CASCADE, NOT NULL | Владелец-организатор |
| title | TEXT | NOT NULL | Название расписания |
| description | TEXT | NULL | Описание |
| duration | INTEGER | NOT NULL, DEFAULT 60 | Длительность встречи (минуты) |
| buffer_time | INTEGER | NOT NULL, DEFAULT 0 | Перерыв между встречами (минуты) |
| work_days | INTEGER[] | NOT NULL, DEFAULT '{0,1,2,3,4}' | Рабочие дни (0=Пн, 6=Вс) |
| start_time | TIME | NOT NULL, DEFAULT '09:00' | Начало рабочего дня |
| end_time | TIME | NOT NULL, DEFAULT '18:00' | Конец рабочего дня |
| location_mode | TEXT | NOT NULL, DEFAULT 'fixed' | Режим выбора платформы (fixed / user_choice) |
| platform | TEXT | NOT NULL, DEFAULT 'jitsi' | Платформа по умолчанию |
| is_active | BOOLEAN | NOT NULL, DEFAULT TRUE | Активно ли расписание |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | Время создания |
| updated_at | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | Время обновления |

**Индексы:**
- `idx_schedules_user_id` ON (user_id)
- `idx_schedules_is_active` ON (is_active)

**Особенности:**
- Удаление мягкое: `is_active = FALSE`. Данные остаются в БД.
- `work_days` — массив целых чисел PostgreSQL: `{0,1,2,3,4}` = Пн-Пт.
- Допустимые значения `platform`: `jitsi`, `zoom`, `other`.
- `location_mode = 'user_choice'` позволяет гостю выбрать платформу при бронировании.

### bookings

Бронирования встреч. Создаются гостями через Mini App или напрямую через API.

| Поле | Тип | Ограничение | Описание |
|------|-----|-------------|---------|
| id | UUID | PK, DEFAULT uuid_generate_v4() | Идентификатор бронирования |
| schedule_id | UUID | FK → schedules(id) ON DELETE CASCADE, NOT NULL | К какому расписанию |
| guest_name | TEXT | NOT NULL | Имя гостя |
| guest_contact | TEXT | NOT NULL | Контакт (email или @username) |
| guest_telegram_id | BIGINT | NULL | Telegram ID гостя (если есть) |
| scheduled_time | TIMESTAMPTZ | NOT NULL | Дата и время встречи |
| status | TEXT | NOT NULL, DEFAULT 'pending' | Статус бронирования |
| meeting_link | TEXT | NULL | Ссылка на видеозвонок |
| notes | TEXT | NULL | Заметки от гостя |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | Время создания |
| updated_at | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | Время обновления |

**Индексы:**
- `idx_bookings_schedule_id` ON (schedule_id)
- `idx_bookings_guest_telegram_id` ON (guest_telegram_id)
- `idx_bookings_scheduled_time` ON (scheduled_time)
- `idx_bookings_status` ON (status)

## Жизненный цикл бронирования

```mermaid
stateDiagram-v2
    [*] --> pending: POST /api/bookings
    pending --> confirmed: PATCH .../confirm (организатор)
    pending --> cancelled: PATCH .../cancel (организатор или гость)
    confirmed --> cancelled: PATCH .../cancel (организатор или гость)

    note right of pending: Создано гостем,<br/>ожидает подтверждения
    note right of confirmed: Организатор подтвердил
    note right of cancelled: Отменено любой стороной
```

**Кто меняет статус:**

| Переход | Кто может | Эндпоинт |
|---------|----------|----------|
| pending → confirmed | Только организатор | PATCH `/api/bookings/{id}/confirm?telegram_id=` |
| pending → cancelled | Организатор или гость | PATCH `/api/bookings/{id}/cancel?telegram_id=` |
| confirmed → cancelled | Организатор или гость | PATCH `/api/bookings/{id}/cancel?telegram_id=` |

**Примечание:** статус `completed` используется во фронтенде для визуального отображения прошедших встреч, но не устанавливается в БД — нет автоматического перехода confirmed → completed.

## View: bookings_detail

Денормализованное представление для чтения бронирований с деталями расписания и организатора.

| Поле | Источник | Описание |
|------|---------|----------|
| * (все поля bookings) | bookings | Все данные бронирования |
| schedule_title | schedules.title | Название расписания |
| schedule_duration | schedules.duration | Длительность встречи |
| schedule_platform | schedules.platform | Платформа |
| organizer_user_id | schedules.user_id | UUID организатора |
| organizer_telegram_id | users.telegram_id | Telegram ID организатора |
| organizer_first_name | users.first_name | Имя организатора |
| organizer_username | users.username | Username организатора |

## Pydantic-схемы (Backend)

Определены в `backend/main.py`, строки 69–93.

### UserAuth (запрос: POST `/api/users/auth`)

| Поле | Тип | Обязательное | Описание |
|------|-----|-------------|---------|
| telegram_id | int | да | Telegram user ID |
| username | Optional[str] | нет | Username в Telegram |
| first_name | Optional[str] | нет | Имя |
| last_name | Optional[str] | нет | Фамилия |

### ScheduleCreate (запрос: POST `/api/schedules`)

| Поле | Тип | Обязательное | Default | Описание |
|------|-----|-------------|---------|---------|
| telegram_id | int | да | — | Telegram ID организатора |
| title | str | да | — | Название расписания |
| description | Optional[str] | нет | None | Описание |
| duration | int | нет | 60 | Длительность встречи (мин) |
| buffer_time | int | нет | 0 | Буфер между встречами (мин) |
| work_days | List[int] | нет | [0,1,2,3,4] | Рабочие дни (0=Пн, 6=Вс) |
| start_time | str | нет | "09:00" | Начало рабочего дня (HH:MM) |
| end_time | str | нет | "18:00" | Конец рабочего дня (HH:MM) |
| location_mode | str | нет | "fixed" | Режим выбора платформы |
| platform | str | нет | "jitsi" | Платформа |

### BookingCreate (запрос: POST `/api/bookings`)

| Поле | Тип | Обязательное | Описание |
|------|-----|-------------|---------|
| schedule_id | str | да | UUID расписания (строка) |
| guest_name | str | да | Имя гостя |
| guest_contact | str | да | Email или @username |
| guest_telegram_id | Optional[int] | нет | Telegram ID гостя |
| scheduled_time | str | да | ISO-формат даты/времени |
| notes | Optional[str] | нет | Заметки |

### Ответы API

Ответы не формализованы в Pydantic Response-моделях. Backend возвращает `dict` из asyncpg Record
через хелперы `row_to_dict()` / `rows_to_list()`. Структура ответа повторяет структуру таблицы.

Для GET `/api/bookings` ответ дополняется вычисляемым полем `my_role` ('organizer' | 'guest')
через SQL CASE.

## Telegram InitData

Данные из Telegram WebApp SDK, используемые системой:

| Поле | Сохраняется в | Описание |
|------|--------------|---------|
| user.id | users.telegram_id | Уникальный Telegram ID |
| user.username | users.username | @handle пользователя |
| user.first_name | users.first_name | Имя |
| user.last_name | users.last_name | Фамилия |

**Важно:** InitData не валидируется на backend (нет проверки подписи). Аутентификация построена
исключительно на доверии к `telegram_id`, передаваемому в query/body параметрах.
