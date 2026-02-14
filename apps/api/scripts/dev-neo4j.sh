#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-${API_DIR}/docker-compose.rag.yml}"
SERVICE="neo4j"
NEO4J_HTTP_PORT="${NEO4J_HTTP_PORT:-8474}"
NEO4J_BOLT_PORT="${NEO4J_BOLT_PORT:-8687}"

if docker compose version >/dev/null 2>&1; then
  DOCKER_COMPOSE=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  DOCKER_COMPOSE=(docker-compose)
else
  echo "Erro: docker compose (plugin) ou docker-compose não encontrado." >&2
  exit 1
fi

usage() {
  cat <<'EOF'
Uso: dev-neo4j.sh <comando>

Comandos:
  up        Sobe o Neo4j local (Enterprise Developer License) em background
  down      Para o container Neo4j
  restart   Reinicia o container Neo4j
  status    Mostra status do serviço Neo4j
  logs      Mostra logs do Neo4j (follow)
EOF
}

action="${1:-up}"
shift || true

run_compose() {
  if ! docker info >/dev/null 2>&1; then
    echo "Erro: Docker daemon não está em execução. Inicie o Docker Desktop e tente novamente." >&2
    exit 1
  fi

  (
    cd "${API_DIR}"
    "${DOCKER_COMPOSE[@]}" -f "${COMPOSE_FILE}" "$@"
  )
}

case "${action}" in
  up)
    run_compose up -d "${SERVICE}"
    cat <<EOF
Neo4j local iniciado.
- Bolt: bolt://localhost:${NEO4J_BOLT_PORT}
- Browser: http://localhost:${NEO4J_HTTP_PORT}
- Usuário: neo4j
- Senha: conforme NEO4J_PASSWORD no ambiente/compose
EOF
    ;;
  down)
    run_compose stop "${SERVICE}"
    echo "Neo4j local parado."
    ;;
  restart)
    run_compose restart "${SERVICE}"
    echo "Neo4j local reiniciado."
    ;;
  status)
    run_compose ps "${SERVICE}"
    ;;
  logs)
    run_compose logs -f "${SERVICE}"
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    echo "Comando inválido: ${action}" >&2
    usage
    exit 1
    ;;
esac
