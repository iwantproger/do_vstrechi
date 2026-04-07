# Первый запуск beta-окружения на VPS

## Архитектура

```
/opt/dovstrechi/            ← main ветка (PROD, всегда)
/opt/dovstrechi-beta/       ← git worktree на dev ветке (BETA)
```

- **Prod** и **beta** работают одновременно на одном сервере
- Один nginx обслуживает оба домена: `dovstrechiapp.ru` и `beta.dovstrechiapp.ru`
- Отдельные БД: `dovstrechi` (prod) и `dovstrechi_beta` (beta)
- Отдельные Telegram боты (разные BOT_TOKEN)
- Общая Docker network `dovstrechi_shared` связывает nginx с beta backend

## Предусловия

- Prod (`dovstrechiapp.ru`) уже работает, `.env` настроен
- Есть SSH-доступ к VPS

## Шаг 1: DNS

Добавь A-запись в DNS:

```
beta.dovstrechiapp.ru → 109.73.192.69
```

Проверь:
```bash
dig beta.dovstrechiapp.ru +short
# Должен вернуть 109.73.192.69
```

## Шаг 2: Создай beta-бота в Telegram

1. Открой [@BotFather](https://t.me/BotFather)
2. `/newbot` → назови, например, `do_vstrechi_beta_bot`
3. Сохрани полученный `BOT_TOKEN`
4. `/setdomain` → выбери beta-бота → введи `beta.dovstrechiapp.ru`
5. `/setmenubutton` → выбери beta-бота → укажи URL `https://beta.dovstrechiapp.ru`

## Шаг 3: Настрой .env.beta на VPS

```bash
ssh root@109.73.192.69
cd /opt/dovstrechi

cp .env.beta.example .env.beta
nano .env.beta
```

Заполни обязательные переменные:
- `BOT_TOKEN` — токен beta-бота из Шага 2
- `POSTGRES_PASSWORD` — новый пароль (не такой как в prod!)
- `SECRET_KEY` — `python3 -c "import secrets; print(secrets.token_hex(64))"`
- `INTERNAL_API_KEY` — `python3 -c "import secrets; print(secrets.token_hex(32))"`
- `ADMIN_TELEGRAM_ID` — твой Telegram ID
- `ANONYMIZE_SALT` — `python3 -c "import secrets; print(secrets.token_hex(16))"`

## Шаг 4: SSL-сертификат

Расшири существующий сертификат чтобы включить beta домен:

```bash
make ssl-beta
```

Или вручную:
```bash
docker compose run --rm certbot certonly --webroot \
    --webroot-path=/var/www/certbot \
    --expand \
    -d dovstrechiapp.ru \
    -d www.dovstrechiapp.ru \
    -d beta.dovstrechiapp.ru \
    --email admin@dovstrechiapp.ru \
    --agree-tos --no-eff-email

docker compose exec nginx nginx -s reload
```

## Шаг 5: Создай shared network и worktree

```bash
# Docker network для связи nginx ↔ beta backend
docker network create dovstrechi_shared

# Git worktree — отдельная директория с dev веткой
cd /opt/dovstrechi
git fetch origin
git worktree add /opt/dovstrechi-beta dev
```

## Шаг 6: Перезапусти prod (подхватит shared network)

```bash
docker compose up -d
```

## Шаг 7: Запусти beta

```bash
make beta-up
```

## Шаг 8: Проверь

```bash
# Статус обоих окружений
make status

# Health check prod
curl -sf https://dovstrechiapp.ru/health | python3 -m json.tool

# Health check beta
curl -sf https://beta.dovstrechiapp.ru/health | python3 -m json.tool

# Проверь что БД разные
docker exec dovstrechi_postgres psql -U dovstrechi -c "\l" | grep dovstrechi
```

## Повседневные команды

| Команда | Описание |
|---------|----------|
| `make beta-up` | Запустить beta |
| `make beta-down` | Остановить beta |
| `make beta-restart` | Перезапустить beta с ребилдом |
| `make beta-logs` | Логи beta |
| `make beta-ps` | Статус beta-контейнеров |
| `make beta-deploy` | Pull dev + build + deploy |
| `make beta-health` | Health check beta |
| `make beta-psql` | psql в beta БД |
| `make beta-migrate-all` | Применить миграции в beta |
| `make status` | Статус обоих окружений |

## CI/CD

- Push в `main` → автодеплой **prod** (`.github/workflows/deploy-prod.yml`)
- Push в `dev` → автодеплой **beta** (`.github/workflows/deploy-beta.yml`)

Beta deploy обновляет worktree (`git reset --hard origin/dev`), собирает образы и перезапускает beta-сервисы. Prod не затрагивается.

## Обновление worktree вручную

```bash
cd /opt/dovstrechi
git fetch origin
cd /opt/dovstrechi-beta
git reset --hard origin/dev
make beta-restart
```

## Удаление beta-окружения

```bash
make beta-down
cd /opt/dovstrechi
git worktree remove /opt/dovstrechi-beta
docker volume rm dovstrechi-beta_postgres_beta_data
```
