"""
LegalKGPipeline — Composed Knowledge Graph construction pipeline.

Architecture:
    TextChunks → [LegalRegexExtractor ∥ LLMExtractor(optional)] → Neo4jWriter → FuzzyResolver

The pipeline:
1. Receives pre-chunked text (from RAG pipeline's chunking stage)
2. Extracts entities via regex (deterministic, no cost)
3. Optionally extracts via LLM (Gemini Flash) in parallel
4. Writes to Neo4j (enrichment-only, not retrieval)
5. Resolves duplicate entities (rapidfuzz)

Usage:
    from app.services.rag.core.kg_builder.pipeline import run_kg_builder

    # After RAG pipeline ingest (async, fire-and-forget)
    await run_kg_builder(
        chunks=chunks,
        doc_hash=doc_hash,
        tenant_id=tenant_id,
        use_llm=True,
    )
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.lower() in ("1", "true", "yes", "on")


# =============================================================================
# SIMPLE PIPELINE (no neo4j-graphrag dependency required)
# =============================================================================

async def run_kg_builder(
    chunks: List[Dict[str, Any]],
    doc_hash: str,
    tenant_id: str,
    *,
    case_id: Optional[str] = None,
    scope: str = "global",
    use_llm: bool = False,
    use_resolver: bool = True,
) -> Dict[str, Any]:
    """
    Run the KG Builder pipeline on pre-chunked text.

    This is the primary entry point. It can work in two modes:
    1. **Simple mode** (default): Uses LegalRegexExtractor + direct Neo4j writes
    2. **neo4j-graphrag mode**: Uses SimpleKGPipeline when available

    Args:
        chunks: List of chunk dicts with 'text', 'chunk_uid'
        doc_hash: Document hash for linking
        tenant_id: Tenant ID for multi-tenant isolation
        case_id: Optional case ID
        scope: Data scope (global, private, group, local)
        use_llm: If True, also run LLM extraction (costs per doc)
        use_resolver: If True, run entity resolution after extraction

    Returns:
        Stats dict with extraction and resolution counts.
    """
    stats: Dict[str, Any] = {
        "doc_hash": doc_hash,
        "chunks_processed": 0,
        "regex_nodes": 0,
        "regex_relationships": 0,
        "llm_nodes": 0,
        "llm_relationships": 0,
        "resolved_merges": 0,
        "mode": "simple",
        "errors": [],
    }

    # Try neo4j-graphrag SimpleKGPipeline first
    if _env_bool("KG_BUILDER_USE_GRAPHRAG", False):
        try:
            result = await _run_graphrag_pipeline(
                chunks, doc_hash, tenant_id,
                case_id=case_id, scope=scope,
                use_llm=use_llm,
            )
            stats.update(result)
            stats["mode"] = "neo4j-graphrag"
            return stats
        except ImportError:
            logger.info("neo4j-graphrag not available, falling back to simple mode")
        except Exception as e:
            logger.warning("neo4j-graphrag pipeline failed, falling back: %s", e)
            stats["errors"].append(f"graphrag_fallback: {e}")

    # Simple mode: LegalRegexExtractor + direct writes
    try:
        regex_stats = await _run_regex_extraction(
            chunks, doc_hash, tenant_id,
            case_id=case_id, scope=scope,
        )
        stats.update(regex_stats)
    except Exception as e:
        logger.error("Regex extraction failed: %s", e)
        stats["errors"].append(f"regex: {e}")

    # Optional: LLM extraction via ArgumentNeo4jService
    if use_llm:
        try:
            llm_stats = await _run_argument_extraction(
                chunks, doc_hash, tenant_id,
                case_id=case_id, scope=scope,
            )
            stats["llm_nodes"] = llm_stats.get("total_claims", 0) + llm_stats.get("total_evidence", 0)
            stats["llm_relationships"] = llm_stats.get("total_relationships", 0)
        except Exception as e:
            logger.error("Argument extraction failed: %s", e)
            stats["errors"].append(f"llm: {e}")

    # Optional: Entity resolution
    if use_resolver and _env_bool("KG_BUILDER_RESOLVE_ENTITIES", True):
        try:
            from app.services.rag.core.kg_builder.fuzzy_resolver import resolve_entities
            result = await resolve_entities()
            stats["resolved_merges"] = result.merged_count
        except Exception as e:
            logger.debug("Entity resolution skipped: %s", e)

    logger.info(
        "KG Builder complete for doc %s: %d regex nodes, %d llm nodes, %d merges",
        doc_hash, stats["regex_nodes"], stats["llm_nodes"], stats["resolved_merges"],
    )
    return stats


# =============================================================================
# SIMPLE MODE: Regex + Direct Neo4j Writes
# =============================================================================

async def _run_regex_extraction(
    chunks: List[Dict[str, Any]],
    doc_hash: str,
    tenant_id: str,
    *,
    case_id: Optional[str] = None,
    scope: str = "global",
) -> Dict[str, Any]:
    """Run regex extraction and write to Neo4j via neo4j_mvp."""
    from app.services.rag.core.kg_builder.legal_extractor import LegalRegexExtractor

    extractor = LegalRegexExtractor(create_relationships=True)
    result = await extractor.run(chunks)

    stats = {
        "chunks_processed": len(chunks),
        "regex_nodes": len(result.nodes),
        "regex_relationships": len(result.relationships),
    }

    # Write to Neo4j via existing neo4j_mvp service
    try:
        from app.services.rag.core.neo4j_mvp import get_neo4j_mvp
        neo4j = get_neo4j_mvp()

        for node in result.nodes:
            try:
                neo4j._merge_entity({
                    "entity_type": node["properties"].get("entity_type", ""),
                    "entity_id": node["id"],
                    "name": node["properties"].get("name", ""),
                    "normalized": node["properties"].get("normalized", ""),
                    "metadata": str(node["properties"]),
                })
            except Exception as e:
                logger.debug("Failed to write node %s: %s", node["id"], e)

        for rel in result.relationships:
            if rel["type"] == "RELATED_TO":
                try:
                    neo4j.link_related_entities(rel["start"], rel["end"])
                except Exception:
                    pass

    except Exception as e:
        logger.warning("Could not write regex results to Neo4j: %s", e)

    return stats


async def _run_argument_extraction(
    chunks: List[Dict[str, Any]],
    doc_hash: str,
    tenant_id: str,
    *,
    case_id: Optional[str] = None,
    scope: str = "global",
) -> Dict[str, Any]:
    """
    Run LLM-based argument extraction via Gemini Flash structured output.

    Uses ArgumentLLMExtractor for claims/evidence/actors/issues extraction,
    with evidence scoring by tribunal authority.

    Falls back to heuristic-based ArgumentNeo4jService if LLM is unavailable.
    """
    try:
        from app.services.rag.core.kg_builder.argument_llm_extractor import (
            ArgumentLLMExtractor,
        )

        extractor = ArgumentLLMExtractor()
        total_stats: Dict[str, Any] = {
            "total_claims": 0,
            "total_evidence": 0,
            "total_actors": 0,
            "total_relationships": 0,
            "mode": "llm",
        }

        for chunk in chunks:
            text = chunk.get("text", "")
            chunk_uid = chunk.get("chunk_uid", "")
            if not text or not chunk_uid:
                continue

            chunk_stats = await extractor.extract_and_ingest(
                text,
                chunk_uid=chunk_uid,
                doc_id=doc_hash,
                doc_hash=doc_hash,
                tenant_id=tenant_id,
                case_id=case_id,
                scope=scope,
            )

            total_stats["total_claims"] += chunk_stats.get("llm_claims", 0)
            total_stats["total_evidence"] += chunk_stats.get("llm_evidence", 0)
            total_stats["total_actors"] += chunk_stats.get("llm_actors", 0)
            total_stats["total_relationships"] += chunk_stats.get("llm_relationships", 0)

        return total_stats

    except (ImportError, Exception) as e:
        logger.warning("LLM argument extraction unavailable, falling back to heuristic: %s", e)

        # Fallback: heuristic-based extraction via ArgumentNeo4jService
        from app.services.rag.core.argument_neo4j import get_argument_neo4j

        svc = get_argument_neo4j()
        result = svc.ingest_arguments(
            doc_hash=doc_hash,
            chunks=chunks,
            tenant_id=tenant_id,
            case_id=case_id,
            scope=scope,
        )
        result["mode"] = "heuristic"
        return result


# =============================================================================
# NEO4J-GRAPHRAG MODE: SimpleKGPipeline
# =============================================================================

async def _run_graphrag_pipeline(
    chunks: List[Dict[str, Any]],
    doc_hash: str,
    tenant_id: str,
    *,
    case_id: Optional[str] = None,
    scope: str = "global",
    use_llm: bool = False,
) -> Dict[str, Any]:
    """
    Run the neo4j-graphrag SimpleKGPipeline.

    Requires: pip install neo4j-graphrag[openai]
    """
    from neo4j_graphrag.experimental.pipeline.kg_builder import SimpleKGPipeline
    from neo4j import GraphDatabase

    from app.services.rag.config import get_rag_config
    from app.services.rag.core.kg_builder.legal_schema import build_legal_schema

    config = get_rag_config()

    driver = GraphDatabase.driver(
        config.neo4j_uri,
        auth=(config.neo4j_user, config.neo4j_password),
    )

    # Build LLM instance for extraction
    llm = None
    embedder = None
    if use_llm:
        try:
            from neo4j_graphrag.llm import OpenAILLM
            llm = OpenAILLM(
                model_name=os.getenv("KG_BUILDER_LLM_MODEL", "gemini-2.0-flash"),
                api_key=os.getenv("GOOGLE_API_KEY", ""),
            )
        except Exception as e:
            logger.warning("Could not create LLM for KG Builder: %s", e)

    schema = build_legal_schema()

    pipeline = SimpleKGPipeline(
        llm=llm,
        driver=driver,
        schema=schema,
        from_pdf=False,
        perform_entity_resolution=True,
        neo4j_database=config.neo4j_database,
        on_error="IGNORE",
    )

    # Combine chunks into text for SimpleKGPipeline
    text = "\n\n".join(c.get("text", "") for c in chunks if c.get("text"))

    try:
        await pipeline.run_async(text=text)
    finally:
        driver.close()

    return {
        "chunks_processed": len(chunks),
        "mode": "neo4j-graphrag",
    }
