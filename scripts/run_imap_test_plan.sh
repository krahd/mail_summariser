#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
PORT="${PORT:-8876}"
TMP_DIR="$(mktemp -d)"
SERVER_PID=""

cleanup() {
  if [[ -n "$SERVER_PID" ]]; then
    kill "$SERVER_PID" >/dev/null 2>&1 || true
    wait "$SERVER_PID" >/dev/null 2>&1 || true
  fi
  rm -rf "$TMP_DIR"
}

trap cleanup EXIT

echo "[1/4] Automated backend and UI contract tests"
cd "$ROOT_DIR"
python3 -m unittest discover -s tests -v

echo "[2/4] Backend compile check"
python3 -m compileall backend >/dev/null

echo "[3/4] HTTP smoke test against a fresh backend"
MAIL_SUMMARISER_DATA_DIR="$TMP_DIR/data" \
  "$BACKEND_DIR/.venv/bin/python" -m uvicorn app:app --app-dir "$BACKEND_DIR" --host 127.0.0.1 --port "$PORT" \
  >"$TMP_DIR/backend.log" 2>&1 &
SERVER_PID="$!"

for _ in {1..30}; do
  if curl -fsS "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

curl -fsS "http://127.0.0.1:$PORT/health" >/dev/null
"$ROOT_DIR/scripts/smoke_test_backend.sh" "http://127.0.0.1:$PORT"

kill "$SERVER_PID" >/dev/null 2>&1 || true
wait "$SERVER_PID" >/dev/null 2>&1 || true
SERVER_PID=""

echo "[4/4] macOS Swift typecheck"
SDK_PATH="$(xcrun --show-sdk-path --sdk macosx)"
xcrun swiftc -typecheck -module-cache-path /tmp/mail-summariser-swift-cache -sdk "$SDK_PATH" "$ROOT_DIR"/macos-app/*.swift

echo "IMAP test plan passed"
