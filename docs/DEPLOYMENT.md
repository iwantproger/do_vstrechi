# Правила деплоя «До встречи»

> **ОБЯЗАТЕЛЬНО К ПРОЧТЕНИЮ** перед любым деплоем.

## Главное правило

**Beta-first. Всегда.**

| Действие | Что делать | Куда попадёт |
|----------|-----------|--------------|
| Обычная работа | `git push origin dev` | beta.dovstrechiapp.ru |
| Срочный хотфикс | `git push origin dev` | beta.dovstrechiapp.ru |
| Деплой в прод | Специальная процедура (см. ниже) | dovstrechiapp.ru |

**В production без явного запроса и подтверждения — НЕЛЬЗЯ.**

---

## Окружения

| Параметр | Beta | Production |
|----------|------|------------|
| Домен | beta.dovstrechiapp.ru | dovstrechiapp.ru |
| Ветка | `dev` | `main` |
| Бот | @beta_do_vstrechi_bot | @do_vstrechi_bot |
| БД | dovstrechi_beta | dovstrechi |
| Путь на VPS | /opt/dovstrechi-beta (worktree) | /opt/dovstrechi |
| Деплой | Автоматически при push в `dev` | Только через Deploy-to-Prod процедуру |
| CI/CD workflow | `deploy-beta.yml` | `deploy-prod.yml` |

---

## Workflow разработки

```
1. Работаешь в ветке dev (или feature/* → merge в dev)
2. git push origin dev
   → GitHub Actions автоматически деплоит на beta
   → Проверяешь на beta.dovstrechiapp.ru

3. Когда всё готово к релизу:
   → Пишешь "deploy to production" / "задеплой в прод"
   → Проходишь все этапы подтверждения
   → Создаётся PR dev → main, changelog, health-checks, деплой
```

---

## Deploy to Production: как запустить

Напиши в Claude Code:

```
deploy to production
```

или

```
задеплой в прод
```

**Что произойдёт:**
1. Покажет все изменения с последнего прод-деплоя (`git diff main..dev`)
2. Сгенерирует changelog
3. Спросит подтверждение — **дважды**
4. Проверит что beta healthy
5. Создаст PR `dev` → `main`
6. Задеплоит на prod
7. Health-check prod
8. Обновит CHANGELOG.md

---

## Частые ошибки

**`git push origin main` напрямую** — ЗАПРЕЩЕНО.
Используй процедуру Deploy to Production.

**`make deploy` без подтверждения** — защищён.
Команда потребует ввести слово `production` и проверит здоровье beta.

**Деплой в прод непроверенного кода** — ЗАПРЕЩЕНО.
Код должен побывать на beta минимум 1 раз.

---

## Ветки

| Ветка | Назначение | Деплой |
|-------|-----------|--------|
| `main` | Production-ready код | dovstrechiapp.ru |
| `dev` | Текущая разработка | beta.dovstrechiapp.ru |
| `feature/*` | Новые фичи | merge в `dev` → beta |
| `hotfix/*` | Срочные фиксы | merge в `dev` → beta → prod |

---

## Команды

| Команда | Описание |
|---------|----------|
| `make beta-up` | Запустить beta |
| `make beta-deploy` | Pull dev + build + deploy на beta |
| `make beta-health` | Health-check beta |
| `make deploy` | Деплой в prod (с подтверждением) |
| `make status` | Статус обоих окружений |
| `make backup` | Дамп prod + beta → `/opt/dovstrechi/backups/` (custom format) |
| `make restore-prod FILE=...` | Восстановить prod из custom-format дампа |
| `make restore-beta FILE=...` | Восстановить beta из custom-format дампа |

Подробнее: [BETA_SETUP.md](BETA_SETUP.md)

---

## Cron-задачи на VPS

Все cron-задачи прописаны в `crontab -l` у root на сервере.

| Расписание | Скрипт | Описание |
|-----------|--------|----------|
| `*/5 * * * *` | `scripts/healthcheck.sh` | Мониторинг prod + beta, Telegram-алерт при HTTP != 200 |
| `0 3 * * *` | `scripts/backup.sh` | pg_dump prod + beta, хранение 14 дней |
| `0 3 * * *` | `make ssl-renew` (рекомендуется) | Обновление SSL-сертификата Let's Encrypt |

**Логи:**
- Healthcheck: `/var/log/dovstrechi-health.log` (ротация до 1000 строк)
- Backup: `/var/log/dovstrechi-backup.log`

**Переменные окружения для healthcheck:**
- `ALERT_BOT_TOKEN` — токен бота для Telegram-алертов (можно тот же что `BOT_TOKEN`)
- `ADMIN_CHAT_ID` — Telegram chat ID для получения алертов (default: 5109612976)
