#!/bin/bash
# Script para reiniciar o servidor backend

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "🛑 Parando servidor backend..."
lsof -ti:8000 | xargs kill -9 2>/dev/null || echo "Nenhum processo na porta 8000"

echo "⏳ Aguardando 2 segundos..."
sleep 2

echo "🚀 Iniciando servidor backend..."
API_DIR="$ROOT_DIR/apps/api"
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
"$PYTHON_BIN" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
