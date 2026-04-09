-- Migration 009: Add is_display_enabled to calendar_connections
-- Controls whether external calendar events are shown in the "Встречи" screen

ALTER TABLE calendar_connections
  ADD COLUMN IF NOT EXISTS is_display_enabled BOOLEAN NOT NULL DEFAULT FALSE;
