#!/usr/bin/env bash
set -euo pipefail

# Test GitHub Actions workflows: dispatch safe, manually-dispatchable workflows
# and wait for their runs to complete (up to 5 minutes per run).

repo_info=$(gh repo view --json nameWithOwner,defaultBranchRef -q ".nameWithOwner + \" \" + .defaultBranchRef.name")
REPO=$(echo "$repo_info" | awk '{print $1}')
DEFAULT_BRANCH=$(echo "$repo_info" | awk '{print $2}')

echo "Repo: $REPO  Default branch: $DEFAULT_BRANCH"

tmp=$(mktemp)
gh workflow list --json id,name,path,state -L 200 > "$tmp" || true
count=$(jq length "$tmp")
if [ "$count" -eq 0 ]; then
  echo "NO_WORKFLOWS"
  exit 0
fi

echo "WORKFLOW_COUNT=$count"
summary=$(mktemp)

for i in $(seq 0 $((count-1))); do
  wf_json=$(jq -c ".[$i]" "$tmp")
  id=$(echo "$wf_json" | jq -r .id)
  name=$(echo "$wf_json" | jq -r .name)
  path=$(echo "$wf_json" | jq -r .path)
  state=$(echo "$wf_json" | jq -r .state)
  echo "----"
  echo "Workflow: $name"
  echo "  path: $path"
  echo "  id: $id"
  echo "  state: $state"

  if [ "$state" != "active" ]; then
    echo "  skip:not-active"
    echo "$name|$path|skipped:not-active" >> "$summary"
    continue
  fi

  if echo "$path" | grep -Eiq "release|publish|deploy|upload" || echo "$name" | grep -Eiq "release|publish|deploy|upload"; then
    echo "  skip:sensitive"
    echo "$name|$path|skipped:sensitive" >> "$summary"
    continue
  fi

  content=$(gh api repos/${REPO}/contents/"$path" --jq '.content' 2>/dev/null || true)
  if [ -z "$content" ]; then
    echo "  skip:cannot-fetch"
    echo "$name|$path|skipped:cannot-fetch" >> "$summary"
    continue
  fi

  yaml=$(echo "$content" | python3 - <<PY
import sys,base64
print(base64.b64decode(sys.stdin.read()).decode())
PY
)

  wf_block=$(echo "$yaml" | awk 'BEGIN{p=0} /^workflow_dispatch:/{p=1;next} p && /^[^ \t]/{exit} p{print}')
  if [ -z "$wf_block" ]; then
    echo "  skip:not-dispatchable"
    echo "$name|$path|skipped:not-dispatchable" >> "$summary"
    continue
  fi

  if echo "$wf_block" | grep -q "inputs:"; then
    if echo "$wf_block" | grep -q "required: *true"; then
      echo "  skip:requires-inputs"
      echo "$name|$path|skipped:requires-inputs" >> "$summary"
      continue
    fi
  fi

  echo "  dispatching to ref $DEFAULT_BRANCH..."
  run_out=$(gh workflow run "$id" --ref "$DEFAULT_BRANCH" 2>&1) || run_out="$run_out"
  echo "  run output: $(echo "$run_out" | sed -n '1,3p')"
  sleep 2

  run_json=$(gh run list --workflow "$id" --branch "$DEFAULT_BRANCH" --json id,url,createdAt,status,conclusion -L 1 | jq -c '.[0]' 2>/dev/null || echo null)
  if [ "$run_json" = "null" ]; then
    echo "  no-run-found"
    echo "$name|$path|dispatched:no-run-found" >> "$summary"
    continue
  fi

  run_id=$(echo "$run_json" | jq -r .id)
  run_url=$(echo "$run_json" | jq -r .url)
  echo "  run id: $run_id url: $run_url"

  timeout=300
  elapsed=0
  interval=5
  while true; do
    st_con=$(gh run view "$run_id" --json status,conclusion --jq '.status + "|" + (.conclusion // "")' 2>/dev/null || echo "unknown|")
    status=${st_con%%|*}
    conclusion=${st_con##*|}
    echo "    status=$status conclusion=$conclusion"
    if [ "$status" = "completed" ] || [ "$status" = "failure" ]; then
      break
    fi
    if [ "$elapsed" -ge "$timeout" ]; then
      echo "    timeout-waiting"
      break
    fi
    sleep $interval
    elapsed=$((elapsed+interval))
  done

  echo "  final: status=$status conclusion=$conclusion"
  echo "$name|$path|dispatched|$run_id|$run_url|$status|$conclusion" >> "$summary"
done

echo "SUMMARY:"
cat "$summary"
echo "SUMMARY_FILE:$summary"
