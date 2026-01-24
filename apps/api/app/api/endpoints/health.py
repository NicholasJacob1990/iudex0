"""
Health Check Endpoints

Provides health check endpoints for monitoring service status:
- /health/rag: Check RAG storage services (OpenSearch, Qdrant)
- Circuit breaker states
- Service connectivity
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# Response Models
# =============================================================================


class CircuitBreakerStatus(BaseModel):
    """Circuit breaker status."""
    state: str
    failure_count: int
    success_count: int
    last_failure_time: Optional[float] = None
    last_success_time: Optional[float] = None
    last_state_change: Optional[float] = None
    total_calls: int
    total_failures: int
    total_successes: int
    total_rejected: int


class ServiceHealthStatus(BaseModel):
    """Health status for a single service."""
    service: str
    healthy: bool
    reachable: bool
    circuit_breaker: CircuitBreakerStatus
    url: Optional[str] = None
    error: Optional[str] = None


class RAGHealthResponse(BaseModel):
    """Response for RAG health check."""
    status: str  # "healthy", "degraded", "unhealthy"
    services: Dict[str, ServiceHealthStatus]
    circuit_breakers: Dict[str, CircuitBreakerStatus]
    details: Optional[Dict[str, Any]] = None


# =============================================================================
# Health Check Endpoints
# =============================================================================


@router.get(
    "/health/rag",
    response_model=RAGHealthResponse,
    summary="RAG Storage Health Check",
    description="Check connectivity and circuit breaker states for RAG storage services (OpenSearch, Qdrant)",
    tags=["health"],
)
async def health_check_rag() -> RAGHealthResponse:
    """
    Check health of RAG storage services.

    Returns status for:
    - OpenSearch (lexical search)
    - Qdrant (vector search)
    - Circuit breaker states for each service

    Status levels:
    - healthy: All services up and circuits closed
    - degraded: Some services down but fallbacks available
    - unhealthy: Critical services unavailable
    """
    from app.services.rag.core.resilience import get_all_circuit_breakers

    services: Dict[str, ServiceHealthStatus] = {}
    overall_healthy = True
    any_reachable = False

    # Check OpenSearch
    opensearch_status = await _check_opensearch()
    services["opensearch"] = opensearch_status
    if opensearch_status.reachable:
        any_reachable = True
    if not opensearch_status.healthy:
        overall_healthy = False

    # Check Qdrant
    qdrant_status = await _check_qdrant()
    services["qdrant"] = qdrant_status
    if qdrant_status.reachable:
        any_reachable = True
    if not qdrant_status.healthy:
        overall_healthy = False

    # Get all circuit breaker states
    circuit_breakers = {}
    for name, breaker in get_all_circuit_breakers().items():
        stats = breaker.stats
        circuit_breakers[name] = CircuitBreakerStatus(
            state=stats.state.value,
            failure_count=stats.failure_count,
            success_count=stats.success_count,
            last_failure_time=stats.last_failure_time,
            last_success_time=stats.last_success_time,
            last_state_change=stats.last_state_change,
            total_calls=stats.total_calls,
            total_failures=stats.total_failures,
            total_successes=stats.total_successes,
            total_rejected=stats.total_rejected,
        )

    # Determine overall status
    if overall_healthy and any_reachable:
        status = "healthy"
    elif any_reachable:
        status = "degraded"
    else:
        status = "unhealthy"

    return RAGHealthResponse(
        status=status,
        services=services,
        circuit_breakers=circuit_breakers,
        details={
            "opensearch_healthy": opensearch_status.healthy,
            "qdrant_healthy": qdrant_status.healthy,
            "all_circuits_closed": all(
                cb.state == "closed" for cb in circuit_breakers.values()
            ) if circuit_breakers else True,
        },
    )


@router.get(
    "/health/rag/opensearch",
    response_model=ServiceHealthStatus,
    summary="OpenSearch Health Check",
    description="Check OpenSearch connectivity and circuit breaker state",
    tags=["health"],
)
async def health_check_opensearch() -> ServiceHealthStatus:
    """Check OpenSearch service health."""
    return await _check_opensearch()


@router.get(
    "/health/rag/qdrant",
    response_model=ServiceHealthStatus,
    summary="Qdrant Health Check",
    description="Check Qdrant connectivity and circuit breaker state",
    tags=["health"],
)
async def health_check_qdrant() -> ServiceHealthStatus:
    """Check Qdrant service health."""
    return await _check_qdrant()


@router.post(
    "/health/rag/reset-circuits",
    summary="Reset Circuit Breakers",
    description="Reset all RAG circuit breakers to closed state (admin only)",
    tags=["health"],
)
async def reset_circuit_breakers() -> Dict[str, str]:
    """
    Reset all circuit breakers to closed state.

    This is useful for:
    - After fixing a known issue with a service
    - During maintenance windows
    - Testing circuit breaker behavior
    """
    from app.services.rag.core.resilience import reset_all_circuit_breakers

    reset_all_circuit_breakers()
    logger.info("All RAG circuit breakers reset via API")

    return {"status": "ok", "message": "All circuit breakers reset to closed state"}


# =============================================================================
# Helper Functions
# =============================================================================


async def _check_opensearch() -> ServiceHealthStatus:
    """Check OpenSearch service health."""
    try:
        from app.services.rag.storage.opensearch_service import get_opensearch_service
        from app.services.rag.core.resilience import CircuitState

        service = get_opensearch_service()
        health = service.get_health_status()

        return ServiceHealthStatus(
            service="opensearch",
            healthy=health.get("healthy", False),
            reachable=health.get("reachable", False),
            circuit_breaker=CircuitBreakerStatus(**health.get("circuit_breaker", {
                "state": "unknown",
                "failure_count": 0,
                "success_count": 0,
                "total_calls": 0,
                "total_failures": 0,
                "total_successes": 0,
                "total_rejected": 0,
            })),
            url=health.get("url"),
        )

    except ImportError as e:
        logger.warning(f"OpenSearch service not available: {e}")
        return ServiceHealthStatus(
            service="opensearch",
            healthy=False,
            reachable=False,
            circuit_breaker=CircuitBreakerStatus(
                state="unknown",
                failure_count=0,
                success_count=0,
                total_calls=0,
                total_failures=0,
                total_successes=0,
                total_rejected=0,
            ),
            error=f"Service not available: {e}",
        )

    except Exception as e:
        logger.error(f"Error checking OpenSearch health: {e}")
        return ServiceHealthStatus(
            service="opensearch",
            healthy=False,
            reachable=False,
            circuit_breaker=CircuitBreakerStatus(
                state="unknown",
                failure_count=0,
                success_count=0,
                total_calls=0,
                total_failures=0,
                total_successes=0,
                total_rejected=0,
            ),
            error=str(e),
        )


async def _check_qdrant() -> ServiceHealthStatus:
    """Check Qdrant service health."""
    try:
        from app.services.rag.storage.qdrant_service import get_qdrant_service

        service = get_qdrant_service()
        health = service.get_health_status()

        return ServiceHealthStatus(
            service="qdrant",
            healthy=health.get("healthy", False),
            reachable=health.get("reachable", False),
            circuit_breaker=CircuitBreakerStatus(**health.get("circuit_breaker", {
                "state": "unknown",
                "failure_count": 0,
                "success_count": 0,
                "total_calls": 0,
                "total_failures": 0,
                "total_successes": 0,
                "total_rejected": 0,
            })),
            url=health.get("url"),
        )

    except ImportError as e:
        logger.warning(f"Qdrant service not available: {e}")
        return ServiceHealthStatus(
            service="qdrant",
            healthy=False,
            reachable=False,
            circuit_breaker=CircuitBreakerStatus(
                state="unknown",
                failure_count=0,
                success_count=0,
                total_calls=0,
                total_failures=0,
                total_successes=0,
                total_rejected=0,
            ),
            error=f"Service not available: {e}",
        )

    except Exception as e:
        logger.error(f"Error checking Qdrant health: {e}")
        return ServiceHealthStatus(
            service="qdrant",
            healthy=False,
            reachable=False,
            circuit_breaker=CircuitBreakerStatus(
                state="unknown",
                failure_count=0,
                success_count=0,
                total_calls=0,
                total_failures=0,
                total_successes=0,
                total_rejected=0,
            ),
            error=str(e),
        )
