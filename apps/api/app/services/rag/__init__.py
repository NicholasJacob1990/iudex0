"""
RAG (Retrieval-Augmented Generation) Module

Provides a complete RAG pipeline with:
- CRAG (Corrective RAG) gating for relevance validation
- Query expansion (HyDE, multi-query)
- Cross-encoder reranking
- Context compression
- Chunk expansion (parent-child)
- Legal knowledge graph enrichment
- Hybrid search (lexical + vector)
- Full tracing and observability
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .config import RAGConfig, get_rag_config

if TYPE_CHECKING:
    from .pipeline import RAGPipeline, PipelineResult, PipelineTrace


def __getattr__(name: str) -> Any:
    """Lazy import for pipeline module which may not exist yet."""
    _lazy_imports = {
        "RAGPipeline": ".pipeline",
        "PipelineResult": ".pipeline",
        "PipelineTrace": ".pipeline",
    }

    if name in _lazy_imports:
        import importlib
        module_name = _lazy_imports[name]
        try:
            module = importlib.import_module(module_name, package=__name__)
            return getattr(module, name)
        except (ImportError, AttributeError) as e:
            raise ImportError(
                f"{name} is not yet implemented. "
                f"Expected in {module_name} module."
            ) from e

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Main classes
    "RAGPipeline",
    "RAGConfig",
    "get_rag_config",
    # Convenience functions
    "rag_search",
]


async def rag_search(
    query: str,
    *,
    top_k: int = 10,
    sources: list[str] | None = None,
    case_id: str | None = None,
    user_id: str | None = None,
) -> "PipelineResult":
    """
    Convenience function for RAG search.

    Args:
        query: The search query
        top_k: Number of results to return
        sources: List of source types to search (e.g., ["lei", "juris"])
        case_id: Optional case ID for local document filtering
        user_id: Optional user ID for access control

    Returns:
        PipelineResult with chunks and trace information
    """
    from .pipeline import RAGPipeline

    config = get_rag_config()
    pipeline = RAGPipeline(config)
    return await pipeline.search(
        query=query,
        top_k=top_k,
        sources=sources,
        case_id=case_id,
        user_id=user_id,
    )
