.PHONY: up down restart logs ps build pull-db migrate ssl help

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
