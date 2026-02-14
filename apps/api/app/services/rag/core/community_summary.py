"""
Community Summary — Leiden clustering + LLM summarization for legal KG.

Detects communities of related entities, generates summaries via LLM,
and stores them as (:Community) nodes in Neo4j. Summaries are used in
Stage 9 (graph enrichment) to answer macro questions like
"tendências do STJ em 2024" or "resumo sobre dano moral".

Usage:
    from app.services.rag.core.community_summary import (
        detect_and_summarize_communities,
        get_community_summaries_for_entities,
    )

    # Offline: recompute communities (Celery task or endpoint)
    stats = await detect_and_summarize_communities(tenant_id="t1")

    # Online: get relevant summaries during RAG Stage 9
    summaries = await get_community_summaries_for_entities(entity_ids, tenant_id)
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class CommunitySummaryStats:
    """Stats from community detection + summarization run."""
    communities_detected: int = 0
    communities_summarized: int = 0
    entities_clustered: int = 0
    errors: List[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []


async def detect_and_summarize_communities(
    tenant_id: str,
    *,
    max_levels: int = 10,
    min_community_size: int = 3,
    max_communities_to_summarize: int = 50,
    llm_provider: str = "",
) -> CommunitySummaryStats:
    """
    Detect communities via Leiden and generate summaries via LLM.

    Steps:
    1. Run Leiden clustering via GDS client
    2. For each community: extract member names and types
    3. Generate summary via LLM (Gemini Flash for cost efficiency)
    4. Save as (:Community) nodes linked to member entities

    Args:
        tenant_id: Tenant scope
        max_levels: Leiden hierarchy levels
        min_community_size: Minimum entities per community
        max_communities_to_summarize: Cap on LLM calls
        llm_provider: Override LLM provider (default: from env)
    """
    stats = CommunitySummaryStats()

    try:
        from app.services.rag.core.gds_analytics import get_gds_client
        gds = get_gds_client()
    except Exception as e:
        stats.errors.append(f"GDS client unavailable: {e}")
        return stats

    # 1. Detect communities
    try:
        result = await asyncio.to_thread(
            gds.detect_communities,
            tenant_id,
            max_levels=max_levels,
            min_community_size=min_community_size,
        )
        stats.communities_detected = result.total_communities
        stats.entities_clustered = sum(c["size"] for c in result.communities)
    except Exception as e:
        stats.errors.append(f"Leiden detection failed: {e}")
        return stats

    if not result.communities:
        logger.info("No communities detected for tenant %s", tenant_id)
        return stats

    # 2. Generate summaries
    communities_to_process = result.communities[:max_communities_to_summarize]

    for community in communities_to_process:
        try:
            summary = await _summarize_community(community, llm_provider=llm_provider)
            if summary:
                community["summary"] = summary
                stats.communities_summarized += 1
        except Exception as e:
            logger.warning("Failed to summarize community %s: %s", community.get("community_id"), e)
            stats.errors.append(f"summarize_{community.get('community_id')}: {e}")

    # 3. Write to Neo4j
    try:
        await _write_communities_to_neo4j(communities_to_process, tenant_id)
    except Exception as e:
        stats.errors.append(f"Neo4j write failed: {e}")

    logger.info(
        "Community summaries for tenant %s: %d detected, %d summarized, %d entities",
        tenant_id, stats.communities_detected, stats.communities_summarized, stats.entities_clustered,
    )
    return stats


async def _summarize_community(
    community: Dict[str, Any],
    *,
    llm_provider: str = "",
) -> Optional[str]:
    """Generate a summary for a community using LLM."""
    member_names = community.get("member_names", [])
    if not member_names:
        return None

    members_text = ", ".join(member_names[:15])
    size = community.get("size", len(member_names))

    prompt = (
        f"Você é um assistente jurídico. Analise este grupo de {size} entidades "
        f"jurídicas relacionadas e gere um resumo temático de 1-2 frases em português:\n\n"
        f"Entidades: {members_text}\n\n"
        f"Resumo temático:"
    )

    provider = llm_provider or os.getenv("COMMUNITY_SUMMARY_LLM_PROVIDER", "gemini")

    try:
        if provider == "gemini":
            def _run_gemini() -> Any:
                from google import genai

                client = genai.Client()
                model = os.getenv("COMMUNITY_SUMMARY_LLM_MODEL", "gemini-2.0-flash")
                return client.models.generate_content(model=model, contents=prompt)

            response = await asyncio.to_thread(_run_gemini)
            return response.text.strip()[:500] if response.text else None
        elif provider == "openai":
            def _run_openai() -> Any:
                import openai

                client = openai.OpenAI()
                model = os.getenv("COMMUNITY_SUMMARY_LLM_MODEL", "gpt-4o-mini")
                return client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=200,
                )

            response = await asyncio.to_thread(_run_openai)
            return response.choices[0].message.content.strip()[:500] if response.choices else None
        else:
            # Fallback: heuristic summary (no LLM cost)
            return f"Cluster temático com {size} entidades relacionadas: {members_text}"
    except Exception as e:
        logger.warning("LLM summarization failed, using heuristic: %s", e)
        return f"Cluster temático com {size} entidades: {members_text}"


async def _write_communities_to_neo4j(
    communities: List[Dict[str, Any]],
    tenant_id: str,
) -> None:
    """Write community nodes and link them to member entities."""
    try:
        from app.services.rag.core.neo4j_mvp import get_neo4j_mvp
        neo4j = get_neo4j_mvp()
    except Exception as e:
        logger.warning("Neo4j unavailable for community write: %s", e)
        return

    # First, clean up old communities for this tenant
    cleanup_query = """
        MATCH (c:Community {tenant_id: $tenant_id})
        DETACH DELETE c
    """
    try:
        await _neo4j_execute_write(neo4j, cleanup_query, {"tenant_id": tenant_id})
    except Exception as e:
        logger.debug("Community cleanup failed (may not exist): %s", e)

    # Create new community nodes in batch
    rows: List[Dict[str, Any]] = []
    for comm in communities:
        summary = comm.get("summary", "")
        members = comm.get("members", [])
        comm_id = f"community_{tenant_id[:8]}_{comm.get('community_id', 0)}"
        rows.append(
            {
                "comm_id": comm_id,
                "name": f"Cluster: {', '.join(comm.get('member_names', [])[:3])}",
                "summary": summary,
                "size": comm.get("size", 0),
                "tenant_id": tenant_id,
                "member_ids": [m.get("entity_id", "") for m in members if m.get("entity_id")],
            }
        )

    if not rows:
        return

    create_query = """
        UNWIND $rows AS row
        MERGE (c:Community {community_id: row.comm_id})
        SET c.name = row.name,
            c.summary = row.summary,
            c.size = row.size,
            c.tenant_id = row.tenant_id,
            c.level = 0
    """
    link_query = """
        UNWIND $rows AS row
        MATCH (c:Community {community_id: row.comm_id})
        UNWIND row.member_ids AS eid
        MATCH (e:Entity {entity_id: eid})
        MERGE (e)-[:BELONGS_TO]->(c)
    """
    await _neo4j_execute_write(neo4j, create_query, {"rows": rows})
    await _neo4j_execute_write(neo4j, link_query, {"rows": rows})


async def get_community_summaries_for_entities(
    entity_ids: List[str],
    tenant_id: str,
    *,
    limit: int = 5,
) -> List[Dict[str, Any]]:
    """
    Get community summaries relevant to a set of entities.

    Used in RAG Stage 9 to enrich results with macro context.

    Args:
        entity_ids: Entity IDs from retrieval
        tenant_id: Tenant scope
        limit: Max communities to return

    Returns:
        List of {community_id, summary, size, member_names}
    """
    if not entity_ids:
        return []

    try:
        from app.services.rag.core.neo4j_mvp import get_neo4j_mvp
        neo4j = get_neo4j_mvp()
    except Exception:
        return []

    query = """
        UNWIND $entity_ids AS eid
        MATCH (e:Entity {entity_id: eid})-[:BELONGS_TO]->(c:Community)
        WHERE c.tenant_id = $tenant_id AND c.summary IS NOT NULL
        WITH DISTINCT c
        RETURN c.community_id AS community_id,
               c.summary AS summary,
               c.size AS size,
               c.name AS name
        ORDER BY c.size DESC
        LIMIT $limit
    """
    try:
        results = await _neo4j_execute_read(
            neo4j,
            query,
            {
                "entity_ids": entity_ids,
                "tenant_id": tenant_id,
                "limit": limit,
            },
        )
        return [dict(r) for r in results] if results else []
    except Exception as e:
        logger.debug("Community summary lookup failed: %s", e)
        return []


async def _neo4j_execute_write(neo4j: Any, query: str, params: Dict[str, Any]) -> Any:
    """Execute write query using async Neo4j APIs when available."""
    write_async = getattr(neo4j, "_execute_write_async", None)
    if callable(write_async):
        maybe_result = write_async(query, params)
        if inspect.isawaitable(maybe_result):
            return await maybe_result
    return await asyncio.to_thread(neo4j._execute_write, query, params)


async def _neo4j_execute_read(neo4j: Any, query: str, params: Dict[str, Any]) -> Any:
    """Execute read query using async Neo4j APIs when available."""
    read_async = getattr(neo4j, "_execute_read_async", None)
    if callable(read_async):
        maybe_result = read_async(query, params)
        if inspect.isawaitable(maybe_result):
            return await maybe_result
    return await asyncio.to_thread(neo4j._execute_read, query, params)
