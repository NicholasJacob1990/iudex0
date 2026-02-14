#!/usr/bin/env bash
set -euo pipefail

PORT="${1:-${IUDEX_API_PORT:-8000}}"
TARGET_URL="http://localhost:${PORT}"

if ! curl -fsS "${TARGET_URL}/health" >/dev/null 2>&1; then
  echo "API não respondeu em ${TARGET_URL}/health."
  echo "Suba a API antes de abrir o túnel."
  exit 1
fi

pick_provider() {
  if command -v cloudflared >/dev/null 2>&1; then
    echo "cloudflared"
    return
  fi
  if command -v ngrok >/dev/null 2>&1; then
    echo "ngrok"
    return
  fi
  echo ""
}

extract_url() {
  local logfile="$1"
  grep -Eo 'https://[a-zA-Z0-9.-]+\.trycloudflare\.com|https://[a-zA-Z0-9.-]+\.ngrok-free\.app|https://[a-zA-Z0-9.-]+\.ngrok\.io' "${logfile}" | head -n 1 || true
}

PROVIDER="$(pick_provider)"
if [[ -z "${PROVIDER}" ]]; then
  echo "Nenhum túnel encontrado. Instale cloudflared (recomendado) ou ngrok."
  exit 1
fi

LOGFILE="$(mktemp -t runpod-tunnel.XXXX.log)"

if [[ "${PROVIDER}" == "cloudflared" ]]; then
  CMD=(cloudflared tunnel --url "${TARGET_URL}" --no-autoupdate)
else
  CMD=(ngrok http "${PORT}" --log stdout --log-format logfmt)
fi

echo "Iniciando túnel (${PROVIDER}) para ${TARGET_URL}..."
"${CMD[@]}" >"${LOGFILE}" 2>&1 &
TUNNEL_PID=$!

cleanup() {
  if kill -0 "${TUNNEL_PID}" >/dev/null 2>&1; then
    kill "${TUNNEL_PID}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

PUBLIC_URL=""
for _ in $(seq 1 40); do
  PUBLIC_URL="$(extract_url "${LOGFILE}")"
  if [[ -n "${PUBLIC_URL}" ]]; then
    break
  fi
  sleep 1
done

if [[ -z "${PUBLIC_URL}" ]]; then
  echo "Não foi possível descobrir URL pública do túnel."
  echo "Logs:"
  tail -n 80 "${LOGFILE}" || true
  exit 1
fi

echo ""
echo "Túnel ativo: ${PUBLIC_URL}"
echo "Configure no backend atual:"
echo "export IUDEX_RUNPOD_PUBLIC_BASE_URL=${PUBLIC_URL}"
echo ""
echo "Para persistir em apps/api/.env:"
echo "IUDEX_RUNPOD_PUBLIC_BASE_URL=${PUBLIC_URL}"
echo ""
echo "Pressione Ctrl+C para encerrar o túnel."
echo ""

tail -f "${LOGFILE}" >/dev/null
