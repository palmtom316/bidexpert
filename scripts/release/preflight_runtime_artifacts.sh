#!/usr/bin/env sh
set -eu

if ! command -v git >/dev/null 2>&1; then
  echo "git is required" >&2
  exit 2
fi

status_output="$(git status --short --untracked-files=all)"
if [ -z "${status_output}" ]; then
  echo "OK: workspace is clean."
  exit 0
fi

forbidden_regex='(^|/)(backups/|data/workflow-runs/|data/exports/|data/tender-expert-lib/(01_raw|02_extracted|03_enriched|04_md|05_chunks|06_index|07_review|08_conversion_sessions|99_logs)/|.*\.db(\..*)?$|.*\.partial_[0-9]+$)'
violations="$(
  printf '%s\n' "${status_output}" \
    | awk '{print $2}' \
    | grep -E "${forbidden_regex}" \
    | grep -Ev '(^|/)\.gitkeep$' \
    || true
)"

if [ -n "${violations}" ]; then
  echo "Found forbidden runtime artifacts in git status:"
  printf '%s\n' "${violations}"
  echo "Please clean these files before release."
  exit 1
fi

echo "OK: no forbidden runtime artifacts detected."
