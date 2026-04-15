#!/bin/bash
# Health check для prod и beta
# Запуск через cron каждые 5 минут

PROD_URL="https://dovstrechiapp.ru/health"
BETA_URL="https://beta.dovstrechiapp.ru/health"
BOT_TOKEN="${ALERT_BOT_TOKEN:-}"    # токен бота для алертов (основной бот или support)
ADMIN_CHAT_ID="${ADMIN_CHAT_ID:-5109612976}"
LOG_FILE="/var/log/dovstrechi-health.log"

check_health() {
    local name="$1"
    local url="$2"

    status=$(curl -sf -o /dev/null -w "%{http_code}" --max-time 10 "$url" 2>/dev/null)

    if [ "$status" = "200" ]; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') [OK] $name — $status" >> "$LOG_FILE"
        return 0
    else
        echo "$(date '+%Y-%m-%d %H:%M:%S') [FAIL] $name — $status" >> "$LOG_FILE"

        # Отправить алерт в Telegram
        if [ -n "$BOT_TOKEN" ]; then
            curl -sf "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
                -d "chat_id=${ADMIN_CHAT_ID}" \
                -d "text=🚨 ALERT: ${name} is DOWN (HTTP ${status:-timeout})%0A${url}" \
                -d "parse_mode=HTML" > /dev/null 2>&1
        fi
        return 1
    fi
}

check_health "PROD" "$PROD_URL"
check_health "BETA" "$BETA_URL"

# Ротация лога (хранить ~1000 последних строк)
if [ -f "$LOG_FILE" ]; then
    tail -1000 "$LOG_FILE" > "${LOG_FILE}.tmp" && mv "${LOG_FILE}.tmp" "$LOG_FILE"
fi
