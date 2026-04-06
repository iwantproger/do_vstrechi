-- Migration 005: add min_booking_advance to schedules
-- Value in minutes: 0 = no restriction, 60 = at least 1h before slot, etc.
ALTER TABLE schedules ADD COLUMN IF NOT EXISTS min_booking_advance INTEGER NOT NULL DEFAULT 0;
