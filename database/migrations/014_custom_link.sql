-- Migration 014: Add custom_link to schedules
-- Allows setting a fixed meeting link for platform='other'
ALTER TABLE schedules ADD COLUMN IF NOT EXISTS custom_link TEXT;
