# Changelog

Все значимые изменения проекта «До встречи» фиксируются здесь.

Формат: [Semantic Versioning](https://semver.org/)

---

## [Unreleased]

---

## [1.2.0] — 15.04.2026

### Added
- Cross-schedule slot blocking: бронирования из других расписаний блокируют слоты в `/available-slots`
- Поле `blocks_slots` для ручных встреч — управление блокировкой доступности
- Статус `no_answer` + утренний поток подтверждения: бот спрашивает гостя «Встреча в силе?», auto-transition в no_answer через 1ч без ответа
- Бот поддержки (@dovstrechi_support_bot) — пересылка сообщений пользователей администратору
- Ссылка «Связаться с поддержкой» в профиле Mini App
- Улучшенные уведомления о бронировании с CTA-кнопками для гостя
- Онбординг: разные сообщения `/start` для новых и возвращающихся пользователей
- Inline-режим: поиск и шаринг расписаний через @bot в любом чате
- Лендинг с определением контекста (Telegram / браузер)

### Fixed
- Quick Add: 7+ багов (layout, native pickers, schedules, dates, labels)
- Quick Add: поддержка end_date, ночные встречи, schedule end_time
- Скрыт app-footer в Mini App — устранён сдвиг layout на всех экранах

### Security
- R1 (секреты в git history) — ЗАКРЫТ: ротация + git filter-repo
- R4 (at-rest encryption), R5 (audit log), R6 (DDoS) — зафиксированы как принятые риски

> **Примечание о версионировании:** Версии 2.0.0–2.2.0 были внутренними milestone-метками.
> Начиная с v1.2.0 используется единая нумерация, согласованная с frontend (config.js).

---

## [2.2.0] — 09.04.2026

### Added
- Интеграция Google Calendar: OAuth, синхронизация событий, push-уведомления через webhooks
- Интеграция Яндекс Календарь и Apple Calendar (CalDAV)
- Блокировка занятых слотов из внешних календарей (zero-config)
- Запись/удаление бронирований во внешних календарях
- Новый экран настроек календарей: provider-cards, 3 переключателя на календарь
- `is_display_enabled`: показ событий из внешних календарей в экране Встречи и на главном экране
- Privacy Policy и Terms of Service (`/privacy`, `/terms`) на RU+EN
- Google Search Console верификация (`/google6eb70911ad60f85e.html`)

### Fixed
- CalDAV: прямой URL вместо REPORT-запроса для Apple iCloud (delete/update)
- ENCRYPTION_KEY в beta-окружении
- Google Calendar кнопка подключения (отсутствовали скобки в onclick)
- Дедупликация внешних событий (NOT EXISTS event_mapping)
- Beta deploy использует compose-файл из dev-worktree

### Changed
- Убран избыточный scope `calendar.readonly` (покрывается `calendar.events`)
- `deploy-beta.yml`: compose и env файлы из worktree `/opt/dovstrechi-beta/`

---

## [2.1.0] — 08.04.2026

### Added
- Beta-окружение (beta.dovstrechiapp.ru)
- Разделение prod и beta баз данных (dovstrechi / dovstrechi_beta)
- Отдельный Telegram-бот для beta (@beta_do_vstrechi_bot)
- CI/CD: автодеплой dev → beta, prod только по запросу
- Git worktree архитектура на VPS (/opt/dovstrechi-beta)
- Shared Docker network для связи nginx с beta backend
- Настраиваемый CORS через ALLOWED_ORIGINS env var
- docs/DEPLOYMENT.md — правила деплоя (beta-first)
- docs/AGENTS.md — правила для AI-агентов
- docs/BETA_SETUP.md — инструкция первого запуска beta

### Changed
- Makefile: команда `deploy` требует ввод "production" + health-check beta
- README.md: таблица окружений, обновлён CI/CD раздел

### Infrastructure
- docs/DECISIONS.md: решения #23-25 (beta-first, prod-on-demand, worktrees)

---

## [2.0.0] — Рефакторинг + Админка

### Added
- Админ-панель (/admin/) с Telegram Login Widget
- Kanban-доска задач с drag & drop
- Structlog JSON-логирование
- Event tracking с анонимизацией (app_events)
- Модульная архитектура backend (routers/) и bot (handlers/)
- Напоминания о встречах (24ч и 1ч)
- Быстрое добавление встречи (Quick Add)
- Поддержка таймзон (users.timezone + viewer_tz)
- min_booking_advance — минимальное время бронирования заранее

---

## [1.0.0] — Первый релиз

### Added
- Создание расписаний через Telegram-бота
- Бронирование встреч через Mini App
- Интеграция Jitsi Meet для видеозвонков
- Push-уведомления при бронировании
- Поддержка 152-ФЗ (self-hosted на Timeweb VPS)
