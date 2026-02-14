#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────
# dev-api-tunnel.sh — Inicia túnel Cloudflare + API em um só comando
#
# 1. Sobe cloudflared tunnel em background
# 2. Espera pela URL pública
# 3. Atualiza IUDEX_RUNPOD_PUBLIC_BASE_URL no .env
# 4. Exporta a var no ambiente e inicia uvicorn
#
# Uso: bash apps/api/scripts/dev-api-tunnel.sh [PORT]
# ──────────────────────────────────────────────────────────────
set -euo pipefail

PORT="${1:-${IUDEX_API_PORT:-8000}}"
TARGET_URL="http://localhost:${PORT}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${API_DIR}/.env"
TUNNEL_PID=""

# ── Cores ──
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

cleanup() {
  echo ""
  echo -e "${YELLOW}Encerrando...${NC}"
  if [[ -n "${TUNNEL_PID}" ]] && kill -0 "${TUNNEL_PID}" 2>/dev/null; then
    kill "${TUNNEL_PID}" 2>/dev/null || true
    echo -e "${GREEN}Túnel encerrado.${NC}"
  fi
  # uvicorn será encerrado pelo trap do shell pai
}
trap cleanup EXIT INT TERM

# ── Verificar cloudflared ──
if ! command -v cloudflared >/dev/null 2>&1; then
  echo -e "${RED}cloudflared não encontrado.${NC}"
  echo "Instale com: brew install cloudflared"
  exit 1
fi

# ── Verificar .env existe ──
if [[ ! -f "${ENV_FILE}" ]]; then
  echo -e "${RED}.env não encontrado em ${ENV_FILE}${NC}"
  echo "Copie de .env.example: cp ${API_DIR}/.env.example ${ENV_FILE}"
  exit 1
fi

# ── Iniciar túnel ──
LOGFILE="$(mktemp -t iudex-tunnel.XXXX.log)"
echo -e "${CYAN}Iniciando túnel Cloudflare para ${TARGET_URL}...${NC}"
cloudflared tunnel --url "${TARGET_URL}" --no-autoupdate >"${LOGFILE}" 2>&1 &
TUNNEL_PID=$!

# ── Esperar URL pública ──
PUBLIC_URL=""
echo -n "Aguardando URL pública"
for i in $(seq 1 30); do
  PUBLIC_URL="$(grep -Eo 'https://[a-zA-Z0-9._-]+\.trycloudflare\.com' "${LOGFILE}" 2>/dev/null | head -n 1 || true)"
  if [[ -n "${PUBLIC_URL}" ]]; then
    break
  fi
  echo -n "."
  sleep 1
done
echo ""

if [[ -z "${PUBLIC_URL}" ]]; then
  echo -e "${RED}Não foi possível obter URL do túnel.${NC}"
  echo "Logs:"
  tail -n 20 "${LOGFILE}" 2>/dev/null || true
  exit 1
fi

echo -e "${GREEN}Túnel ativo: ${PUBLIC_URL}${NC}"

# ── Atualizar .env ──
ENV_KEY="IUDEX_RUNPOD_PUBLIC_BASE_URL"
if grep -q "^${ENV_KEY}=" "${ENV_FILE}" 2>/dev/null; then
  # Substitui valor existente (macOS sed -i requer '')
  sed -i '' "s|^${ENV_KEY}=.*|${ENV_KEY}=${PUBLIC_URL}|" "${ENV_FILE}"
  echo -e "${GREEN}.env atualizado: ${ENV_KEY}=${PUBLIC_URL}${NC}"
elif grep -q "^#.*${ENV_KEY}" "${ENV_FILE}" 2>/dev/null; then
  # Descomenta e atualiza
  sed -i '' "s|^#.*${ENV_KEY}=.*|${ENV_KEY}=${PUBLIC_URL}|" "${ENV_FILE}"
  echo -e "${GREEN}.env atualizado (descomentado): ${ENV_KEY}=${PUBLIC_URL}${NC}"
else
  # Adiciona no final
  echo "" >> "${ENV_FILE}"
  echo "${ENV_KEY}=${PUBLIC_URL}" >> "${ENV_FILE}"
  echo -e "${GREEN}.env atualizado (adicionado): ${ENV_KEY}=${PUBLIC_URL}${NC}"
fi

# ── Exportar no ambiente atual ──
export IUDEX_RUNPOD_PUBLIC_BASE_URL="${PUBLIC_URL}"

# ── Ativar venv se existir ──
if [[ -f "${API_DIR}/.venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "${API_DIR}/.venv/bin/activate"
fi

# ── Iniciar API ──
echo ""
echo -e "${CYAN}Iniciando API (uvicorn) na porta ${PORT}...${NC}"
echo -e "${CYAN}RunPod usará: ${PUBLIC_URL}${NC}"
echo "──────────────────────────────────────────"
cd "${API_DIR}"
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT}" --reload
