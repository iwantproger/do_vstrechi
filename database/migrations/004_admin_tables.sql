-- Migration 004: Admin panel tables
-- Date: 2026-04-05
-- Description: Tables for admin panel — sessions, audit log, event tracking, task management
-- Depends on: 003_add_reminder_flags.sql
-- Apply: docker-compose exec postgres psql -U dovstrechi -d dovstrechi -f /docker-entrypoint-initdb.d/migrations/004_admin_tables.sql

-- ─────────────────────────────────────────────
-- Сессии администратора
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS admin_sessions (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    telegram_id     BIGINT NOT NULL,
    session_token   TEXT UNIQUE NOT NULL,
    ip_address      INET NOT NULL,
    user_agent      TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ NOT NULL,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS idx_admin_sessions_token
    ON admin_sessions (session_token) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_admin_sessions_expires
    ON admin_sessions (expires_at);

-- ─────────────────────────────────────────────
-- Аудит-лог действий администратора
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS admin_audit_log (
    id              BIGSERIAL PRIMARY KEY,
    action          TEXT NOT NULL
                    CHECK (action IN (
                        'login', 'logout', 'session_check',
                        'view_dashboard', 'view_logs', 'view_analytics',
                        'task_create', 'task_update', 'task_delete',
                        'settings_change', 'invalidate_sessions', 'cleanup_events'
                    )),
    details         JSONB,
    ip_address      INET NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Idempotent constraint upgrade (if table already existed with old constraint)
DO $$
BEGIN
    -- Drop old constraint if it doesn't include the new values
    IF EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'admin_audit_log_action_check'
          AND conrelid = 'admin_audit_log'::regclass
          AND consrc NOT LIKE '%invalidate_sessions%'
    ) THEN
        ALTER TABLE admin_audit_log DROP CONSTRAINT admin_audit_log_action_check;
        ALTER TABLE admin_audit_log ADD CONSTRAINT admin_audit_log_action_check
            CHECK (action IN (
                'login', 'logout', 'session_check',
                'view_dashboard', 'view_logs', 'view_analytics',
                'task_create', 'task_update', 'task_delete',
                'settings_change', 'invalidate_sessions', 'cleanup_events'
            ));
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_audit_log_created
    ON admin_audit_log (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_log_action
    ON admin_audit_log (action);

-- ─────────────────────────────────────────────
-- Событийный трекинг (анонимизированный)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS app_events (
    id              BIGSERIAL PRIMARY KEY,
    event_type      TEXT NOT NULL
                    CHECK (event_type IN (
                        'page_view', 'booking_created', 'booking_confirmed',
                        'booking_cancelled', 'slot_selected',
                        'schedule_created', 'schedule_deleted',
                        'error', 'api_call'
                    )),
    anonymous_id    TEXT NOT NULL,
    session_id      TEXT,
    metadata        JSONB,
    severity        TEXT NOT NULL DEFAULT 'info'
                    CHECK (severity IN ('info', 'warn', 'error', 'critical')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_app_events_type
    ON app_events (event_type);
CREATE INDEX IF NOT EXISTS idx_app_events_severity
    ON app_events (severity);
CREATE INDEX IF NOT EXISTS idx_app_events_created
    ON app_events (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_app_events_anonymous_id
    ON app_events (anonymous_id);

-- ─────────────────────────────────────────────
-- Задачи (Kanban)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS admin_tasks (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title           TEXT NOT NULL,
    description     TEXT,
    description_plain TEXT,
    status          TEXT NOT NULL DEFAULT 'backlog'
                    CHECK (status IN ('backlog', 'in_progress', 'done')),
    priority        INTEGER NOT NULL DEFAULT 0,
    source          TEXT NOT NULL DEFAULT 'manual'
                    CHECK (source IN ('manual', 'git_commit', 'ai_generated', 'github_issue')),
    source_ref      TEXT,
    tags            TEXT[] DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_admin_tasks_status
    ON admin_tasks (status);
CREATE INDEX IF NOT EXISTS idx_admin_tasks_status_priority
    ON admin_tasks (status, priority);

-- Триггер updated_at (переиспользуем существующую функцию)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger WHERE tgname = 'set_admin_tasks_updated_at'
    ) THEN
        CREATE TRIGGER set_admin_tasks_updated_at
            BEFORE UPDATE ON admin_tasks
            FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();
    END IF;
END
$$;
