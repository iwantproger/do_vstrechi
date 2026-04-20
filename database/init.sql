-- =============================================
-- До встречи — инициализация базы данных
-- PostgreSQL 16
-- =============================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ─────────────────────────────────────────────
-- Пользователи (организаторы)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id                        UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    telegram_id               BIGINT UNIQUE NOT NULL,
    username                  TEXT,
    first_name                TEXT,
    last_name                 TEXT,
    timezone                  TEXT NOT NULL DEFAULT 'UTC',
    morning_summary_sent_date DATE,
    reminder_settings         JSONB NOT NULL DEFAULT '{"reminders":["1440","60","5"],"customReminders":[],"booking_notif":true,"reminder_notif":true}',
    created_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at                TIMESTAMPTZ NOT NULL DEFAULT NOW()
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
    location_mode          TEXT NOT NULL DEFAULT 'fixed',
    platform               TEXT NOT NULL DEFAULT 'jitsi',
    location_address       TEXT,
    min_booking_advance    INTEGER NOT NULL DEFAULT 0,
    requires_confirmation  BOOLEAN NOT NULL DEFAULT TRUE,
    custom_link            TEXT,
    is_active              BOOLEAN NOT NULL DEFAULT TRUE,
    is_default      BOOLEAN NOT NULL DEFAULT FALSE,
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
                        CHECK (status IN ('pending', 'confirmed', 'cancelled', 'completed', 'no_answer', 'expired')),
    meeting_link        TEXT,
    notes               TEXT,
    title               TEXT,
    end_time            TIMESTAMPTZ,
    is_manual           BOOLEAN NOT NULL DEFAULT FALSE,
    created_by          BIGINT,
    platform            TEXT,
    location_address    TEXT,
    confirmation_asked    BOOLEAN NOT NULL DEFAULT FALSE,
    confirmation_asked_at TIMESTAMPTZ,
    blocks_slots        BOOLEAN NOT NULL DEFAULT TRUE,
    guest_timezone      TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_bookings_schedule_id ON bookings(schedule_id);
CREATE INDEX IF NOT EXISTS idx_bookings_guest_telegram_id ON bookings(guest_telegram_id);
CREATE INDEX IF NOT EXISTS idx_bookings_scheduled_time ON bookings(scheduled_time);
CREATE INDEX IF NOT EXISTS idx_bookings_status ON bookings(status);
-- Composite / partial indexes for hot query paths (migration 015)
CREATE INDEX IF NOT EXISTS idx_bookings_schedule_time_active
    ON bookings (schedule_id, scheduled_time)
    WHERE status <> 'cancelled';
CREATE INDEX IF NOT EXISTS idx_bookings_scheduled_time_desc
    ON bookings (scheduled_time DESC);

-- ─────────────────────────────────────────────
-- Row Level Security — bookings (pilot)
-- ─────────────────────────────────────────────
CREATE OR REPLACE FUNCTION current_telegram_id() RETURNS BIGINT AS $$
BEGIN
  RETURN NULLIF(current_setting('app.telegram_id', true), '')::BIGINT;
EXCEPTION WHEN OTHERS THEN
  RETURN NULL;
END;
$$ LANGUAGE plpgsql STABLE;

ALTER TABLE bookings ENABLE ROW LEVEL SECURITY;
ALTER TABLE bookings FORCE ROW LEVEL SECURITY;

CREATE POLICY bookings_internal ON bookings
  FOR ALL USING (current_setting('app.is_internal', true) = 'true');

CREATE POLICY bookings_organizer ON bookings
  FOR ALL USING (
    schedule_id IN (
      SELECT s.id FROM schedules s
      JOIN users u ON s.user_id = u.id
      WHERE u.telegram_id = current_telegram_id()
    )
  );

CREATE POLICY bookings_guest ON bookings
  FOR ALL USING (
    guest_telegram_id IS NOT NULL
    AND guest_telegram_id = current_telegram_id()
  );

CREATE POLICY bookings_insert ON bookings
  FOR INSERT WITH CHECK (
    current_telegram_id() IS NOT NULL
    OR current_setting('app.is_internal', true) = 'true'
  );

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

-- ─────────────────────────────────────────────
-- Лог отправленных напоминаний (v2, idempotent)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sent_reminders (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    booking_id    UUID NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,
    reminder_type TEXT NOT NULL,
    sent_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(booking_id, reminder_type)
);
CREATE INDEX IF NOT EXISTS idx_sent_reminders_booking ON sent_reminders(booking_id);

-- ─────────────────────────────────────────────
-- Подключённые аккаунты внешних календарей
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS calendar_accounts (
    id                        UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id                   UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider                  TEXT NOT NULL CHECK (provider IN ('google', 'yandex', 'apple', 'outlook')),
    provider_email            TEXT,
    access_token_encrypted    TEXT,
    refresh_token_encrypted   TEXT,
    token_expires_at          TIMESTAMPTZ,
    caldav_url                TEXT,
    caldav_username           TEXT,
    caldav_password_encrypted TEXT,
    status                    TEXT NOT NULL DEFAULT 'active'
                              CHECK (status IN ('active', 'expired', 'revoked', 'error')),
    last_error                TEXT,
    last_sync_at              TIMESTAMPTZ,
    created_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at                TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_calendar_accounts_user_id ON calendar_accounts(user_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_calendar_accounts_uniq ON calendar_accounts(user_id, provider, provider_email);

CREATE TRIGGER set_calendar_accounts_updated_at
    BEFORE UPDATE ON calendar_accounts FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

COMMENT ON TABLE calendar_accounts IS 'Подключённые аккаунты внешних календарей (Google, Yandex, Apple, Outlook)';

-- ─────────────────────────────────────────────
-- Календари в подключённом аккаунте
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS calendar_connections (
    id                    UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    account_id            UUID NOT NULL REFERENCES calendar_accounts(id) ON DELETE CASCADE,
    external_calendar_id  TEXT NOT NULL,
    calendar_name         TEXT NOT NULL,
    calendar_color        TEXT,
    is_visible            BOOLEAN NOT NULL DEFAULT TRUE,
    is_read_enabled       BOOLEAN NOT NULL DEFAULT TRUE,
    is_write_target       BOOLEAN NOT NULL DEFAULT FALSE,
    sync_token            TEXT,
    last_sync_at          TIMESTAMPTZ,
    webhook_channel_id    TEXT,
    webhook_resource_id   TEXT,
    webhook_expires_at    TIMESTAMPTZ,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_calendar_connections_account_id ON calendar_connections(account_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_calendar_connections_uniq ON calendar_connections(account_id, external_calendar_id);

CREATE TRIGGER set_calendar_connections_updated_at
    BEFORE UPDATE ON calendar_connections FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

COMMENT ON TABLE calendar_connections IS 'Календари внутри подключённого аккаунта (выбранные пользователем для чтения/записи)';

-- ─────────────────────────────────────────────
-- Привязка календарей к расписаниям
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS schedule_calendar_rules (
    id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    schedule_id      UUID NOT NULL REFERENCES schedules(id) ON DELETE CASCADE,
    connection_id    UUID NOT NULL REFERENCES calendar_connections(id) ON DELETE CASCADE,
    use_for_blocking BOOLEAN NOT NULL DEFAULT TRUE,
    use_for_writing  BOOLEAN NOT NULL DEFAULT FALSE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_schedule_calendar_rules_uniq ON schedule_calendar_rules(schedule_id, connection_id);

COMMENT ON TABLE schedule_calendar_rules IS 'Привязка внешних календарей к расписаниям (блокировка слотов / запись бронирований)';

-- ─────────────────────────────────────────────
-- Кэш busy-слотов из внешних календарей
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS external_busy_slots (
    id                 UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    connection_id      UUID NOT NULL REFERENCES calendar_connections(id) ON DELETE CASCADE,
    external_event_id  TEXT NOT NULL,
    summary            TEXT,
    start_time         TIMESTAMPTZ NOT NULL,
    end_time           TIMESTAMPTZ NOT NULL,
    is_all_day         BOOLEAN NOT NULL DEFAULT FALSE,
    etag               TEXT,
    raw_data           JSONB,
    fetched_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_external_busy_slots_connection_id ON external_busy_slots(connection_id);
CREATE INDEX IF NOT EXISTS idx_external_busy_slots_time ON external_busy_slots(start_time, end_time);
CREATE UNIQUE INDEX IF NOT EXISTS idx_external_busy_slots_uniq ON external_busy_slots(connection_id, external_event_id);

CREATE TRIGGER set_external_busy_slots_updated_at
    BEFORE UPDATE ON external_busy_slots FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

COMMENT ON TABLE external_busy_slots IS 'Кэш занятых слотов из внешних календарей (обновляется при синхронизации)';

-- ─────────────────────────────────────────────
-- Маппинг бронирований → внешние события
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS event_mapping (
    id                 UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    booking_id         UUID NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,
    connection_id      UUID NOT NULL REFERENCES calendar_connections(id) ON DELETE CASCADE,
    external_event_id  TEXT NOT NULL,
    external_event_url TEXT,
    sync_status        TEXT NOT NULL DEFAULT 'synced'
                       CHECK (sync_status IN ('synced', 'pending', 'error', 'deleted')),
    sync_direction     TEXT NOT NULL DEFAULT 'outbound'
                       CHECK (sync_direction IN ('outbound', 'inbound')),
    last_synced_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_error         TEXT,
    etag               TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_event_mapping_uniq ON event_mapping(booking_id, connection_id);
CREATE INDEX IF NOT EXISTS idx_event_mapping_ext ON event_mapping(connection_id, external_event_id);
CREATE INDEX IF NOT EXISTS idx_event_mapping_sync_status ON event_mapping(sync_status);

CREATE TRIGGER set_event_mapping_updated_at
    BEFORE UPDATE ON event_mapping FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

COMMENT ON TABLE event_mapping IS 'Маппинг бронирований на события во внешних календарях (двусторонняя синхронизация)';

-- ─────────────────────────────────────────────
-- Логи синхронизации
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sync_log (
    id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    account_id     UUID REFERENCES calendar_accounts(id) ON DELETE SET NULL,
    connection_id  UUID REFERENCES calendar_connections(id) ON DELETE SET NULL,
    action         TEXT NOT NULL,
    status         TEXT NOT NULL,
    details        JSONB,
    error_message  TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_sync_log_account_id ON sync_log(account_id);
CREATE INDEX IF NOT EXISTS idx_sync_log_created_at ON sync_log(created_at);

COMMENT ON TABLE sync_log IS 'Лог операций синхронизации с внешними календарями';

-- ─────────────────────────────────────────────
-- app_events composite index + cleanup (migration 015)
-- app_events table itself is created in migration 004_admin_tables.sql
-- ─────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_app_events_severity_created
    ON app_events (severity, created_at DESC);

CREATE OR REPLACE FUNCTION cleanup_old_events(days_to_keep INT DEFAULT 90)
RETURNS INT AS $$
DECLARE
    deleted_count INT;
BEGIN
    DELETE FROM app_events
    WHERE severity IN ('info', 'warn')
      AND created_at < NOW() - (days_to_keep || ' days')::interval;
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION cleanup_old_events(INT) IS
    'Удаляет info/warn записи app_events старше N дней (default 90). '
    'Severity error/critical сохраняется бессрочно.';
