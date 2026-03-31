# До встречи 🗓

Telegram Mini App для записи на встречи. Аналог Calendly, работает прямо в Telegram.

**Стек:** FastAPI · asyncpg · PostgreSQL 16 · aiogram 3.x · Vanilla JS · Docker · Nginx  
**152-ФЗ:** данные хранятся на серверах Timeweb в России ✓

---

## Быстрый старт на VPS

```bash
# 1. Клонируй репозиторий
git clone https://github.com/YOUR_USERNAME/do-vstrechi.git /opt/dovstrechi
cd /opt/dovstrechi

# 2. Создай .env
cp .env.example .env
nano .env   # заполни BOT_TOKEN, POSTGRES_PASSWORD, SECRET_KEY, MINI_APP_URL

# 3. Запуск (без SSL — для теста)
docker compose up -d

# 4. Проверь
curl http://localhost/health
```

---

## Структура проекта

```
do-vstrechi/
├── backend/          FastAPI + asyncpg (PostgreSQL)
│   ├── main.py
│   ├── requirements.txt
│   └── Dockerfile
├── bot/              aiogram 3.x бот
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
├── Makefile          удобные команды
└── deploy.sh         деплой одной командой
```

---

## Получение SSL сертификата

```bash
# 1. Сначала запусти nginx без SSL (проверь что 80 порт открыт)
# 2. Замени YOUR_DOMAIN.ru в nginx/nginx.conf и Makefile на твой домен
# 3. Получи сертификат
make ssl

# 4. После получения — перезапусти nginx
docker compose restart nginx
```

---

## Полезные команды

```bash
make up           # запустить все
make down         # остановить все
make logs         # логи всех сервисов
make logs-backend # логи только backend
make logs-bot     # логи только бота
make psql         # открыть psql
make backup       # сделать дамп БД
make restart      # полный перезапуск с ребилдом
```

---

## API Endpoints

| Метод | URL | Описание |
|-------|-----|----------|
| GET | `/health` | Здоровье сервиса |
| POST | `/api/users/auth` | Авторизация / регистрация |
| POST | `/api/schedules` | Создать расписание |
| GET | `/api/schedules?telegram_id=X` | Список расписаний |
| GET | `/api/schedules/{id}` | Расписание по ID |
| DELETE | `/api/schedules/{id}?telegram_id=X` | Удалить расписание |
| GET | `/api/available-slots/{id}?date=YYYY-MM-DD` | Свободные слоты |
| POST | `/api/bookings` | Создать бронирование |
| GET | `/api/bookings?telegram_id=X` | Список встреч |
| PATCH | `/api/bookings/{id}/confirm?telegram_id=X` | Подтвердить |
| PATCH | `/api/bookings/{id}/cancel?telegram_id=X` | Отменить |
| GET | `/api/stats?telegram_id=X` | Статистика |

---

## CI/CD (GitHub Actions)

Добавь секреты в GitHub → Settings → Secrets:
- `VPS_HOST` — IP адрес VPS
- `VPS_USER` — пользователь SSH (обычно `root`)
- `VPS_SSH_KEY` — приватный SSH ключ

При каждом `git push main` → автоматический деплой на VPS.

---

## Регистрация домена

1. Зайди на [timeweb.com](https://timeweb.com) → Домены
2. Найди подходящий `.ru` домен
3. Зарегистрируй (от 199 ₽/год)
4. Подключи к хостингу или настрой A-запись на IP твоего VPS
5. Замени `YOUR_DOMAIN.ru` в `nginx/nginx.conf`

---

## Лицензия

MIT
# deploy test
