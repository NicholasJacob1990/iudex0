"""
RAG Pipeline - Custom Exceptions

Hierarchical exception classes for structured error handling in the RAG pipeline.
These exceptions allow for:
- Fine-grained error handling per component
- Fail-soft behavior for optional components
- Proper error propagation for critical components
- Detailed logging with context

Exception Hierarchy:
    RAGPipelineError (base)
    ├── SearchError
    │   ├── LexicalSearchError
    │   └── VectorSearchError
    ├── EmbeddingError
    ├── RerankerError
    ├── CRAGError
    ├── GraphEnrichError
    ├── CompressionError
    └── ExpansionError
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class RAGPipelineError(Exception):
    """
    Base exception for all RAG pipeline errors.

    Attributes:
        message: Human-readable error description
        component: Name of the component that raised the error
        context: Additional context for debugging
        recoverable: Whether the pipeline can continue after this error
    """

    def __init__(
        self,
        message: str,
        *,
        component: str = "pipeline",
        context: Optional[Dict[str, Any]] = None,
        recoverable: bool = True,
        cause: Optional[Exception] = None,
    ) -> None:
        self.message = message
        self.component = component
        self.context = context or {}
        self.recoverable = recoverable
        self.cause = cause

        # Build detailed message
        detail_parts = [message]
        if context:
            detail_parts.append(f"context={context}")
        if cause:
            detail_parts.append(f"caused_by={type(cause).__name__}: {cause}")

        super().__init__(" | ".join(detail_parts))

    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for logging/tracing."""
        return {
            "error_type": type(self).__name__,
            "message": self.message,
            "component": self.component,
            "context": self.context,
            "recoverable": self.recoverable,
            "cause": str(self.cause) if self.cause else None,
        }


class SearchError(RAGPipelineError):
    """
    Base exception for search-related errors (lexical and vector).

    Attributes:
        query: The query that failed
        backend: The search backend that failed (opensearch, qdrant, neo4j)
    """

    def __init__(
        self,
        message: str,
        *,
        query: Optional[str] = None,
        backend: Optional[str] = None,
        indices: Optional[List[str]] = None,
        collections: Optional[List[str]] = None,
        context: Optional[Dict[str, Any]] = None,
        recoverable: bool = True,
        cause: Optional[Exception] = None,
    ) -> None:
        ctx = context or {}
        if query:
            ctx["query"] = query[:100] + "..." if len(query or "") > 100 else query
        if backend:
            ctx["backend"] = backend
        if indices:
            ctx["indices"] = indices
        if collections:
            ctx["collections"] = collections

        super().__init__(
            message,
            component="search",
            context=ctx,
            recoverable=recoverable,
            cause=cause,
        )
        self.query = query
        self.backend = backend


class LexicalSearchError(SearchError):
    """Exception for lexical (BM25/fulltext) search failures."""

    def __init__(
        self,
        message: str,
        *,
        query: Optional[str] = None,
        indices: Optional[List[str]] = None,
        backend: str = "opensearch",
        context: Optional[Dict[str, Any]] = None,
        recoverable: bool = True,
        cause: Optional[Exception] = None,
    ) -> None:
        super().__init__(
            message,
            query=query,
            backend=backend,
            indices=indices,
            context=context,
            recoverable=recoverable,
            cause=cause,
        )
        self.component = "lexical_search"


class VectorSearchError(SearchError):
    """Exception for vector (semantic) search failures."""

    def __init__(
        self,
        message: str,
        *,
        query: Optional[str] = None,
        collections: Optional[List[str]] = None,
        backend: str = "qdrant",
        context: Optional[Dict[str, Any]] = None,
        recoverable: bool = True,
        cause: Optional[Exception] = None,
    ) -> None:
        super().__init__(
            message,
            query=query,
            backend=backend,
            collections=collections,
            context=context,
            recoverable=recoverable,
            cause=cause,
        )
        self.component = "vector_search"


class EmbeddingError(RAGPipelineError):
    """
    Exception for embedding generation failures.

    Attributes:
        model: The embedding model that failed
        text_length: Length of text that failed to embed
    """

    def __init__(
        self,
        message: str,
        *,
        model: Optional[str] = None,
        text_length: Optional[int] = None,
        context: Optional[Dict[str, Any]] = None,
        recoverable: bool = True,
        cause: Optional[Exception] = None,
    ) -> None:
        ctx = context or {}
        if model:
            ctx["model"] = model
        if text_length is not None:
            ctx["text_length"] = text_length

        super().__init__(
            message,
            component="embeddings",
            context=ctx,
            recoverable=recoverable,
            cause=cause,
        )
        self.model = model
        self.text_length = text_length


class RerankerError(RAGPipelineError):
    """
    Exception for reranking failures.

    Attributes:
        model: The reranker model that failed
        candidates_count: Number of candidates being reranked
    """

    def __init__(
        self,
        message: str,
        *,
        model: Optional[str] = None,
        candidates_count: Optional[int] = None,
        context: Optional[Dict[str, Any]] = None,
        recoverable: bool = True,
        cause: Optional[Exception] = None,
    ) -> None:
        ctx = context or {}
        if model:
            ctx["model"] = model
        if candidates_count is not None:
            ctx["candidates_count"] = candidates_count

        super().__init__(
            message,
            component="reranker",
            context=ctx,
            recoverable=recoverable,
            cause=cause,
        )
        self.model = model
        self.candidates_count = candidates_count


class CRAGError(RAGPipelineError):
    """
    Exception for CRAG (Corrective RAG) gate failures.

    Attributes:
        decision: The CRAG decision at time of failure
        retry_count: Number of retries attempted
    """

    def __init__(
        self,
        message: str,
        *,
        decision: Optional[str] = None,
        retry_count: int = 0,
        results_count: Optional[int] = None,
        context: Optional[Dict[str, Any]] = None,
        recoverable: bool = True,
        cause: Optional[Exception] = None,
    ) -> None:
        ctx = context or {}
        if decision:
            ctx["decision"] = decision
        ctx["retry_count"] = retry_count
        if results_count is not None:
            ctx["results_count"] = results_count

        super().__init__(
            message,
            component="crag_gate",
            context=ctx,
            recoverable=recoverable,
            cause=cause,
        )
        self.decision = decision
        self.retry_count = retry_count


class GraphEnrichError(RAGPipelineError):
    """
    Exception for knowledge graph enrichment failures.

    Attributes:
        backend: The graph backend that failed (neo4j, networkx)
        entities_count: Number of entities being processed
    """

    def __init__(
        self,
        message: str,
        *,
        backend: Optional[str] = None,
        entities_count: Optional[int] = None,
        context: Optional[Dict[str, Any]] = None,
        recoverable: bool = True,
        cause: Optional[Exception] = None,
    ) -> None:
        ctx = context or {}
        if backend:
            ctx["backend"] = backend
        if entities_count is not None:
            ctx["entities_count"] = entities_count

        super().__init__(
            message,
            component="graph_enrich",
            context=ctx,
            recoverable=recoverable,
            cause=cause,
        )
        self.backend = backend
        self.entities_count = entities_count


class CompressionError(RAGPipelineError):
    """Exception for context compression failures."""

    def __init__(
        self,
        message: str,
        *,
        token_budget: Optional[int] = None,
        results_count: Optional[int] = None,
        context: Optional[Dict[str, Any]] = None,
        recoverable: bool = True,
        cause: Optional[Exception] = None,
    ) -> None:
        ctx = context or {}
        if token_budget is not None:
            ctx["token_budget"] = token_budget
        if results_count is not None:
            ctx["results_count"] = results_count

        super().__init__(
            message,
            component="compressor",
            context=ctx,
            recoverable=recoverable,
            cause=cause,
        )


class ExpansionError(RAGPipelineError):
    """Exception for chunk expansion failures."""

    def __init__(
        self,
        message: str,
        *,
        chunks_count: Optional[int] = None,
        window: Optional[int] = None,
        context: Optional[Dict[str, Any]] = None,
        recoverable: bool = True,
        cause: Optional[Exception] = None,
    ) -> None:
        ctx = context or {}
        if chunks_count is not None:
            ctx["chunks_count"] = chunks_count
        if window is not None:
            ctx["window"] = window

        super().__init__(
            message,
            component="expander",
            context=ctx,
            recoverable=recoverable,
            cause=cause,
        )


class QueryExpansionError(RAGPipelineError):
    """Exception for query expansion (HyDE/multi-query) failures."""

    def __init__(
        self,
        message: str,
        *,
        query: Optional[str] = None,
        expansion_type: Optional[str] = None,  # "hyde", "multiquery"
        context: Optional[Dict[str, Any]] = None,
        recoverable: bool = True,
        cause: Optional[Exception] = None,
    ) -> None:
        ctx = context or {}
        if query:
            ctx["query"] = query[:100] + "..." if len(query or "") > 100 else query
        if expansion_type:
            ctx["expansion_type"] = expansion_type

        super().__init__(
            message,
            component="query_expansion",
            context=ctx,
            recoverable=recoverable,
            cause=cause,
        )


class ComponentInitError(RAGPipelineError):
    """Exception for component initialization failures."""

    def __init__(
        self,
        message: str,
        *,
        component_name: str,
        context: Optional[Dict[str, Any]] = None,
        recoverable: bool = True,
        cause: Optional[Exception] = None,
    ) -> None:
        ctx = context or {}
        ctx["component_name"] = component_name

        super().__init__(
            message,
            component="initialization",
            context=ctx,
            recoverable=recoverable,
            cause=cause,
        )
        self.component_name = component_name


# Export all exceptions
__all__ = [
    "RAGPipelineError",
    "SearchError",
    "LexicalSearchError",
    "VectorSearchError",
    "EmbeddingError",
    "RerankerError",
    "CRAGError",
    "GraphEnrichError",
    "CompressionError",
    "ExpansionError",
    "QueryExpansionError",
    "ComponentInitError",
]
