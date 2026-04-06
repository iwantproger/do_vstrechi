.PHONY: up down restart logs ps build backup restore migrate migrate-all admin health cleanup ssl ssl-renew psql help

## Запустить все сервисы
up:
	docker compose up -d

## Остановить все сервисы
down:
	docker compose down

## Перезапустить все (с ребилдом)
restart:
	docker compose down
	docker compose build --no-cache
	docker compose up -d

## Логи всех сервисов
logs:
	docker compose logs -f

## Логи отдельного сервиса (make logs-backend)
logs-%:
	docker compose logs -f $*

## Статус контейнеров
ps:
	docker compose ps

## Пересобрать образы
build:
	docker compose build --no-cache

## Дамп PostgreSQL (бэкап)
backup:
	docker compose exec postgres pg_dump -U $${POSTGRES_USER:-dovstrechi} $${POSTGRES_DB:-dovstrechi} \
		> backup_$$(date +%Y%m%d_%H%M%S).sql
	@echo "✓ Backup saved"

## Восстановление из дампа (make restore FILE=backup_xxx.sql)
restore:
	docker compose exec -T postgres psql -U $${POSTGRES_USER:-dovstrechi} $${POSTGRES_DB:-dovstrechi} < $(FILE)

## Применить миграцию (make migrate FILE=004_admin_tables.sql)
migrate:
	docker compose exec -T postgres psql -U $${POSTGRES_USER:-dovstrechi} \
		-d $${POSTGRES_DB:-dovstrechi} \
		-f /docker-entrypoint-initdb.d/migrations/$(FILE)
	@echo "✓ Migration $(FILE) applied"

## Применить все миграции по порядку
migrate-all:
	@for f in $$(ls database/migrations/*.sql | sort); do \
		echo "Applying $$f..."; \
		docker compose exec -T postgres psql -U $${POSTGRES_USER:-dovstrechi} \
			-d $${POSTGRES_DB:-dovstrechi} \
			-f /docker-entrypoint-initdb.d/migrations/$$(basename $$f); \
	done
	@echo "✓ All migrations applied"

## Открыть админку в браузере
admin:
	@echo "Opening https://dovstrechiapp.ru/admin/"
	@which xdg-open > /dev/null 2>&1 && xdg-open https://dovstrechiapp.ru/admin/ || \
		which open > /dev/null 2>&1 && open https://dovstrechiapp.ru/admin/ || \
		echo "Open https://dovstrechiapp.ru/admin/ in your browser"

## Проверить здоровье всех сервисов
health:
	@echo "=== Backend ==="
	@curl -sf http://localhost/health | python3 -m json.tool 2>/dev/null || echo "  ERR: Backend down"
	@echo "=== Admin ==="
	@curl -sf -o /dev/null -w "  HTTP %{http_code}\n" http://localhost/admin/ || echo "  ERR: Admin unreachable"
	@echo "=== Postgres ==="
	@docker compose exec postgres pg_isready -U $${POSTGRES_USER:-dovstrechi} 2>/dev/null && echo "  OK: Ready" || echo "  ERR: Not ready"

## Очистить старые Docker образы и тома
cleanup:
	docker image prune -f
	docker volume prune -f
	@echo "✓ Cleanup done"

## Получить SSL сертификат (первый раз)
ssl:
	@echo "Запускаем certbot..."
	docker compose run --rm certbot certonly --webroot \
		--webroot-path=/var/www/certbot \
		--email YOUR_EMAIL@example.com \
		--agree-tos --no-eff-email \
		-d YOUR_DOMAIN.ru -d www.YOUR_DOMAIN.ru

## Обновить SSL (cron: 0 3 * * * cd /opt/dovstrechi && make ssl-renew)
ssl-renew:
	docker compose run --rm certbot renew --quiet
	docker compose exec nginx nginx -s reload

## Открыть psql
psql:
	docker compose exec postgres psql -U $${POSTGRES_USER:-dovstrechi} $${POSTGRES_DB:-dovstrechi}

help:
	@echo "Доступные команды:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  make %-15s %s\n", $$1, $$2}'
