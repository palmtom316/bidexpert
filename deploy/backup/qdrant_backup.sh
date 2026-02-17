#!/usr/bin/env sh
set -eu

ts="$(date +%Y%m%d-%H%M%S)"
backup_dir="${BACKUP_DIR:-/backups}"
qdrant_storage_dir="${QDRANT_STORAGE_DIR:-/qdrant/storage}"

mkdir -p "${backup_dir}"

output_file="${backup_dir}/qdrant-storage-${ts}.tar.gz"
tar -czf "${output_file}" -C "${qdrant_storage_dir}" .

echo "created ${output_file}"

