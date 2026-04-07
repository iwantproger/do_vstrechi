# /db — Работа с базой данных

Выполни операции с PostgreSQL через Docker. Сервис называется `postgres`, контейнер — `dovstrechi_postgres`.

1. Проверь статус контейнера БД:
   ```
   docker compose ps postgres
   ```

2. Покажи список всех таблиц:
   ```
   docker compose exec postgres psql -U dovstrechi -d dovstrechi -c "\dt"
   ```

3. Проверь наличие миграций:
   ```
   ls -lt database/migrations/
   ```

4. Если нужно применить конкретную миграцию (передай имя файла):
   ```
   docker compose exec postgres psql -U dovstrechi -d dovstrechi -f /docker-entrypoint-initdb.d/migrations/<файл>
   ```
   Или через Makefile: `make migrate FILE=<имя>.sql`

5. Открыть psql-консоль интерактивно:
   ```
   make psql
   ```

6. Создать резервную копию:
   ```
   make backup
   ```

7. Выведи итог: статус БД, список таблиц, статус миграций.

**При любых операциях изменения данных — сначала спроси подтверждения.**

Таблицы проекта: `users`, `schedules`, `bookings`, `admin_sessions`, `admin_audit_log`, `app_events`, `admin_tasks`.
View: `bookings_detail`.
