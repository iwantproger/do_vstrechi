-- =============================================
-- 010: Notifications v2
-- Таблица sent_reminders + reminder_settings
-- =============================================

-- Таблица для отслеживания отправленных напоминаний (вместо boolean флагов)
CREATE TABLE IF NOT EXISTS sent_reminders (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    booking_id    UUID NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,
    reminder_type TEXT NOT NULL,   -- '1440', '60', '30', '15', '5', 'morning', 'confirmation_request'
    sent_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(booking_id, reminder_type)
);

CREATE INDEX IF NOT EXISTS idx_sent_reminders_booking ON sent_reminders(booking_id);

-- Настройки уведомлений пользователя (серверная копия)
ALTER TABLE users ADD COLUMN IF NOT EXISTS reminder_settings JSONB NOT NULL DEFAULT '{"reminders":["1440","60"],"customReminders":[]}';
