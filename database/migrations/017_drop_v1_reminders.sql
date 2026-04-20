-- =============================================
-- 017: Удаление V1 системы напоминаний
-- См. docs/audit/notifications-audit-2026-04-20.md FINDING-002
--
-- V1 использовала boolean-флаги (reminder_24h_sent и т.д.) в таблице bookings.
-- Система полностью заменена на V2 (таблица sent_reminders + users.reminder_settings).
-- Boolean-флаги не читаются и не записываются ни одним клиентом.
--
-- ВАЖНО: перед накаткой сделать бэкап БД:
--   pg_dump -U dovstrechi dovstrechi > backup_pre_v1_drop_$(date +%Y%m%d_%H%M%S).sql
--
-- DROP COLUMN необратим!
-- =============================================

-- Удалить partial index по V1-флагам
DROP INDEX IF EXISTS idx_bookings_reminders_pending;

-- Удалить V1 boolean-колонки
ALTER TABLE bookings
    DROP COLUMN IF EXISTS reminder_24h_sent,
    DROP COLUMN IF EXISTS reminder_1h_sent,
    DROP COLUMN IF EXISTS reminder_15m_sent,
    DROP COLUMN IF EXISTS reminder_5m_sent,
    DROP COLUMN IF EXISTS morning_reminder_sent;