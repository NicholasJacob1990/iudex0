"""
Real-world smoke test for the RAG pipeline.

Runs against live OpenSearch + Qdrant + Neo4j services (local Docker).
Designed to be safe to run repeatedly: uses dedicated index/collection prefixes.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _env(name: str, default: str) -> str:
    value = os.getenv(name)
    return value if value is not None else default


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _compose_default_neo4j_password() -> Optional[str]:
    try:
        compose = Path(__file__).resolve().parents[1] / "docker-compose.rag.yml"
        text = compose.read_text(encoding="utf-8")
    except Exception:
        return None
    match = re.search(r"NEO4J_AUTH=neo4j/\$\{NEO4J_PASSWORD:-([^}]+)\}", text)
    if not match:
        return None
    return match.group(1).strip()


@dataclass(frozen=True)
class SeedChunk:
    doc_id: str
    title: str
    scope: str
    text: str
    source_type: str = "local"


def _load_argument_graph_doc_ids() -> List[str]:
    # The legacy graph store used for ArgumentRAG lives here.
    path = Path(__file__).resolve().parents[1] / "app" / "services" / "graph_db" / "scopes" / "knowledge_graph_private.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    doc_ids: List[str] = []
    for node in data.get("nodes", []):
        doc_id = node.get("doc_id")
        if doc_id and doc_id not in doc_ids:
            doc_ids.append(str(doc_id))
    return doc_ids


def _ensure_private_graph_for_tenant(tenant_id: str) -> None:
    """
    Ensure the tenant-specific private graph file exists.

    The runtime can load `RAG_GRAPH_TENANT_SCOPED` from `.env` during imports, so we
    can't rely on that env var being present early in this script. For deterministic
    local smoke tests we always provision the tenant-scoped copy if missing.
    """
    safe_id = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(tenant_id)).strip("_") or "default"
    base_dir = Path(__file__).resolve().parents[1] / "app" / "services" / "graph_db" / "scopes"
    src = base_dir / "knowledge_graph_private.json"
    dst = base_dir / f"knowledge_graph_private_{safe_id}.json"
    if dst.exists() or not src.exists():
        return
    dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")


def _seed_chunks() -> List[SeedChunk]:
    doc_ids = _load_argument_graph_doc_ids()
    # Ensure stable, graph-matching doc_ids for ArgumentRAG.
    arg_doc_1 = doc_ids[0] if doc_ids else str(uuid.uuid4())
    arg_doc_2 = doc_ids[1] if len(doc_ids) > 1 else str(uuid.uuid4())

    return [
        SeedChunk(
            doc_id=arg_doc_1,
            title="Jurisprudência STJ - Dano moral (seed)",
            scope="private",
            text=(
                "STJ - Dano moral - REsp 1234567. A autora afirma que houve dano moral. "
                "A ré contesta e diz que não houve dano. Jurisprudência STJ - Dano moral."
            ),
            source_type="juris",
        ),
        SeedChunk(
            doc_id=arg_doc_2,
            title="STJ - Dano moral - REsp 1234567 (seed)",
            scope="private",
            text=(
                "STJ - Dano moral - REsp 1234567. A parte autora afirma que houve dano moral. "
                "O réu contesta e diz que não houve dano."
            ),
            source_type="juris",
        ),
        SeedChunk(
            doc_id=str(uuid.uuid4()),
            title="Lei 8.666/1993 - Art. 37 (seed)",
            scope="global",
            text=(
                "Lei 8.666/1993. Art. 37. Este é um texto de exemplo para teste de roteamento "
                "lexical (citação legal) e GraphRAG via Neo4j."
            ),
            source_type="lei",
        ),
        SeedChunk(
            doc_id=str(uuid.uuid4()),
            title="Responsabilidade civil do Estado por omissão (seed)",
            scope="global",
            text=(
                "Responsabilidade civil do Estado por omissão. Em geral, discute-se culpa, "
                "nexo causal e dever específico de agir. Texto sintético para teste semântico."
            ),
            source_type="doutrina",
        ),
    ]


async def _run(args: argparse.Namespace) -> int:
    # Ensure `app.*` imports work when executing from `apps/api/scripts/`.
    api_root = Path(__file__).resolve().parents[1]
    if str(api_root) not in sys.path:
        sys.path.insert(0, str(api_root))

    # Configure endpoints (prefer explicit env, fall back to common local dev ports)
    os.environ.setdefault("OPENSEARCH_URL", _env("OPENSEARCH_URL", "http://localhost:9201"))
    os.environ.setdefault("OPENSEARCH_VERIFY_CERTS", _env("OPENSEARCH_VERIFY_CERTS", "false"))
    os.environ.setdefault("QDRANT_URL", _env("QDRANT_URL", "http://localhost:6335"))
    os.environ.setdefault("QDRANT_API_KEY", _env("QDRANT_API_KEY", ""))

    os.environ.setdefault("NEO4J_URI", _env("NEO4J_URI", "bolt://localhost:7687"))
    os.environ.setdefault("NEO4J_USER", _env("NEO4J_USER", "neo4j"))
    if "NEO4J_PASSWORD" not in os.environ:
        default_pw = _compose_default_neo4j_password()
        if default_pw:
            os.environ["NEO4J_PASSWORD"] = default_pw
    os.environ.setdefault("NEO4J_DATABASE", _env("NEO4J_DATABASE", "iudex"))

    # Keep integration tests deterministic by default.
    os.environ.setdefault("RAG_EMBEDDINGS_PROVIDER", _env("RAG_EMBEDDINGS_PROVIDER", "local"))
    os.environ.setdefault(
        "RAG_LOCAL_EMBEDDING_MODEL",
        _env("RAG_LOCAL_EMBEDDING_MODEL", "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"),
    )
    os.environ.setdefault("EMBEDDING_DIMENSIONS", _env("EMBEDDING_DIMENSIONS", "768"))

    if not args.use_llm:
        os.environ.setdefault("RAG_ENABLE_HYDE", "false")
        os.environ.setdefault("RAG_ENABLE_MULTIQUERY", "false")
        os.environ.setdefault("RAG_ENABLE_CRAG", "false")
        os.environ.setdefault("RAG_MULTI_QUERY_LLM", "false")

    if args.enable_rerank:
        os.environ.setdefault("RAG_ENABLE_RERANK", "true")
        os.environ.setdefault("RERANK_PROVIDER", _env("RERANK_PROVIDER", "local"))
    else:
        os.environ.setdefault("RAG_ENABLE_RERANK", "false")

    if args.enable_compression:
        os.environ.setdefault("RAG_ENABLE_COMPRESSION", "true")
    else:
        os.environ.setdefault("RAG_ENABLE_COMPRESSION", "false")

    # Import after env is set.
    from app.services.rag.config import reset_rag_config, get_rag_config
    from app.services.rag.storage.opensearch_service import OpenSearchService
    from app.services.rag.storage.qdrant_service import QdrantService, UpsertPayload
    from app.services.rag.pipeline.rag_pipeline import RAGPipeline
    from app.services.rag.pipeline.rag_pipeline import PipelineStage

    reset_rag_config()

    cfg = get_rag_config()

    if args.official_names:
        # Use canonical names from config/env.
        index_name = None
        collection_name = None
        indices_official = cfg.get_opensearch_indices()
        collections_official = cfg.get_qdrant_collections()
    else:
        index_name = args.opensearch_index
        collection_name = args.qdrant_collection
        indices_official = None
        collections_official = None
    tenant_id = args.tenant_id
    user_id = args.user_id

    _ensure_private_graph_for_tenant(tenant_id)

    # If using official names, align EMBEDDING_DIMENSIONS to the existing Qdrant collections (if any).
    # This avoids vector-size mismatch when the collections were created previously with different dims.
    if args.official_names:
        tmp_qdrant = QdrantService()
        existing_sizes: List[int] = []
        for coll in (collections_official or []):
            info = tmp_qdrant.get_collection_info(coll)
            if info and isinstance(info.get("config"), dict):
                size = info["config"].get("vector_size")
                if isinstance(size, int) and size > 0:
                    existing_sizes.append(size)
        if existing_sizes:
            size0 = existing_sizes[0]
            if any(s != size0 for s in existing_sizes):
                raise SystemExit(f"Qdrant collections have mixed vector sizes: {sorted(set(existing_sizes))}")
            os.environ["EMBEDDING_DIMENSIONS"] = str(size0)
            reset_rag_config()

    opensearch = OpenSearchService()
    qdrant = QdrantService()

    if args.cleanup:
        if args.official_names and not args.force_delete_official:
            print("[warn] --cleanup ignored for official names (pass --force-delete-official to delete rag-* indices/collections).")
        else:
            if args.official_names:
                for idx in indices_official or []:
                    try:
                        opensearch.client.indices.delete(index=idx, ignore=[400, 404])
                    except Exception:
                        pass
                for coll in collections_official or []:
                    try:
                        qdrant.delete_collection(coll)
                    except Exception:
                        pass
            else:
                try:
                    opensearch.client.indices.delete(index=index_name, ignore=[400, 404])
                except Exception:
                    pass
                try:
                    qdrant.delete_collection(collection_name)
                except Exception:
                    pass

    if args.official_names:
        # Create all official indices/collections (safe if already exists).
        opensearch.ensure_all_indices()
        qdrant.create_all_collections()
    else:
        if not opensearch.ensure_index(index_name):
            raise SystemExit(f"Failed to create OpenSearch index: {index_name}")
        qdrant.create_collection(collection_name, vector_size=int(os.environ["EMBEDDING_DIMENSIONS"]))

    pipeline = RAGPipeline()
    pipeline._ensure_components()

    # Seed chunks into OpenSearch + Qdrant + Neo4j.
    seed_chunks = _seed_chunks()
    now = int(time.time())

    if pipeline._neo4j is None:
        raise SystemExit("Neo4j MVP component not available (check neo4j python driver + env).")

    docs_for_neo4j: Dict[str, Tuple[SeedChunk, List[Dict[str, Any]]]] = {}
    payloads: List[UpsertPayload] = []

    # Resolve per-source official index/collection targets.
    source_to_index = {
        "lei": cfg.opensearch_index_lei,
        "juris": cfg.opensearch_index_juris,
        "pecas_modelo": cfg.opensearch_index_pecas,
        "pecas": cfg.opensearch_index_pecas,
        "doutrina": cfg.opensearch_index_doutrina,
        "sei": cfg.opensearch_index_sei,
        "local": cfg.opensearch_index_local,
    }
    source_to_collection = {
        "lei": cfg.qdrant_collection_lei,
        "juris": cfg.qdrant_collection_juris,
        "pecas_modelo": cfg.qdrant_collection_pecas,
        "pecas": cfg.qdrant_collection_pecas,
        "doutrina": cfg.qdrant_collection_doutrina,
        "sei": cfg.qdrant_collection_sei,
        "local": cfg.qdrant_collection_local,
    }

    for chunk in seed_chunks:
        chunk_uid = f"it-{uuid.uuid4()}"
        doc_hash = f"it-{chunk.doc_id}"
        metadata = {"title": chunk.title, "source_type": chunk.source_type, "doc_id": chunk.doc_id}

        target_index = index_name
        target_collection = collection_name
        if args.official_names:
            target_index = source_to_index.get(chunk.source_type, cfg.opensearch_index_local)
            target_collection = source_to_collection.get(chunk.source_type, cfg.qdrant_collection_local)

        # OpenSearch: use allowed_users for private visibility.
        opensearch.index_chunk(
            chunk_uid=chunk_uid,
            text=chunk.text,
            index=str(target_index),
            doc_id=chunk.doc_id,
            scope=chunk.scope,
            # Keep tenant_id on all docs so tenant-scoped queries see global + private consistently.
            tenant_id=tenant_id,
            allowed_users=[user_id] if chunk.scope == "private" else None,
            sigilo="publico",
            chunk_index=0,
            title=chunk.title,
            source_type=chunk.source_type,
            metadata=metadata,
            refresh=False,
        )

        # Qdrant: embed + upsert
        if pipeline._embeddings is None:
            raise SystemExit("Embeddings component not available.")
        vec = await asyncio.to_thread(pipeline._embeddings.embed_query, chunk.text)
        payloads.append(
            UpsertPayload(
                chunk_uid=chunk_uid,
                vector=list(vec),
                text=chunk.text,
                tenant_id=tenant_id,
                scope=chunk.scope,
                sigilo="publico",
                group_ids=[],
                case_id=None,
                allowed_users=[user_id] if chunk.scope == "private" else [],
                uploaded_at=now,
                metadata=metadata,
            )
        )

        # Neo4j: batch per document
        docs_for_neo4j.setdefault(doc_hash, (chunk, []))[1].append(
            {"chunk_uid": chunk_uid, "text": chunk.text, "chunk_index": 0}
        )

    if args.official_names:
        # Upsert per target collection.
        by_collection: Dict[str, List[UpsertPayload]] = {}
        for pld in payloads:
            st = (pld.metadata or {}).get("source_type") or "local"
            coll = source_to_collection.get(str(st), cfg.qdrant_collection_local)
            by_collection.setdefault(coll, []).append(pld)
        for coll, items in by_collection.items():
            qdrant.upsert(coll, items)
        opensearch.refresh(index=",".join(indices_official or cfg.get_opensearch_indices()))
    else:
        qdrant.upsert(collection_name, payloads)
        opensearch.refresh(index=index_name)

    for doc_hash, (one_chunk, chunks) in docs_for_neo4j.items():
        pipeline._neo4j.ingest_document(
            doc_hash=doc_hash,
            chunks=chunks,
            metadata={"title": one_chunk.title, "source_type": one_chunk.source_type, "doc_id": one_chunk.doc_id},
            tenant_id=tenant_id,
            scope=one_chunk.scope,
            case_id=None,
            extract_entities=True,
            semantic_extraction=False,
            extract_facts=False,
        )

    # Run queries.
    queries = [
        ("argument", "dano moral STJ REsp 1234567", True),
        ("lexical", "Lei 8.666/1993 art. 37", False),
        ("semantic", "responsabilidade civil do Estado por omissão", False),
    ]

    ok = True
    for label, q, want_argument in queries:
        # Backend switching: ArgumentRAG currently lives in the legacy GraphRAG store.
        # Keep Neo4j MVP for the other queries (path-based context).
        os.environ["RAG_GRAPH_ENRICH_BACKEND"] = "legacy" if want_argument else "neo4j_mvp"

        indices_arg = indices_official if args.official_names else [index_name]
        collections_arg = collections_official if args.official_names else [collection_name]

        result = await pipeline.search(
            q,
            indices=list(indices_arg or []),
            collections=list(collections_arg or []),
            filters={"tenant_id": tenant_id, "user_id": user_id, "include_global": True},
            top_k=6,
            include_graph=True,
            argument_graph_enabled=want_argument,
            hyde_enabled=args.use_llm,
            multi_query=args.use_llm,
            multi_query_max=2,
            crag_gate=args.use_llm,
            tenant_id=tenant_id,
            scope="",  # auto scope: derive from filters
        )

        # Basic assertions
        hits = result.results or []
        mode = getattr(result.trace.search_mode, "value", str(result.trace.search_mode))
        graph_summary_len = len((result.graph_context.summary or "").strip()) if result.graph_context else 0
        graph_paths = len(getattr(result.graph_context, "paths", []) or []) if result.graph_context else 0
        stage = result.trace.get_stage(PipelineStage.GRAPH_ENRICH)
        legacy_used = bool(getattr(stage, "data", None) and stage.data.get("legacy_graph_used"))
        has_legacy_prefix = bool(result.graph_context and (result.graph_context.summary or "").startswith("Use apenas como evidencia"))

        print(
            f"[{label}] mode={mode} hits={len(hits)} "
            f"graph_summary_len={graph_summary_len} graph_paths={graph_paths} "
            f"legacy_used={legacy_used} legacy_prefix={has_legacy_prefix}"
        )

        if label == "lexical" and mode != "lexical_only":
            ok = False
            print("  FAIL: expected lexical_only routing for citation query")

        if label == "argument":
            if graph_summary_len <= 0:
                ok = False
                print("  FAIL: expected non-empty graph_context.summary for ArgumentRAG")

    try:
        if pipeline._neo4j is not None:
            pipeline._neo4j.close()
    except Exception:
        pass

    # Optional: agentic dataset router (LLM) smoke check
    if args.use_llm and args.test_agentic_router:
        try:
            from app.services.ai.agentic_rag import AgenticRAGRouter, DatasetRegistry

            routed = await AgenticRAGRouter(DatasetRegistry()).route(
                query="Preciso de jurisprudência sobre dano moral no STJ",
                history=[],
                summary_text=None,
            )
            datasets = routed.get("datasets") if isinstance(routed, dict) else None
            print(f"[agentic_router] ok={bool(datasets)} datasets={datasets or []}")
        except Exception as e:
            ok = False
            print(f"[agentic_router] FAIL: {e}")

    return 0 if ok else 2


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--use-llm", action="store_true", help="Enable HyDE/multiquery/CRAG (uses configured LLM keys).")
    parser.add_argument("--enable-rerank", action="store_true", help="Enable reranking stage (local model by default).")
    parser.add_argument("--enable-compression", action="store_true", help="Enable compression stage.")
    parser.add_argument("--cleanup", action="store_true", help="Delete and recreate test index/collection before seeding.")
    parser.add_argument("--official-names", action="store_true", help="Use canonical rag-* OpenSearch indices and Qdrant collections from config.")
    parser.add_argument("--force-delete-official", action="store_true", help="Allow --cleanup to delete official rag-* indices/collections.")
    parser.add_argument("--test-agentic-router", action="store_true", help="Also smoke-test AgenticRAGRouter when --use-llm is set.")
    parser.add_argument("--tenant-id", default="tenant-it", help="Tenant id used in filters (non-global scopes).")
    parser.add_argument("--user-id", default="user-it", help="User id used for private scope access.")
    parser.add_argument("--opensearch-index", default="rag-it-local", help="OpenSearch index name for the test.")
    parser.add_argument("--qdrant-collection", default="it_local_chunks", help="Qdrant collection name for the test.")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
