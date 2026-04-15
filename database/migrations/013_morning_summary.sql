-- Migration 013: Add morning_summary_sent_date to users
-- Tracks when the organizer last received a "pending bookings today" summary.
-- Prevents duplicate morning summaries within the same day.

ALTER TABLE users ADD COLUMN IF NOT EXISTS morning_summary_sent_date DATE;

COMMENT ON COLUMN users.morning_summary_sent_date IS
    'Date when the morning organizer summary (pending bookings today) was last sent. NULL = never sent.';
