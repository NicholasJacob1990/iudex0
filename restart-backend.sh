#!/bin/bash
# Script para reiniciar o servidor backend
# Padrão: inicia backend COM túnel público (necessário para RunPod baixar áudio).
# Use --no-tunnel para subir uvicorn local sem cloudflared.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
API_DIR="$ROOT_DIR/apps/api"
TUNNEL_SCRIPT="$ROOT_DIR/apps/api/scripts/dev-api-tunnel.sh"
PORT="${IUDEX_API_PORT:-8000}"
USE_TUNNEL=1

if [[ "${1:-}" == "--no-tunnel" ]]; then
  USE_TUNNEL=0
fi

echo "🛑 Parando servidor backend (porta $PORT)..."
lsof -ti:"$PORT" | xargs kill -9 2>/dev/null || echo "Nenhum processo na porta $PORT"

echo "⏳ Aguardando 2 segundos..."
sleep 2

if [[ "$USE_TUNNEL" -eq 1 ]]; then
  if [[ ! -f "$TUNNEL_SCRIPT" ]]; then
    echo "❌ Script de tunnel não encontrado em: $TUNNEL_SCRIPT"
    echo "Use: ./restart-backend.sh --no-tunnel"
    exit 1
  fi
  echo "🚀 Iniciando backend com tunnel (cloudflared)..."
  exec bash "$TUNNEL_SCRIPT" "$PORT"
fi

echo "🚀 Iniciando backend local sem tunnel..."
cd "$API_DIR"

PYTHON_BIN=""
for candidate in \
  "$API_DIR/.venv312/bin/python" \
  "$API_DIR/venv/bin/python" \
  "$API_DIR/.venv/bin/python" \
  "$ROOT_DIR/.venv/bin/python"
do
  if [ -x "$candidate" ]; then
    PYTHON_BIN="$candidate"
    break
  fi
done

if [ -z "$PYTHON_BIN" ]; then
  if command -v python3.12 >/dev/null 2>&1; then
    PYTHON_BIN="python3.12"
  elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
  fi
fi

if [ -z "$PYTHON_BIN" ]; then
  echo "❌ Python não encontrado. Ative a venv em apps/api."
  exit 1
fi

echo "🐍 Usando Python: $PYTHON_BIN"
exec "$PYTHON_BIN" -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --reload
