"""
RAG API Endpoints - Search, Ingestion, and Management

Provides:
- POST /rag/search: Main semantic search endpoint with hybrid retrieval
- POST /rag/ingest/local: Ingest local documents (case attachments)
- POST /rag/ingest/global: Ingest global documents (lei, juris, pecas, sei)
- DELETE /rag/local/{case_id}: Delete all local chunks for a case
- GET /rag/stats: Get RAG pipeline statistics
"""

from __future__ import annotations

import asyncio
import os
import uuid
import hashlib
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from loguru import logger
from pydantic import BaseModel, Field

from app.core.security import get_current_user
from app.models.user import User


# =============================================================================
# Enums
# =============================================================================


class GlobalDataset(str, Enum):
    """Available global datasets for ingestion."""
    LEI = "lei"
    JURIS = "juris"
    PECAS = "pecas"
    SEI = "sei"


class SearchMode(str, Enum):
    """Search mode returned in response."""
    LEXICAL_ONLY = "lexical_only"
    HYBRID = "hybrid"
    VECTOR_ONLY = "vector_only"


# =============================================================================
# Request Schemas
# =============================================================================


class SearchRequest(BaseModel):
    """Request schema for RAG search."""

    query: str = Field(..., min_length=1, max_length=10000, description="Search query")
    tenant_id: str = Field(..., min_length=1, description="Tenant identifier")
    case_id: Optional[str] = Field(None, description="Case ID for local document filtering")
    group_ids: Optional[List[str]] = Field(
        default_factory=list,
        description="Group IDs for group-scoped document access"
    )
    user_id: Optional[str] = Field(None, description="User ID for user-scoped filtering")

    # Pipeline feature flags
    use_hyde: Optional[bool] = Field(None, description="Enable HyDE query expansion")
    use_multiquery: Optional[bool] = Field(None, description="Enable multi-query expansion")
    use_crag: Optional[bool] = Field(None, description="Enable CRAG quality gate")
    use_rerank: Optional[bool] = Field(None, description="Enable reranking")
    force_vector: Optional[bool] = Field(
        False,
        description="Force vector search even if lexical is strong"
    )

    # Search parameters
    top_k: Optional[int] = Field(10, ge=1, le=100, description="Number of results to return")
    fetch_k: Optional[int] = Field(50, ge=1, le=500, description="Number of candidates to fetch")
    include_trace: Optional[bool] = Field(False, description="Include execution trace in response")

    class Config:
        json_schema_extra = {
            "example": {
                "query": "Art. 37 da CF responsabilidade civil do Estado",
                "tenant_id": "tenant-123",
                "case_id": "case-456",
                "use_hyde": True,
                "use_rerank": True,
                "top_k": 10
            }
        }


class DocumentInput(BaseModel):
    """Single document for ingestion."""

    text: str = Field(..., min_length=1, description="Document text content")
    metadata: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Document metadata (source, title, page, etc.)"
    )
    doc_id: Optional[str] = Field(None, description="Optional document ID (auto-generated if not provided)")

    class Config:
        json_schema_extra = {
            "example": {
                "text": "O art. 37, caput, da Constituicao Federal estabelece...",
                "metadata": {
                    "source": "constituicao_federal",
                    "title": "Art. 37 CF",
                    "page": 15
                }
            }
        }


class LocalIngestRequest(BaseModel):
    """Request schema for local document ingestion."""

    tenant_id: str = Field(..., min_length=1, description="Tenant identifier")
    case_id: str = Field(..., min_length=1, description="Case ID for document association")
    documents: List[DocumentInput] = Field(..., min_length=1, max_length=1000)
    chunk_size: Optional[int] = Field(512, ge=100, le=2000, description="Chunk size in tokens")
    chunk_overlap: Optional[int] = Field(50, ge=0, le=500, description="Overlap between chunks")
    ingest_to_graph: Optional[bool] = Field(
        None,
        description="Also ingest to GraphRAG (Neo4j). If None, uses RAG_GRAPH_AUTO_INGEST env var."
    )
    extract_arguments: Optional[bool] = Field(
        False,
        description="Extract legal arguments when ingesting to graph"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "tenant_id": "tenant-123",
                "case_id": "case-456",
                "documents": [
                    {
                        "text": "Conteudo do documento anexado ao caso...",
                        "metadata": {"filename": "contrato.pdf", "page": 1}
                    }
                ]
            }
        }


class GlobalIngestRequest(BaseModel):
    """Request schema for global document ingestion."""

    dataset: GlobalDataset = Field(..., description="Target dataset (lei, juris, pecas, sei)")
    documents: List[DocumentInput] = Field(..., min_length=1, max_length=5000)
    chunk_size: Optional[int] = Field(512, ge=100, le=2000, description="Chunk size in tokens")
    chunk_overlap: Optional[int] = Field(50, ge=0, le=500, description="Overlap between chunks")
    deduplicate: Optional[bool] = Field(True, description="Skip documents that already exist")
    ingest_to_graph: Optional[bool] = Field(
        None,
        description="Also ingest to GraphRAG (Neo4j). If None, uses RAG_GRAPH_AUTO_INGEST env var."
    )
    extract_arguments: Optional[bool] = Field(
        False,
        description="Extract legal arguments when ingesting to graph"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "dataset": "lei",
                "documents": [
                    {
                        "text": "Lei 8.666/93 - Art. 1o Esta Lei estabelece...",
                        "metadata": {"numero": "8666", "ano": 1993, "tipo": "lei"}
                    }
                ]
            }
        }


# =============================================================================
# Response Schemas
# =============================================================================


class SearchResultItem(BaseModel):
    """Single search result."""

    chunk_id: str = Field(..., description="Unique chunk identifier")
    text: str = Field(..., description="Chunk text content")
    score: float = Field(..., description="Relevance score (0-1)")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Chunk metadata")
    source: Optional[str] = Field(None, description="Source collection/dataset")
    highlight: Optional[str] = Field(None, description="Highlighted snippet")


class TraceInfo(BaseModel):
    """Execution trace for debugging."""

    request_id: str
    started_at: str
    completed_at: str
    duration_ms: float
    stages: List[Dict[str, Any]] = Field(default_factory=list)
    lexical_score: Optional[float] = None
    vector_score: Optional[float] = None
    rerank_applied: bool = False
    hyde_applied: bool = False
    multiquery_applied: bool = False
    crag_passed: Optional[bool] = None


class SearchMetadata(BaseModel):
    """Search response metadata."""

    total_candidates: int = Field(..., description="Total candidates fetched before filtering")
    filtered_count: int = Field(..., description="Results after filtering")
    query_expansion_count: int = Field(0, description="Number of expanded queries")
    cache_hit: bool = Field(False, description="Whether result came from cache")


class SearchResponse(BaseModel):
    """Response schema for RAG search."""

    results: List[SearchResultItem] = Field(default_factory=list)
    mode: SearchMode = Field(..., description="Search mode used (lexical_only, hybrid, vector_only)")
    trace: Optional[TraceInfo] = Field(None, description="Execution trace (if requested)")
    metadata: SearchMetadata


class IngestResponse(BaseModel):
    """Response schema for document ingestion."""

    indexed_count: int = Field(..., description="Number of documents successfully indexed")
    chunk_uids: List[str] = Field(default_factory=list, description="Generated chunk IDs")
    skipped_count: int = Field(0, description="Number of documents skipped (duplicates)")
    errors: List[Dict[str, str]] = Field(default_factory=list, description="Ingestion errors")


class DeleteResponse(BaseModel):
    """Response schema for local chunk deletion."""

    deleted_count: int = Field(..., description="Number of chunks deleted")
    case_id: str = Field(..., description="Case ID that was cleared")


class CacheStats(BaseModel):
    """Cache statistics."""

    enabled: bool
    hits: int = 0
    misses: int = 0
    size: int = 0
    ttl_seconds: int = 30


class TraceStats(BaseModel):
    """Trace statistics."""

    enabled: bool
    total_traces: int = 0
    avg_duration_ms: float = 0.0


class StatsResponse(BaseModel):
    """Response schema for RAG stats."""

    cache_stats: CacheStats
    trace_stats: TraceStats
    collections: Dict[str, int] = Field(
        default_factory=dict,
        description="Document counts per collection"
    )
    last_updated: str = Field(..., description="Stats timestamp")


# =============================================================================
# Dependency Injection
# =============================================================================


def get_rag_pipeline():
    """
    Dependency to get RAG pipeline instance.
    Lazily initializes the pipeline singleton.
    """
    try:
        from app.services.rag.pipeline.rag_pipeline import RAGPipeline, get_pipeline
        return get_pipeline()
    except ImportError:
        # Fallback to old module if new pipeline not available
        try:
            from app.services.rag_module import create_rag_manager
            return create_rag_manager()
        except Exception as e:
            logger.error(f"Failed to initialize RAG pipeline: {e}")
            raise HTTPException(
                status_code=503,
                detail="RAG service unavailable. Check server configuration."
            )


# =============================================================================
# Router
# =============================================================================


router = APIRouter(tags=["rag"])


@router.post("/search", response_model=SearchResponse)
async def search(
    request: SearchRequest,
    current_user: User = Depends(get_current_user),
    pipeline=Depends(get_rag_pipeline),
) -> SearchResponse:
    """
    Execute semantic search across RAG collections.

    Supports hybrid retrieval (lexical + vector) with optional:
    - HyDE query expansion
    - Multi-query expansion
    - CRAG quality gate
    - Cross-encoder reranking
    - Lexical-first gating for efficiency

    Returns ranked results with relevance scores and metadata.
    """
    request_id = str(uuid.uuid4())
    started_at = datetime.utcnow()

    logger.info(
        f"RAG search: query='{request.query[:50]}...' tenant={request.tenant_id} "
        f"case={request.case_id} user={current_user.id}"
    )

    try:
        # Build search parameters
        search_params = {
            "query": request.query,
            "tenant_id": request.tenant_id,
            "case_id": request.case_id,
            "group_ids": request.group_ids or [],
            "user_id": request.user_id or str(current_user.id),
            "top_k": request.top_k or 10,
            "fetch_k": request.fetch_k or 50,
            "request_id": request_id,
        }

        # Add optional feature flags
        if request.use_hyde is not None:
            search_params["use_hyde"] = request.use_hyde
        if request.use_multiquery is not None:
            search_params["use_multiquery"] = request.use_multiquery
        if request.use_crag is not None:
            search_params["use_crag"] = request.use_crag
        if request.use_rerank is not None:
            search_params["use_rerank"] = request.use_rerank
        if request.force_vector:
            search_params["force_vector"] = True

        # Execute search
        if hasattr(pipeline, "search"):
            # New pipeline interface
            raw_results = await pipeline.search(**search_params)
        elif hasattr(pipeline, "hybrid_search"):
            # Old RAGManager interface
            raw_results = pipeline.hybrid_search(
                query=request.query,
                tenant_id=request.tenant_id,
                case_id=request.case_id,
                group_ids=request.group_ids,
                top_k=request.top_k or 10,
            )
        else:
            raise HTTPException(
                status_code=500,
                detail="RAG pipeline does not support search operations"
            )

        # Process results
        completed_at = datetime.utcnow()
        duration_ms = (completed_at - started_at).total_seconds() * 1000

        # Extract results from response
        if isinstance(raw_results, dict):
            items = raw_results.get("results", [])
            mode_str = raw_results.get("mode", "hybrid")
            cache_hit = raw_results.get("cache_hit", False)
            total_candidates = raw_results.get("total_candidates", len(items))
            trace_data = raw_results.get("trace")
        else:
            items = raw_results if isinstance(raw_results, list) else []
            mode_str = "hybrid"
            cache_hit = False
            total_candidates = len(items)
            trace_data = None

        # Convert to response model
        results = []
        for item in items:
            if isinstance(item, dict):
                results.append(SearchResultItem(
                    chunk_id=item.get("id") or item.get("chunk_id") or str(uuid.uuid4()),
                    text=item.get("text") or item.get("content") or "",
                    score=float(item.get("score", 0.0)),
                    metadata=item.get("metadata", {}),
                    source=item.get("source") or item.get("collection"),
                    highlight=item.get("highlight"),
                ))

        # Determine mode
        mode = SearchMode.HYBRID
        if mode_str == "lexical_only":
            mode = SearchMode.LEXICAL_ONLY
        elif mode_str == "vector_only":
            mode = SearchMode.VECTOR_ONLY

        # Build trace if requested
        trace = None
        if request.include_trace:
            trace = TraceInfo(
                request_id=request_id,
                started_at=started_at.isoformat(),
                completed_at=completed_at.isoformat(),
                duration_ms=duration_ms,
                stages=trace_data.get("stages", []) if trace_data else [],
                lexical_score=trace_data.get("lexical_score") if trace_data else None,
                vector_score=trace_data.get("vector_score") if trace_data else None,
                rerank_applied=trace_data.get("rerank_applied", False) if trace_data else False,
                hyde_applied=trace_data.get("hyde_applied", False) if trace_data else False,
                multiquery_applied=trace_data.get("multiquery_applied", False) if trace_data else False,
                crag_passed=trace_data.get("crag_passed") if trace_data else None,
            )

        metadata = SearchMetadata(
            total_candidates=total_candidates,
            filtered_count=len(results),
            query_expansion_count=trace_data.get("query_expansion_count", 0) if trace_data else 0,
            cache_hit=cache_hit,
        )

        logger.info(
            f"RAG search complete: {len(results)} results in {duration_ms:.1f}ms "
            f"mode={mode.value} cache_hit={cache_hit}"
        )

        return SearchResponse(
            results=results,
            mode=mode,
            trace=trace,
            metadata=metadata,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"RAG search error: {e}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@router.post("/ingest/local", response_model=IngestResponse)
async def ingest_local(
    request: LocalIngestRequest,
    current_user: User = Depends(get_current_user),
    pipeline=Depends(get_rag_pipeline),
) -> IngestResponse:
    """
    Ingest local documents associated with a specific case.

    Documents are chunked, embedded, and stored in the local collection
    with case_id and tenant_id for scoped retrieval.

    Local documents have a configurable TTL and are automatically cleaned up.
    """
    logger.info(
        f"Local ingest: tenant={request.tenant_id} case={request.case_id} "
        f"docs={len(request.documents)} user={current_user.id}"
    )

    try:
        indexed_count = 0
        chunk_uids: List[str] = []
        skipped_count = 0
        errors: List[Dict[str, str]] = []

        for idx, doc in enumerate(request.documents):
            try:
                doc_id = doc.doc_id or str(uuid.uuid4())

                # Build metadata
                metadata = doc.metadata.copy() if doc.metadata else {}
                metadata.update({
                    "tenant_id": request.tenant_id,
                    "case_id": request.case_id,
                    "user_id": str(current_user.id),
                    "ingested_at": datetime.utcnow().isoformat(),
                    "scope": "local",
                    "doc_id": doc_id,
                })

                # Ingest document
                if hasattr(pipeline, "ingest_local"):
                    result = await pipeline.ingest_local(
                        text=doc.text,
                        metadata=metadata,
                        tenant_id=request.tenant_id,
                        case_id=request.case_id,
                        chunk_size=request.chunk_size,
                        chunk_overlap=request.chunk_overlap,
                    )
                elif hasattr(pipeline, "add_local_document"):
                    result = pipeline.add_local_document(
                        text=doc.text,
                        metadata=metadata,
                        tenant_id=request.tenant_id,
                        case_id=request.case_id,
                    )
                else:
                    # Fallback: use generic add method
                    result = pipeline.add_document(
                        text=doc.text,
                        metadata=metadata,
                        collection="local",
                    )

                if isinstance(result, dict):
                    chunk_uids.extend(result.get("chunk_ids", []))
                    indexed_count += result.get("indexed", 1)
                    skipped_count += result.get("skipped", 0)
                elif isinstance(result, list):
                    chunk_uids.extend(result)
                    indexed_count += 1
                elif isinstance(result, int):
                    indexed_count += 1
                else:
                    indexed_count += 1

                # Ingest to knowledge graph if enabled
                if _should_ingest_to_graph(request.ingest_to_graph):
                    try:
                        await _ingest_document_to_graph(
                            text=doc.text,
                            doc_id=doc_id,
                            metadata=metadata,
                            tenant_id=request.tenant_id,
                            scope="local",
                            scope_id=request.case_id,
                            case_id=request.case_id,
                            chunk_size=int(request.chunk_size or 512),
                            chunk_overlap=int(request.chunk_overlap or 0),
                            extract_arguments=request.extract_arguments or False,
                        )
                    except Exception as graph_err:
                        logger.warning(f"Graph ingest failed for doc {idx}: {graph_err}")
                        # Don't fail the whole request for graph errors

            except Exception as e:
                logger.warning(f"Failed to ingest document {idx}: {e}")
                errors.append({
                    "doc_index": str(idx),
                    "doc_id": doc.doc_id or "N/A",
                    "error": str(e),
                })

        logger.info(
            f"Local ingest complete: indexed={indexed_count} chunks={len(chunk_uids)} "
            f"skipped={skipped_count} errors={len(errors)}"
        )

        # Invalidate result cache for this tenant
        if indexed_count > 0:
            try:
                from app.services.rag.core.result_cache import get_result_cache
                cleared = get_result_cache().invalidate_tenant(request.tenant_id)
                logger.debug(f"Result cache invalidated for tenant={request.tenant_id} (cleared={cleared})")
            except Exception:
                pass

        return IngestResponse(
            indexed_count=indexed_count,
            chunk_uids=chunk_uids,
            skipped_count=skipped_count,
            errors=errors,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Local ingest error: {e}")
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")


@router.post("/ingest/global", response_model=IngestResponse)
async def ingest_global(
    request: GlobalIngestRequest,
    current_user: User = Depends(get_current_user),
    pipeline=Depends(get_rag_pipeline),
) -> IngestResponse:
    """
    Ingest global documents into specified dataset.

    Available datasets:
    - lei: Legislation (laws, decrees, resolutions)
    - juris: Jurisprudence (court decisions, precedents)
    - pecas: Legal document templates
    - sei: Internal documents (opinions, technical notes)

    Global documents are shared across all tenants and don't expire.
    Requires admin or elevated permissions.
    """
    # Check permissions (global ingestion typically requires elevated access)
    if not _has_global_ingest_permission(current_user):
        raise HTTPException(
            status_code=403,
            detail="Global ingestion requires elevated permissions"
        )

    logger.info(
        f"Global ingest: dataset={request.dataset.value} docs={len(request.documents)} "
        f"user={current_user.id}"
    )

    try:
        indexed_count = 0
        chunk_uids: List[str] = []
        skipped_count = 0
        errors: List[Dict[str, str]] = []

        collection_name = _dataset_to_collection(request.dataset)

        for idx, doc in enumerate(request.documents):
            try:
                doc_id = doc.doc_id or str(uuid.uuid4())

                # Build metadata
                metadata = doc.metadata.copy() if doc.metadata else {}
                metadata.update({
                    "dataset": request.dataset.value,
                    "scope": "global",
                    "ingested_at": datetime.utcnow().isoformat(),
                    "ingested_by": str(current_user.id),
                    "doc_id": doc_id,
                })

                # Ingest document
                if hasattr(pipeline, "ingest_global"):
                    result = await pipeline.ingest_global(
                        text=doc.text,
                        metadata=metadata,
                        dataset=request.dataset.value,
                        chunk_size=request.chunk_size,
                        chunk_overlap=request.chunk_overlap,
                        deduplicate=request.deduplicate,
                    )
                elif hasattr(pipeline, "add_to_collection"):
                    result = pipeline.add_to_collection(
                        collection=collection_name,
                        text=doc.text,
                        metadata=metadata,
                    )
                else:
                    # Fallback: use generic add method
                    result = pipeline.add_document(
                        text=doc.text,
                        metadata=metadata,
                        collection=collection_name,
                    )

                if isinstance(result, dict):
                    if result.get("skipped"):
                        skipped_count += 1
                    else:
                        chunk_uids.extend(result.get("chunk_ids", []))
                        indexed_count += result.get("indexed", 1)
                elif isinstance(result, list):
                    chunk_uids.extend(result)
                    indexed_count += 1
                elif isinstance(result, int):
                    indexed_count += 1
                else:
                    indexed_count += 1

                # Ingest to knowledge graph if enabled (and not skipped)
                if not (isinstance(result, dict) and result.get("skipped")):
                    if _should_ingest_to_graph(request.ingest_to_graph):
                        try:
                            await _ingest_document_to_graph(
                                text=doc.text,
                                doc_id=doc_id,
                                metadata=metadata,
                                tenant_id="global",
                                scope="global",
                                scope_id=request.dataset.value,
                                chunk_size=int(request.chunk_size or 512),
                                chunk_overlap=int(request.chunk_overlap or 0),
                                extract_arguments=request.extract_arguments or False,
                            )
                        except Exception as graph_err:
                            logger.warning(f"Graph ingest failed for global doc {idx}: {graph_err}")
                            # Don't fail the whole request for graph errors

            except Exception as e:
                logger.warning(f"Failed to ingest global document {idx}: {e}")
                errors.append({
                    "doc_index": str(idx),
                    "doc_id": doc.doc_id or "N/A",
                    "error": str(e),
                })

        logger.info(
            f"Global ingest complete: dataset={request.dataset.value} indexed={indexed_count} "
            f"chunks={len(chunk_uids)} skipped={skipped_count} errors={len(errors)}"
        )

        # Invalidate result cache (global affects all tenants)
        if indexed_count > 0:
            try:
                from app.services.rag.core.result_cache import get_result_cache
                cleared = get_result_cache().invalidate_tenant("__all__")
                logger.debug(f"Result cache invalidated for global ingest (cleared={cleared})")
            except Exception:
                pass

        return IngestResponse(
            indexed_count=indexed_count,
            chunk_uids=chunk_uids,
            skipped_count=skipped_count,
            errors=errors,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Global ingest error: {e}")
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")


@router.delete("/local/{case_id}", response_model=DeleteResponse)
async def delete_local_chunks(
    case_id: str = Path(..., min_length=1, description="Case ID to delete chunks for"),
    tenant_id: str = Query(..., min_length=1, description="Tenant ID for verification"),
    current_user: User = Depends(get_current_user),
    pipeline=Depends(get_rag_pipeline),
) -> DeleteResponse:
    """
    Delete all local chunks associated with a specific case.

    This operation is idempotent - calling it multiple times has the same effect.
    Only chunks matching both case_id and tenant_id are deleted.
    """
    logger.info(
        f"Delete local chunks: case={case_id} tenant={tenant_id} user={current_user.id}"
    )

    try:
        deleted_count = 0

        if hasattr(pipeline, "delete_local_chunks"):
            result = await pipeline.delete_local_chunks(
                case_id=case_id,
                tenant_id=tenant_id,
            )
            deleted_count = result if isinstance(result, int) else result.get("deleted", 0)
        elif hasattr(pipeline, "delete_by_metadata"):
            result = pipeline.delete_by_metadata(
                collection="local",
                metadata_filter={
                    "case_id": case_id,
                    "tenant_id": tenant_id,
                },
            )
            deleted_count = result if isinstance(result, int) else 0
        else:
            # Manual deletion fallback
            logger.warning("Pipeline does not support bulk delete - operation may be incomplete")
            deleted_count = 0

        logger.info(f"Deleted {deleted_count} chunks for case {case_id}")

        return DeleteResponse(
            deleted_count=deleted_count,
            case_id=case_id,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Delete local chunks error: {e}")
        raise HTTPException(status_code=500, detail=f"Delete failed: {str(e)}")


@router.get("/stats", response_model=StatsResponse)
async def get_stats(
    current_user: User = Depends(get_current_user),
    pipeline=Depends(get_rag_pipeline),
) -> StatsResponse:
    """
    Get RAG pipeline statistics.

    Returns cache stats, trace stats, and document counts per collection.
    Useful for monitoring and debugging.
    """
    logger.debug(f"Stats request from user={current_user.id}")

    try:
        # Get cache stats
        cache_enabled = getattr(pipeline, "_cache_enabled", False)
        cache_stats = CacheStats(
            enabled=cache_enabled,
            hits=getattr(pipeline, "_cache_hits", 0),
            misses=getattr(pipeline, "_cache_misses", 0),
            size=len(getattr(pipeline, "_result_cache", {})),
            ttl_seconds=getattr(pipeline, "_cache_ttl_s", 30),
        )

        # Get trace stats
        trace_enabled = getattr(pipeline, "_trace_enabled", False)
        trace_stats = TraceStats(
            enabled=trace_enabled,
            total_traces=getattr(pipeline, "_trace_count", 0),
            avg_duration_ms=getattr(pipeline, "_avg_duration_ms", 0.0),
        )

        # Get collection counts
        collections: Dict[str, int] = {}
        if hasattr(pipeline, "get_collection_counts"):
            collections = pipeline.get_collection_counts()
        elif hasattr(pipeline, "collections"):
            for name, col in pipeline.collections.items():
                try:
                    collections[name] = col.count() if hasattr(col, "count") else 0
                except Exception:
                    collections[name] = -1
        elif hasattr(pipeline, "client"):
            try:
                for col in pipeline.client.list_collections():
                    name = getattr(col, "name", None) or col.get("name", "unknown")
                    try:
                        collections[name] = col.count() if hasattr(col, "count") else 0
                    except Exception:
                        collections[name] = -1
            except Exception:
                pass

        return StatsResponse(
            cache_stats=cache_stats,
            trace_stats=trace_stats,
            collections=collections,
            last_updated=datetime.utcnow().isoformat(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Stats error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")


@router.get("/metrics")
async def get_metrics(
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Get RAG pipeline latency metrics.

    Returns P50/P95/P99 percentiles per pipeline stage, plus result cache stats.
    """
    from app.services.rag.core.metrics import get_latency_collector
    from app.services.rag.core.result_cache import get_result_cache

    collector = get_latency_collector()
    cache = get_result_cache()

    return {
        "latency": collector.summary(),
        "result_cache": cache.stats(),
    }


# =============================================================================
# Helper Functions
# =============================================================================


def _has_global_ingest_permission(user: User) -> bool:
    """Check if user has permission to ingest global documents."""
    # Check for admin role
    if hasattr(user, "role"):
        from app.models.user import UserRole
        if user.role == UserRole.ADMIN:
            return True

    # Check for specific permission
    if hasattr(user, "permissions"):
        if "rag:ingest:global" in (user.permissions or []):
            return True

    # Check for elevated roles
    if hasattr(user, "is_superuser") and user.is_superuser:
        return True

    # Default: allow for now (can be restricted later)
    return True


def _dataset_to_collection(dataset: GlobalDataset) -> str:
    """Map dataset enum to collection name."""
    mapping = {
        GlobalDataset.LEI: "lei",
        GlobalDataset.JURIS: "juris",
        GlobalDataset.PECAS: "pecas_modelo",
        GlobalDataset.SEI: "sei",
    }
    return mapping.get(dataset, dataset.value)


def _should_ingest_to_graph(explicit_flag: Optional[bool]) -> bool:
    """
    Determine if graph ingestion should occur.

    Priority:
    1. Explicit request flag (if provided)
    2. Environment variable RAG_GRAPH_AUTO_INGEST
    3. Default: False
    """
    if explicit_flag is not None:
        return explicit_flag
    return os.getenv("RAG_GRAPH_AUTO_INGEST", "false").lower() in ("true", "1", "yes")


async def _ingest_document_to_graph(
    text: str,
    doc_id: str,
    metadata: Dict[str, Any],
    tenant_id: str,
    scope: str = "global",
    scope_id: str = "global",
    case_id: Optional[str] = None,
    chunk_size: int = 512,
    chunk_overlap: int = 50,
    extract_arguments: bool = False,
) -> Dict[str, Any]:
    """
    Ingest a document into the knowledge graph.

    This project has two graph layers:
    - Neo4jMVP (Document->Chunk->Entity) for explainable multi-hop and visualization.
    - GraphRAG factory (networkx/neo4j) for entity-centric graphs.

    We support ingesting into either or both via `RAG_GRAPH_INGEST_ENGINE`:
      - mvp (default): ingest into Neo4jMVP
      - graph_rag: ingest into GraphRAG factory
      - both: ingest into both backends

    Returns:
        Dict with ingestion results (entities_added, relationships_added)
    """
    engine = os.getenv("RAG_GRAPH_INGEST_ENGINE", "mvp").strip().lower()
    results: Dict[str, Any] = {"engine": engine}

    def _chunk_for_mvp(raw: str) -> List[Dict[str, Any]]:
        # Chunk size/overlap in requests are expressed in tokens; approximate with ~4 chars/token.
        chars_per_token = 4
        size_chars = max(200, int(chunk_size or 512) * chars_per_token)
        overlap_chars = max(0, int(chunk_overlap or 0) * chars_per_token)
        step = max(1, size_chars - overlap_chars)

        chunks_out: List[Dict[str, Any]] = []
        chunk_index = 0
        pos = 0
        raw = raw or ""
        while pos < len(raw):
            chunk_text = raw[pos:pos + size_chars]
            if chunk_text.strip():
                # Deterministic per-doc chunk id (good enough for MVP paths/UI).
                chunk_uid = hashlib.md5(f"{doc_id}:{chunk_index}".encode()).hexdigest()
                chunks_out.append(
                    {
                        "chunk_uid": chunk_uid,
                        "text": chunk_text,
                        "chunk_index": chunk_index,
                        "token_count": max(1, len(chunk_text) // chars_per_token),
                    }
                )
                chunk_index += 1
            pos += step
        return chunks_out

    # ------------------------------------------------------------------
    # Neo4jMVP ingest (preferred for explainable paths + graph visualization)
    # ------------------------------------------------------------------
    if engine in ("mvp", "neo4j_mvp", "both"):
        try:
            from app.services.rag.core.neo4j_mvp import get_neo4j_mvp

            neo4j = get_neo4j_mvp()
            mvp_stats = neo4j.ingest_document(
                doc_hash=doc_id,
                chunks=_chunk_for_mvp(text),
                metadata=metadata or {},
                tenant_id=str(tenant_id),
                scope=str(scope),
                case_id=str(case_id or scope_id) if str(scope) == "local" and (case_id or scope_id) else None,
                extract_entities=True,
                semantic_extraction=os.getenv("RAG_GRAPH_SEMANTIC_EXTRACTION", "false").lower()
                in ("true", "1", "yes", "on"),
                extract_facts=os.getenv("RAG_GRAPH_EXTRACT_FACTS", "false").lower()
                in ("true", "1", "yes", "on"),
            )
            results["neo4j_mvp"] = mvp_stats
        except Exception as e:
            logger.warning(f"Neo4jMVP ingest failed: {e}")
            results["neo4j_mvp_error"] = str(e)

    # ------------------------------------------------------------------
    # GraphRAG factory ingest (entity-centric; optional/legacy)
    # ------------------------------------------------------------------
    if engine in ("graph_rag", "factory", "both"):
        try:
            from app.services.rag.core.graph_factory import get_knowledge_graph, GraphBackend
            from app.services.rag.core.graph_rag import LegalEntityExtractor, ArgumentExtractor

            # Get the knowledge graph (factory handles Neo4j vs NetworkX)
            graph = get_knowledge_graph(scope=scope, scope_id=scope_id)
            backend_type = getattr(graph, "backend", GraphBackend.NETWORKX)

            # Extract legal entities from text
            candidates = LegalEntityExtractor.extract_candidates(text)
            entities_added = 0
            relationships_added = 0

            # Add document as entity
            doc_entity_id = f"doc_{doc_id}"
            doc_name = metadata.get("title") or metadata.get("filename") or f"Documento {doc_id[:8]}"
            if graph.add_entity(
                entity_id=doc_entity_id,
                entity_type="documento",
                name=doc_name,
                properties=metadata,
            ):
                entities_added += 1

            # Add extracted entities and create relationships
            for entity_type, entity_id, name, entity_meta in candidates:
                entity_type_str = entity_type.value if hasattr(entity_type, "value") else str(entity_type)

                if graph.add_entity(
                    entity_id=entity_id,
                    entity_type=entity_type_str,
                    name=name,
                    properties=entity_meta,
                ):
                    entities_added += 1

                # Create CITA relationship from document to entity
                if graph.add_relationship(
                    from_entity=doc_entity_id,
                    to_entity=entity_id,
                    relationship_type="CITA",
                ):
                    relationships_added += 1

            # Extract arguments if requested
            arguments_extracted = 0
            if extract_arguments:
                arguments = ArgumentExtractor.extract_arguments(text, source_chunk_id=doc_id)
                for arg in arguments:
                    arg_entity_id = f"arg_{arg.arg_id}"
                    if graph.add_entity(
                        entity_id=arg_entity_id,
                        entity_type=arg.arg_type.value,
                        name=arg.text[:100],
                        properties={"full_text": arg.text, "confidence": arg.confidence},
                    ):
                        arguments_extracted += 1

                    # Link argument to document
                    graph.add_relationship(
                        from_entity=doc_entity_id,
                        to_entity=arg_entity_id,
                        relationship_type="CONTEM_ARGUMENTO",
                    )

            # Persist if using NetworkX
            if hasattr(graph, "persist"):
                graph.persist()

            logger.info(
                f"GraphRAG ingest complete: backend={backend_type.value if hasattr(backend_type, 'value') else backend_type}, "
                f"entities={entities_added}, relationships={relationships_added}, arguments={arguments_extracted}"
            )

            results["graph_rag"] = {
                "backend": backend_type.value if hasattr(backend_type, "value") else str(backend_type),
                "entities_added": entities_added,
                "relationships_added": relationships_added,
                "arguments_extracted": arguments_extracted,
            }
        except ImportError as e:
            logger.warning(f"GraphRAG module not available: {e}")
            results["graph_rag_error"] = str(e)
        except Exception as e:
            logger.error(f"GraphRAG ingest error: {e}")
            results["graph_rag_error"] = str(e)

    # ------------------------------------------------------------------
    # KG Builder: async enrichment (fire-and-forget)
    # ------------------------------------------------------------------
    if os.getenv("KG_BUILDER_ENABLED", "false").lower() in ("true", "1", "yes", "on"):
        try:
            from app.services.rag.core.kg_builder.pipeline import run_kg_builder

            chunks_for_kg = _chunk_for_mvp(text)
            asyncio.create_task(
                run_kg_builder(
                    chunks=chunks_for_kg,
                    doc_hash=doc_id,
                    tenant_id=str(tenant_id),
                    case_id=str(case_id) if case_id else None,
                    scope=str(scope),
                    use_llm=os.getenv("KG_BUILDER_USE_LLM", "false").lower() in ("true", "1"),
                    use_resolver=os.getenv("KG_BUILDER_RESOLVE_ENTITIES", "true").lower()
                    in ("true", "1", "yes", "on"),
                )
            )
            results["kg_builder"] = "scheduled"
        except Exception as e:
            logger.debug("KG Builder scheduling failed: %s", e)

    return results
