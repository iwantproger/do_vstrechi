.PHONY: up down restart logs ps build backup restore migrate migrate-all admin health cleanup ssl ssl-renew psql help
.PHONY: beta-up beta-down beta-restart beta-logs beta-ps beta-build beta-deploy beta-migrate beta-migrate-all beta-psql beta-health
.PHONY: status ssl-beta

# Короткая переменная для beta compose
BETA_COMPOSE = docker compose -f docker-compose.beta.yml --env-file .env.beta --project-name dovstrechi-beta

# ═══════════════════════════════════════════════════════════
# PROD
# ═══════════════════════════════════════════════════════════

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

# ═══════════════════════════════════════════════════════════
# BETA
# ═══════════════════════════════════════════════════════════

## Запустить beta-окружение
beta-up:
	$(BETA_COMPOSE) up -d

## Остановить beta-окружение
beta-down:
	$(BETA_COMPOSE) down

## Перезапустить beta (с ребилдом)
beta-restart:
	$(BETA_COMPOSE) down
	$(BETA_COMPOSE) build --no-cache
	$(BETA_COMPOSE) up -d

## Логи beta-сервисов
beta-logs:
	$(BETA_COMPOSE) logs -f

## Статус beta-контейнеров
beta-ps:
	$(BETA_COMPOSE) ps

## Пересобрать beta-образы
beta-build:
	$(BETA_COMPOSE) build --no-cache

## Деплой beta (pull dev + build + up)
beta-deploy:
	@echo "=== Updating beta worktree ==="
	cd /opt/dovstrechi && git fetch origin
	cd /opt/dovstrechi-beta && git reset --hard origin/dev
	@echo "=== Building and deploying beta ==="
	$(BETA_COMPOSE) build
	$(BETA_COMPOSE) up -d
	@echo "=== Reloading nginx ==="
	docker exec dovstrechi_nginx nginx -s reload
	@echo "✓ Beta deploy complete"
	$(BETA_COMPOSE) ps

## Применить миграцию в beta (make beta-migrate FILE=004_admin_tables.sql)
beta-migrate:
	docker exec -i dovstrechi_postgres_beta psql -U $${POSTGRES_USER:-dovstrechi} \
		-d $${POSTGRES_DB:-dovstrechi_beta} \
		-f /docker-entrypoint-initdb.d/migrations/$(FILE)
	@echo "✓ Beta migration $(FILE) applied"

## Применить все миграции в beta
beta-migrate-all:
	@for f in $$(ls /opt/dovstrechi-beta/database/migrations/*.sql 2>/dev/null | sort); do \
		echo "Applying $$(basename $$f) to beta..."; \
		docker exec -i dovstrechi_postgres_beta psql -U $${POSTGRES_USER:-dovstrechi} \
			-d $${POSTGRES_DB:-dovstrechi_beta} \
			-f /docker-entrypoint-initdb.d/migrations/$$(basename $$f); \
	done
	@echo "✓ All beta migrations applied"

## Открыть psql beta
beta-psql:
	docker exec -it dovstrechi_postgres_beta psql -U $${POSTGRES_USER:-dovstrechi} $${POSTGRES_DB:-dovstrechi_beta}

## Проверить здоровье beta
beta-health:
	@echo "=== Beta Backend ==="
	@curl -sf https://beta.dovstrechiapp.ru/health | python3 -m json.tool 2>/dev/null || echo "  ERR: Beta backend down"
	@echo "=== Beta Postgres ==="
	@docker exec dovstrechi_postgres_beta pg_isready -U $${POSTGRES_USER:-dovstrechi} 2>/dev/null && echo "  OK: Ready" || echo "  ERR: Not ready"

# ═══════════════════════════════════════════════════════════
# ОБЩИЕ
# ═══════════════════════════════════════════════════════════

## Статус обоих окружений
status:
	@echo "╔══════════════════════════════════════╗"
	@echo "║            PROD                      ║"
	@echo "╚══════════════════════════════════════╝"
	@docker compose ps
	@echo ""
	@echo "╔══════════════════════════════════════╗"
	@echo "║            BETA                      ║"
	@echo "╚══════════════════════════════════════╝"
	@$(BETA_COMPOSE) ps 2>/dev/null || echo "  Beta не запущена"

## Расширить SSL на beta домен
ssl-beta:
	docker compose run --rm certbot certonly --webroot \
		--webroot-path=/var/www/certbot \
		--expand \
		-d dovstrechiapp.ru \
		-d www.dovstrechiapp.ru \
		-d beta.dovstrechiapp.ru \
		--email YOUR_EMAIL@example.com \
		--agree-tos --no-eff-email
	docker compose exec nginx nginx -s reload
	@echo "✓ SSL expanded for beta.dovstrechiapp.ru"

help:
	@echo "Доступные команды:"
	@echo ""
	@echo "  PROD:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | grep -v beta | grep -v status | grep -v ssl-beta | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  make %-18s %s\n", $$1, $$2}'
	@echo ""
	@echo "  BETA:"
	@grep -E '^beta-[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  make %-18s %s\n", $$1, $$2}'
	@echo ""
	@echo "  ОБЩИЕ:"
	@echo "  make status            Статус обоих окружений"
	@echo "  make ssl-beta          Расширить SSL на beta домен"
