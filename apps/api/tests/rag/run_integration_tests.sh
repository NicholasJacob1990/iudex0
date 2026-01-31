#!/bin/bash
# =============================================================================
# RAG Integration Tests Runner
# =============================================================================
#
# This script manages the test infrastructure and runs integration tests.
#
# Usage:
#   ./tests/rag/run_integration_tests.sh          # Run all integration tests
#   ./tests/rag/run_integration_tests.sh qdrant   # Run only Qdrant tests
#   ./tests/rag/run_integration_tests.sh opensearch # Run only OpenSearch tests
#   ./tests/rag/run_integration_tests.sh neo4j    # Run only Neo4j tests
#   ./tests/rag/run_integration_tests.sh --start  # Only start containers
#   ./tests/rag/run_integration_tests.sh --start-neo4j # Start Neo4j container
#   ./tests/rag/run_integration_tests.sh --stop   # Only stop containers
#   ./tests/rag/run_integration_tests.sh --status # Check container status
#
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.test.yml"
COMPOSE_NEO4J="$SCRIPT_DIR/docker-compose.neo4j.yml"
PROJECT_NAME="rag-test"
PYTHON_BIN="${PYTHON_BIN:-python}"

if [ -x "$SCRIPT_DIR/../../.venv312/bin/python" ]; then
    PYTHON_BIN="$SCRIPT_DIR/../../.venv312/bin/python"
elif [ -x "$SCRIPT_DIR/../../.venv/bin/python" ]; then
    PYTHON_BIN="$SCRIPT_DIR/../../.venv/bin/python"
fi

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    if command -v python3 >/dev/null 2>&1; then
        PYTHON_BIN="python3"
    fi
fi

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# =============================================================================
# Functions
# =============================================================================

start_containers() {
    log_info "Starting test containers (Qdrant + OpenSearch)..."
    docker-compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" up -d

    log_info "Waiting for services to be healthy..."

    # Wait for Qdrant
    echo -n "  Qdrant: "
    for i in {1..30}; do
        if curl -s http://localhost:6333/health > /dev/null 2>&1; then
            echo -e "${GREEN}ready${NC}"
            break
        fi
        echo -n "."
        sleep 1
    done

    # Wait for OpenSearch
    echo -n "  OpenSearch: "
    for i in {1..60}; do
        if curl -s http://localhost:9200/_cluster/health 2>/dev/null | grep -q '"status"'; then
            echo -e "${GREEN}ready${NC}"
            break
        fi
        echo -n "."
        sleep 2
    done

    log_success "All services are ready!"
}

start_neo4j() {
    log_info "Starting Neo4j container..."
    docker-compose -f "$COMPOSE_NEO4J" -p "${PROJECT_NAME}-neo4j" up -d

    log_info "Waiting for Neo4j to be healthy..."

    echo -n "  Neo4j: "
    for i in {1..60}; do
        if curl -s http://localhost:7474 > /dev/null 2>&1; then
            echo -e "${GREEN}ready${NC}"
            break
        fi
        echo -n "."
        sleep 2
    done

    log_success "Neo4j is ready!"
}

stop_neo4j() {
    log_info "Stopping Neo4j container..."
    docker-compose -f "$COMPOSE_NEO4J" -p "${PROJECT_NAME}-neo4j" down -v
    log_success "Neo4j stopped and volumes removed."
}

stop_containers() {
    log_info "Stopping test containers..."
    docker-compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" down -v
    log_success "Containers stopped and volumes removed."
}

check_status() {
    log_info "Checking service status..."
    echo ""

    echo -n "Qdrant (localhost:6333): "
    if curl -s http://localhost:6333/health > /dev/null 2>&1; then
        echo -e "${GREEN}UP${NC}"
    else
        echo -e "${RED}DOWN${NC}"
    fi

    echo -n "OpenSearch (localhost:9200): "
    if curl -s http://localhost:9200/_cluster/health 2>/dev/null | grep -q '"status"'; then
        HEALTH=$(curl -s http://localhost:9200/_cluster/health | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
        echo -e "${GREEN}UP${NC} (status: $HEALTH)"
    else
        echo -e "${RED}DOWN${NC}"
    fi

    echo -n "Neo4j (localhost:7474): "
    if curl -s http://localhost:7474 > /dev/null 2>&1; then
        echo -e "${GREEN}UP${NC}"
    else
        echo -e "${RED}DOWN${NC}"
    fi
    echo ""
}

run_tests() {
    local test_target="$1"

    # Check if services are running
    if ! curl -s http://localhost:6333/health > /dev/null 2>&1; then
        log_warn "Qdrant not running. Starting containers..."
        start_containers
    fi

    if ! curl -s http://localhost:9200/_cluster/health > /dev/null 2>&1; then
        log_warn "OpenSearch not running. Starting containers..."
        start_containers
    fi

    log_info "Running integration tests..."
    echo ""

    cd "$SCRIPT_DIR/../.."

    case "$test_target" in
        qdrant)
            log_info "Running Qdrant integration tests..."
            "$PYTHON_BIN" -m pytest tests/rag/test_qdrant_integration.py -v --tb=short -o "addopts="
            ;;
        opensearch)
            log_info "Running OpenSearch integration tests..."
            "$PYTHON_BIN" -m pytest tests/rag/test_opensearch_integration.py -v --tb=short -o "addopts="
            ;;
        neo4j)
            log_info "Running Neo4j integration tests..."
            # Check if Neo4j is running
            if ! curl -s http://localhost:7474 > /dev/null 2>&1; then
                log_warn "Neo4j not running. Starting container..."
                start_neo4j
            fi
            "$PYTHON_BIN" -m pytest tests/rag/test_neo4j_integration.py -v --tb=short -o "addopts="
            ;;
        *)
            log_info "Running all integration tests (Qdrant + OpenSearch)..."
            "$PYTHON_BIN" -m pytest tests/rag/test_qdrant_integration.py tests/rag/test_opensearch_integration.py -v --tb=short -o "addopts="
            ;;
    esac
}

# =============================================================================
# Main
# =============================================================================

case "${1:-}" in
    --start)
        start_containers
        ;;
    --start-neo4j)
        start_neo4j
        ;;
    --stop)
        stop_containers
        stop_neo4j 2>/dev/null || true
        ;;
    --stop-neo4j)
        stop_neo4j
        ;;
    --status)
        check_status
        ;;
    --help|-h)
        echo "RAG Integration Tests Runner"
        echo ""
        echo "Usage:"
        echo "  $0              Run Qdrant + OpenSearch tests"
        echo "  $0 qdrant       Run only Qdrant tests"
        echo "  $0 opensearch   Run only OpenSearch tests"
        echo "  $0 neo4j        Run only Neo4j tests"
        echo "  $0 --start      Start Qdrant + OpenSearch containers"
        echo "  $0 --start-neo4j Start Neo4j container"
        echo "  $0 --stop       Stop all containers"
        echo "  $0 --stop-neo4j Stop Neo4j container"
        echo "  $0 --status     Check container status"
        echo ""
        echo "Requirements:"
        echo "  - Docker and docker-compose installed"
        echo "  - Python virtual environment with test dependencies"
        echo "  - pip install neo4j (for Neo4j tests)"
        ;;
    *)
        run_tests "$1"
        ;;
esac
