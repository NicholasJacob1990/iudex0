#!/bin/bash
#
# Inicia o Chrome com Remote Debugging habilitado
# Necessário para usar o SEI Daemon em modo CDP
#
# Uso:
#   ./start-chrome-debug.sh
#
# Depois:
#   1. Faça login no SEI manualmente no Chrome
#   2. Em outro terminal: SEI_CDP=http://localhost:9222 npx tsx start-daemon.ts
#

PORT=${1:-9222}

echo "🚀 Iniciando Chrome com Remote Debugging na porta $PORT..."
echo ""
echo "Próximos passos:"
echo "  1. Faça login no SEI manualmente"
echo "  2. Em outro terminal, execute:"
echo "     SEI_CDP=http://localhost:$PORT npx tsx start-daemon.ts"
echo ""

# macOS
if [[ "$OSTYPE" == "darwin"* ]]; then
    /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
        --remote-debugging-port=$PORT \
        --user-data-dir="$HOME/.sei-playwright/chrome-debug-profile" \
        "https://www.sei.mg.gov.br/sei/" \
        2>/dev/null &
# Linux
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    google-chrome \
        --remote-debugging-port=$PORT \
        --user-data-dir="$HOME/.sei-playwright/chrome-debug-profile" \
        "https://www.sei.mg.gov.br/sei/" \
        2>/dev/null &
# Windows (WSL)
elif [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "cygwin" ]]; then
    "/mnt/c/Program Files/Google/Chrome/Application/chrome.exe" \
        --remote-debugging-port=$PORT \
        --user-data-dir="$HOME/.sei-playwright/chrome-debug-profile" \
        "https://www.sei.mg.gov.br/sei/" \
        2>/dev/null &
fi

echo "✅ Chrome iniciado! PID: $!"
