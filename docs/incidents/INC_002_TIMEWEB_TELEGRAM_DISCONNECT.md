# INC-002: Двусторонний обрыв связности Timeweb ↔ Telegram CDN

**Дата:** 2026-05-02
**Критичность:** P0 (полная неработоспособность бота — основная точка входа в продукт)
**Время простоя:** ~3 часа от первых симптомов до hot-fix; ~6 часов до полного решения через миграцию
**Затронуто:** все Telegram-пользователи бота — `/start`, бронирования, push-уведомления, напоминания

---

## Симптомы

- Бот молчит на `/start` или отвечает с задержкой 60+ секунд
- Push-уведомления о новых бронированиях не приходят организаторам
- Напоминания (`reminder_loop`) не срабатывают
- В логах бота:
  ```
  TelegramNetworkError: HTTP Client says - Request timeout error
  Update id=... handled. Duration 60218 ms
  ```
- `getWebhookInfo` показывает:
  ```json
  "last_error_message": "Connection timed out",
  "ip_address": "109.73.192.69"
  ```
- Контейнеры backend/bot/postgres все `Up`, никаких рестартов — проблема НЕ в коде

## Корневая причина

VPS Timeweb (109.73.192.69) потерял сетевую связность с подсетями Telegram CDN (149.154.166.0/24, 149.154.167.0/24, 2001:67c:4e8:f004::/64) **в обе стороны**:

- **Outbound** (бот → api.telegram.org): TCP connect timeout. Бот не может ни отправить сообщение, ни взять getUpdates.
- **Inbound** (Telegram → webhook): Telegram CDN не достукивается до nginx на dovstrechiapp.ru — `Connection timed out`.

**Усугубляющий фактор:** системный resolver на Timeweb отдавал IPv6 (`2001:67c:4e8:f004::9`) первым в `getaddrinfo`. IPv6-маршрут до Telegram был **полностью мёртв** (TCP timeout 100% попыток), а fallback на IPv4 в aiogram срабатывал слишком поздно — после 60s aiogram timeout.

Скорее всего комбинация:
1. РКН-фильтрация маршрута к Telegram CDN на магистрали Timeweb
2. Системный resolver предпочитает IPv6 по RFC 6724

После форсирования IPv4 (`extra_hosts` в docker-compose.yml) connect-таймауты сохранились на уровне ~70% попыток — стало ясно, что блокировка глубже DNS, на уровне сетевого маршрута / DPI.

## Диагностика (хронология)

| Время (UTC) | Событие |
|-------------|---------|
| ~07:00 | Первые `TelegramNetworkError: Request timeout` в логах бота |
| ~12:00 | Пользователь сообщил «бот не работает» |
| 12:50 | Запущена SSH-диагностика на проде. Контейнеры все `Up`, бот в webhook-режиме, webhook доставляется, но ответы виснут |
| 13:00 | Установлено: `bash </dev/tcp/api.telegram.org/443>` зависает (берёт IPv6 первым) |
| 13:05 | `curl -v` сам падает на IPv4-fallback после успешного TLS handshake → понятно что DPI режет HTTP-уровень поверх TLS на api.telegram.org |
| 13:20 | Hot-fix `extra_hosts` в `docker-compose.yml` (хардкод IPv4 в /etc/hosts контейнера). IPv6-проблема снята, IPv4-таймауты остались |
| 13:25-13:38 | Мониторинг 20×30s TCP-проб — `OK` только 6 из 20 (30%), нестабильно |
| 13:45 | Решение: перенести бота на foreign VPS, БД оставить в РФ (152-ФЗ) |
| 14:18 | Финский VPS (38.244.193.239) подготовлен — Docker, ufw, fail2ban |
| 14:21-14:27 | Bot tarball + .env (через ssh-pipe), build образа (232 MB) |
| 14:27 | Phase 5A: запуск бота на финском, polling started, webhook очищен |
| 14:28 | Phase 5B: остановка bot на Timeweb, переключение `BOT_INTERNAL_URL` → финский, рестарт backend |
| 14:33 | Юзерский E2E: `/start` обработан за **858 ms** (vs 60+ s ранее) |
| 14:38 | Vторичный фикс: nginx booking rate-limit ловил bot-VPS (single IP, 5+ req/min) → geo-whitelist |

## Решение

**Архитектурное:** перенос Telegram-бота на foreign VPS (ishosting Финляндия), backend и БД оставлены на Timeweb для соблюдения 152-ФЗ.

**Конкретно:**
- Бот в polling-режиме на 38.244.193.239 (вместо webhook), Redis для FSM
- Backend → Bot: `http://38.244.193.239:8080/internal/*` (plain HTTP + `X-Internal-Key`, ufw whitelist Timeweb IP)
- Bot → Backend: `https://dovstrechiapp.ru/api/*` (HTTPS + `X-Internal-Key`, nginx geo-whitelist для booking rate-limit)
- Bot → Telegram: `https://api.telegram.org` напрямую (foreign route, стабильно)
- Содержимое уведомлений (telegram_id, тексты) не критично-секретное; для полной изоляции в TODO — WireGuard-туннель Timeweb↔ishosting

**Изменения в репо** (PR #12, 4 коммита):
- `2b79720` extra_hosts (IPv4 force) — оставлен как defense in depth
- `44e399e` `docker-compose.bot.yml` + `.env.bot.example`
- `74c23f4` `docker-compose.yml`: bot → `profiles: ["archived"]`, `BOT_INTERNAL_URL` через env-substitution
- `df3b981` `nginx.conf`: `/bot/webhook` закомментирован, geo-whitelist для `booking` rate-limit zone

## Уроки

1. **Telegram-боты на РФ-VPS — высокий риск.** Связность с api.telegram.org может пропасть в любой момент без предупреждения. Для критичных integrations с Telegram — размещать вне РФ изначально.

2. **DNS-resolver предпочитает IPv6.** Это RFC 6724 поведение системного `getaddrinfo`. При мёртвом IPv6-маршруте — таймауты. Решения: `extra_hosts` (хардкод IPv4 в контейнере), `gai.conf precedence`, `socket.AF_INET` в коде клиента.

3. **Webhook ↔ polling — разные failure modes.** Webhook требует входящей связности (Telegram → нас); polling — исходящей (мы → Telegram). При двусторонней блокировке оба ломаются, но polling восстанавливается легче через прокси/foreign VPS.

4. **Single-IP клиенты упираются в rate-limit.** После переноса бота на foreign VPS все его запросы к backend идут с одного IP. Default nginx rate-limit (5 req/min для `/api/bookings/*`) для бота, который опрашивает 5+ endpoints в минуту, оказался слишком жёстким. Решение: geo-whitelist по IP (security защита остаётся на уровне FastAPI `Depends(get_internal_caller)`).

5. **Hot-fixes на проде → дрифт от git.** При каждой ручной правке `docker-compose.yml`, `nginx.conf`, `.env` на VPS делал бэкап с timestamp и сразу синхронизировал в git через PR. Иначе следующий CI deploy перетёр бы фикс. Хорошая практика на будущее: даже при экстренной правке прода — сразу же отдельный коммит с тем же diff.

## TODO (отдельные тикеты)

- [ ] CI/CD workflow для финского VPS (`deploy-bot.yml`) — сейчас деплой бота ручной (scp + docker compose build)
- [ ] WireGuard-туннель Timeweb↔ishosting для шифрования backend↔bot трафика
- [ ] Внешний uptime-монитор (uptimerobot или healthchecks.io)
- [ ] Бэкап `/opt/dovstrechi-bot/.env` (содержит секреты)
- [ ] Алерт на падение TCP-связности с api.telegram.org из обоих VPS
