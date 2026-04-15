-- =============================================
-- Migration 015: Performance indexes
-- =============================================
-- Composite + partial B-tree indexes for the hottest query paths:
--   * /api/available-slots — bookings filtered by schedule_id + scheduled_time window,
--     almost always excluding 'cancelled'. A partial composite index drops roughly
--     the ~20% cancelled rows and collapses the schedule_id + time filter into one
--     index scan instead of combining idx_bookings_schedule_id with idx_bookings_scheduled_time.
--   * /api/bookings pagination — ORDER BY scheduled_time DESC with limit/offset.
--   * Admin /api/admin/logs — severity filter + created_at DESC pagination.
--   * reminder_loop — finds bookings with pending reminder flags soon to start.
--
-- All indexes are created with CONCURRENTLY so production traffic is not blocked.
-- CONCURRENTLY cannot run inside a transaction block — apply this migration with
--   psql -v ON_ERROR_STOP=1 -f 015_performance_indexes.sql
-- (each statement commits independently).
--
-- Naming stays consistent with existing idx_* convention. Original indexes
-- (idx_bookings_schedule_id, idx_bookings_scheduled_time, idx_bookings_status,
--  idx_app_events_severity, idx_app_events_created) are kept — PostgreSQL will
-- pick the better one per query; removing them requires separate ANALYZE'd decision.
--
-- Expected sizes (rough, 100k bookings / 1M events):
--   idx_bookings_schedule_time_active     ~4 MB  (partial, ~80% of rows)
--   idx_bookings_scheduled_time_desc      ~5 MB
--   idx_bookings_reminders_pending        ~1 MB  (partial on pending reminders)
--   idx_app_events_severity_created       ~40 MB
--
-- Write impact: each INSERT/UPDATE on bookings touches 1–2 more small indexes
-- (sub-millisecond overhead). Acceptable given read-heavy workload.
-- =============================================

-- ─────────────────────────────────────────────
-- bookings: available-slots + admin lookups
-- ─────────────────────────────────────────────
-- Partial index covering the schedule_id + time window lookup used by
-- /api/available-slots and bookings detail queries. Excluding cancelled rows
-- keeps the index ~20% smaller and makes index-only scans more likely.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_bookings_schedule_time_active
    ON bookings (schedule_id, scheduled_time)
    WHERE status <> 'cancelled';

-- Pagination on /api/bookings uses ORDER BY scheduled_time DESC.
-- A dedicated DESC index avoids a sort step for large result sets.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_bookings_scheduled_time_desc
    ON bookings (scheduled_time DESC);

-- reminder_loop: looks up bookings with any of the _sent flags still FALSE
-- and scheduled_time in the near future. Partial index drops cancelled rows
-- (never reminded) and rows where all reminders were already sent.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_bookings_reminders_pending
    ON bookings (scheduled_time)
    WHERE status <> 'cancelled'
      AND (reminder_24h_sent = FALSE
           OR reminder_1h_sent = FALSE
           OR reminder_15m_sent = FALSE
           OR reminder_5m_sent = FALSE
           OR morning_reminder_sent = FALSE);

-- ─────────────────────────────────────────────
-- app_events: admin /api/admin/logs filter+sort
-- ─────────────────────────────────────────────
-- Admin log view filters by severity and sorts by created_at DESC.
-- Composite (severity, created_at DESC) serves both in a single scan.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_app_events_severity_created
    ON app_events (severity, created_at DESC);

-- ─────────────────────────────────────────────
-- Cleanup strategy for app_events
-- ─────────────────────────────────────────────
-- Purges info/warn entries older than N days (default 90). Critical/error
-- rows are kept indefinitely — they are rare and valuable for incident review.
-- Invoke manually or via a cron job:
--   SELECT cleanup_old_events(90);
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
    'Severity error/critical сохраняется бессрочно для разбора инцидентов.';
