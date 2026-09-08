#!/usr/bin/env bash
#
# Nightly Postgres backup for the production database. Dumps to a
# local directory, optionally uploads to S3-compatible storage, and
# prunes local backups older than BACKUP_RETENTION_DAYS.
#
# Usage (run from the project root, next to docker-compose.prod.yml):
#   ./scripts/backup_db.sh
#
# Cron example (2 AM daily; add via `crontab -e` on the server):
#   0 2 * * * cd /path/to/universal-ai-agent && ./scripts/backup_db.sh >> /var/log/uai-backup.log 2>&1
#
# Restore from a dump:
#   gunzip -c backups/app_2026-08-30_020000.sql.gz | \
#     docker compose -f docker-compose.prod.yml exec -T postgres \
#     psql -U app -d app

set -euo pipefail

cd "$(dirname "$0")/.."

BACKUP_DIR="${BACKUP_DIR:-./backups}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"

# Reads POSTGRES_USER / POSTGRES_DB from .env if present, same
# defaults as docker-compose.prod.yml.
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

POSTGRES_USER="${POSTGRES_USER:-app}"
POSTGRES_DB="${POSTGRES_DB:-app}"

mkdir -p "$BACKUP_DIR"

timestamp="$(date +%Y-%m-%d_%H%M%S)"
dump_file="$BACKUP_DIR/${POSTGRES_DB}_${timestamp}.sql.gz"

echo "[$(date -Is)] dumping ${POSTGRES_DB} -> ${dump_file}"

docker compose -f "$COMPOSE_FILE" exec -T postgres \
  pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --no-privileges \
  | gzip > "$dump_file"

echo "[$(date -Is)] dump complete: $(du -h "$dump_file" | cut -f1)"

# --- Optional: upload to S3-compatible storage -----------------------------
# Set these three (plus AWS creds via env or ~/.aws/credentials) to
# also ship backups off-box. Uses the AWS CLI so it works with real
# S3, R2, Spaces, B2, or MinIO via --endpoint-url.
if [ -n "${BACKUP_S3_BUCKET:-}" ]; then
  echo "[$(date -Is)] uploading to s3://${BACKUP_S3_BUCKET}/"
  aws s3 cp "$dump_file" "s3://${BACKUP_S3_BUCKET}/db-backups/$(basename "$dump_file")" \
    ${BACKUP_S3_ENDPOINT_URL:+--endpoint-url "$BACKUP_S3_ENDPOINT_URL"}
fi

# --- Prune old local dumps ---------------------------------------------------
echo "[$(date -Is)] pruning local dumps older than ${RETENTION_DAYS} days"
find "$BACKUP_DIR" -name "${POSTGRES_DB}_*.sql.gz" -mtime "+${RETENTION_DAYS}" -delete

echo "[$(date -Is)] done"
