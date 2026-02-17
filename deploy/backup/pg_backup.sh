#!/usr/bin/env sh
set -eu

ts="$(date +%Y%m%d-%H%M%S)"
backup_dir="${BACKUP_DIR:-/backups}"
db_host="${DB_HOST:-postgres}"
db_port="${DB_PORT:-5432}"
db_name="${DB_NAME:-bidexpert}"
db_user="${DB_USER:-bidexpert}"
db_password="${DB_PASSWORD:-bidexpert}"

mkdir -p "${backup_dir}"
export PGPASSWORD="${db_password}"

output_file="${backup_dir}/postgres-${db_name}-${ts}.dump"
pg_dump -h "${db_host}" -p "${db_port}" -U "${db_user}" -d "${db_name}" -Fc -f "${output_file}"

echo "created ${output_file}"

