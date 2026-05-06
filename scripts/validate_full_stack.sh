#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

BACKEND_URL="http://127.0.0.1:8766"
WEB_URL="http://127.0.0.1:8000"

cleanup() {
  if [[ -n "${BACKEND_PID:-}" ]]; then
    kill "$BACKEND_PID" >/dev/null 2>&1 || true
  fi
  if [[ -n "${WEB_PID:-}" ]]; then
    kill "$WEB_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

./start_backend.sh --host 127.0.0.1 --port 8766 >/tmp/mail_summariser_backend.log 2>&1 &
BACKEND_PID=$!

for _ in {1..40}; do
  if curl -fsS "$BACKEND_URL/health" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

curl -fsS "$BACKEND_URL/health" >/dev/null
curl -fsS "$BACKEND_URL/runtime/status" >/dev/null
curl -fsS "$BACKEND_URL/models/options?provider=openai" >/dev/null
curl -fsS "$BACKEND_URL/models/catalog?limit=5" >/dev/null

backend/.venv/bin/python -m http.server 8000 --directory webapp >/tmp/mail_summariser_web.log 2>&1 &
WEB_PID=$!

for _ in {1..20}; do
  if curl -fsS "$WEB_URL" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

curl -fsS "$WEB_URL" >/dev/null

echo "Full-stack validation passed."
