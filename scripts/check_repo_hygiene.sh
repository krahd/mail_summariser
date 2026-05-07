#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

bad_files=()

while IFS= read -r path; do
  [[ -e "$path" ]] || continue
  bad_files+=("$path")
done < <(
  git ls-files | grep -E '(^dist/|^release_artifacts/|\.egg-info/|/__pycache__/|\.pyc$|\.pyo$|^temp\.txt$|(^|/)\.env$|^backend/data/.*\.sqlite3|^docs/(MIGRATION_|CALIBRATION\.md|IMAP_TEST_PLAN\.md|TESTING_STRATEGY\.md))' || true
)

if ((${#bad_files[@]} > 0)); then
  echo "Repository hygiene check failed. Remove these tracked files:"
  for file in "${bad_files[@]}"; do
    echo "  - $file"
  done
  exit 1
fi

echo "Repository hygiene check passed."
