#!/usr/bin/env bash
# Run mail_summariser tests and ensure `modelito` dependency is installed.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_BIN="$(command -v python || true)"
if [ -z "$PYTHON_BIN" ]; then
  PYTHON_BIN=python
fi

echo "Ensuring modelito (v0.1.1) is installed (TestPyPI fallback)..."
"$PYTHON_BIN" -m pip install -U "modelito==0.1.1" --extra-index-url https://test.pypi.org/simple || true

echo "Running test suite..."
"$PYTHON_BIN" -m pytest -q
