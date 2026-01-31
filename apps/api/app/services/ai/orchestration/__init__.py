"""
Orchestration - Camada de orquestração de agentes.

Contém:
- OrchestrationRouter: Decide qual executor usar
- ParallelExecutor: Executa múltiplos agentes em paralelo
- EventMerger: Merge SSE de múltiplas fontes
- RoutingDecision: Decisão de routing com metadados
- OrchestrationContext: Contexto para execução de prompts
- get_orchestration_router: Singleton do router

Uso básico:
    from app.services.ai.orchestration import get_orchestration_router

    router = get_orchestration_router()

    async for event in router.execute(prompt, models, context, mode):
        # Processar evento SSE
        print(event.to_json())
"""

from app.services.ai.orchestration.router import (
    OrchestrationRouter,
    ExecutorType,
    RoutingDecision,
    OrchestrationContext,
    get_orchestration_router,
)
from app.services.ai.orchestration.parallel_executor import (
    ParallelExecutor,
    ParallelResult,
    ExecutionContext,
    run_parallel_execution,
)
from app.services.ai.orchestration.event_merger import EventMerger, MergedResult

__all__ = [
    # Router
    "OrchestrationRouter",
    "ExecutorType",
    "RoutingDecision",
    "OrchestrationContext",
    "get_orchestration_router",
    # Parallel execution
    "ParallelExecutor",
    "ParallelResult",
    "ExecutionContext",
    "run_parallel_execution",
    # Event merging
    "EventMerger",
    "MergedResult",
]
