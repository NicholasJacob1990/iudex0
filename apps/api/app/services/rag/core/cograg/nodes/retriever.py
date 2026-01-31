"""
CogGRAG Retriever Nodes — Dual-phase structured retrieval.

Implements two LangGraph nodes:

1. theme_activator_node: Top-down — activates (:Tema) nodes in Neo4j
   based on macro themes identified by the Planner. (Cog-RAG pattern)

2. dual_retriever_node: Bottom-up — for each leaf sub-question:
   - Extract entities via LegalEntityExtractor (regex, zero LLM)
   - Local retrieval: Neo4j entity/triple lookup
   - Global retrieval: Neo4j subgraph traversal (multi-hop)
   - Chunk retrieval: OpenSearch BM25 + Qdrant semantic
   - Deduplication cross-subquestion by chunk_uid
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger("rag.cograg.retriever")

# ── Lazy imports (graceful degradation) ────────────────────────────────

def _get_neo4j_service():
    try:
        from app.services.rag.core.neo4j_mvp import Neo4jMVPService, get_neo4j_service
        return get_neo4j_service()
    except Exception as e:
        logger.debug(f"Neo4j service unavailable: {e}")
        return None


def _get_entity_extractor():
    try:
        from app.services.rag.core.neo4j_mvp import LegalEntityExtractor
        return LegalEntityExtractor
    except ImportError:
        return None


def _get_opensearch_service():
    try:
        from app.services.rag.storage.opensearch_service import OpenSearchService
        return OpenSearchService()
    except Exception as e:
        logger.debug(f"OpenSearchService unavailable: {e}")
        return None


def _get_qdrant_service():
    try:
        from app.services.rag.storage.qdrant_service import QdrantService
        return QdrantService()
    except Exception as e:
        logger.debug(f"QdrantService unavailable: {e}")
        return None


def _get_embeddings_service():
    try:
        from app.services.rag.core.embeddings import get_embeddings_service
        return get_embeddings_service()
    except Exception as e:
        logger.debug(f"EmbeddingsService unavailable: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════════
# Theme Activator Node
# ═══════════════════════════════════════════════════════════════════════════

async def theme_activator_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    LangGraph node: activate (:Tema) nodes in Neo4j (top-down, Cog-RAG pattern).

    Reads from state:
        - temas: macro themes from Planner
        - tenant_id

    Writes to state:
        - graph_nodes: list of activated theme nodes with connected entities
        - metrics.theme_*
    """
    temas: List[str] = state.get("temas", [])
    tenant_id: str = state.get("tenant_id", "default")
    enabled: bool = bool(state.get("cograg_theme_retrieval_enabled", False))
    start = time.time()

    if not enabled:
        return {
            "graph_nodes": state.get("graph_nodes", []),
            "metrics": {
                **state.get("metrics", {}),
                "theme_latency_ms": 0,
                "theme_enabled": False,
                "theme_count": 0,
            },
        }

    if not temas:
        logger.info("[CogGRAG:ThemeActivator] No themes → skip")
        return {
            "graph_nodes": state.get("graph_nodes", []),
            "metrics": {
                **state.get("metrics", {}),
                "theme_latency_ms": 0,
                "theme_enabled": True,
                "theme_count": 0,
            },
        }

    neo4j = _get_neo4j_service()
    graph_nodes: List[Dict[str, Any]] = list(state.get("graph_nodes", []))

    if neo4j:
        for tema in temas:
            try:
                # Query for (:Tema) nodes matching the theme name
                results = neo4j._execute_read(
                    """
                    MATCH (t:Tema)
                    WHERE t.tenant_id = $tenant_id
                      AND (toLower(t.nome) CONTAINS toLower($tema)
                           OR toLower($tema) CONTAINS toLower(t.nome))
                    OPTIONAL MATCH (t)<-[:TRATA_DE]-(p)
                    OPTIONAL MATCH (t)<-[:SOBRE_TEMA]-(j)
                    RETURN t.nome AS tema_nome,
                           t.nivel AS nivel,
                           t.descricao AS descricao,
                           collect(DISTINCT {type: labels(p)[0], id: id(p)}) AS processos,
                           collect(DISTINCT {type: labels(j)[0], id: id(j)}) AS jurisprudencia
                    LIMIT 5
                    """,
                    {"tenant_id": tenant_id, "tema": tema},
                )
                for r in results:
                    graph_nodes.append({
                        "source": "theme_activation",
                        "tema": r.get("tema_nome", tema),
                        "nivel": r.get("nivel", "macro"),
                        "descricao": r.get("descricao", ""),
                        "related_count": len(r.get("processos", [])) + len(r.get("jurisprudencia", [])),
                    })
            except Exception as e:
                logger.warning(f"[CogGRAG:ThemeActivator] Error querying theme '{tema}': {e}")
    else:
        logger.info("[CogGRAG:ThemeActivator] Neo4j unavailable → themes stored as metadata only")
        for tema in temas:
            graph_nodes.append({
                "source": "theme_activation",
                "tema": tema,
                "nivel": "macro",
                "descricao": "",
                "related_count": 0,
            })

    latency = int((time.time() - start) * 1000)
    logger.info(f"[CogGRAG:ThemeActivator] Activated {len(temas)} themes → {len(graph_nodes)} nodes, {latency}ms")

    return {
        "graph_nodes": graph_nodes,
        "metrics": {
            **state.get("metrics", {}),
            "theme_latency_ms": latency,
            "theme_enabled": True,
            "theme_count": len(graph_nodes),
        },
    }


# ═══════════════════════════════════════════════════════════════════════════
# Dual Retriever Node
# ═══════════════════════════════════════════════════════════════════════════

def _content_hash(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:16]

def _path_uid(path: Dict[str, Any]) -> str:
    """
    Stable-ish id for a Neo4j path (for prompt references like [path:...]).

    Uses only node ids + edge types + direction to avoid huge payload hashing.
    """
    nodes = path.get("path_nodes") or []
    edges = path.get("path_edges") or []
    node_ids = [str(n.get("id")) for n in nodes if n.get("id") is not None]
    edge_bits = []
    for e in edges:
        src = e.get("from_id")
        dst = e.get("to_id")
        rel = e.get("type")
        if src is None or dst is None or not rel:
            continue
        edge_bits.append(f"{src}->{rel}->{dst}")
    canonical = "|".join(node_ids + edge_bits)
    return hashlib.md5(canonical.encode("utf-8")).hexdigest()[:12]


def _path_to_text(path: Dict[str, Any], *, max_len: int = 220) -> str:
    """
    Convert a Neo4j find_paths() output entry into a compact, readable string.
    """
    nodes = path.get("path_nodes") or []
    edges = path.get("path_edges") or []
    node_by_id: Dict[str, Dict[str, Any]] = {}
    for n in nodes:
        nid = n.get("id")
        if nid is None:
            continue
        node_by_id[str(nid)] = {
            "id": str(nid),
            "label": n.get("label"),
            "name": n.get("name") or n.get("value") or n.get("title"),
        }

    parts: List[str] = []
    for e in edges:
        src = e.get("from_id")
        dst = e.get("to_id")
        rel = e.get("type")
        if src is None or dst is None or not rel:
            continue
        src_id = str(src)
        dst_id = str(dst)
        src_node = node_by_id.get(src_id, {"id": src_id})
        dst_node = node_by_id.get(dst_id, {"id": dst_id})
        src_name = src_node.get("name") or src_node.get("label") or src_id
        dst_name = dst_node.get("name") or dst_node.get("label") or dst_id
        parts.append(f"({src_name})-[:{rel}]->({dst_name})")

    text = " ".join(parts).strip()
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "…"


def _paths_to_triples(paths: List[Dict[str, Any]], *, limit: int = 50) -> List[Dict[str, Any]]:
    """
    Convert Neo4j find_paths() output to a de-duplicated list of triples.

    Expected path shape (from Neo4jMVPService.find_paths):
      { path_nodes: [{id,label,name,...}], path_edges: [{from_id,to_id,type,...}], ... }
    """
    triples: List[Dict[str, Any]] = []
    seen = set()

    for p in paths or []:
        nodes = p.get("path_nodes") or []
        edges = p.get("path_edges") or []

        node_by_id: Dict[str, Dict[str, Any]] = {}
        for n in nodes:
            nid = n.get("id")
            if nid is None:
                continue
            node_by_id[str(nid)] = {
                "id": str(nid),
                "label": n.get("label"),
                "name": n.get("name") or n.get("value") or n.get("title"),
            }

        for e in edges:
            src = e.get("from_id")
            dst = e.get("to_id")
            rel = e.get("type")
            if src is None or dst is None or not rel:
                continue
            src_id = str(src)
            dst_id = str(dst)
            rel_s = str(rel)
            key = (src_id, rel_s, dst_id)
            if key in seen:
                continue
            seen.add(key)

            src_node = node_by_id.get(src_id, {"id": src_id})
            dst_node = node_by_id.get(dst_id, {"id": dst_id})
            src_name = src_node.get("name") or src_node.get("label") or src_id
            dst_name = dst_node.get("name") or dst_node.get("label") or dst_id
            triples.append(
                {
                    "from": src_node,
                    "rel": rel_s,
                    "to": dst_node,
                    "text": f"({src_name})-[:{rel_s}]->({dst_name})",
                }
            )
            if len(triples) >= limit:
                return triples

    return triples


async def _retrieve_for_subquestion(
    question: str,
    node_id: str,
    tenant_id: str,
    scope: str,
    case_id: Optional[str],
    neo4j: Any,
    entity_extractor: Any,
    similarity_threshold: float,
    *,
    opensearch: Any,
    qdrant: Any,
    embeddings: Any,
    indices: Optional[List[str]],
    collections: Optional[List[str]],
    user_id: str,
    group_ids: Optional[List[str]],
    graph_evidence_enabled: bool,
    graph_evidence_max_hops: int,
    graph_evidence_limit: int,
) -> Dict[str, Any]:
    """Retrieve evidence for a single sub-question (runs in parallel)."""

    evidence: Dict[str, Any] = {
        "node_id": node_id,
        "question": question,
        "local_results": [],
        "global_results": [],
        "chunk_results": [],
        "entity_keys": [],
        "graph_paths": [],
        "graph_triples": [],
    }

    # ── 1. Extract entity keys (regex, zero LLM) ─────────────────────
    entities: List[Dict[str, Any]] = []
    if entity_extractor:
        entities = entity_extractor.extract(question)
        evidence["entity_keys"] = [
            {"type": e.get("entity_type", ""), "id": e.get("entity_id", ""), "name": e.get("name", "")}
            for e in entities
        ]

    entity_ids = [e["entity_id"] for e in entities]

    # ── 2. Local retrieval: entity/triple lookup in Neo4j ─────────────
    if neo4j and entity_ids:
        try:
            local_results = neo4j.query_chunks_by_entities(
                entity_ids=entity_ids,
                tenant_id=tenant_id,
                scope=scope,
                case_id=case_id,
                limit=10,
            )
            evidence["local_results"] = local_results
        except Exception as e:
            logger.warning(f"[CogGRAG:Retriever] Local retrieval failed for '{question[:50]}': {e}")

    # ── 3. Graph evidence: paths/triples (MindMap KG prompting) ───────
    if graph_evidence_enabled and neo4j and entity_ids:
        try:
            paths = neo4j.find_paths(
                entity_ids=entity_ids[:3],  # Top 3 entities to limit traversal
                tenant_id=tenant_id,
                scope=scope,
                case_id=case_id,
                group_ids=list(group_ids or []),
                user_id=user_id or None,
                max_hops=int(graph_evidence_max_hops or 2),
                limit=int(graph_evidence_limit or 10),
                include_arguments=False,
            )
            norm_paths: List[Dict[str, Any]] = []
            for p in (paths or []):
                pd = dict(p or {})
                pd.setdefault("path_uid", _path_uid(pd))
                pd.setdefault("path_text", _path_to_text(pd))
                norm_paths.append(pd)

            evidence["graph_paths"] = norm_paths
            evidence["graph_triples"] = _paths_to_triples(norm_paths, limit=50)
        except Exception as e:
            logger.debug(f"[CogGRAG:Retriever] Graph evidence skipped: {e}")

    # ── 4. Chunk retrieval: Neo4j fulltext as fallback ────────────────
    if neo4j and not evidence["local_results"]:
        try:
            text_results = neo4j.query_chunks_by_text(
                query_text=question,
                tenant_id=tenant_id,
                scope=scope,
                case_id=case_id,
                limit=10,
            )
            evidence["chunk_results"] = text_results
        except Exception as e:
            logger.debug(f"[CogGRAG:Retriever] Chunk text retrieval skipped: {e}")

    # Ensure list container for downstream appends
    if not isinstance(evidence.get("chunk_results"), list):
        evidence["chunk_results"] = []

    # ── 5. Chunk retrieval: OpenSearch BM25 (lexical) ─────────────────
    if opensearch and indices:
        try:
            # Allow tenant-specific docs + "global" docs.
            tenant_filter: Optional[Dict[str, Any]] = None
            if tenant_id:
                tenant_filter = {
                    "bool": {
                        "should": [
                            {"term": {"tenant_id": tenant_id}},
                            {"term": {"tenant_id": "global"}},
                            {"bool": {"must_not": {"exists": {"field": "tenant_id"}}}},
                        ],
                        "minimum_should_match": 1,
                    }
                }

            lexical_k = 8

            results = await asyncio.to_thread(
                opensearch.search_lexical,
                query=question,
                indices=list(indices),
                top_k=lexical_k,
                scope=None,  # include global + local visibility via case_id/user_id/group_ids
                tenant_id=None,  # handled by tenant_filter
                case_id=case_id,
                user_id=user_id or None,
                group_ids=list(group_ids or []),
                include_global=True,
                source_filter=tenant_filter,
                highlight=False,
                use_fallback=True,
            )
            results = list(results or [])
            if results:
                max_score = float(results[0].get("score", 1.0) or 1.0)
                max_score = max(1e-9, max_score)
                for r in results:
                    meta = dict(r.get("metadata", {}) or {})
                    raw_score = float(r.get("score", 0.0) or 0.0)
                    norm_score = min(1.0, max(0.0, raw_score / max_score))
                    evidence["chunk_results"].append(
                        {
                            "chunk_uid": r.get("chunk_uid"),
                            "text": r.get("text", ""),
                            "score": norm_score,
                            "source": "opensearch_bm25",
                            "source_type": meta.get("source_type") or meta.get("dataset") or "opensearch",
                            "doc_id": meta.get("doc_id"),
                            "doc_type": meta.get("source_type") or meta.get("dataset") or "",
                            "metadata": meta,
                        }
                    )
        except Exception as e:
            logger.debug(f"[CogGRAG:Retriever] OpenSearch lexical skipped: {e}")

    # ── 6. Chunk retrieval: Qdrant (semantic) ──────────────────────────
    if qdrant and embeddings and collections:
        try:
            query_vector = await asyncio.to_thread(embeddings.embed_query, question)
        except Exception as e:
            logger.debug(f"[CogGRAG:Retriever] Embedding generation failed: {e}")
            query_vector = None

        if query_vector:
            try:
                # Collections are configured as logical types (lei, juris, ..., local_chunks).
                all_types = [str(c) for c in collections if c]
                global_types = [c for c in all_types if c != "local_chunks"]
                vector_k = 6

                # Global-ish semantic search: tenant + "global" tenant (if different).
                tenant_ids = [tenant_id]
                if tenant_id != "global":
                    tenant_ids.append("global")

                for tid in tenant_ids:
                    try:
                        if not global_types:
                            continue
                        res_by_coll = await asyncio.to_thread(
                            qdrant.search_multi_collection,
                            collection_types=global_types,
                            query_vector=query_vector,
                            tenant_id=tid,
                            user_id=user_id or "system",
                            top_k=vector_k,
                            scopes=["global"],
                            sigilo_levels=["publico"],
                            group_ids=list(group_ids or []),
                            case_id=None,
                            score_threshold=None,
                            metadata_filters=None,
                        )
                        for _coll, hits in (res_by_coll or {}).items():
                            for h in hits:
                                d = h.to_dict() if hasattr(h, "to_dict") else dict(h)
                                meta = dict(d.get("metadata", {}) or {})
                                raw_score = float(d.get("score", 0.0) or 0.0)
                                norm_score = min(1.0, max(0.0, raw_score))
                                evidence["chunk_results"].append(
                                    {
                                        "chunk_uid": d.get("chunk_uid"),
                                        "text": d.get("text", ""),
                                        "score": norm_score,
                                        "source": "qdrant",
                                        "source_type": meta.get("source_type") or meta.get("dataset") or _coll,
                                        "doc_id": meta.get("doc_id"),
                                        "doc_type": meta.get("source_type") or meta.get("dataset") or "",
                                        "metadata": meta,
                                    }
                                )
                    except Exception as e:
                        logger.debug(f"[CogGRAG:Retriever] Qdrant global search skipped (tenant={tid}): {e}")

                # Local semantic search (only if we have a user_id, since local scope checks allowed_users).
                if case_id and user_id and "local_chunks" in all_types:
                    try:
                        local_hits = await asyncio.to_thread(
                            qdrant.search,
                            collection_type="local_chunks",
                            query_vector=query_vector,
                            tenant_id=tenant_id,
                            user_id=user_id,
                            top_k=vector_k,
                            scopes=["local"],
                            sigilo_levels=["publico", "restrito", "sigiloso"],
                            group_ids=list(group_ids or []),
                            case_id=case_id,
                            score_threshold=None,
                            metadata_filters=None,
                            use_fallback=True,
                        )
                        for h in (local_hits or []):
                            d = h.to_dict() if hasattr(h, "to_dict") else dict(h)
                            meta = dict(d.get("metadata", {}) or {})
                            raw_score = float(d.get("score", 0.0) or 0.0)
                            norm_score = min(1.0, max(0.0, raw_score))
                            evidence["chunk_results"].append(
                                {
                                    "chunk_uid": d.get("chunk_uid"),
                                    "text": d.get("text", ""),
                                    "score": norm_score,
                                    "source": "qdrant",
                                    "source_type": meta.get("source_type") or "local_chunks",
                                    "doc_id": meta.get("doc_id"),
                                    "doc_type": meta.get("source_type") or "",
                                    "metadata": meta,
                                }
                            )
                    except Exception as e:
                        logger.debug(f"[CogGRAG:Retriever] Qdrant local search skipped: {e}")
            except Exception as e:
                logger.debug(f"[CogGRAG:Retriever] Qdrant semantic skipped: {e}")

    return evidence


async def dual_retriever_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    LangGraph node: structured retrieval per sub-question (CogGRAG dual-phase).

    Fan-out: run retrieval for all leaf sub-questions in parallel.
    Fan-in: merge results, deduplicate by content hash.

    Reads from state:
        - sub_questions, tenant_id, scope, case_id
        - cograg_similarity_threshold (optional)

    Writes to state:
        - evidence_map: {node_id: evidence_dict}
        - text_chunks: deduplicated chunks from all sub-questions
        - metrics.retriever_*
    """
    sub_questions: List[Dict[str, Any]] = state.get("sub_questions", [])
    tenant_id: str = state.get("tenant_id", "default")
    scope: str = state.get("scope", "global")
    case_id: Optional[str] = state.get("case_id")
    similarity_threshold: float = state.get("cograg_similarity_threshold", 0.7)
    graph_evidence_enabled: bool = bool(state.get("cograg_graph_evidence_enabled", True))
    graph_evidence_max_hops: int = int(state.get("cograg_graph_evidence_max_hops", 2) or 2)
    graph_evidence_limit: int = int(state.get("cograg_graph_evidence_limit", 10) or 10)
    user_id: str = str(state.get("user_id") or "").strip()
    group_ids: List[str] = list(state.get("group_ids") or [])
    indices: Optional[List[str]] = state.get("indices")
    collections: Optional[List[str]] = state.get("collections")
    start = time.time()

    if not sub_questions:
        logger.info("[CogGRAG:Retriever] No sub-questions → skip")
        return {
            "evidence_map": {},
            "text_chunks": [],
            "metrics": {
                **state.get("metrics", {}),
                "retriever_latency_ms": 0,
                "retriever_subquestion_count": 0,
            },
        }

    logger.info(f"[CogGRAG:Retriever] Retrieving for {len(sub_questions)} sub-questions")

    neo4j = _get_neo4j_service()
    entity_extractor = _get_entity_extractor()
    opensearch = _get_opensearch_service()
    qdrant = _get_qdrant_service()
    embeddings = _get_embeddings_service()

    # Defaults if caller didn't provide explicit targets
    if not indices or not isinstance(indices, list):
        try:
            from app.services.rag.config import get_rag_config
            indices = get_rag_config().get_opensearch_indices()
        except Exception:
            indices = None
    if not collections or not isinstance(collections, list):
        try:
            from app.services.rag.config import get_rag_config
            collections = get_rag_config().get_qdrant_collections()
        except Exception:
            collections = None

    # ── Fan-out: parallel retrieval per sub-question ──────────────────
    tasks = [
        _retrieve_for_subquestion(
            question=sq["question"],
            node_id=sq["node_id"],
            tenant_id=tenant_id,
            scope=scope,
            case_id=case_id,
            neo4j=neo4j,
            entity_extractor=entity_extractor,
            similarity_threshold=similarity_threshold,
            opensearch=opensearch,
            qdrant=qdrant,
            embeddings=embeddings,
            indices=indices,
            collections=collections,
            user_id=user_id,
            group_ids=group_ids,
            graph_evidence_enabled=graph_evidence_enabled,
            graph_evidence_max_hops=graph_evidence_max_hops,
            graph_evidence_limit=graph_evidence_limit,
        )
        for sq in sub_questions
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # ── Fan-in: merge + deduplicate ───────────────────────────────────
    evidence_map: Dict[str, Any] = {}
    all_chunks: List[Dict[str, Any]] = []
    seen_hashes: Set[str] = set()
    all_graph_paths: List[Dict[str, Any]] = []
    all_graph_triples: List[Dict[str, Any]] = []
    seen_triples: Set[str] = set()

    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"[CogGRAG:Retriever] Sub-question {i} failed: {result}")
            continue

        node_id = result["node_id"]
        evidence_map[node_id] = result

        # Collect all chunks for deduplication
        for chunk_list_key in ("local_results", "global_results", "chunk_results"):
            for chunk in result.get(chunk_list_key, []):
                text = chunk.get("text", "") or chunk.get("preview", "")
                if not text:
                    continue
                h = _content_hash(text)
                if h not in seen_hashes:
                    seen_hashes.add(h)
                    chunk["_source_subquestion"] = node_id
                    chunk["_content_hash"] = h
                    all_chunks.append(chunk)

        for p in result.get("graph_paths", []) or []:
            all_graph_paths.append({**p, "_source_subquestion": node_id})
        for tr in result.get("graph_triples", []) or []:
            key = f"{tr.get('from', {}).get('id')}|{tr.get('rel')}|{tr.get('to', {}).get('id')}|{tr.get('text')}"
            if key in seen_triples:
                continue
            seen_triples.add(key)
            all_graph_triples.append({**tr, "_source_subquestion": node_id})

    latency = int((time.time() - start) * 1000)
    logger.info(
        f"[CogGRAG:Retriever] Done: {len(evidence_map)} evidence sets, "
        f"{len(all_chunks)} unique chunks, {latency}ms"
    )

    return {
        "evidence_map": evidence_map,
        "text_chunks": all_chunks,
        "graph_paths": all_graph_paths[:200],
        "graph_triples": all_graph_triples[:200],
        "metrics": {
            **state.get("metrics", {}),
            "retriever_latency_ms": latency,
            "retriever_subquestion_count": len(sub_questions),
            "retriever_evidence_sets": len(evidence_map),
            "retriever_unique_chunks": len(all_chunks),
            "retriever_graph_paths": len(all_graph_paths),
            "retriever_graph_triples": len(all_graph_triples),
        },
    }
