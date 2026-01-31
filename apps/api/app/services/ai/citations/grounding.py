"""
Citation Grounding — Post-generation verification of legal citations.

Extracts legal entities from LLM response text and verifies each one
against: (1) the RAG context provided to the LLM, (2) Neo4j entity store.

Returns a GroundingResult with fidelity_index and per-citation status.

Usage:
    from app.services.ai.citations.grounding import verify_citations, annotate_response_text

    result = await verify_citations(response_text, rag_context, tenant_id="t1")
    if result.unverified_count > 0:
        text = annotate_response_text(response_text, result)
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


# =============================================================================
# Data Structures
# =============================================================================

class VerificationStatus(str, Enum):
    VERIFIED = "verified"          # Found in RAG context AND Neo4j
    CONTEXT_ONLY = "context_only"  # Found in RAG context only (counts as verified)
    NEO4J_ONLY = "neo4j_only"      # Found in Neo4j only (counts as verified)
    UNVERIFIED = "unverified"      # Not found anywhere


@dataclass
class CitationVerification:
    entity_id: str
    entity_type: str
    name: str
    status: VerificationStatus
    found_in_context: bool
    found_in_neo4j: bool
    confidence: float


@dataclass
class GroundingResult:
    citations: List[CitationVerification]
    fidelity_index: float
    total_legal_citations: int
    verified_count: int
    unverified_count: int
    elapsed_ms: float
    below_threshold: bool
    threshold: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fidelity_index": round(self.fidelity_index, 3),
            "total_legal_citations": self.total_legal_citations,
            "verified_count": self.verified_count,
            "unverified_count": self.unverified_count,
            "elapsed_ms": round(self.elapsed_ms, 1),
            "below_threshold": self.below_threshold,
            "threshold": self.threshold,
            "citations": [
                {
                    "entity_id": c.entity_id,
                    "entity_type": c.entity_type,
                    "name": c.name,
                    "status": c.status.value,
                    "confidence": round(c.confidence, 2),
                }
                for c in self.citations
            ],
        }


# =============================================================================
# Entity Extraction
# =============================================================================

def extract_legal_entities_from_response(text: str) -> List[Dict[str, Any]]:
    """
    Extract legal entities from LLM response using LegalEntityExtractor.
    Deterministic regex-based, <1ms.
    """
    if not text or not text.strip():
        return []
    try:
        from app.services.rag.core.neo4j_mvp import LegalEntityExtractor
        return LegalEntityExtractor.extract(text)
    except ImportError:
        logger.debug("LegalEntityExtractor not available")
        return []


# =============================================================================
# Context Verification
# =============================================================================

def verify_against_context(
    entities: List[Dict[str, Any]],
    rag_context: str,
) -> Dict[str, bool]:
    """
    Verify which entities exist in the RAG context string.
    Runs LegalEntityExtractor on the context to get entity_ids that
    were available to the LLM.
    """
    if not entities or not rag_context:
        return {ent["entity_id"]: False for ent in entities}

    context_entities = extract_legal_entities_from_response(rag_context)
    context_ids: Set[str] = {ent["entity_id"] for ent in context_entities}

    return {
        ent["entity_id"]: ent["entity_id"] in context_ids
        for ent in entities
    }


# =============================================================================
# Neo4j Verification
# =============================================================================

def verify_against_neo4j(
    entity_ids: List[str],
    tenant_id: str,
) -> Dict[str, bool]:
    """
    Batch check which entity_ids exist in Neo4j.
    Uses UNIQUE index on entity_id for fast lookup (<10ms).
    Fail-open: returns {} on any error.
    """
    if not entity_ids:
        return {}
    try:
        from app.services.rag.core.neo4j_mvp import get_neo4j_mvp
        neo4j = get_neo4j_mvp()
        if neo4j is None:
            return {}
        query = (
            "MATCH (e:Entity) WHERE e.entity_id IN $ids "
            "RETURN e.entity_id AS eid"
        )
        results = neo4j._execute_read(query, {"ids": entity_ids})
        found: Set[str] = {r["eid"] for r in results}
        return {eid: eid in found for eid in entity_ids}
    except Exception as e:
        logger.debug("Neo4j entity lookup failed: %s", e)
        return {}


# =============================================================================
# Main Verification
# =============================================================================

async def verify_citations(
    response_text: str,
    rag_context: str,
    *,
    tenant_id: str = "",
    threshold: float = 0.85,
    enable_neo4j: bool = True,
) -> GroundingResult:
    """
    Verify legal citations in LLM response against available sources.

    Args:
        response_text: The LLM-generated response text.
        rag_context: The RAG context string provided to the LLM.
        tenant_id: Tenant ID for Neo4j lookup.
        threshold: Minimum fidelity index before warning.
        enable_neo4j: Whether to also check Neo4j entity store.

    Returns:
        GroundingResult with per-citation verification and fidelity index.
    """
    t0 = time.perf_counter()

    # Step 1: Extract entities from LLM response
    entities = extract_legal_entities_from_response(response_text)

    if not entities:
        return GroundingResult(
            citations=[],
            fidelity_index=1.0,
            total_legal_citations=0,
            verified_count=0,
            unverified_count=0,
            elapsed_ms=(time.perf_counter() - t0) * 1000,
            below_threshold=False,
            threshold=threshold,
        )

    # Step 2: Verify against RAG context
    context_hits = verify_against_context(entities, rag_context)

    # Step 3: Verify against Neo4j (fail-open)
    neo4j_hits: Dict[str, bool] = {}
    if enable_neo4j:
        try:
            entity_ids = [e["entity_id"] for e in entities]
            neo4j_hits = await asyncio.to_thread(
                verify_against_neo4j, entity_ids, tenant_id,
            )
        except Exception as e:
            logger.debug("Neo4j grounding check failed: %s", e)

    # Step 4: Build verification results
    verifications: List[CitationVerification] = []
    for ent in entities:
        eid = ent["entity_id"]
        in_context = context_hits.get(eid, False)
        in_neo4j = neo4j_hits.get(eid, False)

        if in_context and in_neo4j:
            status = VerificationStatus.VERIFIED
            confidence = 1.0
        elif in_context:
            status = VerificationStatus.CONTEXT_ONLY
            confidence = 0.9
        elif in_neo4j:
            status = VerificationStatus.NEO4J_ONLY
            confidence = 0.7
        else:
            status = VerificationStatus.UNVERIFIED
            confidence = 0.0

        verifications.append(CitationVerification(
            entity_id=eid,
            entity_type=ent.get("entity_type", ""),
            name=ent.get("name", eid),
            status=status,
            found_in_context=in_context,
            found_in_neo4j=in_neo4j,
            confidence=confidence,
        ))

    # Step 5: Calculate fidelity index
    total = len(verifications)
    verified = sum(
        1 for v in verifications
        if v.status != VerificationStatus.UNVERIFIED
    )
    fidelity = verified / total if total > 0 else 1.0

    elapsed = (time.perf_counter() - t0) * 1000

    logger.info(
        "Citation grounding: %d/%d verified (fidelity=%.2f) in %.1fms",
        verified, total, fidelity, elapsed,
    )

    return GroundingResult(
        citations=verifications,
        fidelity_index=fidelity,
        total_legal_citations=total,
        verified_count=verified,
        unverified_count=total - verified,
        elapsed_ms=elapsed,
        below_threshold=fidelity < threshold,
        threshold=threshold,
    )


# =============================================================================
# Response Annotation
# =============================================================================

def annotate_response_text(
    text: str,
    grounding: GroundingResult,
) -> str:
    """
    Annotate response text with verification status for unverified citations.

    - Unverified citations get [NÃO VERIFICADO] tag after first occurrence.
    - If below threshold, appends a warning banner at the end.
    """
    if not grounding.citations or not text:
        return text

    unverified_names = [
        c.name for c in grounding.citations
        if c.status == VerificationStatus.UNVERIFIED
    ]

    if not unverified_names:
        return text

    result = text
    for name in unverified_names:
        pattern = re.escape(name)
        result = re.sub(
            pattern,
            f"{name} [NÃO VERIFICADO]",
            result,
            count=1,
        )

    if grounding.below_threshold:
        warning = (
            f"\n\n> **Aviso de Fidelidade**: {grounding.unverified_count} de "
            f"{grounding.total_legal_citations} citações jurídicas não puderam "
            f"ser verificadas automaticamente. Índice de fidelidade: "
            f"{grounding.fidelity_index:.0%} (mínimo: {grounding.threshold:.0%}). "
            f"Recomenda-se verificação manual.\n"
        )
        result = result.rstrip() + warning

    return result
