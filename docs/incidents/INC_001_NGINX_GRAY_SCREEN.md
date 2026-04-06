# INC-001: Серый экран Mini App — nginx не запускается

**Дата:** 2026-04-06
**Критичность:** P0 (полная недоступность приложения)
**Время простоя:** ~9 часов (с момента деплоя коммита `6eb6181` до фикса `c40bf53`)
**Затронуто:** все пользователи — Mini App, API, админка недоступны

---

## Симптомы

- Telegram Mini App показывает серый/пустой экран
- `https://dovstrechiapp.ru/` в браузере — `ERR_CONNECTION_CLOSED`
- Backend, bot, postgres работают нормально
- Контейнер `dovstrechi_nginx` отсутствует в `docker compose ps`

## Корневая причина

В коммите `6eb6181` (админ-панель Фаза 1) в `docker-compose.yml` был добавлен вложенный bind mount:

```yaml
volumes:
  - ./frontend:/usr/share/nginx/html:ro        # строка 94 — родительский mount
  - ./admin:/usr/share/nginx/html/admin:ro      # строка 95 — вложенный mount
```

**Проблема:** Docker не может создать точку монтирования (`/usr/share/nginx/html/admin`) внутри файловой системы, которая уже примонтирована как **read-only** (`:ro`). При попытке запуска nginx Docker выдавал:

```
OCI runtime create failed: runc create failed: unable to start container process:
error during container init: error mounting "/opt/dovstrechi/admin" to rootfs at
"/usr/share/nginx/html/admin": create mountpoint for /usr/share/nginx/html/admin mount:
make mountpoint "/usr/share/nginx/html/admin": mkdirat .../overlayfs/...: read-only file system
```

Nginx не запускался → порты 80/443 не слушались → сервер не отвечал вообще.

### Почему не поймали раньше

1. **Нет smoke test после деплоя** — CI/CD делает `docker compose up -d`, но не проверяет что все контейнеры живы
2. **Нет мониторинга** — нет health-check пинга или алерта при падении контейнера
3. **docker compose up -d** не выводит ошибку при запуске в фоне — exit code 0, даже если один контейнер не запустился

## Решение

### Инфраструктура (docker-compose.yml)

Убран `:ro` с родительского frontend-маунта:

```yaml
# Было (сломано):
- ./frontend:/usr/share/nginx/html:ro
- ./admin:/usr/share/nginx/html/admin:ro

# Стало (работает):
- ./frontend:/usr/share/nginx/html          # без :ro — Docker может создать mountpoint для admin
- ./admin:/usr/share/nginx/html/admin:ro
```

**Почему не `:ro`:** при вложенном bind mount Docker нужно создать директорию-mountpoint внутри родительского маунта. Если родительский маунт read-only, `mkdirat` падает. Убирая `:ro` с frontend, мы позволяем Docker создать точку монтирования, при этом admin остаётся read-only.

**Альтернативный вариант (не применён):** копировать admin в Dockerfile nginx вместо bind mount. Более надёжно, но медленнее при разработке.

### Фронтенд (frontend/index.html) — защита от серого экрана

Добавлены три слоя защиты, чтобы приложение не зависало на прозрачности `opacity:0` при любом JS-краше:

1. **CSS safety net** — `@keyframes _force-show` автоматически показывает `#app` через 5 секунд, даже если JavaScript полностью мёртв
2. **Global error handlers** — `window.error` и `unhandledrejection` добавляют класс `.ready` при любом необработанном исключении
3. **try/catch на TG SDK init** — весь блок инициализации Telegram SDK обёрнут в try/catch, каждый отдельный вызов (`enableClosingConfirmation`, `requestFullscreen`, `adaptTgInsets`) тоже

## Правила на будущее

### Docker volume mounts

> **ПРАВИЛО:** Никогда не использовать `:ro` на родительском bind mount, если внутрь него вложен другой bind mount. Docker не сможет создать точку монтирования.

Безопасные паттерны:
```yaml
# OK — родитель без :ro, дочерний с :ro
- ./frontend:/usr/share/nginx/html
- ./admin:/usr/share/nginx/html/admin:ro

# OK — плоские маунты (не вложенные)
- ./frontend:/usr/share/nginx/html/frontend:ro
- ./admin:/usr/share/nginx/html/admin:ro

# OK — копирование в Dockerfile вместо bind mount
COPY frontend/ /usr/share/nginx/html/
COPY admin/ /usr/share/nginx/html/admin/
```

Опасный паттерн:
```yaml
# СЛОМАЕТ nginx — :ro на родителе блокирует mountpoint для admin
- ./frontend:/usr/share/nginx/html:ro
- ./admin:/usr/share/nginx/html/admin:ro
```

### CI/CD smoke test

После `docker compose up -d` нужно проверять:
```bash
# Все контейнеры Up
docker compose ps --format json | jq -e '.[] | select(.State != "running")' && echo "FAIL" && exit 1

# HTTP-ответ 200
curl -sf -o /dev/null https://dovstrechiapp.ru/health || (echo "Health check failed" && exit 1)
```

### Frontend resilience

Любой код инициализации, который блокирует видимость приложения (управляет `opacity`, `display`, классом `.ready`), должен:
1. Быть обёрнут в try/catch
2. Иметь CSS fallback на случай полного краша JS
3. Иметь global error handler, который показывает приложение

## Файлы затронутые фиксом

| Файл | Изменение |
|------|-----------|
| `docker-compose.yml:94` | Убран `:ro` с frontend bind mount |
| `frontend/index.html:74-75` | CSS `@keyframes _force-show` (5s fallback) |
| `frontend/index.html:1364` | Global error/unhandledrejection handlers |
| `frontend/index.html:1455` | TG SDK init обёрнут в try/catch |

## Коммиты

- `6eb6181` — коммит, вызвавший инцидент (добавление admin bind mount с `:ro` на родителе)
- `c40bf53` — коммит с фиксом
