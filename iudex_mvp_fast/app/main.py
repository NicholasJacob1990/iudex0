
from __future__ import annotations

import datetime as dt
import asyncio
import re
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from tenacity import retry, stop_after_attempt, wait_exponential

from .settings import get_settings, get_pipeline_config
from .services.opensearch_service import OpenSearchService
from .services.qdrant_service import QdrantService
from .services.embeddings import EmbeddingsClient
from .services.ingest_utils import chunk_text, extract_pdf_pages
from .services.retrieval_orchestrator import RetrievalOrchestrator
from .services.rag_pipeline import RAGPipeline, get_rag_pipeline, PipelineResult
from .ttl_cleanup import run_ttl_cleanup

app = FastAPI(title="Iudex MVP (OpenSearch + Qdrant)")
settings = get_settings()

os_svc = OpenSearchService(settings.opensearch_url, settings.opensearch_user, settings.opensearch_pass)
qd_svc = QdrantService(settings.qdrant_url)

emb = EmbeddingsClient(
    api_key=settings.openai_api_key,
    model=settings.openai_embedding_model,
    dimensions=settings.openai_embedding_dimensions,
)

OS_DATASET_INDICES = {"lei": "rag-lei", "juris": "rag-juris", "pecas_modelo": "rag-pecas_modelo", "sei": "rag-sei"}
QD_DATASET_COLLECTIONS = {"lei": "lei", "juris": "juris", "pecas_modelo": "pecas_modelo", "sei": "sei"}

OS_LOCAL_INDEX = "rag-local"
QD_LOCAL_COLLECTION = "local_chunks"

VECTOR_SIZE = settings.openai_embedding_dimensions or 3072  # text-embedding-3-large default


def chunk_uid(doc_hash: str, chunk_index: int) -> str:
    return f"{doc_hash}:{chunk_index}"


def is_lexical_heavy(query: str) -> bool:
    """
    Heuristic: legal-citation patterns usually benefit most from BM25.
    If true, we try lexical-only first and only fall back to vectors if recall looks weak.
    """
    q = (query or "").lower()
    patterns = [
        r"\bart\.?\b",
        r"§",
        r"\binc\.?\b",
        r"\binciso\b",
        r"\bal[ií]nea\b",
        r"\bs[úu]mula\b",
        r"\bre[cs]p\b",
        r"\badi\b|\badpf\b",
        r"\bproc\.?\b|\bprocesso\b",
        r"\bn[ºo]\b",
    ]
    if any(re.search(p, q) for p in patterns):
        return True
    digits = sum(ch.isdigit() for ch in q)
    if digits >= 6:
        return True
    return False


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=0.5, max=4))
def _embed(text: str) -> List[float]:
    vec = emb.embed_query(text, ttl_seconds=3600)
    if not vec:
        raise ValueError("Empty embedding (likely empty text chunk).")
    return vec


@app.on_event("startup")
async def startup() -> None:
    for idx in list(OS_DATASET_INDICES.values()) + [OS_LOCAL_INDEX]:
        await run_in_threadpool(os_svc.ensure_index, idx)

    for col in list(QD_DATASET_COLLECTIONS.values()) + [QD_LOCAL_COLLECTION]:
        await run_in_threadpool(qd_svc.ensure_collection, col, VECTOR_SIZE)

    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        lambda: run_ttl_cleanup(
            os_svc=os_svc,
            qd_svc=qd_svc,
            os_local_index=OS_LOCAL_INDEX,
            qd_local_collection=QD_LOCAL_COLLECTION,
            ttl_days=settings.local_ttl_days,
        ),
        trigger="interval",
        hours=6,
        id="ttl_cleanup",
        replace_existing=True,
    )
    scheduler.start()


@app.post("/local/ingest")
async def ingest_local(
    tenant_id: str = Form(...),
    case_id: str = Form(...),
    doc_id: str = Form(...),
    doc_hash: str = Form(...),
    sigilo: str = Form("publico"),
    allowed_users: str = Form(""),
    group_ids: str = Form(""),
    file: UploadFile = File(...),
):
    raw = await file.read()
    filename = (file.filename or "").lower()

    chunks = []
    if filename.endswith(".pdf"):
        pages = await run_in_threadpool(extract_pdf_pages, raw)
        for page_num, page_text in pages:
            chunks.extend(chunk_text(page_text, page=page_num))
    else:
        text = raw.decode("utf-8", errors="ignore")
        chunks = chunk_text(text, page=None)

    if not chunks:
        return JSONResponse({"ok": False, "error": "No extractable text/chunks."}, status_code=400)

    allowed_list = [x.strip() for x in allowed_users.split(",") if x.strip()]
    group_list = [x.strip() for x in group_ids.split(",") if x.strip()]

    uploaded_at_iso = dt.datetime.now(dt.timezone.utc).isoformat()
    uploaded_at_epoch = int(dt.datetime.now(dt.timezone.utc).timestamp())

    indexed = 0
    # Batch embeddings for ingestion (faster than per-chunk calls)
    texts = [c.text for c in chunks]
    vecs = await run_in_threadpool(emb.embed_many, texts, 64)

    for ch, vec in zip(chunks, vecs):
        uid = chunk_uid(doc_hash, ch.chunk_index)
        text = ch.text

        if not vec:
            continue

        os_doc: Dict[str, Any] = {
            "chunk_uid": uid,
            "dataset": "local",
            "scope": "local",
            "tenant_id": tenant_id,
            "case_id": case_id,
            "sigilo": sigilo,
            "allowed_users": allowed_list,
            "group_ids": group_list,
            "doc_id": doc_id,
            "doc_hash": doc_hash,
            "doc_version": "v1",
            "chunk_index": ch.chunk_index,
            "page": ch.page,
            "uploaded_at": uploaded_at_iso,
            "text": text,
        }
        await run_in_threadpool(os_svc.index_chunk, OS_LOCAL_INDEX, uid, os_doc)

        payload: Dict[str, Any] = {
            "chunk_uid": uid,
            "dataset": "local",
            "scope": "local",
            "tenant_id": tenant_id,
            "case_id": case_id,
            "sigilo": sigilo,
            "allowed_users": allowed_list,
            "group_ids": group_list,
            "doc_id": doc_id,
            "doc_hash": doc_hash,
            "doc_version": "v1",
            "chunk_index": ch.chunk_index,
            "page": ch.page,
            "uploaded_at": uploaded_at_epoch,
            "text": text,
        }
        await run_in_threadpool(qd_svc.upsert, QD_LOCAL_COLLECTION, uid, vec, payload)

        indexed += 1

    await run_in_threadpool(os_svc.refresh, OS_LOCAL_INDEX)

    return {"ok": True, "indexed_chunks": indexed, "case_id": case_id}


@app.post("/search")
async def search(
    query: str,
    tenant_id: str,
    case_id: Optional[str] = None,
    group_ids: Optional[List[str]] = None,
    user_id: Optional[str] = None,
    datasets: Optional[List[str]] = None,
    top_k: int = 10,
    include_global: bool = True,
    include_private: bool = True,
    include_group: bool = True,
    include_local: bool = True,
    # Feature flags (overrides config)
    use_hyde: Optional[bool] = None,
    use_multiquery: Optional[bool] = None,
    use_crag: Optional[bool] = None,
    use_rerank: Optional[bool] = None,
    use_compression: Optional[bool] = None,
    use_expansion: Optional[bool] = None,
    use_graph_enrich: Optional[bool] = None,
):
    """
    Advanced RAG search endpoint with full pipeline support.

    The pipeline stages are:
    1. Query Enhancement (HyDE / Multi-query)
    2. Lexical Search (BM25/OpenSearch)
    3. Vector Search (Embeddings/Qdrant)
    4. Merge (RRF fusion)
    5. CRAG Gate (quality check with retry)
    6. Rerank (cross-encoder scoring)
    7. Expand (sibling chunks)
    8. Compress (keyword extraction)
    9. Graph Enrich (knowledge graph context)
    10. Trace (audit trail)

    Feature flags can override environment configuration per-request.
    """
    datasets = datasets or ["lei", "juris", "pecas_modelo", "sei"]

    # Build scope filters for OpenSearch and Qdrant
    os_filter = os_svc.build_scope_filter(
        tenant_id=tenant_id,
        group_ids=group_ids,
        include_global=include_global,
        include_private=include_private,
        include_group=include_group,
        include_local=include_local,
        case_id=case_id,
        user_id=user_id,
    )

    qd_filter = qd_svc.build_filter(
        tenant_id=tenant_id,
        group_ids=group_ids,
        include_global=include_global,
        include_private=include_private,
        include_group=include_group,
        include_local=include_local,
        case_id=case_id,
        user_id=user_id,
    )

    os_indices = [OS_DATASET_INDICES[d] for d in datasets if d in OS_DATASET_INDICES]
    if include_local and case_id:
        os_indices += [OS_LOCAL_INDEX]

    qd_cols = [QD_DATASET_COLLECTIONS[d] for d in datasets if d in QD_DATASET_COLLECTIONS]
    if include_local and case_id:
        qd_cols += [QD_LOCAL_COLLECTION]

    # Create search functions for the pipeline
    def lexical_search_fn(q: str, k: int) -> List[Dict[str, Any]]:
        return os_svc.search_lexical(os_indices, q, os_filter, k)

    def vector_search_fn(q: str, k: int) -> List[Dict[str, Any]]:
        qvec = _embed(q)
        all_results: List[Dict[str, Any]] = []
        for col in qd_cols:
            results = qd_svc.search(col, qvec, qd_filter, k)
            all_results.extend(results)
        return all_results

    def fetch_siblings_fn(doc_hash: str, chunk_index: int) -> List[Dict[str, Any]]:
        """Fetch sibling chunks for expansion."""
        # Query OpenSearch for neighboring chunks
        try:
            from opensearchpy import OpenSearch
            sibling_query = {
                "query": {
                    "bool": {
                        "must": [
                            {"term": {"doc_hash": doc_hash}},
                            {"range": {"chunk_index": {
                                "gte": chunk_index - 1,
                                "lte": chunk_index + 1,
                            }}},
                        ],
                    }
                },
                "size": 3,
            }
            response = os_svc.client.search(index=OS_LOCAL_INDEX, body=sibling_query)
            return [hit["_source"] for hit in response.get("hits", {}).get("hits", [])]
        except Exception:
            return []

    # Get or create the RAG pipeline
    pipeline = get_rag_pipeline()

    # Calculate fetch_k based on pipeline settings
    pipeline_config = get_pipeline_config()
    fetch_k = max(50, top_k * 5)

    # Execute the full pipeline
    result: PipelineResult = await pipeline.search(
        query=query,
        lexical_fn=lexical_search_fn,
        vector_fn=vector_search_fn,
        top_k=top_k,
        fetch_k=fetch_k,
        tenant_id=tenant_id,
        user_id=user_id,
        group_ids=group_ids,
        case_id=case_id,
        fetch_siblings_fn=fetch_siblings_fn if pipeline_config.enable_chunk_expansion else None,
        # Feature flag overrides
        use_hyde=use_hyde,
        use_multiquery=use_multiquery,
        use_crag=use_crag,
        use_rerank=use_rerank,
        use_compression=use_compression,
        use_expansion=use_expansion,
        use_graph_enrich=use_graph_enrich,
    )

    # Build response
    response = {
        "query": query,
        "top_k": top_k,
        "results": result.results,
        "mode": "rag_pipeline",
        "metadata": result.metadata,
    }

    # Include optional fields
    if result.crag_evaluation:
        response["crag_evaluation"] = result.crag_evaluation

    if result.graph_context:
        response["graph_context"] = result.graph_context

    if result.trace and pipeline_config.enable_tracing:
        response["trace"] = result.trace.to_dict()

    return response


@app.post("/search/simple")
async def search_simple(
    query: str,
    tenant_id: str,
    case_id: Optional[str] = None,
    group_ids: Optional[List[str]] = None,
    user_id: Optional[str] = None,
    datasets: Optional[List[str]] = None,
    top_k: int = 10,
    include_global: bool = True,
    include_private: bool = True,
    include_group: bool = True,
    include_local: bool = True,
):
    """
    Simple hybrid search endpoint (lexical + vector with RRF merge).

    This is a lightweight alternative to /search that skips advanced features
    like CRAG, reranking, compression, and graph enrichment.
    Use this for faster response times when advanced features are not needed.
    """
    datasets = datasets or ["lei", "juris", "pecas_modelo", "sei"]

    # --- Gating: try lexical-only first for citation-heavy queries ---
    lexical_first = is_lexical_heavy(query)

    os_filter = os_svc.build_scope_filter(
        tenant_id=tenant_id,
        group_ids=group_ids,
        include_global=include_global,
        include_private=include_private,
        include_group=include_group,
        include_local=include_local,
        case_id=case_id,
        user_id=user_id,
    )

    qd_filter = qd_svc.build_filter(
        tenant_id=tenant_id,
        group_ids=group_ids,
        include_global=include_global,
        include_private=include_private,
        include_group=include_group,
        include_local=include_local,
        case_id=case_id,
        user_id=user_id,
    )

    os_indices = [OS_DATASET_INDICES[d] for d in datasets if d in OS_DATASET_INDICES]
    if include_local and case_id:
        os_indices += [OS_LOCAL_INDEX]

    # Run lexical search first (cheap) when query looks citation-heavy.
    lexical = await run_in_threadpool(os_svc.search_lexical, os_indices, query, os_filter, max(50, top_k * 10))

    if lexical_first and len(lexical) >= top_k:
        # Good enough lexical evidence; skip vectors to save latency/cost.
        orch = RetrievalOrchestrator()
        merged = orch.merge_results(lexical, [], top_k=top_k, k_rrf=60, w_lex=1.0, w_vec=0.0)
        return {
            "query": query,
            "top_k": top_k,
            "counts": {"lexical": len(lexical), "vector": 0, "merged": len(merged)},
            "results": merged,
            "mode": "lexical_only",
        }

    qd_cols = [QD_DATASET_COLLECTIONS[d] for d in datasets if d in QD_DATASET_COLLECTIONS]
    if include_local and case_id:
        qd_cols += [QD_LOCAL_COLLECTION]

    qvec = await run_in_threadpool(_embed, query)

    # Vector search (multi-collection) in parallel
    async def _search_one(col: str):
        return await run_in_threadpool(qd_svc.search, col, qvec, qd_filter, max(20, top_k * 5))

    vector_lists = await asyncio.gather(*[_search_one(c) for c in qd_cols])
    vector: List[Dict[str, Any]] = []
    for lst in vector_lists:
        vector.extend(lst)

    orch = RetrievalOrchestrator()
    merged = orch.merge_results(lexical, vector, top_k=top_k, k_rrf=60, w_lex=0.5, w_vec=0.5)

    return {
        "query": query,
        "top_k": top_k,
        "counts": {"lexical": len(lexical), "vector": len(vector), "merged": len(merged)},
        "results": merged,
        "mode": "hybrid_lex+vec",
    }
