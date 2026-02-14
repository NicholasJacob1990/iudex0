"""
Pipeline orchestrator: query → retrieve → rerank → answer.

Also handles the ingestion pipeline: parse → chunk → embed → store.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import List, Optional

from neo4j import GraphDatabase

from .config import settings
from .ingest.chunker import chunk_document, extract_text_from_file
from .ingest.contextual import build_context_prefixes
from .ingest.embedder import embed_query, embed_texts
from .ingest.graph_builder import GraphBuilder, IngestStats
from .models import Document, RetrievalResult, SearchResult, SourceType
from .retrieval.hybrid import hybrid_search
from .retrieval.reranker import rerank

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Index preflight — auto-creates required indexes on first use
# ---------------------------------------------------------------------------

_indexes_verified = False


def ensure_indexes(session) -> None:
    """
    Verify and create required Neo4j indexes if they don't exist.

    Called automatically on first search/ingest. Uses IF NOT EXISTS
    so it's safe to call multiple times.

    Critical indexes (vector, fulltext, uniqueness constraints) must all
    succeed — failure raises RuntimeError. Optional indexes (lookup) are
    best-effort.
    """
    global _indexes_verified
    if _indexes_verified:
        return

    dims = settings.voyage_dimensions

    # Critical indexes — failure here means search/ingest will break
    critical_statements = [
        # Vector index (HNSW)
        (
            f"CREATE VECTOR INDEX chunk_embedding IF NOT EXISTS "
            f"FOR (c:Chunk) ON c.embedding "
            f"OPTIONS {{indexConfig: {{"
            f"`vector.dimensions`: {dims}, "
            f"`vector.similarity_function`: 'cosine'"
            f"}}}}"
        ),
        # Fulltext index (BM25)
        (
            "CREATE FULLTEXT INDEX chunk_fulltext IF NOT EXISTS "
            "FOR (c:Chunk) ON EACH [c.text]"
        ),
        # Uniqueness constraints
        "CREATE CONSTRAINT chunk_unique_id IF NOT EXISTS FOR (c:Chunk) REQUIRE c.id IS UNIQUE",
        "CREATE CONSTRAINT document_unique_id IF NOT EXISTS FOR (d:Document) REQUIRE d.id IS UNIQUE",
        "CREATE CONSTRAINT entity_unique_id IF NOT EXISTS FOR (e:Entity) REQUIRE e.id IS UNIQUE",
    ]

    # Optional indexes — nice-to-have for performance but not essential
    optional_statements = [
        "CREATE INDEX entity_name IF NOT EXISTS FOR (e:Entity) ON (e.normalized_name)",
        "CREATE INDEX entity_type IF NOT EXISTS FOR (e:Entity) ON (e.entity_type)",
        "CREATE INDEX document_id IF NOT EXISTS FOR (d:Document) ON (d.id)",
        "CREATE INDEX chunk_id IF NOT EXISTS FOR (c:Chunk) ON (c.id)",
        "CREATE INDEX chunk_doc IF NOT EXISTS FOR (c:Chunk) ON (c.doc_id)",
    ]

    # Critical: must all succeed
    critical_ok = 0
    for stmt in critical_statements:
        try:
            session.run(stmt)
            critical_ok += 1
        except Exception as e:
            logger.error("CRITICAL index failed: %s — %s", stmt[:60], e)
            raise RuntimeError(
                f"Critical Neo4j index creation failed: {e}. "
                f"Run 'neo4j-rag setup' manually or check Neo4j version."
            ) from e

    # Optional: best-effort
    optional_ok = 0
    for stmt in optional_statements:
        try:
            session.run(stmt)
            optional_ok += 1
        except Exception as e:
            logger.warning("Optional index skipped: %s — %s", stmt[:60], e)

    _indexes_verified = True
    logger.info(
        "Neo4j indexes verified: %d/%d critical OK, %d/%d optional OK",
        critical_ok, len(critical_statements),
        optional_ok, len(optional_statements),
    )


def _infer_source_type(path: Path) -> SourceType:
    """Infer source type from file path."""
    path_str = str(path).lower()
    if "cursotrevo" in path_str or "trevo" in path_str:
        return SourceType.CURSO_TREVO
    elif "ceap" in path_str:
        return SourceType.CEAP
    return SourceType.NICHOLAS


def _make_doc_id(path: Path) -> str:
    return hashlib.sha256(str(path.resolve()).encode()).hexdigest()[:16]


def ingest_directory(
    directory: str,
    *,
    batch_size: int = 50,
    use_contextual_llm: bool = False,
) -> IngestStats:
    """
    Ingest all PDF/DOCX files from a directory into Neo4j.

    Steps per document:
    1. Extract text (PyMuPDF/python-docx)
    2. Chunk with legal-aware separators
    3. Generate contextual prefix (regex or LLM)
    4. Generate embeddings (voyage-4-large)
    5. Store in Neo4j (Document, Chunk, Entity nodes + relationships)
    """
    dir_path = Path(directory)
    if not dir_path.exists():
        raise FileNotFoundError(f"Directory not found: {directory}")

    files = sorted(
        p for p in dir_path.rglob("*")
        if p.suffix.lower() in (".pdf", ".docx", ".txt")
    )
    logger.info(f"Found {len(files)} files in {directory}")

    total_stats = IngestStats()

    # Ensure indexes exist before ingesting
    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )
    try:
        with driver.session(database=settings.neo4j_database) as session:
            ensure_indexes(session)
    finally:
        driver.close()

    with GraphBuilder() as builder:
        for i in range(0, len(files), batch_size):
            batch_files = files[i : i + batch_size]
            batch_docs = []

            for file_path in batch_files:
                try:
                    text, doc_type = extract_text_from_file(file_path)
                    if not text.strip():
                        logger.warning(f"Empty text: {file_path}")
                        continue

                    doc_id = _make_doc_id(file_path)
                    doc = Document(
                        id=doc_id,
                        title=file_path.stem,
                        source_type=_infer_source_type(file_path),
                        document_type=doc_type,
                        path=str(file_path),
                    )

                    chunks = chunk_document(text, doc_id, doc_type)
                    if not chunks:
                        logger.warning(f"No chunks: {file_path}")
                        continue

                    # Contextual prefixes
                    doc_prefix = text[:3000]
                    prefixes = build_context_prefixes(
                        [c.text for c in chunks],
                        doc_prefix,
                        use_llm=use_contextual_llm,
                    )
                    for chunk, prefix in zip(chunks, prefixes):
                        chunk.contextual_prefix = prefix

                    # Embeddings
                    embedding_inputs = [
                        (f"{c.contextual_prefix}\n\n{c.text}" if c.contextual_prefix else c.text)
                        for c in chunks
                    ]
                    embeddings = embed_texts(embedding_inputs)
                    for chunk, emb in zip(chunks, embeddings):
                        chunk.embedding = emb

                    batch_docs.append((doc, chunks))

                except Exception as e:
                    total_stats.errors.append(f"{file_path}: {e}")
                    logger.error(f"Failed to process {file_path}: {e}")

            if batch_docs:
                stats = builder.ingest_batch(batch_docs)
                total_stats.documents_created += stats.documents_created
                total_stats.chunks_created += stats.chunks_created
                total_stats.entities_extracted += stats.entities_extracted
                total_stats.mentions_created += stats.mentions_created
                total_stats.next_edges_created += stats.next_edges_created
                total_stats.pertence_a_created += stats.pertence_a_created
                total_stats.subdispositivo_de_created += stats.subdispositivo_de_created
                total_stats.errors.extend(stats.errors)

            logger.info(
                f"Batch {i // batch_size + 1}: "
                f"{total_stats.documents_created} docs, "
                f"{total_stats.chunks_created} chunks"
            )

    return total_stats


def search(
    query: str,
    *,
    top_n: Optional[int] = None,
) -> RetrievalResult:
    """
    Execute a full retrieval pipeline:
    1. Embed query (voyage-4-large)
    2. Hybrid search (vector + fulltext + graph)
    3. Rerank (Cohere)
    4. Return top results
    """
    top_n = top_n or settings.rerank_top_n

    # 1. Embed query
    query_embedding = embed_query(query)

    # 2. Hybrid search (with index preflight)
    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )

    try:
        with driver.session(database=settings.neo4j_database) as session:
            ensure_indexes(session)
            results = hybrid_search(session, query, query_embedding)
    finally:
        driver.close()

    total_candidates = len(results)

    # 3. Rerank
    final = rerank(query, results, top_n=top_n)

    return RetrievalResult(
        query=query,
        results=final,
        total_candidates=total_candidates,
    )
