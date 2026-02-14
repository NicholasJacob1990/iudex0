"""
Fase 3: Link suggestion via LLM.

Este módulo usa um LLM para validar e propor relações entre nós com contexto semântico,
especialmente útil para casos ambíguos onde regras e similaridade não são suficientes.

Abordagem "transparência-first": todas as arestas criadas são
:RELATED_TO com layer='candidate', verified=false.
O LLM classifica o tipo (CITA, COMPLEMENTA, etc.) mas grava como candidate_type='rel:CITA'.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class LLMLinkSuggestionStats:
    """Estatísticas de sugestão de links via LLM."""
    pairs_evaluated: int = 0
    links_suggested: int = 0
    links_created: int = 0
    llm_api_calls: int = 0
    llm_errors: int = 0
    evidence_validated: int = 0
    evidence_failed: int = 0
    l2_candidates_validated: int = 0
    l2_candidates_rejected: int = 0


def _get_llm_client(provider: str = "openai"):
    """Lazy import do cliente LLM para evitar dependências circulares."""
    try:
        from app.services.model_registry import get_model_client
        return get_model_client(provider)
    except Exception as e:
        logger.warning(f"Failed to load LLM client: {e}")
        return None


# ============================================================================
# ANTI-HALLUCINATION: Evidence validation
# ============================================================================


def _validate_evidence(evidence: str, snippets: list[str]) -> bool:
    """
    Valida que a evidência fornecida pelo LLM é substring de algum snippet.

    Anti-alucinação: se o LLM inventar evidência que não está no contexto
    fornecido, a validação falha e a confiança é penalizada.
    """
    if not evidence or len(evidence) < 10:
        return False
    evidence_lower = evidence.lower().strip()
    for snippet in snippets:
        if snippet and evidence_lower in snippet.lower():
            return True
    return False


def _fetch_node_snippets(session, element_id: str, max_snippets: int = 3) -> list[str]:
    """Busca snippets de texto associados a um nó via chunks."""
    try:
        result = list(session.run(
            """
            MATCH (n) WHERE elementId(n) = $eid
            OPTIONAL MATCH (c:Chunk)-[:MENTIONS]->(n)
            WHERE c.text_preview IS NOT NULL
            RETURN collect(DISTINCT c.text_preview)[0..$max] AS snippets
            """,
            eid=element_id, max=max_snippets
        ))
        if result and result[0]["snippets"]:
            return [s for s in result[0]["snippets"] if s]
    except Exception:
        pass
    return []


# ============================================================================
# L3 CLASSIFICATION: Validate L2 candidates via LLM
# ============================================================================


def validate_l2_candidates_via_llm(
    session,
    candidates: list,  # list[EmbeddingCandidate]
    model_provider: str = "openai",
    model: str = "gpt-4o-mini",
    min_confidence: float = 0.75,
) -> tuple[list[dict], LLMLinkSuggestionStats]:
    """
    Valida e classifica candidatos L2 (embedding similarity) via LLM.

    Recebe EmbeddingCandidate do L2, busca contexto, pede classificação ao LLM,
    valida evidência como substring, e cria :RELATED_TO com candidate_type='rel:...'.

    Returns:
        (suggestions_created, stats)
    """
    stats = LLMLinkSuggestionStats()
    suggestions = []

    client = _get_llm_client(model_provider)
    if not client:
        return suggestions, stats

    logger.info(f"Validating {len(candidates)} L2 candidates via LLM ({model_provider}/{model})")

    for candidate in candidates:
        try:
            # Buscar snippets de contexto
            snippets_a = _fetch_node_snippets(session, candidate.source_element_id)
            snippets_b = _fetch_node_snippets(session, candidate.target_element_id)
            all_snippets = snippets_a + snippets_b

            context_a = "\n".join(snippets_a[:2]) if snippets_a else "(sem contexto)"
            context_b = "\n".join(snippets_b[:2]) if snippets_b else "(sem contexto)"

            prompt = f"""Você é um especialista jurídico. Classifique a relação entre:

**A**: {candidate.source_name} (Tipo: {candidate.source_type})
**B**: {candidate.target_name} (Tipo: {candidate.target_type})
**Similaridade embedding**: {candidate.similarity_score:.3f}

**Contexto A**: {context_a[:500]}
**Contexto B**: {context_b[:500]}

Responda SOMENTE com JSON válido (sem markdown):
{{
  "has_relationship": true ou false,
  "relationship_type": "CITA" | "COMPLEMENTA" | "INTERPRETA" | "REMETE_A" | "CONFIRMA" | "SUPERA" | "DISTINGUE" | null,
  "confidence": 0.0-1.0,
  "evidence": "trecho EXATO do contexto acima que sustenta a relação (copie literalmente)",
  "reasoning": "justificativa curta (max 100 chars)"
}}

**Regras**:
- evidence DEVE ser um trecho exato copiado do contexto fornecido
- Se não encontrar evidência textual, has_relationship = false
- confidence >= 0.75 para aceitar
"""

            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0,
                max_tokens=300,
            )

            stats.llm_api_calls += 1
            result = json.loads(response.choices[0].message.content)

            if not result.get("has_relationship"):
                stats.l2_candidates_rejected += 1
                continue

            confidence = result.get("confidence", 0)
            evidence = result.get("evidence", "")
            evidence_ok = _validate_evidence(evidence, all_snippets)

            if evidence_ok:
                stats.evidence_validated += 1
            else:
                stats.evidence_failed += 1
                confidence *= 0.5  # Penalizar evidência inválida

            if confidence < min_confidence:
                stats.l2_candidates_rejected += 1
                continue

            rel_type = result.get("relationship_type", "RELATED")
            suggestion = {
                "source_element_id": candidate.source_element_id,
                "target_element_id": candidate.target_element_id,
                "source_name": candidate.source_name,
                "target_name": candidate.target_name,
                "source_type": candidate.source_type,
                "target_type": candidate.target_type,
                "type": rel_type,
                "confidence": confidence,
                "reasoning": result.get("reasoning", ""),
                "evidence": evidence if evidence_ok else "",
                "evidence_validated": evidence_ok,
                "similarity_score": candidate.similarity_score,
            }
            suggestions.append(suggestion)
            stats.l2_candidates_validated += 1

        except Exception as e:
            stats.llm_errors += 1
            logger.warning(f"LLM validation failed for {candidate.source_name} - {candidate.target_name}: {e}")

    stats.links_suggested = len(suggestions)
    # Criar links
    if suggestions:
        stats.links_created = create_llm_suggested_links(session, suggestions)

    logger.info(
        f"L2→L3 validation: {stats.l2_candidates_validated} validated, "
        f"{stats.l2_candidates_rejected} rejected, "
        f"{stats.links_created} created, {stats.llm_api_calls} API calls"
    )

    return suggestions, stats


# ============================================================================
# L3 DISCOVERY: Find new pairs via LLM
# ============================================================================


def suggest_decisao_relationships_via_llm(
    session,
    model_provider: str = "openai",
    model: str = "gpt-4o-mini",
    max_pairs: int = 50,
    min_confidence: float = 0.75,
) -> tuple[List[Dict[str, Any]], int]:
    """
    Usa LLM para sugerir relações entre Decisões com contexto compartilhado.

    Returns:
        (suggestions, api_calls)
    """
    suggestions = []
    api_calls = 0

    try:
        client = _get_llm_client(model_provider)
        if not client:
            return suggestions, api_calls

        pairs = list(session.run(
            """
            MATCH (d1:Decisao)-[:INTERPRETA]->(art:Artigo)<-[:INTERPRETA]-(d2:Decisao)
            WHERE d1 <> d2
              AND id(d1) < id(d2)
              AND NOT (d1)-[:CITA]-(d2)
              AND NOT (d1)-[:RELATED_TO]-(d2)
            WITH d1, d2, collect(DISTINCT art.name) AS shared_articles
            WHERE size(shared_articles) >= 2
            RETURN d1.name AS decisao_a,
                   d2.name AS decisao_b,
                   elementId(d1) AS id_a,
                   elementId(d2) AS id_b,
                   shared_articles
            LIMIT $limit
            """,
            limit=max_pairs
        ))

        logger.info(f"Evaluating {len(pairs)} Decisao pairs via LLM ({model_provider}/{model})")

        for pair in pairs:
            # Buscar snippets para anti-alucinação
            snippets_a = _fetch_node_snippets(session, pair["id_a"])
            snippets_b = _fetch_node_snippets(session, pair["id_b"])
            all_snippets = snippets_a + snippets_b

            context_a = "\n".join(snippets_a[:2]) if snippets_a else "(sem contexto)"
            context_b = "\n".join(snippets_b[:2]) if snippets_b else "(sem contexto)"

            prompt = f"""Você é um especialista jurídico. Analise se há relação entre essas decisões:

**Decisão A**: {pair['decisao_a']}
**Decisão B**: {pair['decisao_b']}
**Ambas interpretam**: {', '.join(pair['shared_articles'][:5])}

**Contexto A**: {context_a[:400]}
**Contexto B**: {context_b[:400]}

Responda SOMENTE com JSON válido (sem markdown):
{{
  "has_relationship": true ou false,
  "relationship_type": "CITA" | "CONFIRMA" | "SUPERA" | "DISTINGUE" | null,
  "confidence": 0.0-1.0,
  "evidence": "trecho EXATO do contexto que sustenta a relação",
  "reasoning": "justificativa curta (max 100 chars)"
}}

**Critérios**:
- CITA: uma decisão menciona/invoca a outra como precedente
- CONFIRMA: ratifica o entendimento da outra
- SUPERA: muda/supera o entendimento da outra
- DISTINGUE: casos factuais diferentes (distinguishing)
- evidence DEVE ser trecho exato do contexto
- confidence >= 0.75 para aceitar
"""

            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"},
                    temperature=0,
                    max_tokens=300
                )

                api_calls += 1
                result = json.loads(response.choices[0].message.content)

                if result.get("has_relationship"):
                    confidence = result.get("confidence", 0)
                    evidence = result.get("evidence", "")
                    evidence_ok = _validate_evidence(evidence, all_snippets)

                    if not evidence_ok:
                        confidence *= 0.5

                    if confidence >= min_confidence:
                        suggestions.append({
                            "source": pair["decisao_a"],
                            "target": pair["decisao_b"],
                            "source_element_id": pair["id_a"],
                            "target_element_id": pair["id_b"],
                            "node_type": "Decisao",
                            "type": result["relationship_type"],
                            "confidence": confidence,
                            "reasoning": result.get("reasoning", ""),
                            "evidence": evidence if evidence_ok else "",
                            "evidence_validated": evidence_ok,
                            "shared_articles": pair["shared_articles"],
                        })

            except Exception as e:
                logger.warning(f"LLM evaluation failed for pair {pair['decisao_a']} - {pair['decisao_b']}: {e}")
                continue

        logger.info(f"LLM suggested {len(suggestions)} Decisao relationships from {api_calls} API calls")

    except Exception as e:
        logger.error(f"LLM-based Decisao suggestion failed: {e}")

    return suggestions, api_calls


def suggest_doutrina_relationships_via_llm(
    session,
    model_provider: str = "openai",
    model: str = "gpt-4o-mini",
    max_pairs: int = 30,
    min_confidence: float = 0.75,
) -> tuple[List[Dict[str, Any]], int]:
    """
    Usa LLM para sugerir relações entre Doutrinas.
    """
    suggestions = []
    api_calls = 0

    try:
        client = _get_llm_client(model_provider)
        if not client:
            return suggestions, api_calls

        pairs = list(session.run(
            """
            MATCH (d1:Doutrina)-[:INTERPRETA]->(art:Artigo)<-[:INTERPRETA]-(d2:Doutrina)
            WHERE d1 <> d2
              AND id(d1) < id(d2)
              AND NOT (d1)-[:CITA]-(d2)
              AND NOT (d1)-[:RELATED_TO]-(d2)
            WITH d1, d2, collect(DISTINCT art.name) AS shared_articles
            WHERE size(shared_articles) >= 1
            RETURN d1.name AS doutrina_a,
                   d2.name AS doutrina_b,
                   elementId(d1) AS id_a,
                   elementId(d2) AS id_b,
                   shared_articles
            LIMIT $limit
            """,
            limit=max_pairs
        ))

        for pair in pairs:
            snippets_a = _fetch_node_snippets(session, pair["id_a"])
            snippets_b = _fetch_node_snippets(session, pair["id_b"])
            all_snippets = snippets_a + snippets_b

            context_a = "\n".join(snippets_a[:2]) if snippets_a else "(sem contexto)"
            context_b = "\n".join(snippets_b[:2]) if snippets_b else "(sem contexto)"

            prompt = f"""Analise se esses autores/obras doutrinários têm relação:

**Doutrina A**: {pair['doutrina_a']}
**Doutrina B**: {pair['doutrina_b']}
**Ambos interpretam**: {', '.join(pair['shared_articles'][:3])}

**Contexto A**: {context_a[:400]}
**Contexto B**: {context_b[:400]}

JSON:
{{
  "has_relationship": true ou false,
  "relationship_type": "CITA" | "COMPLEMENTA" | "SUPERA" | null,
  "confidence": 0.0-1.0,
  "evidence": "trecho EXATO do contexto",
  "reasoning": "max 80 chars"
}}
"""

            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"},
                    temperature=0,
                    max_tokens=200
                )

                api_calls += 1
                result = json.loads(response.choices[0].message.content)

                if result.get("has_relationship"):
                    confidence = result.get("confidence", 0)
                    evidence = result.get("evidence", "")
                    evidence_ok = _validate_evidence(evidence, all_snippets)

                    if not evidence_ok:
                        confidence *= 0.5

                    if confidence >= min_confidence:
                        suggestions.append({
                            "source": pair["doutrina_a"],
                            "target": pair["doutrina_b"],
                            "source_element_id": pair["id_a"],
                            "target_element_id": pair["id_b"],
                            "node_type": "Doutrina",
                            "type": result["relationship_type"],
                            "confidence": confidence,
                            "reasoning": result.get("reasoning", ""),
                            "evidence": evidence if evidence_ok else "",
                            "evidence_validated": evidence_ok,
                            "shared_articles": pair["shared_articles"],
                        })

            except Exception as e:
                continue

    except Exception as e:
        logger.error(f"Doutrina LLM suggestion failed: {e}")

    return suggestions, api_calls


# ============================================================================
# LINK CREATION (transparency-first)
# ============================================================================


def create_llm_suggested_links(
    session,
    suggestions: List[Dict[str, Any]]
) -> int:
    """
    Cria :RELATED_TO candidatos sugeridos pelo LLM no grafo.

    Transparency-first: NÃO cria relações tipadas (CITA, COMPLEMENTA, etc.).
    Grava como :RELATED_TO com candidate_type='rel:{type}'.
    """
    created = 0

    for sug in suggestions:
        try:
            node_type = sug.get("node_type", "")
            rel_type = sug.get("type", "RELATED")
            candidate_type = f"rel:{rel_type.lower()}"

            # Usar element_id se disponível, senão fallback por nome
            if sug.get("source_element_id") and sug.get("target_element_id"):
                session.run(
                    """
                    MATCH (a), (b)
                    WHERE elementId(a) = $id_a AND elementId(b) = $id_b
                    CREATE (a)-[r:RELATED_TO]->(b)
                    SET r.source = 'llm_suggestion',
                        r.layer = 'candidate',
                        r.verified = false,
                        r.candidate_type = $candidate_type,
                        r.confidence = $confidence,
                        r.llm_reasoning = $reasoning,
                        r.evidence = $evidence,
                        r.evidence_validated = $evidence_validated,
                        r.created_at = datetime()
                    """,
                    id_a=sug["source_element_id"],
                    id_b=sug["target_element_id"],
                    candidate_type=candidate_type,
                    confidence=sug.get("confidence", 0),
                    reasoning=sug.get("reasoning", ""),
                    evidence=sug.get("evidence", ""),
                    evidence_validated=sug.get("evidence_validated", False),
                )
            elif node_type:
                session.run(
                    f"""
                    MATCH (a:{node_type} {{name: $source}})
                    MATCH (b:{node_type} {{name: $target}})
                    CREATE (a)-[r:RELATED_TO]->(b)
                    SET r.source = 'llm_suggestion',
                        r.layer = 'candidate',
                        r.verified = false,
                        r.candidate_type = $candidate_type,
                        r.confidence = $confidence,
                        r.llm_reasoning = $reasoning,
                        r.evidence = $evidence,
                        r.evidence_validated = $evidence_validated,
                        r.created_at = datetime()
                    """,
                    source=sug["source"],
                    target=sug["target"],
                    candidate_type=candidate_type,
                    confidence=sug.get("confidence", 0),
                    reasoning=sug.get("reasoning", ""),
                    evidence=sug.get("evidence", ""),
                    evidence_validated=sug.get("evidence_validated", False),
                )
            else:
                logger.warning(f"Skipping suggestion without node_type or element_ids: {sug.get('source')}")
                continue

            created += 1

        except Exception as e:
            logger.warning(f"Failed to create LLM-suggested link {sug.get('source')} -> {sug.get('target')}: {e}")

    return created


# ============================================================================
# ORCHESTRATOR
# ============================================================================


def run_llm_based_inference(
    session,
    model_provider: str = "openai",
    model: str = "gpt-4o-mini",
    enable_decisao: bool = True,
    enable_doutrina: bool = True,
    max_decisao_pairs: int = 50,
    max_doutrina_pairs: int = 30,
    min_confidence: float = 0.75,
    l2_candidates: list | None = None,
) -> LLMLinkSuggestionStats:
    """
    Executa inferência de links via LLM (Fase 3).

    Args:
        session: Neo4j session
        model_provider: provider do LLM
        model: modelo LLM
        enable_*: flags para habilitar/desabilitar
        max_*_pairs: máximo de pares a avaliar por tipo
        min_confidence: confiança mínima para aceitar
        l2_candidates: candidatos do L2 para validação (handoff L2→L3)
    """
    stats = LLMLinkSuggestionStats()

    logger.info(f"Starting LLM-based link suggestion (Phase 3) using {model_provider}/{model}...")

    # 1. Validar candidatos L2 (handoff)
    if l2_candidates:
        logger.info(f"Validating {len(l2_candidates)} L2 candidates via LLM...")
        _, l2_stats = validate_l2_candidates_via_llm(
            session,
            candidates=l2_candidates,
            model_provider=model_provider,
            model=model,
            min_confidence=min_confidence,
        )
        stats.llm_api_calls += l2_stats.llm_api_calls
        stats.links_created += l2_stats.links_created
        stats.l2_candidates_validated += l2_stats.l2_candidates_validated
        stats.l2_candidates_rejected += l2_stats.l2_candidates_rejected
        stats.evidence_validated += l2_stats.evidence_validated
        stats.evidence_failed += l2_stats.evidence_failed

    # 2. Descoberta independente
    all_suggestions = []

    if enable_decisao:
        decisao_sugs, decisao_calls = suggest_decisao_relationships_via_llm(
            session,
            model_provider=model_provider,
            model=model,
            max_pairs=max_decisao_pairs,
            min_confidence=min_confidence
        )
        all_suggestions.extend(decisao_sugs)
        stats.llm_api_calls += decisao_calls

    if enable_doutrina:
        doutrina_sugs, doutrina_calls = suggest_doutrina_relationships_via_llm(
            session,
            model_provider=model_provider,
            model=model,
            max_pairs=max_doutrina_pairs,
            min_confidence=min_confidence
        )
        all_suggestions.extend(doutrina_sugs)
        stats.llm_api_calls += doutrina_calls

    stats.links_suggested += len(all_suggestions)

    if all_suggestions:
        stats.links_created += create_llm_suggested_links(session, all_suggestions)

    logger.info(
        f"LLM-based inference complete: {stats.links_suggested} suggestions, "
        f"{stats.links_created} RELATED_TO candidates created, "
        f"{stats.llm_api_calls} API calls, "
        f"evidence_ok={stats.evidence_validated}, evidence_fail={stats.evidence_failed}"
    )

    return stats
