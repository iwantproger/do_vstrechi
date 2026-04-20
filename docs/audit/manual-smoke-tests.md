# Ручные smoke-тесты — система уведомлений

Эти тесты требуют реального взаимодействия с Mini App и Telegram-клиентом.
Автоматизация невозможна без E2E-фреймворка для Telegram WebApp.

**Перед прогоном**: убедиться что integration-тесты прошли зелёным:
```bash
pytest backend/tests/test_notifications_integration.py -v -m integration
```

**Бот**: @beta_do_vstrechi_bot
**Mini App**: beta.dovstrechiapp.ru
**Ваш telegram_id**: подставить в SQL-проверках

---

## MANUAL-1: Настройки сохраняются на сервере

**Что проверяем**: profile.js читает и пишет настройки через API, не localStorage.

**Шаги**:
1. Открыть @beta_do_vstrechi_bot → "Открыть приложение"
2. Перейти в Профиль → раздел "Напоминания"
3. Выключить "24 ч", включить "30 мин" и "5 мин"
4. Выключить тумблер "Уведомления о записях"
5. Закрыть Mini App полностью
6. Открыть заново → Профиль

**Ожидаемо**: чипы "30 мин" и "5 мин" включены, "24 ч" выключен, тумблер "Уведомления о записях" выключен.

**SQL-проверка**:
```sql
SELECT reminder_settings FROM users WHERE telegram_id = <ваш_id>;
-- reminders: ["30","5"], booking_notif: false, reminder_notif: true
```

**Статус**: `[ ]`

---

## MANUAL-2: Тумблер "Уведомления о записях" блокирует push

**Что проверяем**: booking_notif=false → при новом бронировании push не приходит.

**Шаги**:
1. Убедиться что booking_notif=false (из MANUAL-1)
2. Попросить друга (или второй аккаунт) забронировать через вашу ссылку
3. Наблюдать Telegram

**Ожидаемо**: push "Новая запись" НЕ приходит. У гостя — приходит.

**SQL-проверка**:
```sql
SELECT reminder_settings->>'booking_notif' FROM users WHERE telegram_id = <ваш_id>;
-- false
```

**Статус**: `[ ]`

---

## MANUAL-3: Напоминание гостю в его таймзоне

**Что проверяем**: guest_timezone используется для форматирования времени.

**Подготовка** (curl):
```bash
# Создать бронирование с guest_timezone через API или SQL:
INSERT INTO bookings (schedule_id, guest_name, guest_contact, guest_telegram_id,
  scheduled_time, status, guest_timezone)
VALUES ('<schedule_id>', 'TEST_VERIFY_tz', 'test', <guest_tid>,
  NOW() + INTERVAL '4 minutes', 'confirmed', 'Asia/Vladivostok');
```

**Ожидаемо**: в напоминании гостю время показано в VLAT (+10), не в MSK (+3).
Пример: встреча в 12:00 UTC → гость видит "22:00", организатор видит "15:00".

**Статус**: `[ ]`

---

## MANUAL-4: Утренний запрос не приходит ночью

**Что проверяем**: adaptive floor — не раньше 07:00 в TZ гостя.

**Подготовка**:
1. Создать бронирование на завтра 08:00 MSK, подтвердить
2. Наблюдать: когда придёт "Встреча в силе?"

**Ожидаемо**: запрос придёт в ~07:00 MSK (floor), не раньше.

**Альтернатива** (если не хочется ждать):
```sql
-- Вставить бронирование confirmed, scheduled на 2ч вперёд, created_at = вчера:
INSERT INTO bookings (schedule_id, guest_name, guest_contact, guest_telegram_id,
  scheduled_time, status, created_at, confirmation_asked)
VALUES ('<sid>', 'TEST_VERIFY_morning', 'test', <guest_tid>,
  NOW() + INTERVAL '2 hours', 'confirmed', NOW() - INTERVAL '1 day', FALSE);
-- Подождать ~5 мин (тик confirmation-requests)
```

**Статус**: `[ ]`

---

## MANUAL-5: Late booking instant-уведомление

**Что проверяем**: бронирование за <30 мин → мгновенное "Встреча скоро!".

**Шаги**:
1. Забронировать встречу через Mini App на +25 мин от текущего времени
2. Наблюдать Telegram (и у организатора, и у гостя)

**Ожидаемо**: мгновенно приходит "Встреча скоро! До встречи: 25 мин".

**SQL-проверка**:
```sql
SELECT reminder_type FROM sent_reminders
WHERE booking_id = '<id>' ORDER BY sent_at;
-- Ожидаем: "1440:org", "60:org", "1440:guest", "60:guest" — pre-recorded missed
```

**Статус**: `[ ]`

---

## MANUAL-6: Кнопка "Подключиться" в напоминании <=1ч

**Что проверяем**: inline-кнопка "Подключиться" в напоминании за 5 мин.

**Шаги**:
1. Создать расписание с platform=jitsi
2. Забронировать на +5 мин
3. Дождаться 5-мин напоминания

**Ожидаемо**: в сообщении есть inline-кнопка "Подключиться" (url-кнопка с meeting_link) + "Открыть в приложении".

**Статус**: `[ ]`

---

## MANUAL-7: Статус "Просрочена" в UI

**Что проверяем**: expired отображается корректно в Mini App.

**Подготовка** (SQL):
```sql
-- Перевести тестовое бронирование в expired:
UPDATE bookings SET scheduled_time = NOW() - INTERVAL '3 hours', status = 'pending'
WHERE id = '<test_booking_id>';
```

Затем вызвать:
```bash
curl -X POST https://beta.dovstrechiapp.ru/api/bookings/complete-past \
  -H "X-Internal-Key: $INTERNAL_API_KEY"
```

**Шаги**: открыть Mini App → Мои встречи → Архив.

**Ожидаемо**: встреча помечена "🕑 Просрочена" (серый цвет).

**Статус**: `[ ]`

---

## MANUAL-8: Security — 401 без ключа

**Что проверяем**: internal endpoints отвечают 401 без X-Internal-Key.

**Шаги**:
```bash
curl -s -o /dev/null -w "%{http_code}" \
  https://beta.dovstrechiapp.ru/api/bookings/pending-reminders-v2
```

**Ожидаемо**: `401`

```bash
curl -s -o /dev/null -w "%{http_code}" \
  -H "X-Internal-Key: $INTERNAL_API_KEY" \
  https://beta.dovstrechiapp.ru/api/bookings/pending-reminders-v2
```

**Ожидаемо**: `200`

**Статус**: `[ ]`

---

## MANUAL-9: Фильтр "Нет ответа" в боте показывает no_answer

**Что проверяем**: кнопка "Нет ответа" в боте фильтрует по status=no_answer.

**Подготовка** (SQL):
```sql
-- Создать бронирование со статусом no_answer:
INSERT INTO bookings (schedule_id, guest_name, guest_contact, guest_telegram_id,
  scheduled_time, status)
VALUES ('<sid>', 'TEST_VERIFY_noans', 'test', <guest_tid>,
  NOW() + INTERVAL '2 hours', 'no_answer');
```

**Шаги**: в боте нажать "Встречи" → "Нет ответа".

**Ожидаемо**: TEST_VERIFY_noans отображается в списке.

**Статус**: `[ ]`

---

## Cleanup

После всех тестов:
```sql
DELETE FROM bookings WHERE guest_name LIKE 'TEST_VERIFY_%';
DELETE FROM sent_reminders WHERE booking_id NOT IN (SELECT id FROM bookings);
```
