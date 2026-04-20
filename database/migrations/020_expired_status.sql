-- =============================================
-- 020: Статус expired для зависших бронирований
-- Fixes FINDING-014, FINDING-016
--
-- pending + scheduled_time < NOW()-2h → expired
-- no_answer + scheduled_time < NOW() → expired
--
-- ВАЖНО: бэкап перед миграцией!
--   pg_dump -U dovstrechi dovstrechi > backup_pre_expired.sql
-- =============================================

-- Расширить CHECK constraint (добавить expired)
ALTER TABLE bookings DROP CONSTRAINT IF EXISTS bookings_status_check;
ALTER TABLE bookings ADD CONSTRAINT bookings_status_check
  CHECK (status IN ('pending', 'confirmed', 'cancelled', 'completed', 'no_answer', 'expired'));

-- Конвертация зависших бронирований
UPDATE bookings
SET status = 'expired', updated_at = NOW()
WHERE status = 'pending'
  AND scheduled_time < NOW() - INTERVAL '2 hours';

UPDATE bookings
SET status = 'expired', updated_at = NOW()
WHERE status = 'no_answer'
  AND scheduled_time < NOW();
