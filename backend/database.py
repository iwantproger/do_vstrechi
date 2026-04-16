"""Database connection pool и dependency."""
import asyncpg
import structlog
from fastapi import Request

from config import DATABASE_URL, DATABASE_ADMIN_URL

log = structlog.get_logger()

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        raise RuntimeError("DB pool not initialized")
    return _pool


async def init_pool():
    global _pool
    log.info("Connecting to PostgreSQL…")
    _pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=5,
        max_size=20,
        command_timeout=30,
        # Disable idle-connection auto-close (default 300s). Low-traffic beta
        # was shrinking the pool to 1 and then noisily "reopening" on next request,
        # which triggered spurious db_pool_exhausted warnings.
        max_inactive_connection_lifetime=0,
    )
    log.info("PostgreSQL pool ready", min_size=5, max_size=20, command_timeout=30)


async def close_pool():
    global _pool
    if _pool:
        await _pool.close()
        log.info("PostgreSQL pool closed")


async def run_migrations():
    """Idempotent migrations — safe to run on every startup.

    Uses DATABASE_ADMIN_URL (superuser) for DDL, separate from the
    app-role pool which is subject to RLS.
    """
    import asyncpg as _apg
    conn = await _apg.connect(DATABASE_ADMIN_URL)
    try:
        await conn.execute("""
            ALTER TABLE users
                ADD COLUMN IF NOT EXISTS timezone TEXT NOT NULL DEFAULT 'UTC';
        """)
        await conn.execute("""
            ALTER TABLE bookings
                ADD COLUMN IF NOT EXISTS reminder_24h_sent BOOLEAN NOT NULL DEFAULT FALSE;
        """)
        await conn.execute("""
            ALTER TABLE bookings
                ADD COLUMN IF NOT EXISTS reminder_1h_sent BOOLEAN NOT NULL DEFAULT FALSE;
        """)
        await conn.execute("""
            ALTER TABLE schedules
                ADD COLUMN IF NOT EXISTS is_default BOOLEAN NOT NULL DEFAULT FALSE;
        """)
        await conn.execute("""
            ALTER TABLE bookings ADD COLUMN IF NOT EXISTS title TEXT;
        """)
        await conn.execute("""
            ALTER TABLE bookings ADD COLUMN IF NOT EXISTS end_time TIMESTAMPTZ;
        """)
        await conn.execute("""
            ALTER TABLE bookings
                ADD COLUMN IF NOT EXISTS is_manual BOOLEAN NOT NULL DEFAULT FALSE;
        """)
        await conn.execute("""
            ALTER TABLE bookings ADD COLUMN IF NOT EXISTS created_by BIGINT;
        """)
        await conn.execute("""
            ALTER TABLE schedules
                ADD COLUMN IF NOT EXISTS requires_confirmation BOOLEAN NOT NULL DEFAULT TRUE;
        """)
        await conn.execute("""
            ALTER TABLE bookings
                ADD COLUMN IF NOT EXISTS reminder_15m_sent BOOLEAN NOT NULL DEFAULT FALSE;
        """)
        await conn.execute("""
            ALTER TABLE bookings
                ADD COLUMN IF NOT EXISTS reminder_5m_sent BOOLEAN NOT NULL DEFAULT FALSE;
        """)
        await conn.execute("""
            ALTER TABLE bookings
                ADD COLUMN IF NOT EXISTS morning_reminder_sent BOOLEAN NOT NULL DEFAULT FALSE;
        """)
        # 008: no_answer status + confirmation tracking
        await conn.execute("""
            ALTER TABLE bookings
                ADD COLUMN IF NOT EXISTS confirmation_asked BOOLEAN NOT NULL DEFAULT FALSE;
        """)
        await conn.execute("""
            ALTER TABLE bookings
                ADD COLUMN IF NOT EXISTS confirmation_asked_at TIMESTAMPTZ;
        """)
        # Expand status CHECK (idempotent: drop old, add new)
        try:
            await conn.execute("ALTER TABLE bookings DROP CONSTRAINT IF EXISTS bookings_status_check")
            await conn.execute("""
                ALTER TABLE bookings ADD CONSTRAINT bookings_status_check
                CHECK (status IN ('pending', 'confirmed', 'cancelled', 'completed', 'no_answer'))
            """)
        except Exception:
            pass  # constraint may already be correct
        # 013: morning summary tracking per organizer
        await conn.execute("""
            ALTER TABLE users
                ADD COLUMN IF NOT EXISTS morning_summary_sent_date DATE;
        """)
        # 016: Row Level Security on bookings (idempotent)
        await conn.execute("""
            CREATE OR REPLACE FUNCTION current_telegram_id() RETURNS BIGINT AS $$
            BEGIN
              RETURN NULLIF(current_setting('app.telegram_id', true), '')::BIGINT;
            EXCEPTION WHEN OTHERS THEN
              RETURN NULL;
            END;
            $$ LANGUAGE plpgsql STABLE
        """)
        await conn.execute("ALTER TABLE bookings ENABLE ROW LEVEL SECURITY")
        await conn.execute("ALTER TABLE bookings FORCE ROW LEVEL SECURITY")
        for pol in ('bookings_internal', 'bookings_organizer', 'bookings_guest', 'bookings_insert'):
            await conn.execute(f"DROP POLICY IF EXISTS {pol} ON bookings")
        await conn.execute("""
            CREATE POLICY bookings_internal ON bookings FOR ALL
            USING (current_setting('app.is_internal', true) = 'true')
        """)
        await conn.execute("""
            CREATE POLICY bookings_organizer ON bookings FOR ALL
            USING (schedule_id IN (
                SELECT s.id FROM schedules s JOIN users u ON s.user_id = u.id
                WHERE u.telegram_id = current_telegram_id()
            ))
        """)
        await conn.execute("""
            CREATE POLICY bookings_guest ON bookings FOR ALL
            USING (guest_telegram_id IS NOT NULL AND guest_telegram_id = current_telegram_id())
        """)
        await conn.execute("""
            CREATE POLICY bookings_insert ON bookings FOR INSERT
            WITH CHECK (
                current_telegram_id() IS NOT NULL
                OR current_setting('app.is_internal', true) = 'true'
            )
        """)
        # Grant dovstrechi_app access (idempotent, needed after fresh DB init)
        try:
            await conn.execute("""
                DO $$ BEGIN
                    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dovstrechi_app') THEN
                        GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO dovstrechi_app;
                        GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO dovstrechi_app;
                        GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO dovstrechi_app;
                    END IF;
                END $$
            """)
        except Exception:
            pass
    finally:
        await conn.close()
    log.info("Migrations applied")


async def db(request: Request = None) -> asyncpg.Connection:
    """FastAPI dependency — connection with RLS context (transaction-scoped)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            telegram_id = None
            is_internal = False
            if request:
                telegram_id = getattr(request.state, "telegram_id", None)
                is_internal = getattr(request.state, "is_internal", False)

            await conn.execute(
                "SELECT set_config('app.telegram_id', $1, true)",
                str(telegram_id) if telegram_id else "",
            )
            await conn.execute(
                "SELECT set_config('app.is_internal', $1, true)",
                "true" if is_internal else "false",
            )

            yield conn
