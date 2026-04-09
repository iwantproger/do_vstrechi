-- Офлайн-платформа: адрес встречи в расписании и снапшот в бронировании
ALTER TABLE schedules ADD COLUMN IF NOT EXISTS location_address TEXT;
ALTER TABLE bookings  ADD COLUMN IF NOT EXISTS platform         TEXT;
ALTER TABLE bookings  ADD COLUMN IF NOT EXISTS location_address TEXT;
