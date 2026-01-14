#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
API_DIR="$ROOT_DIR/apps/api"
WEB_DIR="$ROOT_DIR/apps/web"

cleanup() {
  if [[ -n "${API_PID:-}" ]]; then
    kill "${API_PID}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

if curl -sf "http://localhost:8000/health" >/dev/null 2>&1; then
  API_PID=""
else
  if command -v lsof >/dev/null 2>&1; then
    if lsof -iTCP:8000 -sTCP:LISTEN >/dev/null 2>&1; then
      echo "Port 8000 already in use and /health is not responding." >&2
      exit 1
    fi
  fi

  if [[ ! -x "$API_DIR/venv/bin/uvicorn" ]]; then
    echo "uvicorn not found in $API_DIR/venv/bin. Activate the backend venv first." >&2
    exit 1
  fi

  E2E_DB_PATH="$(mktemp -t iudex_e2e_XXXX.db)"
  (cd "$API_DIR" && DATABASE_URL="sqlite+aiosqlite:///$E2E_DB_PATH" "$API_DIR/venv/bin/uvicorn" app.main:app --host 0.0.0.0 --port 8000) &
  API_PID=$!

  until curl -sf "http://localhost:8000/health" >/dev/null 2>&1; do
    sleep 0.5
  done
fi

cd "$WEB_DIR"
export NEXT_PUBLIC_API_URL="http://localhost:8000"
npm run dev -- --port 3001
