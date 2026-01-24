"""
RAG Pipeline Adapter - Unified Entry Point

This module provides a unified entry point for RAG operations, bridging the
legacy build_rag_context() function and the new RAGPipeline class.

Strategy:
- When RAG_USE_NEW_PIPELINE=true, delegate to RAGPipeline
- When RAG_USE_NEW_PIPELINE=false (default), use legacy build_rag_context
- Maintains full backward compatibility with existing code

Usage:
    from app.services.rag.pipeline_adapter import build_rag_context_unified

    # Works identically to the old build_rag_context
    rag_context, graph_context, results = await build_rag_context_unified(
        query=query,
        rag_sources=["lei", "juris"],
        ...
    )

Migration Path:
    1. Set RAG_USE_NEW_PIPELINE=false (default) - uses legacy code
    2. Test with RAG_USE_NEW_PIPELINE=true - uses new pipeline
    3. Once validated, make new pipeline the default
    4. Eventually deprecate legacy path
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("RAGPipelineAdapter")

# Feature flag to control which pipeline to use
_USE_NEW_PIPELINE = os.getenv("RAG_USE_NEW_PIPELINE", "false").lower() in ("1", "true", "yes", "on")


def _format_results_for_prompt(results: List[Dict[str, Any]], max_chars: int = 12000) -> str:
    """Format RAG results as a string for prompt injection."""
    if not results:
        return ""

    lines = []
    total_chars = 0

    for i, result in enumerate(results, 1):
        text = result.get("text", "")
        source = result.get("source_type", result.get("dataset", "documento"))
        title = result.get("title", result.get("doc_title", ""))
        score = result.get("score", result.get("final_score", 0))

        # Build entry
        header = f"[{i}] {source}"
        if title:
            header += f" - {title}"
        if score:
            header += f" (relevância: {score:.2f})"

        entry = f"{header}\n{text}\n"

        if total_chars + len(entry) > max_chars:
            break

        lines.append(entry)
        total_chars += len(entry)

    return "\n---\n".join(lines)


def _format_graph_context(graph_data: Optional[Dict[str, Any]]) -> str:
    """Format graph enrichment data as a string."""
    if not graph_data:
        return ""

    parts = []

    # Related entities
    entities = graph_data.get("entities", [])
    if entities:
        parts.append("Entidades relacionadas:")
        for entity in entities[:10]:
            name = entity.get("name", entity.get("entity_id", ""))
            etype = entity.get("type", entity.get("entity_type", ""))
            parts.append(f"  - {name} ({etype})")

    # Related articles
    articles = graph_data.get("related_articles", [])
    if articles:
        parts.append("\nArtigos relacionados:")
        for art in articles[:10]:
            parts.append(f"  - {art}")

    # Summary if available
    summary = graph_data.get("summary", "")
    if summary:
        parts.append(f"\nResumo: {summary}")

    return "\n".join(parts)


async def _call_new_pipeline(
    query: str,
    rag_sources: Optional[List[str]],
    rag_top_k: Optional[int],
    tenant_id: str,
    scope_groups: Optional[List[str]],
    allow_global_scope: bool,
    graph_rag_enabled: bool,
    graph_hops: int,
    filters: Optional[Dict[str, Any]],
    **kwargs,
) -> Tuple[str, str, List[Dict[str, Any]]]:
    """
    Call the new RAGPipeline and convert results to legacy format.
    """
    try:
        from app.services.rag.pipeline.rag_pipeline import RAGPipeline, RAGPipelineConfig
        from app.services.rag.config import get_rag_config
    except ImportError as e:
        logger.warning(f"RAGPipeline not available, falling back to legacy: {e}")
        return await _call_legacy_pipeline(
            query=query,
            rag_sources=rag_sources,
            rag_top_k=rag_top_k,
            tenant_id=tenant_id,
            scope_groups=scope_groups,
            allow_global_scope=allow_global_scope,
            graph_rag_enabled=graph_rag_enabled,
            graph_hops=graph_hops,
            filters=filters,
            **kwargs,
        )

    config = get_rag_config()

    # Determine scope
    if allow_global_scope:
        scope = "global"
    elif scope_groups:
        scope = "group"
    else:
        scope = "private"

    # Map sources to indices/collections
    # This mapping may need adjustment based on your index naming
    indices = None
    collections = None
    if rag_sources:
        source_to_index = {
            "lei": config.opensearch_index_global,
            "juris": config.opensearch_index_global,
            "pecas_modelo": config.opensearch_index_global,
            "local": config.opensearch_index_local,
        }
        indices = [source_to_index.get(s, config.opensearch_index_global) for s in rag_sources]
        indices = list(set(indices))  # Deduplicate

    # Create pipeline instance
    pipeline = RAGPipeline()

    # Execute search
    try:
        result = await pipeline.search(
            query=query,
            indices=indices,
            collections=collections,
            top_k=rag_top_k,
            include_graph=graph_rag_enabled,
            tenant_id=tenant_id,
            scope=scope,
            filters=filters,
        )
    except Exception as e:
        logger.error(f"RAGPipeline.search failed: {e}")
        # Fall back to legacy
        return await _call_legacy_pipeline(
            query=query,
            rag_sources=rag_sources,
            rag_top_k=rag_top_k,
            tenant_id=tenant_id,
            scope_groups=scope_groups,
            allow_global_scope=allow_global_scope,
            graph_rag_enabled=graph_rag_enabled,
            graph_hops=graph_hops,
            filters=filters,
            **kwargs,
        )

    # Convert to legacy format
    rag_context_str = _format_results_for_prompt(result.results)

    graph_context_str = ""
    if result.graph_context:
        graph_context_str = _format_graph_context(result.graph_context.__dict__)

    return rag_context_str, graph_context_str, result.results


async def _call_legacy_pipeline(
    query: str,
    rag_sources: Optional[List[str]],
    rag_top_k: Optional[int],
    tenant_id: str,
    scope_groups: Optional[List[str]],
    allow_global_scope: bool,
    graph_rag_enabled: bool,
    graph_hops: int,
    filters: Optional[Dict[str, Any]],
    **kwargs,
) -> Tuple[str, str, List[Dict[str, Any]]]:
    """
    Call the legacy build_rag_context function.
    """
    from app.services.rag_context import build_rag_context

    return await build_rag_context(
        query=query,
        rag_sources=rag_sources,
        rag_top_k=rag_top_k,
        tenant_id=tenant_id,
        scope_groups=scope_groups,
        allow_global_scope=allow_global_scope,
        graph_rag_enabled=graph_rag_enabled,
        graph_hops=graph_hops,
        filters=filters,
        **kwargs,
    )


async def build_rag_context_unified(
    *,
    query: str,
    rag_sources: Optional[List[str]] = None,
    rag_top_k: Optional[int] = None,
    attachment_mode: str = "prompt_injection",
    adaptive_routing: bool = False,
    crag_gate: bool = False,
    crag_min_best_score: float = 0.5,
    crag_min_avg_score: float = 0.3,
    hyde_enabled: bool = False,
    multi_query: Optional[bool] = None,
    multi_query_max: Optional[int] = None,
    compression_enabled: Optional[bool] = None,
    compression_max_chars: Optional[int] = None,
    parent_child_enabled: Optional[bool] = None,
    parent_child_window: Optional[int] = None,
    parent_child_max_extra: Optional[int] = None,
    corrective_rag: Optional[bool] = None,
    corrective_use_hyde: Optional[bool] = None,
    corrective_min_best_score: Optional[float] = None,
    corrective_min_avg_score: Optional[float] = None,
    graph_rag_enabled: bool = False,
    graph_hops: int = 1,
    argument_graph_enabled: Optional[bool] = None,
    dense_research: bool = False,
    tenant_id: str = "",
    user_id: Optional[str] = None,
    scope_groups: Optional[List[str]] = None,
    allow_global_scope: Optional[bool] = None,
    allow_group_scope: Optional[bool] = None,
    history: Optional[List[dict]] = None,
    summary_text: Optional[str] = None,
    conversation_id: Optional[str] = None,
    request_id: Optional[str] = None,
    rewrite_query: bool = True,
    filters: Optional[Dict[str, Any]] = None,
    tipo_peca_filter: Optional[str] = None,
) -> Tuple[str, str, List[dict]]:
    """
    Unified entry point for RAG context building.

    This function provides the same interface as the legacy build_rag_context,
    but can optionally delegate to the new RAGPipeline based on configuration.

    Set RAG_USE_NEW_PIPELINE=true to use the new pipeline.

    Returns:
        Tuple of (rag_context_str, graph_context_str, results_list)
    """
    started_at = time.perf_counter()

    # Decide which pipeline to use
    use_new = _USE_NEW_PIPELINE

    # Features that require legacy pipeline (not yet in new pipeline)
    requires_legacy = any([
        history and rewrite_query,  # Query rewriting with history
        adaptive_routing,            # LLM-based source routing
        argument_graph_enabled,      # Argument graph integration
        dense_research,              # Dense research mode
    ])

    if requires_legacy and use_new:
        logger.info(
            f"Falling back to legacy pipeline: "
            f"history_rewrite={bool(history and rewrite_query)}, "
            f"adaptive_routing={adaptive_routing}, "
            f"argument_graph={argument_graph_enabled}, "
            f"dense_research={dense_research}"
        )
        use_new = False

    if use_new:
        logger.debug("Using new RAGPipeline")
        result = await _call_new_pipeline(
            query=query,
            rag_sources=rag_sources,
            rag_top_k=rag_top_k,
            tenant_id=tenant_id,
            scope_groups=scope_groups,
            allow_global_scope=allow_global_scope or False,
            graph_rag_enabled=graph_rag_enabled,
            graph_hops=graph_hops,
            filters=filters,
            # Pass remaining kwargs for potential future use
            crag_gate=crag_gate,
            hyde_enabled=hyde_enabled,
            multi_query=multi_query,
            compression_enabled=compression_enabled,
            parent_child_enabled=parent_child_enabled,
        )
    else:
        logger.debug("Using legacy build_rag_context")
        result = await _call_legacy_pipeline(
            query=query,
            rag_sources=rag_sources,
            rag_top_k=rag_top_k,
            attachment_mode=attachment_mode,
            adaptive_routing=adaptive_routing,
            crag_gate=crag_gate,
            crag_min_best_score=crag_min_best_score,
            crag_min_avg_score=crag_min_avg_score,
            hyde_enabled=hyde_enabled,
            multi_query=multi_query,
            multi_query_max=multi_query_max,
            compression_enabled=compression_enabled,
            compression_max_chars=compression_max_chars,
            parent_child_enabled=parent_child_enabled,
            parent_child_window=parent_child_window,
            parent_child_max_extra=parent_child_max_extra,
            corrective_rag=corrective_rag,
            corrective_use_hyde=corrective_use_hyde,
            corrective_min_best_score=corrective_min_best_score,
            corrective_min_avg_score=corrective_min_avg_score,
            graph_rag_enabled=graph_rag_enabled,
            graph_hops=graph_hops,
            argument_graph_enabled=argument_graph_enabled,
            dense_research=dense_research,
            tenant_id=tenant_id,
            user_id=user_id,
            scope_groups=scope_groups,
            allow_global_scope=allow_global_scope,
            allow_group_scope=allow_group_scope,
            history=history,
            summary_text=summary_text,
            conversation_id=conversation_id,
            request_id=request_id,
            rewrite_query=rewrite_query,
            filters=filters,
            tipo_peca_filter=tipo_peca_filter,
        )

    elapsed_ms = (time.perf_counter() - started_at) * 1000
    logger.info(f"RAG context built in {elapsed_ms:.1f}ms (pipeline={'new' if use_new else 'legacy'})")

    return result


# Convenience alias
build_rag_context = build_rag_context_unified
