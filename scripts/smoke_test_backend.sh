#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-http://127.0.0.1:8766}"
API_KEY="${API_KEY:-}"
API_KEY_HEADER="${API_KEY_HEADER:-X-API-Key}"

request() {
  local method="$1"
  local path="$2"
  local body="${3:-}"
  local tmp_file
  tmp_file="$(mktemp)"

  local status
  if [[ -n "$body" && -n "$API_KEY" ]]; then
    status="$(curl -sS -o "$tmp_file" -w "%{http_code}" -X "$method" -H "$API_KEY_HEADER: $API_KEY" -H "Content-Type: application/json" "$BASE_URL$path" --data "$body")"
  elif [[ -n "$body" ]]; then
    status="$(curl -sS -o "$tmp_file" -w "%{http_code}" -X "$method" -H "Content-Type: application/json" "$BASE_URL$path" --data "$body")"
  elif [[ -n "$API_KEY" ]]; then
    status="$(curl -sS -o "$tmp_file" -w "%{http_code}" -X "$method" -H "$API_KEY_HEADER: $API_KEY" "$BASE_URL$path")"
  else
    status="$(curl -sS -o "$tmp_file" -w "%{http_code}" -X "$method" "$BASE_URL$path")"
  fi

  if [[ "$status" -lt 200 || "$status" -ge 300 ]]; then
    echo "Request failed: $method $path (HTTP $status)"
    echo "Response:"
    cat "$tmp_file"
    rm -f "$tmp_file"
    exit 1
  fi

  cat "$tmp_file"
  rm -f "$tmp_file"
}

extract_json_field() {
  local field="$1"
  python3 -c 'import json,sys; obj=json.loads(sys.stdin.read()); print(obj.get(sys.argv[1], ""))' "$field"
}

assert_json_has_status_ok() {
  python3 -c 'import json,sys; obj=json.loads(sys.stdin.read()); assert obj.get("status") == "ok", f"unexpected status: {obj}"'
}

echo "[1/10] Health check"
health_json="$(request GET /health)"
echo "$health_json" | assert_json_has_status_ok

echo "[2/10] Read settings"
settings_json="$(request GET /settings)"
python3 -c 'import json,sys; obj=json.loads(sys.stdin.read()); required=["imapHost","imapPort","smtpHost","smtpPort","username","recipientEmail","summarisedTag","llmProvider","openaiApiKey","anthropicApiKey","ollamaHost","ollamaAutoStart","modelName","backendBaseURL"]; missing=[k for k in required if k not in obj]; assert not missing, f"missing settings keys: {missing}"' <<< "$settings_json"

echo "[3/10] Save settings"
request POST /settings "$settings_json" >/dev/null

echo "[4/10] Create summary"
summary_payload='{"criteria":{"keyword":"","rawSearch":"","sender":"","recipient":"","unreadOnly":true,"readOnly":false,"replied":null,"tag":"","useAnd":true},"summaryLength":5}'
summary_json="$(request POST /summaries "$summary_payload")"
job_id="$(echo "$summary_json" | extract_json_field jobId)"
if [[ -z "$job_id" ]]; then
  echo "No jobId returned from /summaries"
  exit 1
fi

echo "[5/10] Mark read action"
request POST /actions/mark-read "{\"jobId\":\"$job_id\"}" >/dev/null

echo "[6/10] Tag summarised action"
request POST /actions/tag-summarised "{\"jobId\":\"$job_id\"}" >/dev/null

echo "[7/10] Undo action"
request POST /actions/undo >/dev/null

echo "[8/10] Logs available"
logs_json="$(request GET /logs)"
python3 -c 'import json,sys; obj=json.loads(sys.stdin.read()); assert isinstance(obj, list), "logs response is not a list"' <<< "$logs_json"

echo "[9/10] Model options endpoint"
model_options_json="$(request GET '/models/options?provider=openai')"
python3 -c 'import json,sys; obj=json.loads(sys.stdin.read()); assert obj.get("provider") == "openai", f"unexpected provider: {obj.get('"'"'provider'"'"')}"; assert isinstance(obj.get("models"), list), "models is not a list"' <<< "$model_options_json"

echo "[10/10] Model catalog endpoint"
model_catalog_json="$(request GET '/models/catalog?query=&limit=20')"
python3 -c 'import json,sys; obj=json.loads(sys.stdin.read()); assert obj.get("provider") == "ollama", f"unexpected provider: {obj.get('"'"'provider'"'"')}"; assert isinstance(obj.get("models"), list), "catalog models is not a list"' <<< "$model_catalog_json"

echo "Smoke test passed for $BASE_URL (jobId=$job_id)"
