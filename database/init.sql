-- =============================================
-- До встречи — инициализация базы данных
-- PostgreSQL 16
-- =============================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ─────────────────────────────────────────────
-- Пользователи (организаторы)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    telegram_id   BIGINT UNIQUE NOT NULL,
    username      TEXT,
    first_name    TEXT,
    last_name     TEXT,
    timezone      TEXT NOT NULL DEFAULT 'UTC',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id);

-- ─────────────────────────────────────────────
-- Расписания
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS schedules (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title           TEXT NOT NULL,
    description     TEXT,
    duration        INTEGER NOT NULL DEFAULT 60,
    buffer_time     INTEGER NOT NULL DEFAULT 0,
    work_days       INTEGER[] NOT NULL DEFAULT '{0,1,2,3,4}',
    start_time      TIME NOT NULL DEFAULT '09:00',
    end_time        TIME NOT NULL DEFAULT '18:00',
    location_mode   TEXT NOT NULL DEFAULT 'fixed',
    platform        TEXT NOT NULL DEFAULT 'jitsi',
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_schedules_user_id ON schedules(user_id);
CREATE INDEX IF NOT EXISTS idx_schedules_is_active ON schedules(is_active);

-- ─────────────────────────────────────────────
-- Бронирования
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS bookings (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    schedule_id         UUID NOT NULL REFERENCES schedules(id) ON DELETE CASCADE,
    guest_name          TEXT NOT NULL,
    guest_contact       TEXT NOT NULL,
    guest_telegram_id   BIGINT,
    scheduled_time      TIMESTAMPTZ NOT NULL,
    status              TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'confirmed', 'cancelled', 'completed')),
    meeting_link        TEXT,
    notes               TEXT,
    reminder_24h_sent   BOOLEAN NOT NULL DEFAULT FALSE,
    reminder_1h_sent    BOOLEAN NOT NULL DEFAULT FALSE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_bookings_schedule_id ON bookings(schedule_id);
CREATE INDEX IF NOT EXISTS idx_bookings_guest_telegram_id ON bookings(guest_telegram_id);
CREATE INDEX IF NOT EXISTS idx_bookings_scheduled_time ON bookings(scheduled_time);
CREATE INDEX IF NOT EXISTS idx_bookings_status ON bookings(status);

-- ─────────────────────────────────────────────
-- Автообновление updated_at
-- ─────────────────────────────────────────────
CREATE OR REPLACE FUNCTION trigger_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER set_users_updated_at
    BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();
CREATE TRIGGER set_schedules_updated_at
    BEFORE UPDATE ON schedules FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();
CREATE TRIGGER set_bookings_updated_at
    BEFORE UPDATE ON bookings FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

-- ─────────────────────────────────────────────
-- VIEW: бронирования с деталями
-- ─────────────────────────────────────────────
CREATE OR REPLACE VIEW bookings_detail AS
SELECT
    b.*,
    s.title       AS schedule_title,
    s.duration    AS schedule_duration,
    s.platform    AS schedule_platform,
    s.user_id     AS organizer_user_id,
    u.telegram_id AS organizer_telegram_id,
    u.first_name  AS organizer_first_name,
    u.username    AS organizer_username
FROM bookings b
JOIN schedules s ON s.id = b.schedule_id
JOIN users u ON u.id = s.user_id;
