"""
LegalKGPipeline — Composed Knowledge Graph construction pipeline.

Architecture:
    TextChunks → [LegalRegexExtractor ∥ GLiNERExtractor(optional) ∥ LLMExtractor(optional)] → Neo4jWriter → FuzzyResolver

The pipeline:
1. Receives pre-chunked text (from RAG pipeline's chunking stage)
2. Extracts entities via regex (deterministic, no cost)
3. Optionally extracts via GLiNER zero-shot NER (no cost, catches regex misses)
4. Optionally extracts via LLM (Gemini Flash) in parallel
5. Writes to Neo4j (enrichment-only, not retrieval)
6. Resolves duplicate entities (rapidfuzz)

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
import hashlib
import logging
import os
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.lower() in ("1", "true", "yes", "on")


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except Exception:
        return default


def _estimate_tokens_from_chars(chars: int) -> int:
    # Rough heuristic (works well enough for cost/volume tracking): ~4 chars/token.
    if chars <= 0:
        return 0
    return max(1, int(round(chars / 4)))


def _kg_schema_mode() -> str:
    raw = os.getenv("KG_BUILDER_SCHEMA_MODE", "ontology")
    mode = str(raw).strip().lower()
    if mode not in {"ontology", "auto", "hybrid"}:
        logger.warning("Invalid KG_BUILDER_SCHEMA_MODE=%r, using 'ontology'", raw)
        return "ontology"
    return mode


def _should_trigger_llm_fallback(
    chunks: List[Dict[str, Any]],
    stats: Dict[str, Any],
    *,
    min_total_nodes: int,
    min_gliner_coverage: float,
    min_gliner_confidence: float,
    gliner_enabled: bool,
) -> Dict[str, Any]:
    """
    Decide whether to trigger LLM extraction automatically.

    Heuristics:
    - Low entity count overall.
    - Low GLiNER coverage by chunk (only if GLiNER enabled).
    - Low GLiNER confidence (only if GLiNER enabled).
    """
    chunk_count = max(1, len(chunks))
    total_nodes = int(stats.get("regex_nodes", 0)) + int(stats.get("gliner_nodes", 0))
    gliner_nodes = int(stats.get("gliner_nodes", 0))
    gliner_coverage = gliner_nodes / chunk_count
    gliner_avg_conf = float(stats.get("gliner_avg_confidence", 0.0) or 0.0)

    reasons: List[str] = []
    if total_nodes < min_total_nodes:
        reasons.append(f"low_total_nodes:{total_nodes}<{min_total_nodes}")
    if gliner_enabled:
        if gliner_nodes == 0:
            reasons.append("gliner_zero_entities")
        elif gliner_coverage < min_gliner_coverage:
            reasons.append(f"low_gliner_coverage:{gliner_coverage:.3f}<{min_gliner_coverage:.3f}")
        if gliner_nodes > 0 and gliner_avg_conf < min_gliner_confidence:
            reasons.append(f"low_gliner_confidence:{gliner_avg_conf:.3f}<{min_gliner_confidence:.3f}")

    return {
        "trigger": bool(reasons),
        "reasons": reasons,
        "metrics": {
            "chunk_count": chunk_count,
            "total_nodes": total_nodes,
            "gliner_enabled": gliner_enabled,
            "gliner_nodes": gliner_nodes,
            "gliner_coverage": round(gliner_coverage, 4),
            "gliner_avg_confidence": round(gliner_avg_conf, 4),
            "min_total_nodes": min_total_nodes,
            "min_gliner_coverage": round(min_gliner_coverage, 4),
            "min_gliner_confidence": round(min_gliner_confidence, 4),
        },
    }


def _load_llm_fallback_thresholds() -> Dict[str, float]:
    """Read and sanitize fallback thresholds from env."""
    return {
        "min_total_nodes": max(1, int(_env_float("KG_BUILDER_LLM_MIN_TOTAL_NODES", 2))),
        "min_gliner_coverage": max(
            0.0,
            min(1.0, _env_float("KG_BUILDER_LLM_MIN_GLINER_COVERAGE", 0.15)),
        ),
        "min_gliner_confidence": max(
            0.0,
            min(1.0, _env_float("KG_BUILDER_LLM_MIN_GLINER_CONFIDENCE", 0.60)),
        ),
    }


def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(n in text for n in needles)


# =============================================================================
# FACTUAL RELATIONSHIP PATTERNS — Pattern-based extraction (Opção B)
# =============================================================================

# Role triggers for PARTICIPA_DE (person/company participates in processo)
_PARTICIPA_TRIGGERS: tuple[str, ...] = (
    "autor", "autora", "réu", "ré", "reu",
    "reclamante", "reclamado", "reclamada",
    "apelante", "apelado", "apelada",
    "agravante", "agravado", "agravada",
    "impetrante", "impetrado", "impetrada",
    "exequente", "executado", "executada",
    "embargante", "embargado", "embargada",
    "querelante", "querelado", "querelada",
    "denunciante", "denunciado", "denunciada",
)

# Triggers for REPRESENTA (lawyer represents person/company)
_REPRESENTA_TRIGGERS: tuple[str, ...] = (
    "advogado", "advogada", "advogados",
    "procurador", "procuradora",
    "representante legal",
    "defensor", "defensora",
    "patrono", "patrona",
)

# Regex: "Nome Completo, autor" or "Nome Completo (réu)"
# Captures: group(1)=name, group(2)=role
# NOTE: No IGNORECASE — name detection relies on capitalization to identify proper names.
# Roles are listed in lowercase (standard form in legal text after the name).
# Longer role patterns come first to prevent partial matches (e.g., "re" in "reclamante").
_PESSOA_ROLE_RE = re.compile(
    r"([A-ZÀ-Ú][a-zà-ú]+"                                         # First name (capitalized)
    r"\s+(?:(?:d[aeiou]s?|e)\s+)?"                                  # space + optional preposition
    r"[A-ZÀ-Ú][a-zà-ú]+"                                           # Second name (required)
    r"(?:\s+(?:(?:d[aeiou]s?|e)\s+)?[A-ZÀ-Ú][a-zà-ú]+){0,3})"    # 0-3 more names
    r"\s*[,\(\-]\s*"                                                 # separator (, ( -)
    r"(reclamante|reclamad[ao]|"
    r"embargante|embargad[ao]|"
    r"impetrante|impetrad[ao]|"
    r"agravante|agravad[ao]|"
    r"executad[ao]|exequente|"
    r"apelante|apelad[ao]|"
    r"denunciante|denunciad[ao]|"
    r"querelante|querelad[ao]|"
    r"testemunha|perit[ao]|"
    r"autora?|r[eé]u|r[eé])\b"                                      # role (word boundary)
)


def _slugify_name(name: str) -> str:
    """Normalize a person name to a stable entity ID slug."""
    import unicodedata
    slug = unicodedata.normalize("NFKD", name.strip().lower())
    slug = slug.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "_", slug).strip("_")
    return slug


def _extract_evidence(text: str, match_pos: int, max_len: int = 160) -> str:
    """Extract evidence context around a match position."""
    half = max_len // 2
    start = max(0, match_pos - half)
    end = min(len(text), match_pos + half)
    return text[start:end].strip()


def _build_law_entity_from_citation(raw_law_or_code: str) -> Dict[str, Any]:
    """
    Build a deterministic Lei entity from textual citation snippet.

    Examples:
    - "Lei 8.666/93" -> lei_8666_1993
    - "CTN" -> lei_ctn
    """
    raw = (raw_law_or_code or "").strip()
    if not raw:
        return {}

    code_match = re.fullmatch(r"[A-Za-z]{2,10}", raw)
    if code_match:
        code = code_match.group(0).upper()
        return {
            "entity_type": "lei",
            "entity_id": f"lei_{code.lower()}",
            "name": code,
            "normalized": f"lei:{code.lower()}",
            "metadata": {"sigla": code, "source": "compound_citation"},
        }

    nums = re.findall(r"\d+", raw)
    if not nums:
        return {}

    numero = nums[0]
    ano = ""
    if len(nums) > 1:
        ano = nums[1]
        if len(ano) == 2:
            ano = f"19{ano}" if int(ano) > 50 else f"20{ano}"

    entity_id = f"lei_{numero}"
    if ano:
        entity_id += f"_{ano}"
    name = f"Lei {numero}" + (f"/{ano}" if ano else "")
    return {
        "entity_type": "lei",
        "entity_id": entity_id,
        "name": name,
        "normalized": f"lei:{numero}/{ano}" if ano else f"lei:{numero}",
        "metadata": {"numero": numero, "ano": ano, "source": "compound_citation"},
    }


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
    schema_mode = _kg_schema_mode()
    stats: Dict[str, Any] = {
        "doc_hash": doc_hash,
        "chunks_processed": 0,
        "regex_nodes": 0,
        "regex_relationships": 0,
        "gliner_nodes": 0,
        "gliner_relationships": 0,
        "llm_nodes": 0,
        "llm_relationships": 0,
        "resolved_merges": 0,
        "cross_merger_candidates": 0,
        "cross_merger_merged": 0,
        "cross_merger_conflicts": 0,
        "schema_discovery_found": 0,
        "schema_discovery_registered": 0,
        "pagerank_entities": 0,
        "llm_trigger_mode": "disabled",
        "llm_trigger_reasons": [],
        "llm_trigger_metrics": {},
        "schema_mode": schema_mode,
        "hybrid_second_pass": False,
        "factual_enabled": _env_bool("KG_BUILDER_FACTUAL_EXTRACTION", False),
        "factual_cpf": 0,
        "factual_cnpj": 0,
        "factual_dates": 0,
        "factual_values": 0,
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

    # Optional: GLiNER zero-shot NER
    gliner_enabled = _env_bool("KG_BUILDER_USE_GLINER", False)
    if gliner_enabled:
        try:
            gliner_stats = await _run_gliner_extraction(
                chunks, doc_hash, tenant_id,
                case_id=case_id, scope=scope,
            )
            stats.update(gliner_stats)
        except ImportError:
            logger.info("GLiNER not installed, skipping zero-shot NER")
        except Exception as e:
            logger.error("GLiNER extraction failed: %s", e)
            stats["errors"].append(f"gliner: {e}")

    # Optional: LLM extraction via ArgumentNeo4jService
    llm_enabled = bool(use_llm)
    if llm_enabled:
        stats["llm_trigger_mode"] = "explicit"
    else:
        auto_fallback = _env_bool("KG_BUILDER_LLM_AUTO_FALLBACK", False)
        if auto_fallback:
            thresholds = _load_llm_fallback_thresholds()
            decision = _should_trigger_llm_fallback(
                chunks,
                stats,
                min_total_nodes=int(thresholds["min_total_nodes"]),
                min_gliner_coverage=float(thresholds["min_gliner_coverage"]),
                min_gliner_confidence=float(thresholds["min_gliner_confidence"]),
                gliner_enabled=gliner_enabled,
            )
            stats["llm_trigger_reasons"] = decision["reasons"]
            stats["llm_trigger_metrics"] = decision["metrics"]
            if decision["trigger"]:
                llm_enabled = True
                stats["llm_trigger_mode"] = "auto_fallback"
            else:
                stats["llm_trigger_mode"] = "auto_skipped"

    if llm_enabled:
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

    # Optional: Cross-extractor entity merger (after per-label resolution)
    if use_resolver and _env_bool("KG_BUILDER_CROSS_MERGER", False):
        try:
            from app.services.rag.core.kg_builder.cross_merger import cross_merge_entities
            cross_result = await cross_merge_entities(tenant_id=tenant_id)
            stats["cross_merger_candidates"] = cross_result.candidates
            stats["cross_merger_merged"] = cross_result.merged
            stats["cross_merger_conflicts"] = cross_result.conflicts
        except Exception as e:
            logger.debug("Cross-merger skipped: %s", e)

    # Optional: compute tenant-scoped PageRank after ingest/resolution.
    if _env_bool("KG_BUILDER_COMPUTE_PAGERANK", False):
        try:
            from app.services.rag.core.gds_analytics import get_gds_client

            gds = get_gds_client()
            pr_result = await asyncio.to_thread(gds.compute_pagerank, tenant_id)
            stats["pagerank_entities"] = int(pr_result.total_entities)
        except Exception as e:
            logger.debug("PageRank computation skipped: %s", e)
            stats["errors"].append(f"pagerank: {e}")

    logger.info(
        "KG Builder complete for doc %s: %d regex, %d gliner, %d llm nodes, %d merges, %d pagerank",
        doc_hash, stats["regex_nodes"], stats["gliner_nodes"],
        stats["llm_nodes"], stats["resolved_merges"], stats["pagerank_entities"],
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
    from app.services.rag.core.neo4j_mvp import LegalEntityExtractor

    extractor = LegalRegexExtractor(create_relationships=True)
    result = await extractor.run(chunks)

    stats = {
        "chunks_processed": len(chunks),
        "regex_nodes": len(result.nodes),
        "regex_relationships": len(result.relationships),
        "regex_typed_relationships": 0,
        "regex_remissions": 0,
        "regex_article_law_links": 0,
        "regex_decision_links": 0,
        "factual_participa_links": 0,
        "factual_representa_links": 0,
        "factual_oab_processo_links": 0,
        "factual_pessoa_by_name": 0,
    }

    # Write to Neo4j via existing neo4j_mvp service
    try:
        from app.services.rag.core.neo4j_mvp import get_neo4j_mvp
        neo4j = get_neo4j_mvp()
        merged_ids: set[str] = set()

        for node in result.nodes:
            try:
                neo4j._merge_entity({
                    "entity_type": node["properties"].get("entity_type", ""),
                    "entity_id": node["id"],
                    "name": node["properties"].get("name", ""),
                    "normalized": node["properties"].get("normalized", ""),
                    "metadata": node["properties"],
                })
                merged_ids.add(node["id"])
            except Exception as e:
                logger.debug("Failed to write node %s: %s", node["id"], e)

        for rel in result.relationships:
            if rel["type"] == "RELATED_TO":
                try:
                    if neo4j.link_entities(
                        rel["start"],
                        rel["end"],
                        relation_type="RELATED_TO",
                        properties={"source": "regex_co_occurrence"},
                    ):
                        stats["regex_typed_relationships"] += 1
                except Exception:
                    pass

        # Enrich with granular legal links from deterministic regex parsing.
        for chunk in chunks:
            text = chunk.get("text", "")
            if not text:
                continue

            factual = _env_bool("KG_BUILDER_FACTUAL_EXTRACTION", False)
            parsed = LegalEntityExtractor.extract_all(text, include_factual=factual)
            parsed_entities = parsed.get("entities", [])

            # Ensure entities discovered by extract_all are also persisted.
            for ent in parsed_entities:
                entity_id = ent.get("entity_id", "")
                if not entity_id or entity_id in merged_ids:
                    continue
                try:
                    neo4j._merge_entity(ent)
                    merged_ids.add(entity_id)
                except Exception:
                    continue

            entities_by_type: Dict[str, List[str]] = {}
            for ent in parsed_entities:
                etype = str(ent.get("entity_type", "")).lower()
                eid = ent.get("entity_id")
                if etype and eid:
                    entities_by_type.setdefault(etype, []).append(eid)

            # 1) Artigo -> Artigo remissions (REMETE_A)
            for rem in parsed.get("remissions", []):
                source_article = str(rem.get("source_article") or "").strip()
                target_article = str(rem.get("target_article") or "").strip()
                if not source_article or not target_article:
                    continue
                source_id = f"art_{source_article}"
                target_id = f"art_{target_article}"
                if source_id == target_id:
                    continue
                try:
                    evidence = str(rem.get("context", "") or "")[:160]
                    if neo4j.link_entities(
                        source_id,
                        target_id,
                        relation_type="REMETE_A",
                        properties={
                            "source": "regex_remission",
                            "remission_type": rem.get("remission_type", ""),
                            "context": str(rem.get("context", "") or "")[:180],
                            "dimension": "remissiva",
                            "evidence": evidence,
                        },
                    ):
                        stats["regex_remissions"] += 1
                        stats["regex_typed_relationships"] += 1
                except Exception:
                    continue

            # 2) Artigo -> Lei ownership from compound citations (PERTENCE_A)
            for citation in parsed.get("compound_citations", []):
                cdict = citation.to_dict() if hasattr(citation, "to_dict") else {}
                article_raw = str(cdict.get("article") or "").strip()
                law_raw = str(cdict.get("law") or cdict.get("code") or "").strip()
                if not article_raw or not law_raw:
                    continue

                m = re.search(r"\d+", article_raw)
                if not m:
                    continue
                article_id = f"art_{m.group(0)}"

                law_entity = _build_law_entity_from_citation(law_raw)
                law_id = law_entity.get("entity_id", "")
                if not law_id:
                    continue
                if law_id not in merged_ids:
                    try:
                        neo4j._merge_entity(law_entity)
                        merged_ids.add(law_id)
                    except Exception:
                        continue

                try:
                    citation_text = str(
                        cdict.get("full_text") or cdict.get("full") or f"{article_raw} {law_raw}"
                    )[:160]
                    if neo4j.link_entities(
                        article_id,
                        law_id,
                        relation_type="PERTENCE_A",
                        properties={
                            "source": "compound_citation",
                            "dimension": "hierarquica",
                            "evidence": citation_text,
                        },
                    ):
                        stats["regex_article_law_links"] += 1
                        stats["regex_typed_relationships"] += 1
                except Exception:
                    continue

            # 3) Decision-centric links to avoid Tribunal hub noise.
            text_l = text.lower()
            decisions = entities_by_type.get("decisao", [])
            tribunals = entities_by_type.get("tribunal", [])
            temas = entities_by_type.get("tema", [])
            artigos = entities_by_type.get("artigo", [])
            leis = entities_by_type.get("lei", [])
            teses = entities_by_type.get("tese", [])
            sumulas = entities_by_type.get("sumula", [])

            for decision_id in decisions[:4]:
                candidate_base = {
                    "source": "regex_decision_link",
                    "layer": "candidate",
                    "verified": False,
                    "confidence": 0.3,
                    "tenant_id": tenant_id,
                    "doc_hash": doc_hash,
                }
                for tribunal_id in tribunals[:2]:
                    if neo4j.link_entities(
                        decision_id,
                        tribunal_id,
                        relation_type="RELATED_TO",
                        properties={**candidate_base, "dimension": "hierarquica", "candidate_type": "rel:PROFERIDA_POR"},
                    ):
                        stats["regex_decision_links"] += 1
                        stats["regex_typed_relationships"] += 1

                if _contains_any(text_l, ("tema", "repercuss", "repetitivo")):
                    for tema_id in temas[:4]:
                        if neo4j.link_entities(
                            decision_id,
                            tema_id,
                            relation_type="RELATED_TO",
                            properties={**candidate_base, "dimension": "hierarquica", "candidate_type": "rel:JULGA_TEMA"},
                        ):
                            stats["regex_decision_links"] += 1
                            stats["regex_typed_relationships"] += 1

                if _contains_any(
                    text_l,
                    ("interpreta", "interpretou", "aplica-se", "aplicou", "nos termos do art", "conforme art"),
                ):
                    targets = artigos[:5] if artigos else leis[:3]
                    for target_id in targets:
                        if neo4j.link_entities(
                            decision_id,
                            target_id,
                            relation_type="RELATED_TO",
                            properties={**candidate_base, "dimension": "hierarquica", "candidate_type": "rel:INTERPRETA"},
                        ):
                            stats["regex_decision_links"] += 1
                            stats["regex_typed_relationships"] += 1

                if teses and _contains_any(text_l, ("fixa a tese", "fixou a tese", "tese firmada", "firmou tese")):
                    for tese_id in teses[:3]:
                        if neo4j.link_entities(
                            decision_id,
                            tese_id,
                            relation_type="RELATED_TO",
                            properties={**candidate_base, "dimension": "hierarquica", "candidate_type": "rel:FIXA_TESE"},
                        ):
                            stats["regex_decision_links"] += 1
                            stats["regex_typed_relationships"] += 1

            # 4) Sumula semantics (conservative)
            if sumulas and tribunals:
                for sumula_id in sumulas[:3]:
                    for tribunal_id in tribunals[:2]:
                        if neo4j.link_entities(
                            sumula_id,
                            tribunal_id,
                            relation_type="RELATED_TO",
                            properties={
                                "source": "regex_sumula_link",
                                "layer": "candidate",
                                "verified": False,
                                "confidence": 0.3,
                                "dimension": "hierarquica",
                                "candidate_type": "rel:PROFERIDA_POR",
                                "tenant_id": tenant_id,
                                "doc_hash": doc_hash,
                            },
                        ):
                            stats["regex_typed_relationships"] += 1

            if sumulas and artigos and _contains_any(text_l, ("interpreta", "nos termos do art", "à luz do art")):
                for sumula_id in sumulas[:3]:
                    for artigo_id in artigos[:4]:
                        if neo4j.link_entities(
                            sumula_id,
                            artigo_id,
                            relation_type="RELATED_TO",
                            properties={
                                "source": "regex_sumula_link",
                                "layer": "candidate",
                                "verified": False,
                                "confidence": 0.3,
                                "dimension": "hierarquica",
                                "candidate_type": "rel:INTERPRETA",
                                "tenant_id": tenant_id,
                                "doc_hash": doc_hash,
                            },
                        ):
                            stats["regex_typed_relationships"] += 1

            if sumulas and temas and _contains_any(text_l, ("tema", "vincula", "repercuss", "repetitivo")):
                for sumula_id in sumulas[:3]:
                    for tema_id in temas[:3]:
                        if neo4j.link_entities(
                            sumula_id,
                            tema_id,
                            relation_type="RELATED_TO",
                            properties={
                                "source": "regex_sumula_link",
                                "layer": "candidate",
                                "verified": False,
                                "confidence": 0.25,
                                "dimension": "hierarquica",
                                "candidate_type": "rel:VINCULA",
                                "tenant_id": tenant_id,
                                "doc_hash": doc_hash,
                            },
                        ):
                            stats["regex_typed_relationships"] += 1

            # 5) Decisao -> Sumula via APLICA_SUMULA (v2 parity: dedicated type)
            if decisions and sumulas and _contains_any(
                text_l, ("aplica a sumula", "aplica a súmula", "nos termos da sumula",
                          "nos termos da súmula", "aplica-se a sumula", "aplica-se a súmula")
            ):
                for decision_id in decisions[:4]:
                    for sumula_id in sumulas[:3]:
                        if neo4j.link_entities(
                            decision_id,
                            sumula_id,
                            relation_type="RELATED_TO",
                            properties={
                                "source": "regex_decision_sumula_link",
                                "layer": "candidate",
                                "verified": False,
                                "confidence": 0.3,
                                "dimension": "hierarquica",
                                "candidate_type": "rel:APLICA_SUMULA",
                                "tenant_id": tenant_id,
                                "doc_hash": doc_hash,
                            },
                        ):
                            stats["regex_decision_links"] += 1
                            stats["regex_typed_relationships"] += 1

            # 6) Factual relationship patterns (Opção B — deterministic)
            if factual:
                cpfs = entities_by_type.get("cpf", [])
                cnpjs = entities_by_type.get("cnpj", [])
                oabs = entities_by_type.get("oab", [])
                processos = entities_by_type.get("processo", [])

                factual_base = {
                    "source": "regex_factual_link",
                    "layer": "candidate",
                    "verified": False,
                    "dimension": "fatica",
                    "tenant_id": tenant_id,
                    "doc_hash": doc_hash,
                }

                # 6a) CPF/CNPJ → Processo via PARTICIPA_DE (requires role trigger)
                if processos and _contains_any(text_l, _PARTICIPA_TRIGGERS):
                    for cpf_id in cpfs[:4]:
                        for proc_id in processos[:3]:
                            if neo4j.link_entities(
                                cpf_id, proc_id,
                                relation_type="RELATED_TO",
                                properties={**factual_base, "confidence": 0.3,
                                            "evidence": text[:160],
                                            "candidate_type": "rel:PARTICIPA_DE"},
                            ):
                                stats["factual_participa_links"] += 1
                                stats["regex_typed_relationships"] += 1
                    for cnpj_id in cnpjs[:4]:
                        for proc_id in processos[:3]:
                            if neo4j.link_entities(
                                cnpj_id, proc_id,
                                relation_type="RELATED_TO",
                                properties={**factual_base, "confidence": 0.3,
                                            "evidence": text[:160],
                                            "candidate_type": "rel:PARTICIPA_DE"},
                            ):
                                stats["factual_participa_links"] += 1
                                stats["regex_typed_relationships"] += 1

                # 6b) OAB → CPF/CNPJ via REPRESENTA (requires representation trigger)
                if oabs and _contains_any(text_l, _REPRESENTA_TRIGGERS):
                    for oab_id in oabs[:3]:
                        for cpf_id in cpfs[:3]:
                            if neo4j.link_entities(
                                oab_id, cpf_id,
                                relation_type="RELATED_TO",
                                properties={**factual_base, "confidence": 0.3,
                                            "evidence": text[:160],
                                            "candidate_type": "rel:REPRESENTA"},
                            ):
                                stats["factual_representa_links"] += 1
                                stats["regex_typed_relationships"] += 1
                        for cnpj_id in cnpjs[:3]:
                            if neo4j.link_entities(
                                oab_id, cnpj_id,
                                relation_type="RELATED_TO",
                                properties={**factual_base, "confidence": 0.3,
                                            "evidence": text[:160],
                                            "candidate_type": "rel:REPRESENTA"},
                            ):
                                stats["factual_representa_links"] += 1
                                stats["regex_typed_relationships"] += 1

                # 6c) OAB → Processo via PARTICIPA_DE (implicit — lawyer always participates)
                if oabs and processos:
                    for oab_id in oabs[:3]:
                        for proc_id in processos[:3]:
                            if neo4j.link_entities(
                                oab_id, proc_id,
                                relation_type="RELATED_TO",
                                properties={**factual_base, "confidence": 0.25,
                                            "evidence": text[:160],
                                            "candidate_type": "rel:PARTICIPA_DE"},
                            ):
                                stats["factual_oab_processo_links"] += 1
                                stats["regex_typed_relationships"] += 1

                # 6d) Pessoa by name + role → create entity + PARTICIPA_DE
                for match in _PESSOA_ROLE_RE.finditer(text):
                    nome = match.group(1).strip()
                    role = match.group(2).strip().lower()
                    slug = _slugify_name(nome)
                    if not slug or len(slug) < 4:
                        continue
                    pessoa_id = f"pessoa_{slug}"
                    evidence = _extract_evidence(text, match.start())
                    if pessoa_id not in merged_ids:
                        try:
                            neo4j._merge_entity({
                                "entity_type": "pessoa",
                                "entity_id": pessoa_id,
                                "name": nome,
                                "normalized": f"pessoa:{slug}",
                                "metadata": {"role": role, "source": "regex_name_role"},
                            })
                            merged_ids.add(pessoa_id)
                            stats["factual_pessoa_by_name"] += 1
                        except Exception:
                            continue
                    for proc_id in processos[:3]:
                        if neo4j.link_entities(
                            pessoa_id, proc_id,
                            relation_type="RELATED_TO",
                            properties={**factual_base, "confidence": 0.3,
                                        "evidence": evidence,
                                        "candidate_type": "rel:PARTICIPA_DE"},
                        ):
                            stats["factual_participa_links"] += 1
                            stats["regex_typed_relationships"] += 1

    except Exception as e:
        logger.warning("Could not write regex results to Neo4j: %s", e)

    return stats


async def _run_gliner_extraction(
    chunks: List[Dict[str, Any]],
    doc_hash: str,
    tenant_id: str,
    *,
    case_id: Optional[str] = None,
    scope: str = "global",
) -> Dict[str, Any]:
    """Run GLiNER zero-shot NER and write to Neo4j."""
    from app.services.rag.core.kg_builder.gliner_extractor import GLiNERExtractor

    extractor = GLiNERExtractor(create_relationships=True)
    result = await extractor.run(chunks)

    stats = {
        "gliner_nodes": len(result.nodes),
        "gliner_relationships": len(result.relationships),
        "gliner_avg_confidence": 0.0,
        "gliner_low_confidence_nodes": 0,
    }

    low_conf_threshold = max(
        0.0,
        min(1.0, _env_float("KG_BUILDER_GLINER_LOW_CONFIDENCE", 0.55)),
    )
    confidences: List[float] = []
    low_conf_nodes = 0
    for node in result.nodes:
        score = node.get("properties", {}).get("confidence")
        if isinstance(score, (int, float)):
            conf = float(score)
            confidences.append(conf)
            if conf < low_conf_threshold:
                low_conf_nodes += 1
    if confidences:
        stats["gliner_avg_confidence"] = round(sum(confidences) / len(confidences), 4)
    stats["gliner_low_confidence_nodes"] = low_conf_nodes

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
                    "normalized": node["properties"].get("name", "").lower(),
                    "metadata": str(node["properties"]),
                })
            except Exception as e:
                logger.debug("Failed to write GLiNER node %s: %s", node["id"], e)

        for rel in result.relationships:
            if rel["type"] == "RELATED_TO":
                try:
                    props = dict(rel.get("properties") or {})
                    props.update(
                        {
                            "layer": "candidate",
                            "verified": False,
                            "candidate_type": "gliner:co_occurrence",
                            "tenant_id": tenant_id,
                            "doc_hash": doc_hash,
                            # GLiNER co-occurrence is weak signal; keep it low.
                            "confidence": float(props.get("confidence", 0.2)),
                        }
                    )
                    neo4j.link_entities(
                        rel["start"],
                        rel["end"],
                        relation_type="RELATED_TO",
                        properties=props,
                    )
                except Exception:
                    pass

    except Exception as e:
        logger.warning("Could not write GLiNER results to Neo4j: %s", e)

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

    Requires: pip install neo4j-graphrag
    Suporta LLM providers: openai, vertexai (Gemini), anthropic, ollama.
    """
    from neo4j_graphrag.experimental.pipeline.kg_builder import SimpleKGPipeline

    from app.services.rag.core.neo4j_mvp import get_neo4j_mvp
    from app.services.rag.core.kg_builder.legal_schema import build_legal_schema

    neo4j_svc = get_neo4j_mvp()
    driver = neo4j_svc.driver  # Reusar singleton — NÃO criar novo driver

    llm = _build_graphrag_llm() if use_llm else None
    embedder = _build_graphrag_embedder()

    schema_mode = _kg_schema_mode()

    # Rehydrate previously discovered schema before building GraphSchema so
    # dynamic labels are available during this run (true cross-run reuse).
    if _env_bool("KG_BUILDER_SCHEMA_DISCOVERY", False):
        try:
            from app.services.rag.core.kg_builder.schema_discovery import SchemaDiscoveryProcessor

            processor = SchemaDiscoveryProcessor(driver=driver, database=neo4j_svc.config.database)
            await asyncio.to_thread(processor.rehydrate, tenant_id)
        except Exception as e:
            logger.debug("Schema rehydrate skipped: %s", e)

    schema = build_legal_schema(schema_mode=schema_mode)
    hybrid_second_pass = _env_bool("KG_BUILDER_HYBRID_SECOND_PASS", False)

    # ------------------------------------------------------------
    # Graphrag options (ported from standalone ingest_v2.py)
    # ------------------------------------------------------------
    domain = (os.getenv("KG_BUILDER_DOMAIN") or "legal").strip().lower()
    is_legal_domain = domain == "legal"
    strict_prompt = _env_bool("KG_BUILDER_GRAPHRAG_STRICT_PROMPT", is_legal_domain)
    quality_filter = _env_bool("KG_BUILDER_GRAPHRAG_QUALITY_FILTER", is_legal_domain)
    post_process = _env_bool("KG_BUILDER_GRAPHRAG_POST_PROCESS", is_legal_domain)
    segment_size = int(os.getenv("KG_BUILDER_GRAPHRAG_SEGMENT_SIZE", "4000" if is_legal_domain else "12000"))
    default_overlap = int(segment_size * (0.15 if is_legal_domain else 0.10))
    try:
        overlap = int(os.getenv("KG_BUILDER_GRAPHRAG_SEGMENT_OVERLAP", str(default_overlap)))
    except Exception:
        overlap = default_overlap
    delay_s = float(os.getenv("KG_BUILDER_GRAPHRAG_SEGMENT_DELAY_SECONDS", "0") or 0)

    # Skip identical runs (progress-by-hash + config fingerprint).
    skip_dupe = _env_bool("KG_BUILDER_GRAPHRAG_SKIP_DUPLICATE_RUN", False)
    config_fingerprint = (
        f"domain={domain}|schema_mode={schema_mode}|strict_prompt={strict_prompt}|"
        f"quality_filter={quality_filter}|segment_size={segment_size}|overlap={overlap}"
    )
    config_hash = hashlib.sha256(config_fingerprint.encode("utf-8")).hexdigest()[:12]

    if skip_dupe:
        try:
            def _already_done() -> bool:
                with driver.session(database=neo4j_svc.config.database) as s:
                    r = s.run(
                        "MATCH (r:KGBuildRun {doc_hash:$doc_hash, tenant_id:$tenant_id, mode:'graphrag', "
                        "schema_mode:$schema_mode, config_hash:$config_hash}) "
                        "RETURN count(r) AS c",
                        {
                            "doc_hash": doc_hash,
                            "tenant_id": tenant_id,
                            "schema_mode": schema_mode,
                            "config_hash": config_hash,
                        },
                    ).single()
                    return bool(r and int(r["c"] or 0) > 0)
            if await asyncio.to_thread(_already_done):
                return {
                    "chunks_processed": len(chunks),
                    "mode": "neo4j-graphrag",
                    "schema_mode": schema_mode,
                    "hybrid_second_pass": False,
                    "graphrag_segments": 0,
                    "graphrag_segments_skipped": 0,
                    "graphrag_skipped_duplicate_run": True,
                }
        except Exception as e:
            logger.debug("Duplicate-run skip check failed: %s", e)

    # Build pipeline with optional strict prompt template (when supported by neo4j-graphrag).
    pipeline_kwargs: Dict[str, Any] = {
        "llm": llm,
        "driver": driver,
        "embedder": embedder,
        "schema": schema,
        "from_pdf": False,
        "perform_entity_resolution": True,
        "neo4j_database": neo4j_svc.config.database,
        "on_error": "IGNORE",
    }
    factual_enabled = _env_bool("KG_BUILDER_FACTUAL_EXTRACTION", False)
    if strict_prompt and llm is not None:
        try:
            from app.services.rag.core.kg_builder.legal_graphrag_prompt import StrictLegalExtractionTemplate
            pipeline_kwargs["prompt_template"] = StrictLegalExtractionTemplate(include_factual=factual_enabled)
        except Exception as e:
            logger.debug("Strict prompt template unavailable: %s", e)

    try:
        pipeline = SimpleKGPipeline(**pipeline_kwargs)
    except TypeError as e:
        # Backward compat: older neo4j-graphrag may not accept prompt_template
        if "prompt_template" in str(e):
            pipeline_kwargs.pop("prompt_template", None)
            pipeline = SimpleKGPipeline(**pipeline_kwargs)
        else:
            raise

    raw_text = "\n\n".join(c.get("text", "") for c in chunks if c.get("text"))

    # Segment the input to reduce cross-segment contamination (legal default).
    from app.services.rag.core.kg_builder.legal_text_preprocessor import prepare_segments
    segments, skipped = prepare_segments(
        raw_text,
        segment_size=segment_size,
        overlap=overlap,
        quality_filter=quality_filter,
    )

    for i, seg in enumerate(segments):
        await pipeline.run_async(text=seg)
        if i < len(segments) - 1 and delay_s > 0:
            await asyncio.sleep(delay_s)

    # Hybrid strategy (optional): second permissive pass to capture emergent
    # entities/relationships not covered by strict ontology.
    if schema_mode == "hybrid" and hybrid_second_pass and llm is not None:
        discovery_schema = build_legal_schema(schema_mode="auto")
        discovery_kwargs = dict(pipeline_kwargs)
        discovery_kwargs["schema"] = discovery_schema
        try:
            discovery_pipeline = SimpleKGPipeline(**discovery_kwargs)
        except TypeError as e:
            if "prompt_template" in str(e):
                discovery_kwargs.pop("prompt_template", None)
                discovery_pipeline = SimpleKGPipeline(**discovery_kwargs)
            else:
                raise
        for i, seg in enumerate(segments):
            await discovery_pipeline.run_async(text=seg)
            if i < len(segments) - 1 and delay_s > 0:
                await asyncio.sleep(delay_s)

    result_stats = {
        "chunks_processed": len(chunks),
        "mode": "neo4j-graphrag",
        "schema_mode": schema_mode,
        "hybrid_second_pass": bool(schema_mode == "hybrid" and hybrid_second_pass and llm is not None),
        "graphrag_segments": len(segments),
        "graphrag_segments_skipped": int(skipped),
        "graphrag_config_hash": config_hash,
        "graphrag_strict_prompt": bool(strict_prompt),
        "graphrag_quality_filter": bool(quality_filter),
        "graphrag_segment_size": int(segment_size),
        "graphrag_segment_overlap": int(overlap),
    }

    # Best-effort cost/volume estimation (no provider-specific token accounting here).
    try:
        raw_chars = len(raw_text or "")
        segments_chars = sum(len(s) for s in segments)

        prompt_chars = 0
        pt = pipeline_kwargs.get("prompt_template")
        if pt is not None:
            tmpl = getattr(pt, "template", None)
            if isinstance(tmpl, str):
                prompt_chars = len(tmpl)

        schema_chars = 0
        try:
            import json

            if isinstance(schema, dict):
                schema_chars = len(json.dumps(schema, ensure_ascii=False))
            else:
                schema_chars = len(repr(schema))
        except Exception:
            schema_chars = len(repr(schema))

        overhead_tokens_per_call = _estimate_tokens_from_chars(prompt_chars + schema_chars)
        segment_tokens = _estimate_tokens_from_chars(segments_chars)
        est_input_tokens = segment_tokens + (len(segments) * overhead_tokens_per_call)

        result_stats["graphrag_raw_text_chars"] = raw_chars
        result_stats["graphrag_segments_chars"] = segments_chars
        result_stats["graphrag_prompt_chars_est"] = int(prompt_chars)
        result_stats["graphrag_schema_chars_est"] = int(schema_chars)
        result_stats["graphrag_est_overhead_tokens_per_call"] = int(overhead_tokens_per_call)
        result_stats["graphrag_est_input_tokens"] = int(est_input_tokens)

        # Optional: estimate input cost if caller provides a cost model.
        cost_per_1m = os.getenv("KG_BUILDER_GRAPHRAG_COST_PER_1M_INPUT_TOKENS_USD")
        if cost_per_1m:
            try:
                c = float(cost_per_1m)
                result_stats["graphrag_est_input_cost_usd"] = (est_input_tokens / 1_000_000.0) * c
            except Exception:
                pass
    except Exception:
        # Never fail a build run due to observability bookkeeping.
        pass

    # Optional: post-process graph for normalization/merge fixes.
    if post_process:
        try:
            from app.services.rag.core.kg_builder.legal_postprocessor import post_process_legal_graph

            pp = await asyncio.to_thread(
                post_process_legal_graph,
                driver,
                database=neo4j_svc.config.database,
            )
            result_stats["post_process_tema_from_decisao"] = pp.tema_from_decisao
            result_stats["post_process_decisao_name_normalized"] = pp.decisao_name_normalized
            result_stats["post_process_decisao_duplicates_merged"] = pp.decisao_duplicates_merged
            result_stats["post_process_subdispositivo_de_inferred"] = pp.subdispositivo_de_inferred
            result_stats["post_process_warnings"] = pp.warnings
        except Exception as e:
            logger.debug("Legal post-process skipped: %s", e)

    # Mark run as completed (progress-by-hash).
    try:
        def _mark_done() -> None:
            with driver.session(database=neo4j_svc.config.database) as s:
                s.run(
                    "MERGE (r:KGBuildRun {doc_hash:$doc_hash, tenant_id:$tenant_id, mode:'graphrag', "
                    "schema_mode:$schema_mode, config_hash:$config_hash}) "
                    "SET r.completed_at = timestamp(), r.segments = $segments, r.skipped = $skipped",
                    {
                        "doc_hash": doc_hash,
                        "tenant_id": tenant_id,
                        "schema_mode": schema_mode,
                        "config_hash": config_hash,
                        "segments": int(result_stats["graphrag_segments"]),
                        "skipped": int(result_stats["graphrag_segments_skipped"]),
                    },
                )
        await asyncio.to_thread(_mark_done)
    except Exception as e:
        logger.debug("KGBuildRun marker failed: %s", e)

    # Optional: Schema discovery post-processing
    if _env_bool("KG_BUILDER_SCHEMA_DISCOVERY", False):
        try:
            from app.services.rag.core.kg_builder.schema_discovery import SchemaDiscoveryProcessor
            processor = SchemaDiscoveryProcessor(driver=driver, database=neo4j_svc.config.database)
            discovery = await asyncio.to_thread(processor.discover, tenant_id)
            result_stats["schema_discovery_found"] = len(discovery.discovered_types)
            result_stats["schema_discovery_registered"] = len(discovery.registered_types)
        except Exception as e:
            logger.debug("Schema discovery skipped: %s", e)

    # Optional: Cross-extractor merger
    if _env_bool("KG_BUILDER_CROSS_MERGER", False):
        try:
            from app.services.rag.core.kg_builder.cross_merger import cross_merge_entities
            cross_result = await cross_merge_entities(
                driver=driver, database=neo4j_svc.config.database,
                tenant_id=tenant_id,
            )
            result_stats["cross_merger_candidates"] = cross_result.candidates
            result_stats["cross_merger_merged"] = cross_result.merged
            result_stats["cross_merger_conflicts"] = cross_result.conflicts
        except Exception as e:
            logger.debug("Cross-merger skipped in graphrag mode: %s", e)

    # Optional: Chain analysis (v2 parity — measure 4-5 hop chains)
    if _env_bool("KG_BUILDER_CHAIN_ANALYSIS", False):
        try:
            from app.services.rag.core.kg_builder.chain_analyzer import analyze_chains
            from dataclasses import asdict
            analysis = await asyncio.to_thread(
                analyze_chains, driver, database=neo4j_svc.config.database,
            )
            result_stats["chain_analysis"] = asdict(analysis)
        except Exception as e:
            logger.debug("Chain analysis skipped: %s", e)

    return result_stats


def _build_graphrag_llm():
    """Constrói LLM para o SimpleKGPipeline baseado no provider configurado."""
    provider = os.getenv("KG_BUILDER_LLM_PROVIDER", "openai").lower()
    # Provider-specific defaults to avoid accidentally sending Gemini requests to OpenAI models (or vice-versa).
    if provider == "openai":
        default_model = "gpt-4o-mini"
    elif provider in ("vertexai", "vertex", "vertex_ai", "gcp", "gemini", "google_ai_studio", "ai_studio"):
        default_model = os.getenv("GEMINI_3_FLASH_API_MODEL", "gemini-3-flash-preview")
    elif provider == "anthropic":
        default_model = "claude-sonnet-4-5-20250929"
    elif provider == "ollama":
        default_model = "llama3"
    else:
        default_model = "gpt-4o-mini"

    model = (os.getenv("KG_BUILDER_LLM_MODEL") or "").strip() or default_model

    # Common params (OpenAI-compatible providers support these).
    try:
        temperature = float(os.getenv("KG_BUILDER_LLM_TEMPERATURE", "0") or 0)
    except Exception:
        temperature = 0.0
    try:
        max_tokens = int(os.getenv("KG_BUILDER_LLM_MAX_TOKENS", "4000") or 4000)
    except Exception:
        max_tokens = 4000
    response_format_json = _env_bool("KG_BUILDER_LLM_RESPONSE_FORMAT_JSON", True)
    model_params = {"temperature": temperature, "max_tokens": max_tokens}
    if response_format_json:
        # Request strict JSON object responses (used by our strict extraction prompt).
        model_params["response_format"] = {"type": "json_object"}

    if provider == "openai":
        from neo4j_graphrag.llm import OpenAILLM
        return OpenAILLM(
            model_name=model,
            model_params=model_params,
            api_key=os.getenv("OPENAI_API_KEY", ""),
        )
    elif provider in ("vertexai", "vertex", "vertex_ai", "gcp"):
        from neo4j_graphrag.llm import VertexAILLM
        return VertexAILLM(
            # Default to the model registry envs if the caller did not override.
            model_name=model,
            project_id=os.getenv("GOOGLE_CLOUD_PROJECT", ""),
        )
    elif provider in ("gemini", "google_ai_studio", "ai_studio"):
        # Gemini via Google AI Studio using the OpenAI-compatible endpoint.
        # This is useful when you *don't* want Vertex auth (service accounts),
        # but have GEMINI_API_KEY/GOOGLE_API_KEY available.
        from neo4j_graphrag.llm import OpenAILLM

        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""
        base_url = os.getenv(
            "KG_BUILDER_GEMINI_BASE_URL",
            "https://generativelanguage.googleapis.com/v1beta/openai/",
        )
        return OpenAILLM(
            model_name=model,
            model_params=model_params,
            api_key=api_key,
            base_url=base_url,
        )
    elif provider == "anthropic":
        from neo4j_graphrag.llm import AnthropicLLM
        return AnthropicLLM(
            model_name=model,
            api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        )
    elif provider == "ollama":
        from neo4j_graphrag.llm import OllamaLLM
        return OllamaLLM(
            model_name=model,
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        )
    else:
        raise ValueError(f"KG_BUILDER_LLM_PROVIDER não suportado: {provider}")


def _build_graphrag_embedder():
    """Constrói embedder para o SimpleKGPipeline (necessário pelo pipeline)."""
    provider = (os.getenv("KG_BUILDER_EMBEDDING_PROVIDER") or "openai").strip().lower()
    if provider in {"", "none", "off", "disabled"}:
        return None

    try:
        if provider in {"openai"}:
            from neo4j_graphrag.embeddings import OpenAIEmbeddings

            model = os.getenv("KG_BUILDER_EMBEDDING_MODEL", "text-embedding-3-small")
            api_key = os.getenv("OPENAI_API_KEY", "")
            try:
                return OpenAIEmbeddings(api_key=api_key, model=model)
            except TypeError:
                # Backward compat across neo4j-graphrag versions.
                try:
                    return OpenAIEmbeddings(api_key=api_key, model_name=model)
                except TypeError:
                    return OpenAIEmbeddings(model=model)

        if provider in {"vertexai", "vertex", "vertex_ai", "gcp"}:
            from neo4j_graphrag.embeddings import VertexAIEmbeddings  # type: ignore

            model = os.getenv("KG_BUILDER_EMBEDDING_MODEL", "")
            project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "")
            location = os.getenv("GOOGLE_CLOUD_LOCATION", "")
            kwargs: Dict[str, Any] = {}
            if model:
                kwargs["model"] = model
                kwargs["model_name"] = model  # some versions use model_name
            if project_id:
                kwargs["project_id"] = project_id
            if location:
                kwargs["location"] = location

            # Try a few common ctor shapes.
            for attempt in (
                lambda: VertexAIEmbeddings(model=model, project_id=project_id, location=location),
                lambda: VertexAIEmbeddings(model_name=model, project_id=project_id, location=location),
                lambda: VertexAIEmbeddings(project_id=project_id),
                lambda: VertexAIEmbeddings(),
            ):
                try:
                    return attempt()
                except TypeError:
                    continue

            logger.warning("VertexAIEmbeddings available, but could not be instantiated with current env config.")
            return None

        logger.warning("KG_BUILDER_EMBEDDING_PROVIDER not supported: %r (use openai|vertexai|none)", provider)
        return None
    except Exception as e:
        logger.warning("Could not create embedder for KG Builder: %s", e)
        return None
