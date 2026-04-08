"""Database connection pool и dependency."""
import asyncpg
import structlog

from config import DATABASE_URL

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
    _pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
    log.info("PostgreSQL pool ready")


async def close_pool():
    global _pool
    if _pool:
        await _pool.close()
        log.info("PostgreSQL pool closed")


async def run_migrations():
    """Idempotent migrations — safe to run on every startup."""
    async with _pool.acquire() as conn:
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
    log.info("Migrations applied")


async def db() -> asyncpg.Connection:
    pool = await get_pool()
    async with pool.acquire() as conn:
        yield conn
