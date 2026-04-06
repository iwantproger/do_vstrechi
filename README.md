# До встречи 📅

Telegram Mini App для записи на встречи — аналог Calendly, работает прямо внутри Telegram.

---

## О проекте

«До встречи» позволяет любому пользователю Telegram настроить своё расписание доступности и принимать бронирования от других. Не нужно устанавливать сторонние приложения — всё происходит прямо в чате. Проект разворачивается на собственном VPS, данные хранятся на вашем сервере.

## Возможности

- Создание расписания доступности (дни недели, временные слоты)
- Просмотр свободных слотов и бронирование встречи
- Управление встречами: подтвердить, отменить
- Telegram-уведомления обеим сторонам при изменении статуса
- Личная статистика встреч

## Стек технологий

| Компонент     | Технология                        |
|---------------|-----------------------------------|
| Backend       | FastAPI, asyncpg                  |
| База данных   | PostgreSQL 16                     |
| Telegram-бот  | aiogram 3.x                       |
| Frontend      | Vanilla JS / HTML (Mini App)      |
| Инфраструктура| Docker, docker-compose, nginx     |
| SSL           | Let's Encrypt (Certbot)           |

## Архитектура

```
Пользователь Telegram
       │
       ▼
Telegram Bot (aiogram)  ◄──►  Mini App (HTML/JS)
       │                              │
       └──────────┬───────────────────┘
                  ▼
          Backend API (FastAPI)
                  │
                  ▼
           PostgreSQL 16
                  │
         (nginx — reverse proxy + SSL)
```

## Быстрый старт

### Требования

- Docker и Docker Compose
- Домен с A-записью, указывающей на ваш сервер (для SSL)
- Telegram Bot Token от [@BotFather](https://t.me/BotFather)

### Установка

```bash
git clone https://github.com/YOUR_USERNAME/do-vstrechi.git
cd do-vstrechi

cp .env.example .env
# Заполни .env своими значениями (см. раздел «Конфигурация»)

docker compose up -d

# Проверить что всё поднялось:
curl http://localhost/health
```

### SSL-сертификат

```bash
# Убедись что порт 80 открыт и домен прописан в nginx/nginx.conf
make ssl
docker compose restart nginx
```

## Конфигурация

Все настройки задаются через переменные окружения. Скопируй `.env.example` → `.env` и заполни:

| Переменная          | Описание                                              |
|---------------------|-------------------------------------------------------|
| `BOT_TOKEN`         | Токен бота от @BotFather                              |
| `POSTGRES_DB`       | Имя базы данных                                       |
| `POSTGRES_USER`     | Пользователь PostgreSQL                               |
| `POSTGRES_PASSWORD` | Пароль PostgreSQL                                     |
| `SECRET_KEY`        | Секретный ключ (сгенерируй: `openssl rand -hex 32`)  |
| `MINI_APP_URL`      | Публичный URL задеплоенного Mini App                  |

## Полезные команды

```bash
make up            # запустить все сервисы
make down          # остановить все сервисы
make restart       # полный перезапуск с ребилдом
make logs          # логи всех сервисов
make logs-backend  # логи backend
make logs-bot      # логи бота
make ps            # статус контейнеров
make health        # проверить здоровье всех сервисов
make psql          # открыть psql (интерактивная консоль)
make backup        # сделать дамп БД
make migrate FILE=004_admin_tables.sql  # применить конкретную миграцию
make migrate-all   # применить все миграции по порядку
make admin         # открыть админку в браузере
make cleanup       # очистить старые Docker-образы
```

## Админ-панель

Внутренняя панель управления доступна по адресу `/admin/`.

### Возможности

- **Дашборд** — метрики пользователей, бронирований, ошибок + графики (Chart.js)
- **Логи** — просмотр событий с фильтрацией по severity, типу, пользователю, дате
- **Задачи** — Kanban-доска с drag & drop (Backlog → In Progress → Done)
- **Настройки** — системная информация, управление сессиями, очистка событий

### Доступ

Только для владельца — через Telegram Login Widget. Задать `ADMIN_TELEGRAM_ID` в `.env`.

### Первая настройка

```bash
# 1. Задать домен в BotFather: /setdomain → dovstrechiapp.ru
# 2. Задать ADMIN_TELEGRAM_ID в .env
# 3. Применить миграцию (создаёт 4 таблицы для админки)
make migrate FILE=004_admin_tables.sql
# 4. Пересобрать сервисы
make restart
# 5. Открыть
make admin
```

## API

| Метод    | URL                                          | Описание                      |
|----------|----------------------------------------------|-------------------------------|
| `GET`    | `/health`                                    | Статус сервиса                |
| `POST`   | `/api/users/auth`                            | Авторизация / регистрация     |
| `POST`   | `/api/schedules`                             | Создать расписание            |
| `GET`    | `/api/schedules?telegram_id=X`              | Список расписаний             |
| `GET`    | `/api/schedules/{id}`                        | Расписание по ID              |
| `DELETE` | `/api/schedules/{id}?telegram_id=X`         | Удалить расписание            |
| `GET`    | `/api/available-slots/{id}?date=YYYY-MM-DD` | Свободные слоты               |
| `POST`   | `/api/bookings`                              | Создать бронирование          |
| `GET`    | `/api/bookings?telegram_id=X`               | Список встреч                 |
| `PATCH`  | `/api/bookings/{id}/confirm?telegram_id=X`  | Подтвердить встречу           |
| `PATCH`  | `/api/bookings/{id}/cancel?telegram_id=X`   | Отменить встречу              |
| `GET`    | `/api/stats?telegram_id=X`                  | Статистика                    |

## CI/CD

Проект поддерживает автодеплой через GitHub Actions.  
Добавь секреты в **Settings → Secrets and variables → Actions**:

| Секрет        | Значение                          |
|---------------|-----------------------------------|
| `VPS_HOST`    | IP-адрес вашего VPS               |
| `VPS_USER`    | SSH-пользователь (например, root) |
| `VPS_SSH_KEY` | Приватный SSH-ключ                |

При каждом `git push` в `main` → автоматический деплой на VPS.

## Структура проекта

```
do-vstrechi/
├── backend/          FastAPI + asyncpg
│   ├── main.py
│   ├── requirements.txt
│   └── Dockerfile
├── bot/              aiogram 3.x
│   ├── bot.py
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/         Telegram Mini App (HTML/JS)
│   └── index.html
├── nginx/            Reverse proxy + SSL
│   ├── nginx.conf
│   └── Dockerfile
├── database/         SQL-схема
│   └── init.sql
├── docker-compose.yml
├── .env.example
└── Makefile
```

## Лицензия

MIT
