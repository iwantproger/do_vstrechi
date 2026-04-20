-- =============================================
-- 018: Per-user notification settings
-- Fixes FINDING-001, FINDING-004, FINDING-006, FINDING-012
--
-- Добавляет booking_notif и reminder_notif в reminder_settings JSONB.
-- Обновляет дефолт для новых пользователей: ["1440","60","5"].
-- Существующие reminders/customReminders НЕ трогаем.
-- =============================================

-- Обновить дефолт для новых пользователей
ALTER TABLE users
  ALTER COLUMN reminder_settings
  SET DEFAULT '{"reminders":["1440","60","5"],"customReminders":[],"booking_notif":true,"reminder_notif":true}'::jsonb;

-- Backfill: добавить отсутствующие поля существующим пользователям
UPDATE users SET reminder_settings =
  reminder_settings
  || jsonb_build_object('booking_notif', COALESCE(reminder_settings->'booking_notif', 'true'::jsonb))
  || jsonb_build_object('reminder_notif', COALESCE(reminder_settings->'reminder_notif', 'true'::jsonb))
WHERE reminder_settings->>'booking_notif' IS NULL
   OR reminder_settings->>'reminder_notif' IS NULL;
