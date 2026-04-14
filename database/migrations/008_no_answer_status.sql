-- Migration 008: add no_answer status + confirmation tracking
-- no_answer = guest didn't respond to morning "still coming?" within 1h

-- 1. Expand status CHECK to include no_answer
ALTER TABLE bookings DROP CONSTRAINT IF EXISTS bookings_status_check;
ALTER TABLE bookings ADD CONSTRAINT bookings_status_check
  CHECK (status IN ('pending', 'confirmed', 'cancelled', 'completed', 'no_answer'));

-- 2. Track when confirmation was asked
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS confirmation_asked    BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS confirmation_asked_at TIMESTAMPTZ;
