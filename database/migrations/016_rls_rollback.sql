-- ═══════════════════════════════════════════
-- 016 ROLLBACK: disable RLS on bookings
-- Run this if RLS causes issues after deployment.
-- ═══════════════════════════════════════════

DROP POLICY IF EXISTS bookings_internal ON bookings;
DROP POLICY IF EXISTS bookings_organizer ON bookings;
DROP POLICY IF EXISTS bookings_guest ON bookings;
DROP POLICY IF EXISTS bookings_insert ON bookings;

ALTER TABLE bookings DISABLE ROW LEVEL SECURITY;

DROP FUNCTION IF EXISTS current_telegram_id();
