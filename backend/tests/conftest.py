"""Shared fixtures для integration-тестов уведомлений.

Требует: TEST_DATABASE_URL, INTERNAL_API_KEY (env vars).
Запуск:  pytest backend/tests/ -v -m integration
"""
import os
import uuid
from datetime import datetime, timezone

import asyncpg
import pytest
import pytest_asyncio

# ── Маркеры ──
def pytest_configure(config):
    config.addinivalue_line("markers", "integration: требует реальной БД")
    config.addinivalue_line("markers", "slow: медленный тест (>2 сек)")


# ── Database ──

@pytest.fixture(scope="module")
def db_url():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set")
    return url


@pytest_asyncio.fixture
async def db_conn(db_url):
    conn = await asyncpg.connect(db_url)
    try:
        yield conn
    finally:
        # Cleanup тестовых данных по префиксу
        await conn.execute("DELETE FROM bookings WHERE guest_name LIKE 'TEST_VERIFY_%'")
        await conn.execute("DELETE FROM schedules WHERE title LIKE 'TEST_VERIFY_%'")
        await conn.execute("DELETE FROM users WHERE username LIKE 'test_verify_%'")
        await conn.close()


# ── Test users ──

def _uid():
    return int.from_bytes(uuid.uuid4().bytes[:6], "big") % 900_000_000 + 100_000_000


@pytest_asyncio.fixture
async def test_user_org(db_conn):
    """Тестовый организатор."""
    user_id = uuid.uuid4()
    tid = _uid()
    await db_conn.execute(
        """INSERT INTO users (id, telegram_id, username, first_name, timezone, reminder_settings)
           VALUES ($1, $2, $3, $4, $5, $6)""",
        user_id, tid, f"test_verify_org_{tid}", "TestOrg", "Europe/Moscow",
        '{"reminders":["1440","60","5"],"customReminders":[],"booking_notif":true,"reminder_notif":true}',
    )
    yield {"id": user_id, "telegram_id": tid}
    await db_conn.execute("DELETE FROM users WHERE id = $1", user_id)


@pytest_asyncio.fixture
async def test_user_guest(db_conn):
    """Тестовый гость (зарегистрированный)."""
    user_id = uuid.uuid4()
    tid = _uid()
    await db_conn.execute(
        """INSERT INTO users (id, telegram_id, username, first_name, timezone, reminder_settings)
           VALUES ($1, $2, $3, $4, $5, $6)""",
        user_id, tid, f"test_verify_guest_{tid}", "TestGuest", "Asia/Vladivostok",
        '{"reminders":["5"],"customReminders":[],"booking_notif":true,"reminder_notif":true}',
    )
    yield {"id": user_id, "telegram_id": tid}
    await db_conn.execute("DELETE FROM users WHERE id = $1", user_id)


@pytest_asyncio.fixture
async def test_schedule(db_conn, test_user_org):
    """Тестовое расписание."""
    sid = uuid.uuid4()
    await db_conn.execute(
        """INSERT INTO schedules (id, user_id, title, duration, platform)
           VALUES ($1, $2, $3, $4, $5)""",
        sid, test_user_org["id"], "TEST_VERIFY_schedule", 60, "jitsi",
    )
    yield {"id": sid, "user_id": test_user_org["id"]}
    await db_conn.execute("DELETE FROM schedules WHERE id = $1", sid)


# ── HTTP ──

@pytest.fixture
def internal_headers():
    key = os.environ.get("INTERNAL_API_KEY")
    if not key:
        pytest.skip("INTERNAL_API_KEY not set")
    return {"X-Internal-Key": key}


@pytest.fixture
def beta_url():
    return os.environ.get("BETA_BASE_URL", "https://beta.dovstrechiapp.ru")
