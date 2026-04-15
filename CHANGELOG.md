# Changelog

Все значимые изменения проекта «До встречи» фиксируются здесь.

Формат: [Semantic Versioning](https://semver.org/)

---

## [Unreleased]

---

## [1.2.3] — 15.04.2026

### Added — Adminка: мультивыбор задач

- `feat`: мультивыбор карточек в Kanban — Ctrl/Cmd+клик toggle выделения, без Ctrl — открытие просмотра (как раньше)
- `feat`: кнопка «Выбрать» — режим выбора (любой клик = select, drag & drop отключается)
- `feat`: плавающий тулбар при выделении — счётчик выбранных + «📋 Скопировать» + «✕ Сбросить»
- `feat`: Ctrl+A — выбрать все карточки на доске; Ctrl+C — копировать выбранные (если нет текстового выделения); Esc — сбросить выделение
- `feat`: Markdown-формат при копировании — заголовок, статус, теги, техническое описание, plain-описание, source_ref; несколько задач разделяются `---`
- `feat`: выделение сохраняется при перерисовке доски (`renderKanban`), сбрасывается при уходе со страницы Tasks

---

## [1.2.2] — 15.04.2026

### Fixed

- `fix`: авто-подтверждённые бронирования больше не показывают кнопки «Подтвердить / Отклонить» организатору — только информация о записи + кнопка «📱 Открыть приложение». Ошибка: `requires_confirmation` не передавался в уведомление, бот всегда показывал кнопки.

---

## [1.2.1] — 15.04.2026

### Fixed — Уведомления и утренний флоу

- `fix`: race condition в утреннем подтверждении — гость нажимал «Да, буду!», но через час всё равно получал «⚠️ Не подтвердил». Исправлено: `guest-confirm` очищает `confirmation_asked_at = NULL`, `no-answer-candidates` добавляет `IS NOT NULL` проверку на обоих уровнях (backend + bot)
- `fix`: `confirm_booking` сбрасывает `confirmation_asked = FALSE` — цикл напоминаний автоматически отправит «Встреча в силе?» участнику в течение 5 минут после того как организатор подтвердит встречу на тот же день
- `feat`: утренняя сводка организатору — список pending-встреч на сегодня с кнопками ✅/❌ прямо в сообщении; дедупликация через `users.morning_summary_sent_date` (не более одного раза в день)
- `feat`: утреннее уведомление участнику о pending-встрече — «⏳ Ваша встреча ещё не подтверждена организатором, ожидайте»
- `migration`: `013_morning_summary.sql` — добавлена колонка `users.morning_summary_sent_date DATE`

---

## [1.2.0] — 15.04.2026

> **Примечание о версионировании:** Версии 2.0.0–2.2.0 были внутренними milestone-метками.
> Начиная с v1.2.0 используется единая нумерация, согласованная с frontend (config.js).

### Added — Интеграция внешних календарей

- `feat`: Google Calendar OAuth интеграция (MVP) — 6 новых таблиц: `calendar_accounts`, `calendar_connections`, `schedule_calendar_rules`, `external_busy_slots`, `event_mapping`, `sync_log`
- `feat`: Phase 2 — инкрементальная синхронизация через `sync_token`, Google webhook subscriptions, auto-renewal, уведомления об изменении встречи в боте
- `feat`: Phase 3 — CalDAV адаптер (python-caldav) для Яндекс Календарь и Apple iCloud; подключение по email+пароль
- `feat`: UI карточки провайдеров (Google / Яндекс / Apple) + переключатель `is_display_enabled` для показа событий в ленте
- `feat`: per-schedule настройка правил календаря — какие подключённые календари блокируют слоты и куда записывать бронирования
- `fix`: zero-config slot blocking — внешние занятые слоты учитываются при `/available-slots` без ручной настройки
- `fix`: показ внешних событий на главном экране в блоке «Сегодня»

### Added — Встречи и расписания

- `feat`: платформа «Офлайн» — без ссылки на звонок, с полем адреса места; snapshot полей `platform` и `location_address` в бронировании
- `feat`: при удалении расписания с активными встречами — диалог: сохранить встречи или отменить
- `feat`: manual confirm toggle — организатор может включить обязательное подтверждение бронирования
- `feat`: cross-schedule slot blocking — `e697b51`: бронирования из других расписаний блокируют слоты (`blocks_slots`)
- `feat`: поле `blocks_slots` для ручных встреч — управление влиянием на публичную доступность
- `feat`: статус `no_answer` + утренний поток подтверждения: бот спрашивает гостя «Встреча в силе?», auto-transition через 1ч без ответа
- `fix`: cross-schedule конфликтная проверка учитывает `buffer_time`

### Added — Уведомления v2

- `feat`: таблица `sent_reminders` — идемпотентный лог отправленных напоминаний, заменяет boolean-флаги
- `feat`: `users.reminder_settings` JSONB — индивидуальное время напоминаний вместо фиксированных 24h/1h
- `feat`: новые endpoints: `/pending-reminders-v2`, `/sent-reminders`, `/confirmation-requests`, `/no-answer-candidates`, `/confirmation-asked`, `/set-no-answer`, `/guest-confirm`
- `feat`: полный аудит нотификаций — напоминания, изменения статуса, morning alert; цикл сокращён с 5 мин до 60 сек
- `feat`: улучшенные уведомления гостю о новом бронировании с CTA-кнопками и ссылками на напоминания

### Added — Бот

- `feat`: редизайн меню — 2×2 ReplyKeyboard (🏠 Главная / 📋 Встречи / 📅 Расписания / 👤 Профиль) + WebApp кнопка; handlers зеркалируют вкладки Mini App
- `feat`: inline-режим — поиск и шаринг расписаний через @bot в любом чате
- `feat`: share via Telegram — отправка расписания как rich-message в формате inline
- `feat`: онбординг — разные сообщения `/start` для новых и вернувшихся пользователей
- `feat`: гостевые callbacks `guest_confirm_*` и `guest_cancel_*` — ответ на morning confirmation прямо из чата
- `feat`: support bot (@dovstrechi_support_bot) — пересылка сообщений пользователей администратору
- `feat`: ссылка «Связаться с поддержкой» в профиле Mini App

### Added — Интерфейс и инфраструктура

- `feat`: аватар пользователя из Telegram с прокси и fallback на initials
- `feat`: лендинг `dovstrechiapp.ru` — определение контекста (Telegram / браузер), CTA
- `feat`: Политика конфиденциальности и Условия использования (`/privacy`, `/terms`)
- `feat`: Google Search Console верификация

### Fixed

- `fix`: Quick Add — 7 багов layout, native pickers, schedules, dates, labels
- `fix`: Quick Add — поддержка end_date, ночные встречи (переход за полночь), schedule end_time
- `fix`: Quick Add — стандартный screen layout + прямые native pickers (Android/iOS)
- `fix`: скрыт `app-footer` в Mini App — устранён сдвиг layout на всех экранах
- `fix`: шаринг использует корректный schedule ID
- `fix`: кнопка отмены встречи — гостевые встречи везде (не только в своей вкладке)
- `fix`: дублирование встречи при повторном добавлении в Quick Add
- `fix`: Google connect button — отсутствующие скобки в onclick (кнопка не работала)
- `fix`: Yandex Calendar — ENCRYPTION_KEY + неверная ссылка подключения
- `fix`: CalDAV delete/update — прямой URL вместо REPORT-запроса (Apple iCloud)
- `fix`: восстановлен `calendar.readonly` scope — обязателен для calendarList.list
- `fix`: восстановлен navbar pill layout после регрессии Block E
- `fix`: OAuth `/google/auth-url` возвращает JSON (не redirect)
- `fix`: `::timestamptz` cast в SQL-запросе `/available-slots`
- `fix`: исключён аккаунт владельца из статистики в админке

### Security

- R1 (секреты в git history) — ЗАКРЫТ: ротация + git filter-repo
- R4 (at-rest encryption), R5 (audit log), R6 (DDoS) — зафиксированы как принятые риски

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
