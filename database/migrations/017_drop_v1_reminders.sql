-- =============================================
-- 017: Удаление V1 системы напоминаний
-- См. docs/audit/notifications-audit-2026-04-20.md FINDING-002
--
-- V1 использовала boolean-флаги (reminder_24h_sent и т.д.) в таблице bookings.
-- Система полностью заменена на V2 (таблица sent_reminders + users.reminder_settings).
-- Boolean-флаги не читаются и не записываются ни одним клиентом.
--
-- View bookings_detail использует SELECT b.* и зависит от структуры bookings.
-- PostgreSQL не позволяет DROP COLUMN при зависимом view без CASCADE.
-- Решение: DROP VIEW → DROP COLUMN → CREATE VIEW (атомарно в транзакции).
--
-- ВАЖНО: перед накаткой сделать бэкап БД:
--   pg_dump -U dovstrechi dovstrechi > backup_pre_v1_drop_$(date +%Y%m%d_%H%M%S).sql
--
-- Идемпотентна: можно применять повторно без ошибок.
-- =============================================

BEGIN;

-- 1. Удалить зависимый view (пересоздадим после DROP COLUMN)
DROP VIEW IF EXISTS bookings_detail;

-- 2. Удалить partial index по V1-флагам
DROP INDEX IF EXISTS idx_bookings_reminders_pending;

-- 3. Удалить V1 boolean-колонки
ALTER TABLE bookings
    DROP COLUMN IF EXISTS reminder_24h_sent,
    DROP COLUMN IF EXISTS reminder_1h_sent,
    DROP COLUMN IF EXISTS reminder_15m_sent,
    DROP COLUMN IF EXISTS reminder_5m_sent,
    DROP COLUMN IF EXISTS morning_reminder_sent;

-- 4. Пересоздать view без V1-полей (b.* теперь не содержит удалённых колонок)
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

COMMIT;
