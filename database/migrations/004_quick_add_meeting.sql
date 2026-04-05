-- Migration: quick add meeting feature
-- Apply: docker-compose exec -T postgres psql -U dovstrechi -d dovstrechi -f /tmp/004_quick_add_meeting.sql

-- Дефолтное расписание (скрытое, для личных встреч)
ALTER TABLE schedules ADD COLUMN IF NOT EXISTS is_default BOOLEAN NOT NULL DEFAULT FALSE;

-- Расширение bookings для ручных встреч
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS title TEXT;
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS end_time TIMESTAMPTZ;
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS is_manual BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS created_by BIGINT;
