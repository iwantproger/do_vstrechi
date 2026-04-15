#!/bin/bash
# Автоматический бэкап PostgreSQL (prod + beta)
# Запуск: ежедневно в 03:00 через cron

BACKUP_DIR="/opt/dovstrechi/backups"
RETENTION_DAYS=14
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p "$BACKUP_DIR"

# Prod backup
echo "[$(date)] Starting PROD backup..."
docker exec dovstrechi_postgres pg_dump -U dovstrechi -d dovstrechi --format=custom \
    > "${BACKUP_DIR}/prod_${DATE}.dump" 2>/dev/null

if [ $? -eq 0 ]; then
    SIZE=$(du -h "${BACKUP_DIR}/prod_${DATE}.dump" | cut -f1)
    echo "[$(date)] PROD backup OK: ${SIZE}"
else
    echo "[$(date)] PROD backup FAILED"
fi

# Beta backup
docker exec dovstrechi_postgres_beta pg_dump -U dovstrechi -d dovstrechi_beta --format=custom \
    > "${BACKUP_DIR}/beta_${DATE}.dump" 2>/dev/null

if [ $? -eq 0 ]; then
    SIZE=$(du -h "${BACKUP_DIR}/beta_${DATE}.dump" | cut -f1)
    echo "[$(date)] BETA backup OK: ${SIZE}"
else
    echo "[$(date)] BETA backup FAILED (may not be running)"
fi

# Очистка старых бэкапов
find "$BACKUP_DIR" -name "*.dump" -mtime +${RETENTION_DAYS} -delete
echo "[$(date)] Cleaned backups older than ${RETENTION_DAYS} days"

# Статистика
COUNT=$(ls -1 "${BACKUP_DIR}"/*.dump 2>/dev/null | wc -l)
TOTAL_SIZE=$(du -sh "$BACKUP_DIR" 2>/dev/null | cut -f1)
echo "[$(date)] Total backups: ${COUNT}, size: ${TOTAL_SIZE}"
