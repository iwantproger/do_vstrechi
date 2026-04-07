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

Подробнее: [BETA_SETUP.md](BETA_SETUP.md)
