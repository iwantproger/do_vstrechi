-- =============================================
-- 021: Infrastructure tracking tables
-- API latency, notification delivery, bot heartbeat, inline usage
-- + New columns: bookings.cancelled_by, users.referred_by
-- =============================================

-- 1. Bookings: who cancelled + no-show tracking
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS cancelled_by TEXT;
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS is_no_show BOOLEAN NOT NULL DEFAULT FALSE;

-- 2. Users: referral tracking
ALTER TABLE users ADD COLUMN IF NOT EXISTS referred_by BIGINT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS referral_source TEXT;

-- 3. API latency log (auto-cleanup: keep 7 days)
CREATE TABLE IF NOT EXISTS api_latency_log (
    id          BIGSERIAL PRIMARY KEY,
    path        TEXT NOT NULL,
    method      TEXT NOT NULL,
    status_code INTEGER NOT NULL,
    duration_ms REAL NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_api_latency_created ON api_latency_log(created_at);
CREATE INDEX IF NOT EXISTS idx_api_latency_path ON api_latency_log(path, created_at);

-- 4. Notification delivery log
CREATE TABLE IF NOT EXISTS notification_log (
    id                BIGSERIAL PRIMARY KEY,
    notification_type TEXT NOT NULL,
    recipient_tid     BIGINT NOT NULL,
    success           BOOLEAN NOT NULL DEFAULT TRUE,
    error_message     TEXT,
    duration_ms       REAL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_notification_log_created ON notification_log(created_at);
CREATE INDEX IF NOT EXISTS idx_notification_log_type ON notification_log(notification_type, created_at);

-- 5. Bot heartbeat (1 row per minute when alive)
CREATE TABLE IF NOT EXISTS bot_heartbeat (
    id          BIGSERIAL PRIMARY KEY,
    status      TEXT NOT NULL DEFAULT 'alive',
    uptime_sec  INTEGER NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_bot_heartbeat_created ON bot_heartbeat(created_at DESC);

-- 6. Inline query usage log
CREATE TABLE IF NOT EXISTS inline_usage_log (
    id               BIGSERIAL PRIMARY KEY,
    user_telegram_id BIGINT NOT NULL,
    query_text       TEXT,
    results_count    INTEGER NOT NULL DEFAULT 0,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_inline_usage_created ON inline_usage_log(created_at);
