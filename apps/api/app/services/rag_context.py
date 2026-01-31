"""
RAG Context - Compatibility shim (DEPRECATED).

This module keeps the historic import path (`app.services.rag_context`) stable,
and delegates to the legacy implementation for backward compatibility.

PREFERRED IMPORTS (new pipeline):
    from app.services.rag.pipeline_adapter import build_rag_context_unified
    from app.services.rag_module_old import get_scoped_knowledge_graph, create_rag_manager

The legacy implementation lives in `app.services.rag_context_legacy`.
"""

from app.services.rag_context_legacy import build_rag_context
from app.services import rag_context_legacy as _legacy
from app.services.ai.rag_helpers import generate_multi_queries
from app.services.rag_module_old import get_scoped_knowledge_graph as _get_scoped_knowledge_graph


def get_rag_manager():
    """Compatibility hook for tests/legacy callers that monkeypatch this symbol."""
    return _legacy.get_rag_manager()


def get_scoped_knowledge_graph(*, scope: str, scope_id: str | None = None):
    """Compatibility hook for tests/legacy callers that monkeypatch this symbol."""
    return _get_scoped_knowledge_graph(scope=scope, scope_id=scope_id)


__all__ = ["build_rag_context", "get_rag_manager", "get_scoped_knowledge_graph", "generate_multi_queries"]
