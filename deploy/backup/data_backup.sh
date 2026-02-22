#!/usr/bin/env sh
set -eu

ts="$(date +%Y%m%d-%H%M%S)"
backup_dir="${BACKUP_DIR:-/backups}"
data_dir="${DATA_DIR:-/data}"

if [ ! -d "${data_dir}" ]; then
  echo "data directory not found: ${data_dir}" >&2
  exit 1
fi

mkdir -p "${backup_dir}"
output_file="${backup_dir}/data-artifacts-${ts}.tar.gz"
tar -czf "${output_file}" -C "${data_dir}" .

echo "created ${output_file}"
