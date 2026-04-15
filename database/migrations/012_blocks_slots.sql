-- Флаг блокировки слотов: ручные встречи могут не блокировать слоты
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS blocks_slots BOOLEAN NOT NULL DEFAULT TRUE;
