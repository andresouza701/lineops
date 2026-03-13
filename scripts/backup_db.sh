#!/usr/bin/env bash
# Backup diário do PostgreSQL — mantém os últimos 7 dias
# Agendar no crontab do servidor:
#   0 2 * * * /opt/app/src/lineops/scripts/backup_db.sh >> /var/log/lineops_backup.log 2>&1

set -euo pipefail

BACKUP_DIR="/opt/backups/lineops"
COMPOSE_FILE="/opt/app/src/lineops/docker-compose.prod.yml"
ENV_FILE="/opt/app/src/lineops/.env.prod"
CONTAINER="lineops-db-prod"
RETENTION_DAYS=7

mkdir -p "$BACKUP_DIR"

# Carrega variáveis do .env.prod
set -a
# shellcheck source=/dev/null
source "$ENV_FILE"
set +a

FILENAME="lineops_$(date +%Y%m%d_%H%M%S).sql.gz"
DEST="$BACKUP_DIR/$FILENAME"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Iniciando backup → $DEST"

docker exec "$CONTAINER" \
    pg_dump -U "$DB_USER" "$DB_NAME" | gzip > "$DEST"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Backup concluído: $(du -sh "$DEST" | cut -f1)"

# Remove backups mais antigos que RETENTION_DAYS
find "$BACKUP_DIR" -name "lineops_*.sql.gz" -mtime +"$RETENTION_DAYS" -delete
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Limpeza: backups com mais de ${RETENTION_DAYS} dias removidos"
