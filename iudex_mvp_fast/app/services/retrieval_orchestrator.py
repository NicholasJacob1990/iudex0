"""
Retrieval Orchestrator

Hybrid retrieval combining lexical (OpenSearch) and vector (Qdrant) search
with advanced query expansion techniques (HyDE, Multi-Query).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional

from app.services.query_expansion import (
    QueryExpansionConfig,
    QueryExpansionService,
    get_query_expansion_service,
    merge_lexical_vector_rrf,
    merge_results_rrf,
    rrf_score,
)

logger = logging.getLogger("RetrievalOrchestrator")


def _rrf(rank: int, k: int = 60) -> float:
    """Calculate RRF score for a given rank."""
    return rrf_score(rank, k)


class RetrievalOrchestrator:
    """
    Orchestrates hybrid retrieval with optional query expansion.

    Supports:
    - Basic hybrid search (lexical + vector with RRF)
    - HyDE (Hypothetical Document Embeddings) search
    - Multi-Query search with parallel execution
    - Advanced search combining HyDE + Multi-Query
    """

    def __init__(
        self,
        query_expansion_service: Optional[QueryExpansionService] = None,
        config: Optional[QueryExpansionConfig] = None,
    ):
        """
        Initialize the orchestrator.

        Args:
            query_expansion_service: Pre-configured QueryExpansionService instance
            config: Configuration for query expansion (if service not provided)
        """
        self._query_expansion_service = query_expansion_service
        self._config = config

    @property
    def query_expansion_service(self) -> QueryExpansionService:
        """Lazy-initialize query expansion service."""
        if self._query_expansion_service is None:
            self._query_expansion_service = get_query_expansion_service(
                config=self._config
            )
        return self._query_expansion_service

    # -----------------------------------------------------------------------
    # Basic Hybrid Search (Original Implementation)
    # -----------------------------------------------------------------------

    def merge_results(
        self,
        lexical: List[Dict[str, Any]],
        vector: List[Dict[str, Any]],
        top_k: int = 10,
        k_rrf: int = 60,
        w_lex: float = 0.5,
        w_vec: float = 0.5,
    ) -> List[Dict[str, Any]]:
        """
        Merge lexical and vector results using weighted RRF.

        This is the original merge implementation for backward compatibility.
        """
        return merge_lexical_vector_rrf(
            lexical=lexical,
            vector=vector,
            top_k=top_k,
            k_rrf=k_rrf,
            w_lex=w_lex,
            w_vec=w_vec,
        )

    # -----------------------------------------------------------------------
    # HyDE Search
    # -----------------------------------------------------------------------

    async def hyde_search(
        self,
        query: str,
        lexical_search_fn: Callable[[str, int], List[Dict[str, Any]]],
        vector_search_fn: Callable[[str, int], List[Dict[str, Any]]],
        embed_fn: Optional[Callable[[str], List[float]]] = None,
        top_k: int = 10,
        fetch_k: int = 30,
        use_cache: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Perform HyDE-enhanced hybrid search.

        HyDE (Hypothetical Document Embeddings) generates a hypothetical
        answer document using an LLM, then uses that document for semantic
        search. This improves retrieval quality for complex queries.

        Args:
            query: User's natural language query
            lexical_search_fn: Function(query, k) -> results for BM25/lexical search
            vector_search_fn: Function(query_text, k) -> results for vector search
            embed_fn: Optional embedding function (not used directly, for interface compat)
            top_k: Number of final results to return
            fetch_k: Number of candidates to fetch from each source
            use_cache: Whether to cache hypothetical documents

        Returns:
            List of ranked results with HyDE metadata

        Example:
            async def lexical_fn(q, k):
                return opensearch.search_lexical([index], q, filter_query, k)

            async def vector_fn(q, k):
                vec = embeddings.embed_query(q)
                return qdrant.search(collection, vec, filter, k)

            results = await orchestrator.hyde_search(
                query="O que configura rescisao indireta?",
                lexical_search_fn=lexical_fn,
                vector_search_fn=vector_fn,
            )
        """
        return await self.query_expansion_service.hyde_search(
            query=query,
            lexical_search_fn=lexical_search_fn,
            vector_search_fn=vector_search_fn,
            embed_fn=embed_fn or (lambda x: []),
            top_k=top_k,
            fetch_k=fetch_k,
            use_cache=use_cache,
        )

    def hyde_search_sync(
        self,
        query: str,
        lexical_search_fn: Callable[[str, int], List[Dict[str, Any]]],
        vector_search_fn: Callable[[str, int], List[Dict[str, Any]]],
        embed_fn: Optional[Callable[[str], List[float]]] = None,
        top_k: int = 10,
        fetch_k: int = 30,
        use_cache: bool = True,
    ) -> List[Dict[str, Any]]:
        """Synchronous wrapper for hyde_search."""
        return asyncio.run(
            self.hyde_search(
                query=query,
                lexical_search_fn=lexical_search_fn,
                vector_search_fn=vector_search_fn,
                embed_fn=embed_fn,
                top_k=top_k,
                fetch_k=fetch_k,
                use_cache=use_cache,
            )
        )

    # -----------------------------------------------------------------------
    # Multi-Query Search
    # -----------------------------------------------------------------------

    async def multi_query_search(
        self,
        query: str,
        search_fn: Callable[[str, int], List[Dict[str, Any]]],
        top_k: int = 10,
        fetch_k: int = 20,
        variant_count: Optional[int] = None,
        use_cache: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Perform multi-query search with RRF fusion.

        Generates multiple query variants (reformulations, expansions)
        and executes them in parallel, then merges results using RRF.

        Args:
            query: Original user query
            search_fn: Search function(query, k) -> results (can be hybrid or single source)
            top_k: Number of final results to return
            fetch_k: Number of candidates per variant
            variant_count: Number of query variants (default: 4)
            use_cache: Whether to cache query variants

        Returns:
            Merged and deduplicated results

        Example:
            def hybrid_search(q, k):
                lex = opensearch.search_lexical([index], q, filter, k)
                vec_embed = embeddings.embed_query(q)
                vec = qdrant.search(collection, vec_embed, filter, k)
                return orchestrator.merge_results(lex, vec, top_k=k)

            results = await orchestrator.multi_query_search(
                query="requisitos habeas corpus",
                search_fn=hybrid_search,
            )
        """
        return await self.query_expansion_service.multi_query_search(
            query=query,
            search_fn=search_fn,
            top_k=top_k,
            fetch_k=fetch_k,
            variant_count=variant_count,
            use_cache=use_cache,
        )

    def multi_query_search_sync(
        self,
        query: str,
        search_fn: Callable[[str, int], List[Dict[str, Any]]],
        top_k: int = 10,
        fetch_k: int = 20,
        variant_count: Optional[int] = None,
        use_cache: bool = True,
    ) -> List[Dict[str, Any]]:
        """Synchronous wrapper for multi_query_search."""
        return asyncio.run(
            self.multi_query_search(
                query=query,
                search_fn=search_fn,
                top_k=top_k,
                fetch_k=fetch_k,
                variant_count=variant_count,
                use_cache=use_cache,
            )
        )

    # -----------------------------------------------------------------------
    # Advanced Search (HyDE + Multi-Query)
    # -----------------------------------------------------------------------

    async def advanced_search(
        self,
        query: str,
        lexical_search_fn: Callable[[str, int], List[Dict[str, Any]]],
        vector_search_fn: Callable[[str, int], List[Dict[str, Any]]],
        embed_fn: Optional[Callable[[str], List[float]]] = None,
        top_k: int = 10,
        fetch_k: int = 30,
        use_hyde: bool = True,
        use_multi_query: bool = True,
        use_cache: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Perform advanced search combining HyDE and Multi-Query.

        This is the most comprehensive search strategy:
        1. Generate multiple query variants
        2. For each variant, generate hypothetical document (HyDE)
        3. Execute parallel lexical + vector searches
        4. Merge all results with RRF

        Use this for high-quality retrieval when latency is acceptable.

        Args:
            query: User's natural language query
            lexical_search_fn: Function for lexical/BM25 search
            vector_search_fn: Function for vector/semantic search
            embed_fn: Optional embedding function
            top_k: Number of final results
            fetch_k: Candidates per variant
            use_hyde: Enable HyDE hypothetical document generation
            use_multi_query: Enable query variant generation
            use_cache: Cache expanded queries and hypothetical docs

        Returns:
            Merged results with advanced search metadata
        """
        return await self.query_expansion_service.advanced_search(
            query=query,
            lexical_search_fn=lexical_search_fn,
            vector_search_fn=vector_search_fn,
            embed_fn=embed_fn,
            top_k=top_k,
            fetch_k=fetch_k,
            use_hyde=use_hyde,
            use_multi_query=use_multi_query,
            use_cache=use_cache,
        )

    def advanced_search_sync(
        self,
        query: str,
        lexical_search_fn: Callable[[str, int], List[Dict[str, Any]]],
        vector_search_fn: Callable[[str, int], List[Dict[str, Any]]],
        embed_fn: Optional[Callable[[str], List[float]]] = None,
        top_k: int = 10,
        fetch_k: int = 30,
        use_hyde: bool = True,
        use_multi_query: bool = True,
        use_cache: bool = True,
    ) -> List[Dict[str, Any]]:
        """Synchronous wrapper for advanced_search."""
        return asyncio.run(
            self.advanced_search(
                query=query,
                lexical_search_fn=lexical_search_fn,
                vector_search_fn=vector_search_fn,
                embed_fn=embed_fn,
                top_k=top_k,
                fetch_k=fetch_k,
                use_hyde=use_hyde,
                use_multi_query=use_multi_query,
                use_cache=use_cache,
            )
        )

    # -----------------------------------------------------------------------
    # Query Expansion Utilities
    # -----------------------------------------------------------------------

    async def generate_hypothetical_document(
        self,
        query: str,
        use_cache: bool = True,
    ) -> str:
        """
        Generate a hypothetical document for the given query.
        Useful for inspecting HyDE output or custom implementations.
        """
        return await self.query_expansion_service.generate_hypothetical_document(
            query=query,
            use_cache=use_cache,
        )

    async def generate_query_variants(
        self,
        query: str,
        count: Optional[int] = None,
        use_cache: bool = True,
    ) -> List[str]:
        """
        Generate query variants for multi-query retrieval.
        Useful for inspecting variant generation or custom implementations.
        """
        return await self.query_expansion_service.generate_query_variants(
            query=query,
            count=count,
            use_cache=use_cache,
        )

    async def rewrite_query(
        self,
        query: str,
        use_cache: bool = True,
    ) -> str:
        """
        Rewrite query for optimal retrieval.
        Useful as a preprocessing step.
        """
        return await self.query_expansion_service.rewrite_query(
            query=query,
            use_cache=use_cache,
        )

    # -----------------------------------------------------------------------
    # Cache Management
    # -----------------------------------------------------------------------

    def clear_expansion_cache(self) -> None:
        """Clear the query expansion cache."""
        self.query_expansion_service.clear_cache()

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics for query expansion."""
        return self.query_expansion_service.get_cache_stats()


# ---------------------------------------------------------------------------
# Convenience Functions
# ---------------------------------------------------------------------------

def create_orchestrator(
    api_key: Optional[str] = None,
    config: Optional[QueryExpansionConfig] = None,
) -> RetrievalOrchestrator:
    """
    Create a new RetrievalOrchestrator with optional configuration.

    Args:
        api_key: OpenAI API key for LLM-based query expansion
        config: Query expansion configuration

    Returns:
        Configured RetrievalOrchestrator instance
    """
    service = QueryExpansionService(api_key=api_key, config=config)
    return RetrievalOrchestrator(query_expansion_service=service)


# ---------------------------------------------------------------------------
# Enhanced Retrieval Pipeline with Reranking, Compression, and Expansion
# ---------------------------------------------------------------------------

from app.services.reranker import (
    CrossEncoderReranker,
    RerankerConfig,
    RerankerResult,
    rerank,
)
from app.services.context_compressor import (
    ContextCompressor,
    CompressionConfig,
    CompressionResult,
    TokenBudgetManager,
    compress_context,
)
from app.services.chunk_expander import (
    ChunkExpander,
    ExpansionConfig,
    ExpansionResult,
    expand_chunks,
    create_expander_with_qdrant,
    create_expander_with_opensearch,
)


class EnhancedRetrievalPipeline:
    """
    Complete retrieval pipeline with reranking, expansion, and compression.

    Stages:
    1. Initial retrieval (lexical + vector hybrid)
    2. Cross-encoder reranking
    3. Chunk expansion (neighbors/parent)
    4. Context compression

    This pipeline provides the highest quality results while managing
    token budgets for downstream LLM consumption.
    """

    def __init__(
        self,
        orchestrator: Optional[RetrievalOrchestrator] = None,
        reranker: Optional[CrossEncoderReranker] = None,
        expander: Optional[ChunkExpander] = None,
        compressor: Optional[ContextCompressor] = None,
        budget_manager: Optional[TokenBudgetManager] = None,
    ):
        """
        Initialize the enhanced pipeline.

        Args:
            orchestrator: Base retrieval orchestrator
            reranker: Cross-encoder reranker
            expander: Chunk expander
            compressor: Context compressor
            budget_manager: Token budget manager
        """
        self.orchestrator = orchestrator or RetrievalOrchestrator()
        self.reranker = reranker or CrossEncoderReranker.get_instance()
        self.expander = expander or ChunkExpander()
        self.compressor = compressor or ContextCompressor()
        self.budget_manager = budget_manager or TokenBudgetManager.from_env()

    def process(
        self,
        query: str,
        initial_results: List[Dict[str, Any]],
        *,
        enable_reranking: bool = True,
        enable_expansion: bool = True,
        enable_compression: bool = True,
        rerank_top_k: Optional[int] = None,
        expansion_window: Optional[int] = None,
        max_extra_chunks: Optional[int] = None,
        token_budget: Optional[int] = None,
        max_chars_per_chunk: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Process retrieval results through the complete pipeline.

        Args:
            query: The search query
            initial_results: Results from initial retrieval
            enable_reranking: Enable cross-encoder reranking
            enable_expansion: Enable chunk expansion
            enable_compression: Enable context compression
            rerank_top_k: Top-k for reranking output
            expansion_window: Window size for neighbor expansion
            max_extra_chunks: Maximum extra chunks to add
            token_budget: Total token budget
            max_chars_per_chunk: Max chars per compressed chunk

        Returns:
            Dict with processed results and pipeline statistics
        """
        import time
        start_time = time.perf_counter()

        stats = {
            "initial_count": len(initial_results),
            "reranking": None,
            "expansion": None,
            "compression": None,
        }

        results = initial_results

        # Stage 1: Reranking
        if enable_reranking and results:
            rerank_result = self.reranker.rerank(
                query=query,
                results=results,
                top_k=rerank_top_k,
            )
            results = rerank_result.results
            stats["reranking"] = {
                "input": rerank_result.original_count,
                "output": rerank_result.reranked_count,
                "model": rerank_result.model_used,
                "duration_ms": rerank_result.duration_ms,
            }

        # Stage 2: Expansion
        if enable_expansion and results:
            expansion_result = self.expander.expand_results(
                results=results,
                window=expansion_window,
                max_extra_total=max_extra_chunks,
            )
            results = expansion_result.results
            stats["expansion"] = {
                "input": expansion_result.original_count,
                "output": expansion_result.expanded_count,
                "extra_added": expansion_result.extra_chunks_added,
                "merged_groups": expansion_result.merged_groups,
                "duration_ms": expansion_result.duration_ms,
            }

        # Stage 3: Compression
        if enable_compression and results:
            compression_result = self.compressor.compress_results(
                query=query,
                results=results,
                max_chars_per_chunk=max_chars_per_chunk,
                token_budget=token_budget,
            )
            results = compression_result.results
            stats["compression"] = {
                "original_chars": compression_result.original_chars,
                "compressed_chars": compression_result.compressed_chars,
                "compression_ratio": compression_result.compression_ratio,
                "chunks_compressed": compression_result.chunks_compressed,
                "duration_ms": compression_result.duration_ms,
            }

        total_duration_ms = (time.perf_counter() - start_time) * 1000
        stats["total_duration_ms"] = total_duration_ms
        stats["final_count"] = len(results)

        return {
            "results": results,
            "stats": stats,
        }

    async def search_and_process(
        self,
        query: str,
        lexical_search_fn: Callable[[str, int], List[Dict[str, Any]]],
        vector_search_fn: Callable[[str, int], List[Dict[str, Any]]],
        *,
        fetch_k: int = 30,
        top_k: int = 10,
        use_hyde: bool = False,
        use_multi_query: bool = False,
        enable_reranking: bool = True,
        enable_expansion: bool = True,
        enable_compression: bool = True,
        **pipeline_kwargs,
    ) -> Dict[str, Any]:
        """
        Perform complete search and post-processing pipeline.

        Combines:
        - Query expansion (HyDE / Multi-Query)
        - Hybrid search (lexical + vector)
        - Cross-encoder reranking
        - Chunk expansion
        - Context compression

        Args:
            query: Search query
            lexical_search_fn: Lexical search function
            vector_search_fn: Vector search function
            fetch_k: Initial candidates to fetch
            top_k: Final results to return
            use_hyde: Enable HyDE expansion
            use_multi_query: Enable multi-query expansion
            enable_reranking: Enable cross-encoder reranking
            enable_expansion: Enable chunk expansion
            enable_compression: Enable context compression
            **pipeline_kwargs: Additional args for process()

        Returns:
            Dict with results and complete pipeline stats
        """
        # Step 1: Initial retrieval
        if use_hyde or use_multi_query:
            initial_results = await self.orchestrator.advanced_search(
                query=query,
                lexical_search_fn=lexical_search_fn,
                vector_search_fn=vector_search_fn,
                top_k=fetch_k,
                fetch_k=fetch_k,
                use_hyde=use_hyde,
                use_multi_query=use_multi_query,
            )
        else:
            # Basic hybrid search
            lex_results = lexical_search_fn(query, fetch_k)
            vec_results = vector_search_fn(query, fetch_k)
            initial_results = self.orchestrator.merge_results(
                lexical=lex_results,
                vector=vec_results,
                top_k=fetch_k,
            )

        # Step 2: Pipeline processing
        pipeline_kwargs.setdefault("rerank_top_k", top_k)
        result = self.process(
            query=query,
            initial_results=initial_results,
            enable_reranking=enable_reranking,
            enable_expansion=enable_expansion,
            enable_compression=enable_compression,
            **pipeline_kwargs,
        )

        result["query"] = query
        result["search_mode"] = (
            "advanced" if (use_hyde or use_multi_query)
            else "hybrid"
        )

        return result


def create_enhanced_pipeline(
    qdrant_service: Optional[Any] = None,
    opensearch_service: Optional[Any] = None,
    collection: Optional[str] = None,
    index: Optional[str] = None,
    orchestrator: Optional[RetrievalOrchestrator] = None,
    reranker_config: Optional[RerankerConfig] = None,
    expansion_config: Optional[ExpansionConfig] = None,
    compression_config: Optional[CompressionConfig] = None,
) -> EnhancedRetrievalPipeline:
    """
    Create an enhanced retrieval pipeline with storage backends configured.

    Args:
        qdrant_service: Optional Qdrant service for expansion
        opensearch_service: Optional OpenSearch service for expansion
        collection: Qdrant collection name
        index: OpenSearch index name
        orchestrator: Base retrieval orchestrator
        reranker_config: Reranker configuration
        expansion_config: Chunk expansion configuration
        compression_config: Context compression configuration

    Returns:
        Configured EnhancedRetrievalPipeline
    """
    # Create expander with storage backend if available
    expander = None
    if qdrant_service and collection:
        expander = create_expander_with_qdrant(
            qdrant_service=qdrant_service,
            collection=collection,
            config=expansion_config,
        )
    elif opensearch_service and index:
        expander = create_expander_with_opensearch(
            opensearch_service=opensearch_service,
            index=index,
            config=expansion_config,
        )
    else:
        expander = ChunkExpander(expansion_config)

    # Create other components
    reranker = CrossEncoderReranker(reranker_config) if reranker_config else None
    compressor = ContextCompressor(compression_config) if compression_config else None

    return EnhancedRetrievalPipeline(
        orchestrator=orchestrator,
        reranker=reranker,
        expander=expander,
        compressor=compressor,
    )
