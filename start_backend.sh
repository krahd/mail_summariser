#!/bin/bash
set -euo pipefail

cd ./backend

REINSTALL=false
HOST="127.0.0.1"
PORT="8766"

while [[ $# -gt 0 ]]; do
    case "$1" in
        -R|--reinstall)
            REINSTALL=true
            shift
            ;;
        --host)
            [[ $# -ge 2 ]] || { echo "Error: --host requires a value"; exit 1; }
            HOST="$2"
            shift 2
            ;;
        --host=*)
            HOST="${1#*=}"
            shift
            ;;
        --port)
            [[ $# -ge 2 ]] || { echo "Error: --port requires a value"; exit 1; }
            PORT="$2"
            shift 2
            ;;
        --port=*)
            PORT="${1#*=}"
            shift
            ;;
        *)
            echo "Error: unknown argument: $1"
            exit 1
            ;;
    esac
done

# Recreate if requested or venv is missing/broken
if [ "$REINSTALL" = true ] || [ ! -x .venv/bin/python ]; then
    echo "Creating/reinstalling virtual environment..."
    rm -rf .venv
    python3 -m venv .venv
    .venv/bin/python -m pip install -U pip
    .venv/bin/python -m pip install -r requirements.txt 2>/dev/null || true
    .venv/bin/python -m pip install fastapi uvicorn
fi

source .venv/bin/activate

# Use module form and ensure the repository root is on PYTHONPATH so the
# top-level `backend` package can be imported even when the script cd's into
# the `backend` directory.
PYTHONPATH="$(pwd)/.." python -m uvicorn backend.app:app --reload --host "$HOST" --port "$PORT"