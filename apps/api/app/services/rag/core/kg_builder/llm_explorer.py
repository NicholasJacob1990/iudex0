"""
Fase 3b: Modo exploratório — descoberta de relações para nós isolados.

Identifica nós com poucas ou nenhuma conexão e usa LLM para propor
relações com base em uma shortlist controlada (lexical + embedding + vizinhos).

Todas as arestas criadas são :RELATED_TO com layer='candidate', verified=false.
candidate_type = "exploratory:llm:{TypeA}x{TypeB}"
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Tipos de nós que podem ser explorados
DEFAULT_EXPLORABLE_TYPES = ["Decisao", "Artigo", "Sumula", "Doutrina", "Lei"]

# Relações de infraestrutura a ignorar no cálculo de grau
INFRA_REL_TYPES = ["MENTIONS", "FROM_CHUNK", "HAS_CHUNK", "BELONGS_TO"]


@dataclass
class ExploratoryStats:
    """Estatísticas do modo exploratório."""
    isolated_nodes_found: int = 0
    nodes_explored: int = 0
    suggestions_created: int = 0
    evidence_validated: int = 0
    evidence_failed: int = 0
    llm_api_calls: int = 0
    llm_errors: int = 0
    shortlist_empty: int = 0


def _get_llm_client(provider: str = "openai"):
    """Lazy import do cliente LLM."""
    try:
        from app.services.model_registry import get_model_client
        return get_model_client(provider)
    except Exception as e:
        logger.warning(f"Failed to load LLM client for explorer: {e}")
        return None


def _validate_evidence(evidence: str, snippets: list[str]) -> bool:
    """Anti-alucinação: evidência deve ser substring de algum snippet."""
    if not evidence or len(evidence) < 10:
        return False
    evidence_lower = evidence.lower().strip()
    return any(evidence_lower in s.lower() for s in snippets if s)


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
# FINDING ISOLATED NODES
# ============================================================================


def find_isolated_nodes(
    session,
    node_types: list[str] | None = None,
    max_degree: int = 1,
    limit: int = 100,
) -> list[dict]:
    """
    Busca nós com grau ≤ max_degree, excluindo relações de infraestrutura.

    Args:
        node_types: tipos de nós a considerar (default: todos exploráveis)
        max_degree: grau máximo para ser considerado "isolado"
        limit: máximo de nós a retornar

    Returns:
        Lista de dicts com element_id, name, type, degree
    """
    types = node_types or DEFAULT_EXPLORABLE_TYPES
    isolated = []

    for node_type in types:
        try:
            # Contar relações excluindo infraestrutura
            infra_filter = " AND ".join(
                [f"NOT type(rel) = '{rt}'" for rt in INFRA_REL_TYPES]
            )

            results = list(session.run(
                f"""
                MATCH (n:{node_type})
                WHERE n.name IS NOT NULL
                OPTIONAL MATCH (n)-[rel]-()
                WHERE {infra_filter}
                WITH n, count(rel) AS degree
                WHERE degree <= $max_degree
                RETURN elementId(n) AS element_id,
                       n.name AS name,
                       labels(n)[0] AS type,
                       degree
                ORDER BY degree ASC, n.name
                LIMIT $limit
                """,
                max_degree=max_degree,
                limit=limit
            ))

            for r in results:
                isolated.append({
                    "element_id": r["element_id"],
                    "name": r["name"],
                    "type": r["type"],
                    "degree": r["degree"],
                })

        except Exception as e:
            logger.warning(f"Failed to find isolated {node_type} nodes: {e}")

    logger.info(f"Found {len(isolated)} isolated nodes (degree <= {max_degree})")
    return isolated[:limit]


# ============================================================================
# BUILDING SHORTLIST
# ============================================================================


def _build_exploration_shortlist(
    session,
    node: dict,
    max_candidates: int = 10,
) -> list[dict]:
    """
    Constrói shortlist de candidatos para um nó isolado.

    Combina 3 fontes:
    1. Lexical: nós com nome similar (substring/prefixo)
    2. Embedding: top-k por similaridade de embedding
    3. Neighbor-of-neighbor: nós conectados a vizinhos do nó
    """
    candidates = {}  # element_id -> dict (dedup)

    # 1. Lexical: nós com nome similar
    try:
        name = node["name"]
        # Extrair tokens significativos (>= 4 chars) para busca
        tokens = [t for t in name.split() if len(t) >= 4][:3]
        if tokens:
            # Buscar nós que contêm algum token no nome
            for token in tokens:
                results = list(session.run(
                    """
                    MATCH (n)
                    WHERE n.name IS NOT NULL
                      AND n.name CONTAINS $token
                      AND elementId(n) <> $eid
                      AND NOT n:Chunk
                    RETURN elementId(n) AS element_id,
                           n.name AS name,
                           labels(n)[0] AS type
                    LIMIT 5
                    """,
                    token=token,
                    eid=node["element_id"]
                ))
                for r in results:
                    eid = r["element_id"]
                    if eid not in candidates:
                        candidates[eid] = {
                            "element_id": eid,
                            "name": r["name"],
                            "type": r["type"],
                            "source": "lexical",
                        }
    except Exception as e:
        logger.debug(f"Lexical shortlist failed for {node['name']}: {e}")

    # 2. Embedding: top-k por similaridade
    try:
        results = list(session.run(
            """
            MATCH (n) WHERE elementId(n) = $eid AND n.embedding IS NOT NULL
            WITH n
            MATCH (m)
            WHERE m.embedding IS NOT NULL
              AND elementId(m) <> $eid
              AND NOT m:Chunk
              AND m.name IS NOT NULL
            WITH m,
                 gds.similarity.cosine(n.embedding, m.embedding) AS sim
            WHERE sim > 0.7
            RETURN elementId(m) AS element_id,
                   m.name AS name,
                   labels(m)[0] AS type,
                   sim
            ORDER BY sim DESC
            LIMIT $top_k
            """,
            eid=node["element_id"],
            top_k=max_candidates
        ))
        for r in results:
            eid = r["element_id"]
            if eid not in candidates:
                candidates[eid] = {
                    "element_id": eid,
                    "name": r["name"],
                    "type": r["type"],
                    "source": "embedding",
                    "similarity": r["sim"],
                }
    except Exception as e:
        logger.debug(f"Embedding shortlist failed for {node['name']}: {e}")

    # 3. Neighbor-of-neighbor
    try:
        infra_filter = " AND ".join(
            [f"NOT type(r1) = '{rt}' AND NOT type(r2) = '{rt}'" for rt in INFRA_REL_TYPES]
        )
        results = list(session.run(
            f"""
            MATCH (n)-[r1]-(neighbor)-[r2]-(candidate)
            WHERE elementId(n) = $eid
              AND elementId(candidate) <> $eid
              AND candidate <> n
              AND candidate.name IS NOT NULL
              AND NOT candidate:Chunk
              AND {infra_filter}
            RETURN DISTINCT elementId(candidate) AS element_id,
                   candidate.name AS name,
                   labels(candidate)[0] AS type,
                   neighbor.name AS via_neighbor
            LIMIT $limit
            """,
            eid=node["element_id"],
            limit=max_candidates
        ))
        for r in results:
            eid = r["element_id"]
            if eid not in candidates:
                candidates[eid] = {
                    "element_id": eid,
                    "name": r["name"],
                    "type": r["type"],
                    "source": "neighbor_of_neighbor",
                    "via": r["via_neighbor"],
                }
    except Exception as e:
        logger.debug(f"Neighbor-of-neighbor shortlist failed for {node['name']}: {e}")

    shortlist = list(candidates.values())[:max_candidates]
    return shortlist


# ============================================================================
# LLM EXPLORATION
# ============================================================================


def explore_node_relationships(
    session,
    node: dict,
    shortlist: list[dict],
    client,
    model: str = "gpt-4o-mini",
    min_confidence: float = 0.80,
) -> tuple[list[dict], ExploratoryStats]:
    """
    Usa LLM para explorar relações potenciais de um nó com sua shortlist.

    Args:
        node: nó isolado {element_id, name, type}
        shortlist: candidatos potenciais
        client: cliente LLM
        model: modelo a usar
        min_confidence: confiança mínima (mais alta por ser proativo)

    Returns:
        (suggestions, stats_parciais)
    """
    stats = ExploratoryStats()
    suggestions = []

    # Buscar snippets do nó
    node_snippets = _fetch_node_snippets(session, node["element_id"])
    node_context = "\n".join(node_snippets[:2]) if node_snippets else "(sem contexto)"

    # Formatar shortlist para o prompt
    shortlist_text = "\n".join([
        f"  {i+1}. {c['name']} (Tipo: {c['type']}, via: {c.get('source', '?')})"
        for i, c in enumerate(shortlist)
    ])

    prompt = f"""Você é um especialista jurídico. Um nó do grafo de conhecimento tem poucas conexões.
Analise se ele se relaciona com algum dos candidatos.

**Nó isolado**: {node['name']} (Tipo: {node['type']})
**Contexto**: {node_context[:600]}

**Candidatos**:
{shortlist_text}

Responda SOMENTE com JSON válido (sem markdown):
{{
  "relationships": [
    {{
      "target_index": 1,
      "relationship_type": "CITA" | "COMPLEMENTA" | "INTERPRETA" | "REMETE_A" | "CONFIRMA" | "APLICA_SUMULA",
      "confidence": 0.0-1.0,
      "evidence": "trecho EXATO do contexto que sustenta a relação",
      "reasoning": "max 80 chars"
    }}
  ]
}}

**Regras**:
- Inclua SOMENTE relações com confidence >= 0.80
- evidence DEVE ser trecho exato do contexto fornecido
- Se não houver evidência textual, NÃO inclua a relação
- Máximo 3 relações por nó
- target_index = número do candidato na lista (1-based)
"""

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0,
            max_tokens=500,
        )
        stats.llm_api_calls += 1

        result = json.loads(response.choices[0].message.content)
        relationships = result.get("relationships", [])

        # Buscar snippets de todos os candidatos para validação
        all_snippets = list(node_snippets)
        candidate_snippets_cache: dict[str, list[str]] = {}

        for rel in relationships[:3]:  # Max 3 por nó
            idx = rel.get("target_index", 0) - 1  # 1-based -> 0-based
            if idx < 0 or idx >= len(shortlist):
                continue

            target = shortlist[idx]
            confidence = rel.get("confidence", 0)
            evidence = rel.get("evidence", "")

            # Buscar snippets do target se necessário
            if target["element_id"] not in candidate_snippets_cache:
                candidate_snippets_cache[target["element_id"]] = _fetch_node_snippets(
                    session, target["element_id"]
                )
            target_snippets = candidate_snippets_cache[target["element_id"]]
            validation_snippets = all_snippets + target_snippets

            evidence_ok = _validate_evidence(evidence, validation_snippets)
            if evidence_ok:
                stats.evidence_validated += 1
            else:
                stats.evidence_failed += 1
                confidence *= 0.5

            if confidence < min_confidence:
                continue

            suggestions.append({
                "source_element_id": node["element_id"],
                "target_element_id": target["element_id"],
                "source_name": node["name"],
                "target_name": target["name"],
                "source_type": node["type"],
                "target_type": target["type"],
                "type": rel.get("relationship_type", "RELATED"),
                "confidence": confidence,
                "reasoning": rel.get("reasoning", ""),
                "evidence": evidence if evidence_ok else "",
                "evidence_validated": evidence_ok,
                "shortlist_source": target.get("source", ""),
            })

    except json.JSONDecodeError as e:
        stats.llm_errors += 1
        logger.warning(f"JSON parse error exploring {node['name']}: {e}")
    except Exception as e:
        stats.llm_errors += 1
        logger.warning(f"LLM exploration failed for {node['name']}: {e}")

    return suggestions, stats


# ============================================================================
# CREATING EXPLORATORY CANDIDATES
# ============================================================================


def _create_exploratory_links(
    session,
    suggestions: list[dict],
) -> int:
    """Cria :RELATED_TO candidatos exploratórios no grafo."""
    created = 0

    for sug in suggestions:
        try:
            rel_type = sug.get("type", "RELATED")
            candidate_type = f"exploratory:llm:{sug['source_type']}x{sug['target_type']}"

            session.run(
                """
                MATCH (a), (b)
                WHERE elementId(a) = $id_a AND elementId(b) = $id_b
                  AND NOT (a)-[:RELATED_TO {candidate_type: $candidate_type}]-(b)
                CREATE (a)-[r:RELATED_TO]->(b)
                SET r.source = 'exploratory_llm',
                    r.layer = 'candidate',
                    r.verified = false,
                    r.candidate_type = $candidate_type,
                    r.rel_hint = $rel_hint,
                    r.confidence = $confidence,
                    r.llm_reasoning = $reasoning,
                    r.evidence = $evidence,
                    r.evidence_validated = $evidence_validated,
                    r.shortlist_source = $shortlist_source,
                    r.created_at = datetime()
                """,
                id_a=sug["source_element_id"],
                id_b=sug["target_element_id"],
                candidate_type=candidate_type,
                rel_hint=rel_type.lower(),
                confidence=sug.get("confidence", 0),
                reasoning=sug.get("reasoning", ""),
                evidence=sug.get("evidence", ""),
                evidence_validated=sug.get("evidence_validated", False),
                shortlist_source=sug.get("shortlist_source", ""),
            )
            created += 1

        except Exception as e:
            logger.warning(
                f"Failed to create exploratory link "
                f"{sug.get('source_name')} -> {sug.get('target_name')}: {e}"
            )

    return created


# ============================================================================
# ORCHESTRATOR
# ============================================================================


def run_exploratory_enrichment(
    session,
    node_types: list[str] | None = None,
    max_degree: int = 1,
    max_nodes: int = 50,
    max_shortlist: int = 10,
    model_provider: str = "openai",
    model: str = "gpt-4o-mini",
    min_confidence: float = 0.80,
) -> ExploratoryStats:
    """
    Executa enriquecimento exploratório para nós isolados (Fase 3b).

    Pipeline: find_isolated → build_shortlist → explore_via_llm → validate → create RELATED_TO

    Args:
        session: Neo4j session
        node_types: tipos de nós a explorar
        max_degree: grau máximo para "isolado"
        max_nodes: máximo de nós a explorar
        max_shortlist: tamanho da shortlist por nó
        model_provider: provider do LLM
        model: modelo LLM
        min_confidence: confiança mínima (default 0.80 — mais alto que L3)
    """
    stats = ExploratoryStats()

    logger.info(
        f"Starting exploratory enrichment (Phase 3b) — "
        f"max_degree={max_degree}, max_nodes={max_nodes}, "
        f"model={model_provider}/{model}"
    )

    client = _get_llm_client(model_provider)
    if not client:
        logger.warning("No LLM client available for exploratory enrichment")
        return stats

    # 1. Encontrar nós isolados
    isolated = find_isolated_nodes(
        session,
        node_types=node_types,
        max_degree=max_degree,
        limit=max_nodes
    )
    stats.isolated_nodes_found = len(isolated)

    if not isolated:
        logger.info("No isolated nodes found — skipping exploratory enrichment")
        return stats

    # 2. Para cada nó, construir shortlist e explorar
    all_suggestions = []

    for node in isolated:
        shortlist = _build_exploration_shortlist(
            session, node, max_candidates=max_shortlist
        )

        if not shortlist:
            stats.shortlist_empty += 1
            continue

        suggestions, node_stats = explore_node_relationships(
            session, node, shortlist,
            client=client, model=model,
            min_confidence=min_confidence,
        )

        all_suggestions.extend(suggestions)
        stats.nodes_explored += 1
        stats.llm_api_calls += node_stats.llm_api_calls
        stats.llm_errors += node_stats.llm_errors
        stats.evidence_validated += node_stats.evidence_validated
        stats.evidence_failed += node_stats.evidence_failed

    # 3. Criar candidatos
    if all_suggestions:
        stats.suggestions_created = _create_exploratory_links(session, all_suggestions)

    logger.info(
        f"Exploratory enrichment complete: "
        f"{stats.isolated_nodes_found} isolated found, "
        f"{stats.nodes_explored} explored, "
        f"{stats.suggestions_created} RELATED_TO candidates created, "
        f"{stats.llm_api_calls} API calls, "
        f"evidence_ok={stats.evidence_validated}, evidence_fail={stats.evidence_failed}"
    )

    return stats
