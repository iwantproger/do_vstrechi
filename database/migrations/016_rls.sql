-- ═══════════════════════════════════════════
-- 016: Row Level Security — bookings pilot
--
-- Defence-in-depth: even if the DB connection is
-- compromised, rows are filtered by session context.
-- Pilot: bookings table only. Expand after validation.
--
-- Session variables (set by backend db() dependency):
--   app.telegram_id  — current user's telegram_id ('' if none)
--   app.is_internal  — 'true' for bot/internal requests
--
-- ROLLBACK: database/migrations/016_rls_rollback.sql
-- ═══════════════════════════════════════════

-- Helper: extract current telegram_id from session variable
CREATE OR REPLACE FUNCTION current_telegram_id() RETURNS BIGINT AS $$
BEGIN
  RETURN NULLIF(current_setting('app.telegram_id', true), '')::BIGINT;
EXCEPTION WHEN OTHERS THEN
  RETURN NULL;
END;
$$ LANGUAGE plpgsql STABLE;

-- ══════ BOOKINGS ══════
ALTER TABLE bookings ENABLE ROW LEVEL SECURITY;
ALTER TABLE bookings FORCE ROW LEVEL SECURITY;

-- 1. Internal/bot bypass (reminders, notifications, confirmation flows)
CREATE POLICY bookings_internal ON bookings
  FOR ALL
  USING (current_setting('app.is_internal', true) = 'true');

-- 2. Organizer: full access to bookings of their schedules
CREATE POLICY bookings_organizer ON bookings
  FOR ALL
  USING (
    schedule_id IN (
      SELECT s.id FROM schedules s
      JOIN users u ON s.user_id = u.id
      WHERE u.telegram_id = current_telegram_id()
    )
  );

-- 3. Guest: access to their own bookings
CREATE POLICY bookings_guest ON bookings
  FOR ALL
  USING (
    guest_telegram_id IS NOT NULL
    AND guest_telegram_id = current_telegram_id()
  );

-- 4. INSERT: any authenticated user or internal process can create bookings
--    (application code validates schedule_id, availability, etc.)
CREATE POLICY bookings_insert ON bookings
  FOR INSERT
  WITH CHECK (
    current_telegram_id() IS NOT NULL
    OR current_setting('app.is_internal', true) = 'true'
  );
