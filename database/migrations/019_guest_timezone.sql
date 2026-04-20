-- =============================================
-- 019: Guest timezone на бронированиях
-- Fixes FINDING-007 — гость видит время в своей TZ
--
-- IANA timezone строка (напр. Asia/Vladivostok).
-- NULL = использовать TZ организатора (обратная совместимость).
-- =============================================

ALTER TABLE bookings ADD COLUMN IF NOT EXISTS guest_timezone TEXT;

COMMENT ON COLUMN bookings.guest_timezone IS 'IANA timezone гостя для форматирования уведомлений';
