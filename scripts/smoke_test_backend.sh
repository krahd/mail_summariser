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

echo "[1/14] Health check"
health_json="$(request GET /health)"
echo "$health_json" | assert_json_has_status_ok

echo "[2/14] Read settings"
settings_json="$(request GET /settings)"
python3 -c 'import json,sys; obj=json.loads(sys.stdin.read()); required=["dummyMode","imapHost","imapPort","imapUseSSL","imapPassword","smtpHost","smtpPort","smtpUseSSL","smtpPassword","username","recipientEmail","summarisedTag","llmProvider","openaiApiKey","anthropicApiKey","ollamaHost","ollamaAutoStart","ollamaStartOnStartup","ollamaStopOnExit","ollamaSystemMessage","openaiSystemMessage","anthropicSystemMessage","modelName","backendBaseURL"]; missing=[k for k in required if k not in obj]; assert not missing, f"missing settings keys: {missing}"' <<< "$settings_json"

echo "[3/15] System message defaults"
defaults_json="$(request GET /settings/system-message-defaults)"
python3 -c 'import json,sys; obj=json.loads(sys.stdin.read()); required=["ollamaSystemMessage","openaiSystemMessage","anthropicSystemMessage"]; missing=[k for k in required if k not in obj]; assert not missing, f"missing default system message keys: {missing}"' <<< "$defaults_json"

echo "[4/15] Save settings"
request POST /settings "$settings_json" >/dev/null

echo "[5/15] Runtime status"
runtime_json="$(request GET /runtime/status)"
python3 -c 'import json,sys; obj=json.loads(sys.stdin.read()); assert "backend" in obj and "ollama" in obj, f"unexpected runtime payload: {obj}"; assert "canShutdown" in obj["backend"], f"missing backend.canShutdown: {obj}"; assert "startupAction" in obj["ollama"], f"missing ollama.startupAction: {obj}"' <<< "$runtime_json"

echo "[6/15] Connection test"
connection_json="$(request POST /settings/test-connection "$settings_json")"
python3 -c 'import json,sys; obj=json.loads(sys.stdin.read()); assert obj.get("status") == "ok", f"unexpected connection status: {obj}"; assert obj.get("mode") == "dummy", f"expected dummy mode but got {obj.get('"'"'mode'"'"')}"' <<< "$connection_json"

echo "[7/15] Create summary"
summary_payload='{"criteria":{"keyword":"","rawSearch":"","sender":"","recipient":"","unreadOnly":true,"readOnly":false,"replied":null,"tag":"","useAnd":true},"summaryLength":15}'
summary_json="$(request POST /summaries "$summary_payload")"
job_id="$(echo "$summary_json" | extract_json_field jobId)"
if [[ -z "$job_id" ]]; then
  echo "No jobId returned from /summaries"
  exit 1
fi

echo "[8/15] Mark read action"
request POST /actions/mark-read "{\"jobId\":\"$job_id\"}" >/dev/null

echo "[9/15] Tag summarised action"
request POST /actions/tag-summarised "{\"jobId\":\"$job_id\"}" >/dev/null

echo "[10/15] Undo action"
request POST /actions/undo >/dev/null

echo "[11/15] Logs available"
logs_json="$(request GET /logs)"
python3 -c 'import json,sys; logs=json.loads(sys.stdin.read()); job_id=sys.argv[1]; assert isinstance(logs, list), "logs response is not a list"; mine=[item for item in logs if item.get("job_id")==job_id]; assert mine, f"no logs found for job {job_id}"; assert any(item.get("action")=="mark_read" and item.get("undoable") for item in mine), "mark_read should still be undoable after one undo"; assert any(item.get("action")=="tag_summarised" and item.get("undo_status")=="final" for item in mine), "tag_summarised should become final after undo"' "$job_id" <<< "$logs_json"

echo "[12/15] Model options endpoint"
model_options_json="$(request GET '/models/options?provider=openai')"
python3 -c 'import json,sys; obj=json.loads(sys.stdin.read()); assert obj.get("provider") == "openai", f"unexpected provider: {obj.get('"'"'provider'"'"')}"; assert isinstance(obj.get("models"), list), "models is not a list"' <<< "$model_options_json"

echo "[13/15] Model catalog endpoint"
model_catalog_json="$(request GET '/models/catalog?query=&limit=20')"
python3 -c 'import json,sys; obj=json.loads(sys.stdin.read()); assert obj.get("provider") == "ollama", f"unexpected provider: {obj.get('"'"'provider'"'"')}"; assert isinstance(obj.get("models"), list), "catalog models is not a list"' <<< "$model_catalog_json"

echo "[14/15] Fake mail status endpoint"
fake_mail_json="$(request GET /dev/fake-mail/status)"
python3 -c 'import json,sys; obj=json.loads(sys.stdin.read()); assert "enabled" in obj and "running" in obj, f"unexpected fake mail payload: {obj}"' <<< "$fake_mail_json"

echo "[15/15] Database reset endpoint"
reset_json="$(request POST /admin/database/reset '{"confirmation":"RESET DATABASE"}')"
python3 -c 'import json,sys; obj=json.loads(sys.stdin.read()); assert obj.get("status") == "ok", f"unexpected reset status: {obj}"; assert "removed" in obj and "settings" in obj, f"unexpected reset payload: {obj}"' <<< "$reset_json"

echo "Smoke test passed for $BASE_URL (jobId=$job_id)"
