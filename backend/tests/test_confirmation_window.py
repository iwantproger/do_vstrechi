"""Тесты для адаптивного окна утреннего подтверждения (FINDING-009).

Проверяет SQL-логику: send_at = max(07:00 в TZ получателя, scheduled - 2ч),
не отправляем если target > deadline (scheduled - 1ч).

Запуск: pytest backend/tests/test_confirmation_window.py -v
Требует: PostgreSQL с расширением uuid-ossp (или фиксированные UUID).
"""
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import asyncpg
import pytest
import pytest_asyncio

# SQL из get_confirmation_requests — извлечённый для тестирования
_CONFIRMATION_SQL = """
WITH send_times AS (
    SELECT
        b.id AS booking_id,
        COALESCE(b.guest_timezone, u.timezone, 'UTC') AS rtz,
        (DATE_TRUNC('day', b.scheduled_time AT TIME ZONE COALESCE(b.guest_timezone, u.timezone, 'UTC'))
            + INTERVAL '7 hours')
          AT TIME ZONE COALESCE(b.guest_timezone, u.timezone, 'UTC') AS floor_utc,
        b.scheduled_time - INTERVAL '2 hours' AS target_2h,
        b.scheduled_time - INTERVAL '1 hour'  AS deadline
    FROM bookings b
    JOIN schedules s ON s.id = b.schedule_id
    JOIN users u ON u.id = s.user_id
    WHERE b.status = 'confirmed'
      AND b.confirmation_asked = FALSE
      AND b.guest_telegram_id IS NOT NULL
      AND b.scheduled_time > $1
      AND DATE(b.created_at AT TIME ZONE COALESCE(b.guest_timezone, u.timezone, 'UTC'))
          < DATE(b.scheduled_time AT TIME ZONE COALESCE(b.guest_timezone, u.timezone, 'UTC'))
)
SELECT b.id
FROM send_times st
JOIN bookings b ON b.id = st.booking_id
JOIN schedules s ON s.id = b.schedule_id
JOIN users u ON u.id = s.user_id
WHERE GREATEST(st.floor_utc, st.target_2h) <= st.deadline
  AND $1 >= GREATEST(st.floor_utc, st.target_2h)
  AND $1 <= st.deadline + INTERVAL '6 minutes'
"""


@pytest.fixture(scope="module")
def db_url():
    """URL тестовой БД. Переопределить через env DATABASE_TEST_URL."""
    import os
    return os.environ.get("DATABASE_TEST_URL", "postgresql://dovstrechi:dovstrechi@localhost:5432/dovstrechi_test")


@pytest_asyncio.fixture
async def conn(db_url):
    """Подключение + setup/teardown тестовых данных."""
    c = await asyncpg.connect(db_url)
    try:
        await c.execute("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\"")
        yield c
    finally:
        # Очистка тестовых данных
        await c.execute("DELETE FROM bookings WHERE guest_name LIKE 'test_confirm_%'")
        await c.execute("DELETE FROM schedules WHERE title = 'test_confirm_schedule'")
        await c.execute("DELETE FROM users WHERE username = 'test_confirm_user'")
        await c.close()


async def _setup_booking(conn, scheduled_time_utc: datetime, guest_tz: str = None, org_tz: str = "Europe/Moscow"):
    """Создать пользователя + расписание + бронирование для тестов."""
    user_id = uuid.uuid4()
    schedule_id = uuid.uuid4()
    booking_id = uuid.uuid4()
    tid = 999000000 + int(datetime.now().timestamp() * 1000) % 1000000

    await conn.execute(
        "INSERT INTO users (id, telegram_id, username, first_name, timezone) VALUES ($1, $2, $3, $4, $5)",
        user_id, tid, "test_confirm_user", "Test", org_tz,
    )
    await conn.execute(
        "INSERT INTO schedules (id, user_id, title, duration) VALUES ($1, $2, $3, $4)",
        schedule_id, user_id, "test_confirm_schedule", 60,
    )
    # created_at = вчера (чтобы same-day skip не сработал)
    yesterday = scheduled_time_utc - timedelta(days=1)
    await conn.execute(
        """INSERT INTO bookings (id, schedule_id, guest_name, guest_contact, guest_telegram_id,
                                 scheduled_time, status, guest_timezone, created_at, confirmation_asked)
           VALUES ($1, $2, $3, $4, $5, $6, 'confirmed', $7, $8, FALSE)""",
        booking_id, schedule_id,
        f"test_confirm_{booking_id.hex[:8]}", "test@test.com", tid + 1,
        scheduled_time_utc, guest_tz, yesterday,
    )
    return booking_id


def _msk(hour, minute=0):
    """Timestamp в MSK → UTC."""
    return datetime(2026, 6, 15, hour, minute, tzinfo=ZoneInfo("Europe/Moscow")).astimezone(timezone.utc)


def _vlat(hour, minute=0):
    """Timestamp в Владивостоке → UTC."""
    return datetime(2026, 6, 15, hour, minute, tzinfo=ZoneInfo("Asia/Vladivostok")).astimezone(timezone.utc)


async def _query(conn, now_utc: datetime) -> list:
    """Выполнить SQL с подстановкой $1 = now_utc."""
    rows = await conn.fetch(_CONFIRMATION_SQL, now_utc)
    return [r["id"] for r in rows]


@pytest.mark.asyncio
async def test_meeting_10_00_msk_now_08_00(conn):
    """Встреча 10:00 MSK, NOW=08:00 MSK → target=08:00 (2ч), floor=07:00 → send_at=08:00. В выборке."""
    bid = await _setup_booking(conn, _msk(10, 0), org_tz="Europe/Moscow")
    result = await _query(conn, _msk(8, 0))
    assert bid in result


@pytest.mark.asyncio
async def test_meeting_10_00_msk_now_07_30(conn):
    """Встреча 10:00 MSK, NOW=07:30 MSK → send_at=08:00, ещё не пора. Не в выборке."""
    bid = await _setup_booking(conn, _msk(10, 0), org_tz="Europe/Moscow")
    result = await _query(conn, _msk(7, 30))
    assert bid not in result


@pytest.mark.asyncio
async def test_meeting_10_00_msk_now_09_30(conn):
    """Встреча 10:00 MSK, NOW=09:30 MSK → deadline=09:00+6min=09:06. Просрочили. Не в выборке."""
    bid = await _setup_booking(conn, _msk(10, 0), org_tz="Europe/Moscow")
    result = await _query(conn, _msk(9, 30))
    assert bid not in result


@pytest.mark.asyncio
async def test_meeting_08_00_msk_now_07_00(conn):
    """Встреча 08:00 MSK → target=06:00 (2ч), floor=07:00 → send_at=07:00. deadline=07:00. 07:00<=07:00 ✓."""
    bid = await _setup_booking(conn, _msk(8, 0), org_tz="Europe/Moscow")
    result = await _query(conn, _msk(7, 0))
    assert bid in result


@pytest.mark.asyncio
async def test_meeting_04_00_msk_never(conn):
    """Встреча 04:00 MSK → floor=07:00, deadline=03:00. 07:00 > 03:00 → не отправляем никогда."""
    bid = await _setup_booking(conn, _msk(4, 0), org_tz="Europe/Moscow")
    # Проверяем в разное время — никогда не попадает
    for h in [3, 4, 5, 6, 7, 8]:
        result = await _query(conn, _msk(h, 0))
        assert bid not in result, f"Should not appear at {h}:00 MSK"


@pytest.mark.asyncio
async def test_guest_timezone_vlat(conn):
    """Гость в VLAT (UTC+10), встреча 15:00 VLAT. Floor = 07:00 VLAT, target = 13:00 VLAT."""
    scheduled = _vlat(15, 0)
    bid = await _setup_booking(conn, scheduled, guest_tz="Asia/Vladivostok", org_tz="Europe/Moscow")
    # 13:00 VLAT = 03:00 UTC → в выборке
    now_13_vlat = _vlat(13, 0)
    result = await _query(conn, now_13_vlat)
    assert bid in result


@pytest.mark.asyncio
async def test_meeting_15_00_msk_now_13_00(conn):
    """Встреча 15:00 MSK, NOW=13:00 MSK → target=13:00 (2ч). В выборке."""
    bid = await _setup_booking(conn, _msk(15, 0), org_tz="Europe/Moscow")
    result = await _query(conn, _msk(13, 0))
    assert bid in result


@pytest.mark.asyncio
async def test_meeting_15_00_msk_now_12_59(conn):
    """Встреча 15:00 MSK, NOW=12:59 MSK → target=13:00, ещё не пора."""
    bid = await _setup_booking(conn, _msk(15, 0), org_tz="Europe/Moscow")
    result = await _query(conn, _msk(12, 59))
    assert bid not in result
