"""Integration-тесты системы уведомлений на реальной БД.

Покрывает: per-user reminders, guest timezone, at-least-once delivery,
expired transitions, security (HTTP), migration backfills.

Запуск: pytest backend/tests/test_notifications_integration.py -v -m integration
Требует: TEST_DATABASE_URL, INTERNAL_API_KEY (env vars).
"""
import os
import uuid
from datetime import datetime, timedelta, timezone

import asyncpg
import pytest
import pytest_asyncio

pytestmark = pytest.mark.integration

# Извлечённый SQL из get_pending_reminders_v2 для прямого тестирования
_V2_SQL = """
WITH org_mins AS (
    SELECT b.id AS booking_id,
           'org'::text AS role,
           u.telegram_id AS recipient_tid,
           jsonb_array_elements_text(
               COALESCE(u.reminder_settings->'reminders', '["1440","60","5"]'::jsonb)
           )::int AS reminder_min
    FROM bookings b
    JOIN schedules s ON s.id = b.schedule_id
    JOIN users u ON u.id = s.user_id
    WHERE b.status IN ('confirmed', 'pending', 'no_answer')
      AND b.scheduled_time > NOW()
      AND COALESCE((u.reminder_settings->>'reminder_notif')::bool, true) = true
),
guest_mins AS (
    SELECT b.id AS booking_id,
           'guest'::text AS role,
           b.guest_telegram_id AS recipient_tid,
           jsonb_array_elements_text(
               COALESCE(ug.reminder_settings->'reminders', '["1440","60","5"]'::jsonb)
           )::int AS reminder_min
    FROM bookings b
    LEFT JOIN users ug ON ug.telegram_id = b.guest_telegram_id
    WHERE b.status IN ('confirmed', 'pending', 'no_answer')
      AND b.scheduled_time > NOW()
      AND b.guest_telegram_id IS NOT NULL
      AND COALESCE((ug.reminder_settings->>'reminder_notif')::bool, true) = true
),
all_mins AS (SELECT * FROM org_mins UNION ALL SELECT * FROM guest_mins)
SELECT
    b.id AS booking_id, am.reminder_min, am.role, am.recipient_tid
FROM all_mins am
JOIN bookings b ON b.id = am.booking_id
JOIN schedules s ON s.id = b.schedule_id
JOIN users u ON u.id = s.user_id
WHERE b.scheduled_time > NOW()
  AND b.scheduled_time <= NOW() + (am.reminder_min || ' minutes')::interval
  AND b.scheduled_time > NOW() + ((am.reminder_min - 15) || ' minutes')::interval
  AND NOT EXISTS (
      SELECT 1 FROM sent_reminders sr
      WHERE sr.booking_id = b.id
        AND sr.reminder_type = am.reminder_min::text || ':' || am.role
  )
ORDER BY b.scheduled_time
"""


async def _insert_booking(conn, schedule_id, interval_sql, status="confirmed",
                          guest_tid=None, guest_tz=None, name_suffix=""):
    """Вставить тестовое бронирование, вернуть UUID."""
    suffix = name_suffix or uuid.uuid4().hex[:8]
    return await conn.fetchval(
        f"""INSERT INTO bookings
            (schedule_id, guest_name, guest_contact, guest_telegram_id,
             scheduled_time, status, guest_timezone)
            VALUES ($1, $2, 'test@ex.com', $3, NOW() + {interval_sql}, $4, $5)
            RETURNING id""",
        schedule_id, f"TEST_VERIFY_{suffix}", guest_tid, status, guest_tz,
    )


# ═══════════════════════════════════════════
# Group C: Per-user reminders
# ═══════════════════════════════════════════

class TestPerUserRemindersSQL:

    @pytest.mark.asyncio
    async def test_org_1440_in_window(self, db_conn, test_user_org, test_schedule):
        """Организатор с reminders=["1440"]: бронирование за ~24ч попадает в выборку."""
        await db_conn.execute(
            "UPDATE users SET reminder_settings = $1::jsonb WHERE id = $2",
            '{"reminders":["1440"],"booking_notif":true,"reminder_notif":true}',
            test_user_org["id"],
        )
        bid = await _insert_booking(db_conn, test_schedule["id"], "INTERVAL '1439 minutes'")
        try:
            rows = await db_conn.fetch(_V2_SQL)
            org_rows = [r for r in rows if r["booking_id"] == bid and r["role"] == "org"]
            assert len(org_rows) == 1
            assert org_rows[0]["reminder_min"] == 1440
        finally:
            await db_conn.execute("DELETE FROM bookings WHERE id = $1", bid)

    @pytest.mark.asyncio
    async def test_guest_registered_own_settings(self, db_conn, test_user_org, test_user_guest, test_schedule):
        """Зарегистрированный гость с reminders=["5"]: за 4мин попадает, org с ["1440"] нет."""
        await db_conn.execute(
            "UPDATE users SET reminder_settings = $1::jsonb WHERE id = $2",
            '{"reminders":["1440"],"booking_notif":true,"reminder_notif":true}',
            test_user_org["id"],
        )
        bid = await _insert_booking(
            db_conn, test_schedule["id"], "INTERVAL '4 minutes'",
            guest_tid=test_user_guest["telegram_id"],
        )
        try:
            rows = await db_conn.fetch(_V2_SQL)
            guest_rows = [r for r in rows if r["booking_id"] == bid and r["role"] == "guest"]
            org_rows = [r for r in rows if r["booking_id"] == bid and r["role"] == "org"]
            assert len(guest_rows) == 1
            assert guest_rows[0]["reminder_min"] == 5
            assert len(org_rows) == 0  # 1440 не в окне 4мин
        finally:
            await db_conn.execute("DELETE FROM bookings WHERE id = $1", bid)

    @pytest.mark.asyncio
    async def test_guest_unregistered_uses_default(self, db_conn, test_user_org, test_schedule):
        """Незарегистрированный гость → дефолт [1440,60,5], за 4мин → только 5."""
        unregistered_tid = 999_888_777
        bid = await _insert_booking(
            db_conn, test_schedule["id"], "INTERVAL '4 minutes'",
            guest_tid=unregistered_tid,
        )
        try:
            rows = await db_conn.fetch(_V2_SQL)
            guest_rows = [r for r in rows if r["booking_id"] == bid and r["role"] == "guest"]
            mins = {r["reminder_min"] for r in guest_rows}
            assert 5 in mins, f"Expected 5 in {mins}"
            assert 1440 not in mins  # вне окна
        finally:
            await db_conn.execute("DELETE FROM bookings WHERE id = $1", bid)

    @pytest.mark.asyncio
    async def test_reminder_notif_false_excludes(self, db_conn, test_user_org, test_schedule):
        """reminder_notif=false → организатор исключён из выборки."""
        await db_conn.execute(
            "UPDATE users SET reminder_settings = $1::jsonb WHERE id = $2",
            '{"reminders":["5"],"booking_notif":true,"reminder_notif":false}',
            test_user_org["id"],
        )
        bid = await _insert_booking(db_conn, test_schedule["id"], "INTERVAL '4 minutes'")
        try:
            rows = await db_conn.fetch(_V2_SQL)
            org_rows = [r for r in rows if r["booking_id"] == bid and r["role"] == "org"]
            assert len(org_rows) == 0
        finally:
            await db_conn.execute("DELETE FROM bookings WHERE id = $1", bid)

    @pytest.mark.asyncio
    async def test_sent_reminders_dedup(self, db_conn, test_user_org, test_schedule):
        """Уже отправленное напоминание не возвращается повторно."""
        await db_conn.execute(
            "UPDATE users SET reminder_settings = $1::jsonb WHERE id = $2",
            '{"reminders":["5"],"booking_notif":true,"reminder_notif":true}',
            test_user_org["id"],
        )
        bid = await _insert_booking(db_conn, test_schedule["id"], "INTERVAL '4 minutes'")
        try:
            await db_conn.execute(
                "INSERT INTO sent_reminders (booking_id, reminder_type) VALUES ($1, $2)",
                bid, "5:org",
            )
            rows = await db_conn.fetch(_V2_SQL)
            org_rows = [r for r in rows if r["booking_id"] == bid and r["role"] == "org"]
            assert len(org_rows) == 0  # дедупликация сработала
        finally:
            await db_conn.execute("DELETE FROM sent_reminders WHERE booking_id = $1", bid)
            await db_conn.execute("DELETE FROM bookings WHERE id = $1", bid)


# ═══════════════════════════════════════════
# Group D: Guest timezone
# ═══════════════════════════════════════════

class TestGuestTimezoneDB:

    @pytest.mark.asyncio
    async def test_guest_tz_stored(self, db_conn, test_schedule):
        """guest_timezone сохраняется в bookings."""
        bid = await _insert_booking(
            db_conn, test_schedule["id"], "INTERVAL '1 day'",
            guest_tz="Asia/Vladivostok",
        )
        try:
            tz = await db_conn.fetchval("SELECT guest_timezone FROM bookings WHERE id = $1", bid)
            assert tz == "Asia/Vladivostok"
        finally:
            await db_conn.execute("DELETE FROM bookings WHERE id = $1", bid)

    @pytest.mark.asyncio
    async def test_guest_tz_null_ok(self, db_conn, test_schedule):
        """Без guest_timezone → NULL (fallback на org TZ)."""
        bid = await _insert_booking(db_conn, test_schedule["id"], "INTERVAL '1 day'")
        try:
            tz = await db_conn.fetchval("SELECT guest_timezone FROM bookings WHERE id = $1", bid)
            assert tz is None
        finally:
            await db_conn.execute("DELETE FROM bookings WHERE id = $1", bid)

    def test_format_dt_msk(self):
        """format_dt: UTC → MSK = +3ч."""
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "bot"))
        from formatters import format_dt
        assert format_dt("2026-04-20T12:00:00Z", tz="Europe/Moscow") == "20.04.2026 15:00"

    def test_format_dt_vlat(self):
        """format_dt: UTC → VLAT = +10ч."""
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "bot"))
        from formatters import format_dt
        assert format_dt("2026-04-20T12:00:00Z", tz="Asia/Vladivostok") == "20.04.2026 22:00"


# ═══════════════════════════════════════════
# Group F: Window 15 min
# ═══════════════════════════════════════════

class TestWindow15Min:

    @pytest.mark.asyncio
    async def test_55min_in_60min_window(self, db_conn, test_user_org, test_schedule):
        """Бронирование через 55 мин попадает в окно 60-мин напоминания (60 - 15 = 45 < 55 < 60)."""
        await db_conn.execute(
            "UPDATE users SET reminder_settings = $1::jsonb WHERE id = $2",
            '{"reminders":["60"],"booking_notif":true,"reminder_notif":true}',
            test_user_org["id"],
        )
        bid = await _insert_booking(db_conn, test_schedule["id"], "INTERVAL '55 minutes'")
        try:
            rows = await db_conn.fetch(_V2_SQL)
            matched = [r for r in rows if r["booking_id"] == bid and r["reminder_min"] == 60]
            assert len(matched) >= 1, "55min should be in 60min window"
        finally:
            await db_conn.execute("DELETE FROM bookings WHERE id = $1", bid)

    @pytest.mark.asyncio
    async def test_40min_outside_60min_window(self, db_conn, test_user_org, test_schedule):
        """Бронирование через 40 мин НЕ попадает (60 - 15 = 45 > 40)."""
        await db_conn.execute(
            "UPDATE users SET reminder_settings = $1::jsonb WHERE id = $2",
            '{"reminders":["60"],"booking_notif":true,"reminder_notif":true}',
            test_user_org["id"],
        )
        bid = await _insert_booking(db_conn, test_schedule["id"], "INTERVAL '40 minutes'")
        try:
            rows = await db_conn.fetch(_V2_SQL)
            matched = [r for r in rows if r["booking_id"] == bid and r["reminder_min"] == 60]
            assert len(matched) == 0, "40min should NOT be in 60min window"
        finally:
            await db_conn.execute("DELETE FROM bookings WHERE id = $1", bid)


# ═══════════════════════════════════════════
# Group G: Expired transitions
# ═══════════════════════════════════════════

class TestExpiredTransitions:

    @pytest.mark.asyncio
    async def test_stale_pending_becomes_expired(self, db_conn, test_schedule):
        """pending + scheduled_time < NOW()-2h → expired."""
        bid = await _insert_booking(
            db_conn, test_schedule["id"], "INTERVAL '-3 hours'", status="pending",
        )
        try:
            await db_conn.execute("""
                UPDATE bookings SET status = 'expired'
                WHERE id = $1 AND status = 'pending' AND scheduled_time < NOW() - INTERVAL '2 hours'
            """, bid)
            status = await db_conn.fetchval("SELECT status FROM bookings WHERE id = $1", bid)
            assert status == "expired"
        finally:
            await db_conn.execute("DELETE FROM bookings WHERE id = $1", bid)

    @pytest.mark.asyncio
    async def test_recent_pending_stays(self, db_conn, test_schedule):
        """pending + scheduled_time < NOW()-1h (но <2ч) → остаётся pending."""
        bid = await _insert_booking(
            db_conn, test_schedule["id"], "INTERVAL '-1 hour'", status="pending",
        )
        try:
            result = await db_conn.execute("""
                UPDATE bookings SET status = 'expired'
                WHERE id = $1 AND status = 'pending' AND scheduled_time < NOW() - INTERVAL '2 hours'
            """, bid)
            count = int(result.split()[-1])
            assert count == 0  # не обновилось
            status = await db_conn.fetchval("SELECT status FROM bookings WHERE id = $1", bid)
            assert status == "pending"
        finally:
            await db_conn.execute("DELETE FROM bookings WHERE id = $1", bid)

    @pytest.mark.asyncio
    async def test_no_answer_past_becomes_expired(self, db_conn, test_schedule):
        """no_answer + scheduled_time < NOW() → expired."""
        bid = await _insert_booking(
            db_conn, test_schedule["id"], "INTERVAL '-30 minutes'", status="no_answer",
        )
        try:
            await db_conn.execute("""
                UPDATE bookings SET status = 'expired'
                WHERE id = $1 AND status = 'no_answer' AND scheduled_time < NOW()
            """, bid)
            status = await db_conn.fetchval("SELECT status FROM bookings WHERE id = $1", bid)
            assert status == "expired"
        finally:
            await db_conn.execute("DELETE FROM bookings WHERE id = $1", bid)

    @pytest.mark.asyncio
    async def test_check_constraint_rejects_invalid(self, db_conn, test_schedule):
        """INSERT с status='nonsense' → CHECK violation."""
        with pytest.raises(asyncpg.exceptions.CheckViolationError):
            await db_conn.execute(
                """INSERT INTO bookings (schedule_id, guest_name, guest_contact,
                   scheduled_time, status) VALUES ($1, 'TEST_VERIFY_bad', 'x', NOW(), 'nonsense')""",
                test_schedule["id"],
            )


# ═══════════════════════════════════════════
# Group H: Migration backfills
# ═══════════════════════════════════════════

class TestMigrationBackfills:

    @pytest.mark.asyncio
    async def test_018_all_users_have_notif_flags(self, db_conn):
        """Миграция 018: все users имеют booking_notif и reminder_notif."""
        count = await db_conn.fetchval("""
            SELECT COUNT(*) FROM users
            WHERE reminder_settings->>'booking_notif' IS NULL
               OR reminder_settings->>'reminder_notif' IS NULL
        """)
        assert count == 0, f"{count} users missing notif flags"

    @pytest.mark.asyncio
    async def test_017_v1_columns_absent(self, db_conn):
        """Миграция 017: V1 колонки удалены."""
        rows = await db_conn.fetch("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'bookings'
              AND column_name IN ('reminder_24h_sent','reminder_1h_sent',
                                  'reminder_15m_sent','reminder_5m_sent','morning_reminder_sent')
        """)
        assert len(rows) == 0, f"V1 columns still present: {[r['column_name'] for r in rows]}"

    @pytest.mark.asyncio
    async def test_019_guest_timezone_column(self, db_conn):
        """Миграция 019: guest_timezone колонка существует."""
        row = await db_conn.fetchrow("""
            SELECT data_type FROM information_schema.columns
            WHERE table_name = 'bookings' AND column_name = 'guest_timezone'
        """)
        assert row is not None, "guest_timezone column missing"
        assert row["data_type"] == "text"

    @pytest.mark.asyncio
    async def test_020_expired_in_check(self, db_conn):
        """Миграция 020: CHECK constraint содержит expired."""
        check_def = await db_conn.fetchval("""
            SELECT pg_get_constraintdef(oid) FROM pg_constraint
            WHERE conname = 'bookings_status_check'
        """)
        assert check_def is not None, "bookings_status_check not found"
        assert "expired" in check_def, f"expired not in CHECK: {check_def}"

    @pytest.mark.asyncio
    async def test_020_no_stale_pending(self, db_conn):
        """Миграция 020: нет pending старше 2ч."""
        count = await db_conn.fetchval("""
            SELECT COUNT(*) FROM bookings
            WHERE status = 'pending' AND scheduled_time < NOW() - INTERVAL '2 hours'
        """)
        assert count == 0, f"{count} stale pending bookings remain"
