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
    PARTIAL = "partial"            # Compound citation: some components matched (counts as verified)
    UNVERIFIED = "unverified"      # Not found anywhere


@dataclass
class CitationProvenance:
    """Proveniência de uma citação — de onde ela veio no documento original."""
    page_number: Optional[int] = None
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    source_file: Optional[str] = None
    doc_id: Optional[str] = None
    chunk_text: Optional[str] = None


@dataclass
class CitationVerification:
    entity_id: str
    entity_type: str
    name: str
    status: VerificationStatus
    found_in_context: bool
    found_in_neo4j: bool
    confidence: float
    provenance: Optional[CitationProvenance] = None


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
                    "provenance": {
                        "page_number": c.provenance.page_number,
                        "line_start": c.provenance.line_start,
                        "line_end": c.provenance.line_end,
                        "source_file": c.provenance.source_file,
                        "doc_id": c.provenance.doc_id,
                    } if c.provenance else None,
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


def extract_compound_citations_from_response(text: str) -> List[Any]:
    """
    Extrai citações compostas (hierárquicas) do texto de resposta LLM.

    Retorna lista de CompoundCitation com estrutura completa:
    law, code, article, paragraph, inciso, alinea, normalized_id.
    """
    if not text or not text.strip():
        return []
    try:
        from app.services.rag.core.neo4j_mvp import LegalEntityExtractor
        return LegalEntityExtractor.extract_compound_citations(text)
    except ImportError:
        logger.debug("LegalEntityExtractor compound extraction not available")
        return []


def verify_compound_against_context(
    compound_citations: List[Any],
    rag_context: str,
) -> Dict[str, Dict[str, bool]]:
    """
    Verifica citações compostas contra o contexto RAG.

    Para cada citação composta, verifica se seus componentes individuais
    (lei, artigo, código) aparecem no contexto. Retorna um dict mapeando
    normalized_id -> {full: bool, partial: bool, matched_parts: list}.
    """
    if not compound_citations or not rag_context:
        return {}

    # Extrai entidades simples do contexto para comparação de componentes
    context_entities = extract_legal_entities_from_response(rag_context)
    context_ids: Set[str] = {ent["entity_id"] for ent in context_entities}

    # Também extrai compound do contexto para matching exato
    context_compounds = extract_compound_citations_from_response(rag_context)
    context_compound_ids: Set[str] = {c.normalized_id for c in context_compounds}

    result: Dict[str, Dict[str, bool]] = {}

    for cc in compound_citations:
        nid = cc.normalized_id
        matched_parts: List[str] = []

        # Matching exato pelo normalized_id completo
        full_match = nid in context_compound_ids

        # Matching parcial: verificar componentes individuais
        if cc.article:
            art_num = re.sub(r"[^0-9.]", "", cc.article).replace(".", "")
            art_id = f"art_{art_num}"
            if art_id in context_ids:
                matched_parts.append("article")

        if cc.law:
            # Normaliza para formato entity_id
            law_clean = re.sub(r"[./\s]+", "_", cc.law.strip().lower())
            law_clean = re.sub(r"_+", "_", law_clean).strip("_")
            law_id = f"lei_{re.sub(r'[^0-9_]', '', law_clean)}"
            if any(eid.startswith("lei_") and law_id.rstrip("_") in eid for eid in context_ids):
                matched_parts.append("law")

        if cc.code:
            # Códigos podem aparecer como tribunal ou em referências
            code_lower = cc.code.lower()
            if any(code_lower in eid.lower() for eid in context_ids):
                matched_parts.append("code")

        partial_match = len(matched_parts) > 0

        result[nid] = {
            "full": full_match,
            "partial": partial_match,
            "matched_parts": matched_parts,
        }

    return result


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
    rag_chunks: Optional[List[Dict[str, Any]]] = None,
) -> GroundingResult:
    """
    Verify legal citations in LLM response against available sources.

    Args:
        response_text: The LLM-generated response text.
        rag_context: The RAG context string provided to the LLM.
        tenant_id: Tenant ID for Neo4j lookup.
        threshold: Minimum fidelity index before warning.
        enable_neo4j: Whether to also check Neo4j entity store.
        rag_chunks: Optional list of chunk dicts with provenance metadata
                    (page_number, line_start, line_end, source_file, doc_id, text).

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

    # Build chunk provenance index for fast lookup
    _chunk_provenance_map: Dict[str, CitationProvenance] = {}
    if rag_chunks:
        for chunk in rag_chunks:
            chunk_text_content = chunk.get("text", "") or chunk.get("chunk_text", "")
            # Extract entities from this chunk and map them to provenance
            chunk_entities = extract_legal_entities_from_response(chunk_text_content)
            provenance = CitationProvenance(
                page_number=chunk.get("page_number") or chunk.get("page"),
                line_start=chunk.get("line_start"),
                line_end=chunk.get("line_end"),
                source_file=chunk.get("source_file"),
                doc_id=chunk.get("doc_id"),
                chunk_text=chunk_text_content[:200] if chunk_text_content else None,
            )
            for cent in chunk_entities:
                ceid = cent.get("entity_id", "")
                if ceid and ceid not in _chunk_provenance_map:
                    _chunk_provenance_map[ceid] = provenance

    # Step 3b: Extract and verify compound citations
    compound_citations = extract_compound_citations_from_response(response_text)
    compound_context_hits: Dict[str, Dict[str, bool]] = {}
    if compound_citations:
        compound_context_hits = verify_compound_against_context(
            compound_citations, rag_context,
        )

    # Step 4: Build verification results (simple entities)
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
            provenance=_chunk_provenance_map.get(eid),
        ))

    # Step 4b: Add compound citation verifications
    seen_compound_ids: Set[str] = set()
    for cc in compound_citations:
        nid = cc.normalized_id
        if nid in seen_compound_ids:
            continue
        seen_compound_ids.add(nid)

        cc_hit = compound_context_hits.get(nid, {})
        full_match = cc_hit.get("full", False)
        partial_match = cc_hit.get("partial", False)

        if full_match:
            status = VerificationStatus.VERIFIED
            confidence = 1.0
        elif partial_match:
            status = VerificationStatus.PARTIAL
            confidence = 0.6
        else:
            status = VerificationStatus.UNVERIFIED
            confidence = 0.0

        verifications.append(CitationVerification(
            entity_id=nid,
            entity_type="compound_citation",
            name=cc.full_text,
            status=status,
            found_in_context=full_match or partial_match,
            found_in_neo4j=False,
            confidence=confidence,
            provenance=None,
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
