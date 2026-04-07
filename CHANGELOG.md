# Changelog

Все значимые изменения проекта «До встречи» фиксируются здесь.

Формат: [Semantic Versioning](https://semver.org/)

---

## [Unreleased]

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
