#!/bin/bash
# Script para reiniciar o servidor backend

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "🛑 Parando servidor backend..."
lsof -ti:8000 | xargs kill -9 2>/dev/null || echo "Nenhum processo na porta 8000"

echo "⏳ Aguardando 2 segundos..."
sleep 2

echo "🚀 Iniciando servidor backend..."
cd "$ROOT_DIR/apps/api"
if [ -x "$ROOT_DIR/.venv/bin/python" ]; then
  "$ROOT_DIR/.venv/bin/python" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
else
  python3.12 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
fi
