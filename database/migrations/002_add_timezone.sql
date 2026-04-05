-- Migration: add timezone column to users
-- Apply: docker-compose exec postgres psql -U dovstrechi -d dovstrechi -f /docker-entrypoint-initdb.d/migrations/002_add_timezone.sql

ALTER TABLE users ADD COLUMN IF NOT EXISTS timezone TEXT NOT NULL DEFAULT 'UTC';
