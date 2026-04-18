#!/usr/bin/env bash
# Run mail_summariser tests with the local `modelito-repo` package on PYTHONPATH.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
MODELITO_REPO="${ROOT_DIR}/../modelito-repo"

if [ ! -d "$MODELITO_REPO" ]; then
  echo "modelito-repo not found at $MODELITO_REPO"
  exit 2
fi

export PYTHONPATH="$MODELITO_REPO:$PYTHONPATH"
echo "PYTHONPATH set to: $PYTHONPATH"

pytest -q
