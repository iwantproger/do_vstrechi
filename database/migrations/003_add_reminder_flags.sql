-- Migration: add reminder flags to bookings
-- Apply: docker-compose exec postgres psql -U dovstrechi -d dovstrechi -f /docker-entrypoint-initdb.d/migrations/003_add_reminder_flags.sql

ALTER TABLE bookings ADD COLUMN IF NOT EXISTS reminder_24h_sent BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS reminder_1h_sent BOOLEAN NOT NULL DEFAULT FALSE;
