-- =============================================
-- 008: Интеграция внешних календарей
-- Google, Yandex, Apple, Outlook
-- =============================================

BEGIN;

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

CREATE INDEX IF NOT EXISTS idx_calendar_accounts_user_id
    ON calendar_accounts(user_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_calendar_accounts_uniq
    ON calendar_accounts(user_id, provider, provider_email);

CREATE TRIGGER set_calendar_accounts_updated_at
    BEFORE UPDATE ON calendar_accounts
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

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

CREATE INDEX IF NOT EXISTS idx_calendar_connections_account_id
    ON calendar_connections(account_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_calendar_connections_uniq
    ON calendar_connections(account_id, external_calendar_id);

CREATE TRIGGER set_calendar_connections_updated_at
    BEFORE UPDATE ON calendar_connections
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

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

CREATE UNIQUE INDEX IF NOT EXISTS idx_schedule_calendar_rules_uniq
    ON schedule_calendar_rules(schedule_id, connection_id);

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

CREATE INDEX IF NOT EXISTS idx_external_busy_slots_connection_id
    ON external_busy_slots(connection_id);
CREATE INDEX IF NOT EXISTS idx_external_busy_slots_time
    ON external_busy_slots(start_time, end_time);
CREATE UNIQUE INDEX IF NOT EXISTS idx_external_busy_slots_uniq
    ON external_busy_slots(connection_id, external_event_id);

CREATE TRIGGER set_external_busy_slots_updated_at
    BEFORE UPDATE ON external_busy_slots
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

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

CREATE UNIQUE INDEX IF NOT EXISTS idx_event_mapping_uniq
    ON event_mapping(booking_id, connection_id);
CREATE INDEX IF NOT EXISTS idx_event_mapping_ext
    ON event_mapping(connection_id, external_event_id);
CREATE INDEX IF NOT EXISTS idx_event_mapping_sync_status
    ON event_mapping(sync_status);

CREATE TRIGGER set_event_mapping_updated_at
    BEFORE UPDATE ON event_mapping
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

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

CREATE INDEX IF NOT EXISTS idx_sync_log_account_id
    ON sync_log(account_id);
CREATE INDEX IF NOT EXISTS idx_sync_log_created_at
    ON sync_log(created_at);

COMMENT ON TABLE sync_log IS 'Лог операций синхронизации с внешними календарями';

COMMIT;
