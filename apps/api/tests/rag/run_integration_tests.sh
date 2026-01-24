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
#   ./tests/rag/run_integration_tests.sh --start  # Only start containers
#   ./tests/rag/run_integration_tests.sh --stop   # Only stop containers
#   ./tests/rag/run_integration_tests.sh --status # Check container status
#
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.test.yml"
PROJECT_NAME="rag-test"

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
    log_info "Starting test containers..."
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
            python -m pytest tests/rag/test_qdrant_integration.py -v --tb=short -o "addopts="
            ;;
        opensearch)
            log_info "Running OpenSearch integration tests..."
            python -m pytest tests/rag/test_opensearch_integration.py -v --tb=short -o "addopts="
            ;;
        *)
            log_info "Running all integration tests..."
            python -m pytest tests/rag/test_qdrant_integration.py tests/rag/test_opensearch_integration.py -v --tb=short -o "addopts="
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
    --stop)
        stop_containers
        ;;
    --status)
        check_status
        ;;
    --help|-h)
        echo "RAG Integration Tests Runner"
        echo ""
        echo "Usage:"
        echo "  $0              Run all integration tests"
        echo "  $0 qdrant       Run only Qdrant tests"
        echo "  $0 opensearch   Run only OpenSearch tests"
        echo "  $0 --start      Only start containers"
        echo "  $0 --stop       Only stop containers"
        echo "  $0 --status     Check container status"
        echo ""
        echo "Requirements:"
        echo "  - Docker and docker-compose installed"
        echo "  - Python virtual environment with test dependencies"
        ;;
    *)
        run_tests "$1"
        ;;
esac
