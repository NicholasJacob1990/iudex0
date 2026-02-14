#!/usr/bin/env bash
set -euo pipefail

# Smoke test: Outlook Add-in workflow trigger + status polling.
#
# What it does:
# 1. Starts API (uvicorn) on a local port with RAG preloads disabled.
# 2. Starts Celery worker (queue: celery) with a unique nodename.
# 3. Calls /api/auth/login-test to get a token (requires DEBUG=true).
# 4. Creates an empty workflow.
# 5. Triggers it via /api/outlook-addin/workflow/trigger.
# 6. Polls /api/outlook-addin/workflow/status/{run_id} until completed/failed.
#
# Notes:
# - Uses a temporary SQLite file DB (DATABASE_URL) and relies on app startup `init_db()`
#   (create_all) to bootstrap schema for smoke purposes.
#
# Requirements:
# - apps/api/venv exists and has dependencies installed
# - redis is running locally (broker/result backend defaults)

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_DIR="$ROOT_DIR/apps/api"
PY="$API_DIR/venv/bin/python"
CELERY="$API_DIR/venv/bin/celery"

if [[ ! -x "$PY" ]]; then
  echo "Missing venv python at $PY"
  exit 1
fi
if [[ ! -x "$CELERY" ]]; then
  echo "Missing celery at $CELERY"
  exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "Missing curl"
  exit 1
fi

if command -v redis-cli >/dev/null 2>&1; then
  if ! redis-cli ping >/dev/null 2>&1; then
    echo "Redis not responding to redis-cli ping (expected local Redis)."
    exit 1
  fi
else
  echo "redis-cli not found; cannot verify broker connectivity."
fi

mktemp_dir() {
  # macOS: mktemp requires -t; Linux often accepts mktemp -d directly.
  local d=""
  if d="$(mktemp -d -t iudex-smoke 2>/dev/null)"; then
    echo "$d"
    return 0
  fi
  d="$(mktemp -d 2>/dev/null)"
  echo "$d"
}

SMOKE_TMP="$(mktemp_dir)"
API_LOG="$SMOKE_TMP/api.log"
WORKER_LOG="$SMOKE_TMP/worker.log"
SMOKE_DB_PATH="$SMOKE_TMP/iudex-smoke.db"
SMOKE_DB_URL="sqlite+aiosqlite:///$SMOKE_DB_PATH"

cleanup() {
  local code=$?
  # Best-effort shutdown
  if [[ -n "${API_PID:-}" ]] && kill -0 "$API_PID" >/dev/null 2>&1; then
    kill "$API_PID" >/dev/null 2>&1 || true
  fi
  if [[ -n "${WORKER_PID:-}" ]] && kill -0 "$WORKER_PID" >/dev/null 2>&1; then
    kill "$WORKER_PID" >/dev/null 2>&1 || true
  fi
  if [[ "$code" -ne 0 ]]; then
    echo "Smoke failed; logs kept at: $SMOKE_TMP" >&2
    return 0
  fi
  rm -rf "$SMOKE_TMP" >/dev/null 2>&1 || true
}
trap cleanup EXIT

pick_port() {
  local p
  for p in "${SMOKE_PORT:-8009}" 8010 8011 8012 8013 8014 8015 8016 8017 8018 8019 8020; do
    if command -v lsof >/dev/null 2>&1; then
      if ! lsof -n -iTCP:"$p" -sTCP:LISTEN >/dev/null 2>&1; then
        echo "$p"
        return 0
      fi
    else
      # If lsof isn't available, just try the default.
      echo "$p"
      return 0
    fi
  done
  return 1
}

PORT="$(pick_port)"
BASE_URL="http://127.0.0.1:$PORT"

export PYTHONPATH="$API_DIR${PYTHONPATH:+:$PYTHONPATH}"

# Load local .env if present (but env vars exported below always win).
if [[ -f "$API_DIR/.env" ]]; then
  export IUDEX_ENV_FILE="$API_DIR/.env"
fi

# Minimal env for boot; override as needed.
export DEBUG="${DEBUG:-true}"
export SECRET_KEY="${SECRET_KEY:-smoke-secret-key}"
export JWT_SECRET_KEY="${JWT_SECRET_KEY:-smoke-jwt-secret}"
export DATABASE_URL="$SMOKE_DB_URL"
export CELERY_BROKER_URL="${CELERY_BROKER_URL:-redis://localhost:6379/1}"
export CELERY_RESULT_BACKEND="${CELERY_RESULT_BACKEND:-redis://localhost:6379/2}"

# Avoid expensive/fragile warmups during smoke.
export RAG_PRELOAD_EMBEDDINGS=false
export RAG_PRELOAD_RERANKER=false
export RAG_WARMUP_ON_STARTUP=false

echo "Starting API on $BASE_URL (log: $API_LOG)"
(
  cd "$API_DIR"
  exec "$PY" -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT"
) >"$API_LOG" 2>&1 &
API_PID=$!

echo "Starting Celery worker (log: $WORKER_LOG)"
(
  cd "$API_DIR"
  exec "$CELERY" -A app.workers.celery_app.celery_app worker -l info -Q celery -n "smoke@%h" --pool=solo
) >"$WORKER_LOG" 2>&1 &
WORKER_PID=$!

wait_for_http() {
  local i
  for i in $(seq 1 60); do
    if curl -fsS --max-time 2 "$BASE_URL/openapi.json" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.5
  done
  return 1
}

echo "Waiting for API to become ready..."
if ! wait_for_http; then
  echo "API did not become ready. See logs:"
  echo "  $API_LOG"
  echo "  $WORKER_LOG"
  exit 1
fi

TOKEN="$(
  curl -fsS --max-time 5 -X POST "$BASE_URL/api/auth/login-test" \
  | "$PY" -c "import sys,json; print(json.load(sys.stdin)['access_token'])"
)"

WF_ID="$(
  curl -fsS --max-time 10 -X POST "$BASE_URL/api/workflows" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"name\":\"smoke-wf-$(date +%s)\",\"description\":\"smoke\",\"graph_json\":{\"nodes\":[],\"edges\":[]},\"tags\":[]}" \
  | "$PY" -c "import sys,json; print(json.load(sys.stdin)['id'])"
)"

RUN_JSON="$(
  curl -fsS --max-time 10 -X POST "$BASE_URL/api/outlook-addin/workflow/trigger" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"workflow_id\":\"$WF_ID\",\"email_data\":{\"subject\":\"Smoke\",\"body\":\"Hello\",\"sender\":\"a@b.com\",\"recipients\":[\"x@y.com\"],\"date\":\"2026-02-10T00:00:00Z\",\"attachments\":[]},\"parameters\":{}}" \
)"
RUN_ID="$(echo "$RUN_JSON" | "$PY" -c "import sys,json; print(json.load(sys.stdin)['id'])")"

echo "Triggered run_id=$RUN_ID workflow_id=$WF_ID"

status=""
for i in $(seq 1 60); do
  OUT="$(curl -fsS --max-time 5 "$BASE_URL/api/outlook-addin/workflow/status/$RUN_ID" -H "Authorization: Bearer $TOKEN")"
  status="$(echo "$OUT" | "$PY" -c "import sys,json; print(json.load(sys.stdin).get('status'))")"
  echo "poll $i status=$status"
  if [[ "$status" == "completed" || "$status" == "failed" ]]; then
    break
  fi
  sleep 0.5
done

if [[ "$status" != "completed" ]]; then
  echo "Smoke failed: final status=$status"
  echo "API log: $API_LOG"
  echo "Worker log: $WORKER_LOG"
  exit 1
fi

echo "Smoke ok: status=completed"
