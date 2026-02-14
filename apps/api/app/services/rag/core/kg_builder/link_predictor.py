"""
Fase 2: Link prediction via similaridade de embeddings.

Este módulo usa os embeddings já computados (dos chunks) para descobrir
relações implícitas baseadas em similaridade semântica.

Abordagem "transparência-first": todas as arestas criadas são
:RELATED_TO com layer='candidate', verified=false.
Nunca cria relações tipadas diretamente (CITA, COMPLEMENTA, etc.).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


# ============================================================================
# ADAPTIVE THRESHOLDS CONFIGURATION
# ============================================================================

TYPE_PAIR_CONFIG = {
    # Configuração por par de tipos (type_a, type_b)
    # percentile: qual percentil usar como threshold (99 = top 1%, 99.7 = top 0.3%)
    # min_topk: mínimo de links por nó garantido (budget fixo)
    # rel_hint: sugestão de tipo de relacionamento (metadata, não cria typed rel)
    ("Decisao", "Decisao"): {"percentile": 99.0, "min_topk": 3, "rel_hint": "CITA"},
    ("Sumula", "Sumula"): {"percentile": 99.7, "min_topk": 2, "rel_hint": "COMPLEMENTA"},
    ("Doutrina", "Doutrina"): {"percentile": 99.0, "min_topk": 3, "rel_hint": "CITA"},
    # Novos pares
    ("Artigo", "Artigo"): {"percentile": 99.5, "min_topk": 2, "rel_hint": "REMETE_A"},
    ("Decisao", "Sumula"): {"percentile": 99.0, "min_topk": 2, "rel_hint": "APLICA_SUMULA"},
    ("Decisao", "Artigo"): {"percentile": 99.0, "min_topk": 3, "rel_hint": "INTERPRETA"},
}

# Mapeamento de dimensão por par de tipos
_DIMENSION_MAP = {
    ("Decisao", "Decisao"): "horizontal",
    ("Sumula", "Sumula"): "horizontal",
    ("Doutrina", "Doutrina"): "doutrinaria",
    ("Artigo", "Artigo"): "legislacao",
    ("Decisao", "Sumula"): "vertical",
    ("Decisao", "Artigo"): "vertical",
}


@dataclass
class EmbeddingCandidate:
    """Candidato de link identificado por similaridade de embedding.

    Usado para handoff L2→L3: L2 identifica pares similares,
    L3 valida e classifica via LLM.
    """
    source_element_id: str
    target_element_id: str
    source_name: str
    target_name: str
    source_type: str
    target_type: str
    similarity_score: float
    confidence: float
    candidate_type: str  # "semantic:embedding_similarity:Decisao×Decisao"


@dataclass
class PairProfile:
    """Perfil estatístico de similaridade para um par de tipos."""
    type_a: str
    type_b: str
    n_samples: int
    p50: float  # mediana
    p90: float
    p99: float
    p99_7: float  # top 0.3%
    adaptive_threshold: float  # threshold calculado com base no percentile configurado


@dataclass
class EmbeddingSimilarityStats:
    """Estatísticas de link prediction via embeddings."""
    decisao_cita_by_similarity: int = 0
    sumula_cita_by_similarity: int = 0
    doutrina_cita_by_similarity: int = 0
    artigo_by_similarity: int = 0
    cross_type_by_similarity: int = 0
    total_inferred: int = 0
    candidates_for_l3: List[EmbeddingCandidate] = field(default_factory=list)


def _cosine_similarity_batch(embeddings: np.ndarray) -> np.ndarray:
    """Calcula matriz de similaridade cosseno entre todos os pares."""
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms[norms == 0] = 1  # Evita divisão por zero
    normalized = embeddings / norms
    return np.dot(normalized, normalized.T)


def _cosine_similarity_cross(embeddings_a: np.ndarray, embeddings_b: np.ndarray) -> np.ndarray:
    """Calcula matriz de similaridade cosseno entre dois conjuntos."""
    norms_a = np.linalg.norm(embeddings_a, axis=1, keepdims=True)
    norms_a[norms_a == 0] = 1
    normalized_a = embeddings_a / norms_a

    norms_b = np.linalg.norm(embeddings_b, axis=1, keepdims=True)
    norms_b[norms_b == 0] = 1
    normalized_b = embeddings_b / norms_b

    return np.dot(normalized_a, normalized_b.T)


def allocate_budget_by_potential(
    session,
    total_budget: int = 10000,
    type_pairs: list[tuple[str, str]] | None = None,
) -> dict[tuple[str, str], dict[str, int]]:
    """
    Aloca budget (max links) para cada par de tipos baseado no potencial (não circular).

    A lógica é:
    1. Conta n_entities de cada tipo
    2. Calcula potencial = n_a × n_b (total de pares possíveis)
    3. Garante min_topk por par (da config)
    4. Distribui budget restante proporcionalmente ao potencial
    """
    if type_pairs is None:
        type_pairs = list(TYPE_PAIR_CONFIG.keys())

    # 1. Contar entidades de cada tipo
    type_counts: dict[str, int] = {}
    for type_a, type_b in type_pairs:
        for t in [type_a, type_b]:
            if t not in type_counts:
                count_result = session.run(
                    f"MATCH (n:{t}) WHERE n.embedding IS NOT NULL RETURN count(n) AS cnt"
                ).single()
                type_counts[t] = count_result["cnt"] if count_result else 0

    # 2. Calcular potencial de cada par
    potentials: dict[tuple[str, str], int] = {}
    for type_a, type_b in type_pairs:
        n_a = type_counts.get(type_a, 0)
        n_b = type_counts.get(type_b, 0)
        if type_a == type_b:
            potential = (n_a * (n_a - 1)) // 2 if n_a > 1 else 0
        else:
            potential = n_a * n_b
        potentials[(type_a, type_b)] = potential

    total_potential = sum(potentials.values())
    if total_potential == 0:
        logger.warning("No potential for any pair (no embeddings?)")
        return {}

    # 3. Calcular min_topk total (budget reservado)
    allocations: dict[tuple[str, str], dict] = {}
    reserved_budget = 0
    for pair in type_pairs:
        config = TYPE_PAIR_CONFIG.get(pair, {"min_topk": 3})
        min_topk = config["min_topk"]
        n_nodes = type_counts.get(pair[0], 0)
        reserved = min_topk * n_nodes
        reserved_budget += reserved
        allocations[pair] = {"min_topk": min_topk, "reserved": reserved}

    # 4. Distribuir budget restante proporcionalmente
    remaining_budget = max(0, total_budget - reserved_budget)
    for pair in type_pairs:
        proportion = potentials[pair] / total_potential
        extra_budget = int(remaining_budget * proportion)
        n_nodes = type_counts.get(pair[0], 0)

        total_pair_budget = allocations[pair]["reserved"] + extra_budget
        max_per_node = (total_pair_budget // n_nodes) if n_nodes > 0 else allocations[pair]["min_topk"]
        max_per_node = max(max_per_node, allocations[pair]["min_topk"])

        allocations[pair]["total_budget"] = total_pair_budget
        allocations[pair]["max_links_per_node"] = max_per_node

        logger.info(
            f"Budget allocation {pair[0]}×{pair[1]}: "
            f"potential={potentials[pair]}, "
            f"n_nodes={n_nodes}, "
            f"max_per_node={max_per_node}, "
            f"total_budget={total_pair_budget}"
        )

    return allocations


def compute_pair_profile_by_sampling(
    session,
    type_a: str,
    type_b: str,
    sample_size: int = 200,
) -> PairProfile:
    """
    Calcula perfil estatístico de similaridade para um par de tipos via amostragem.

    Returns:
        PairProfile com estatísticas de similaridade (p50, p90, p99, p99.7)
    """
    result_a = list(session.run(
        f"""
        MATCH (a:{type_a})
        WHERE a.embedding IS NOT NULL
        RETURN a.embedding AS embedding
        ORDER BY rand()
        LIMIT $limit
        """,
        limit=sample_size
    ))

    if type_a == type_b:
        result_b = result_a
    else:
        result_b = list(session.run(
            f"""
            MATCH (b:{type_b})
            WHERE b.embedding IS NOT NULL
            RETURN b.embedding AS embedding
            ORDER BY rand()
            LIMIT $limit
            """,
            limit=sample_size
        ))

    if len(result_a) < 10 or len(result_b) < 10:
        logger.warning(f"Not enough samples for {type_a}×{type_b} profile (a={len(result_a)}, b={len(result_b)})")
        return PairProfile(
            type_a=type_a, type_b=type_b, n_samples=0,
            p50=0.5, p90=0.7, p99=0.85, p99_7=0.88,
            adaptive_threshold=0.85
        )

    embeddings_a = np.array([r["embedding"] for r in result_a])
    embeddings_b = np.array([r["embedding"] for r in result_b])

    if type_a == type_b:
        sim_matrix = _cosine_similarity_batch(embeddings_a)
        mask = np.triu(np.ones_like(sim_matrix, dtype=bool), k=1)
        similarities = sim_matrix[mask].flatten()
    else:
        sim_matrix = _cosine_similarity_cross(embeddings_a, embeddings_b)
        similarities = sim_matrix.flatten()

    p50 = float(np.percentile(similarities, 50))
    p90 = float(np.percentile(similarities, 90))
    p99 = float(np.percentile(similarities, 99))
    p99_7 = float(np.percentile(similarities, 99.7))

    config = TYPE_PAIR_CONFIG.get((type_a, type_b), {"percentile": 99.0})
    target_percentile = config["percentile"]
    adaptive_threshold = float(np.percentile(similarities, target_percentile))

    logger.info(
        f"Profile {type_a}×{type_b}: n={len(similarities)}, "
        f"p50={p50:.3f}, p90={p90:.3f}, p99={p99:.3f}, p99.7={p99_7:.3f}, "
        f"adaptive_threshold={adaptive_threshold:.3f} (p{target_percentile})"
    )

    return PairProfile(
        type_a=type_a, type_b=type_b, n_samples=len(similarities),
        p50=p50, p90=p90, p99=p99, p99_7=p99_7,
        adaptive_threshold=adaptive_threshold
    )


# ============================================================================
# GENERIC EMBEDDING INFERENCE (replaces type-specific functions)
# ============================================================================


def infer_links_by_embedding_generic(
    session,
    type_a: str,
    type_b: str,
    similarity_threshold: float | None = None,
    max_links_per_node: int = 5,
    confidence_base: float = 0.7,
    use_adaptive_threshold: bool = True,
    return_candidates: bool = False,
    node_limit: int = 2000,
) -> tuple[int, list[EmbeddingCandidate]]:
    """
    Descobre links entre entidades usando similaridade de embeddings.

    Transparency-first: cria :RELATED_TO com layer='candidate', nunca typed rels.

    Args:
        session: Neo4j session
        type_a: tipo da entidade fonte (ex: "Decisao")
        type_b: tipo da entidade alvo (pode ser == type_a)
        similarity_threshold: se None e use_adaptive_threshold, calcula via amostragem
        max_links_per_node: máximo de links por nó
        confidence_base: confiança base (ajustada por similaridade)
        use_adaptive_threshold: se True, calcula threshold adaptativo
        return_candidates: se True, retorna EmbeddingCandidate[] sem escrever no grafo
        node_limit: máximo de nós a processar por tipo

    Returns:
        (links_created, candidates_list)
    """
    created = 0
    candidates_out: list[EmbeddingCandidate] = []
    same_type = type_a == type_b
    candidate_type = f"semantic:embedding_similarity:{type_a}x{type_b}"
    dimension = _DIMENSION_MAP.get((type_a, type_b), "unknown")

    try:
        # 0. Determinar threshold
        if use_adaptive_threshold and similarity_threshold is None:
            profile = compute_pair_profile_by_sampling(session, type_a, type_b)
            similarity_threshold = profile.adaptive_threshold
            config = TYPE_PAIR_CONFIG.get((type_a, type_b), {})
            min_topk = config.get("min_topk", 3)
            max_links_per_node = max(min_topk, max_links_per_node)
            logger.info(
                f"Adaptive threshold {type_a}×{type_b}: {similarity_threshold:.3f} "
                f"(min_topk={min_topk}, max_per_node={max_links_per_node})"
            )
        elif similarity_threshold is None:
            similarity_threshold = 0.85
            logger.info(f"Default threshold for {type_a}×{type_b}: {similarity_threshold}")

        # 1. Buscar nós com embeddings
        result_a = list(session.run(
            f"""
            MATCH (n:{type_a})
            WHERE n.embedding IS NOT NULL
            RETURN n.name AS name, n.embedding AS embedding, elementId(n) AS id
            LIMIT $limit
            """,
            limit=node_limit
        ))

        if same_type:
            result_b = result_a
        else:
            result_b = list(session.run(
                f"""
                MATCH (n:{type_b})
                WHERE n.embedding IS NOT NULL
                RETURN n.name AS name, n.embedding AS embedding, elementId(n) AS id
                LIMIT $limit
                """,
                limit=node_limit
            ))

        if len(result_a) < 2 or (not same_type and len(result_b) < 1):
            logger.info(f"Not enough {type_a}/{type_b} nodes with embeddings")
            return 0, []

        # 2. Matrizes
        names_a = [r["name"] for r in result_a]
        ids_a = [r["id"] for r in result_a]
        embeddings_a = np.array([r["embedding"] for r in result_a])

        if same_type:
            names_b, ids_b = names_a, ids_a
            sim_matrix = _cosine_similarity_batch(embeddings_a)
        else:
            names_b = [r["name"] for r in result_b]
            ids_b = [r["id"] for r in result_b]
            embeddings_b = np.array([r["embedding"] for r in result_b])
            sim_matrix = _cosine_similarity_cross(embeddings_a, embeddings_b)

        # 3. Encontrar pares com alta similaridade
        pair_candidates: List[Tuple[int, int, float]] = []

        for i in range(len(result_a)):
            if same_type:
                sims = sim_matrix[i].copy()
                sims[i] = -1  # Remove self
            else:
                sims = sim_matrix[i]

            top_k_indices = np.argsort(sims)[::-1][:max_links_per_node]

            for j in top_k_indices:
                sim = float(sims[j])
                if sim >= similarity_threshold:
                    if same_type and i >= j:
                        continue  # Evita duplicatas
                    pair_candidates.append((i, j, sim))

        logger.info(f"Found {len(pair_candidates)} candidate {type_a}×{type_b} pairs (threshold={similarity_threshold:.3f})")

        # 4. Processar candidatos
        for i, j, similarity in pair_candidates:
            confidence = confidence_base * similarity
            src_id, src_name = ids_a[i], names_a[i]
            tgt_id, tgt_name = ids_b[j], names_b[j]

            if return_candidates:
                candidates_out.append(EmbeddingCandidate(
                    source_element_id=src_id,
                    target_element_id=tgt_id,
                    source_name=src_name,
                    target_name=tgt_name,
                    source_type=type_a,
                    target_type=type_b,
                    similarity_score=similarity,
                    confidence=confidence,
                    candidate_type=candidate_type,
                ))
                continue

            # Verificar se RELATED_TO candidato já existe
            exists = session.run(
                "MATCH (a)-[r:RELATED_TO]-(b) "
                "WHERE elementId(a) = $id_a AND elementId(b) = $id_b "
                "  AND r.candidate_type = $candidate_type "
                "RETURN count(r) > 0 AS exists",
                id_a=src_id, id_b=tgt_id, candidate_type=candidate_type
            ).single()

            if exists and exists["exists"]:
                continue

            # Criar :RELATED_TO candidato (transparency-first)
            session.run(
                f"""
                MATCH (a:{type_a}), (b:{type_b})
                WHERE elementId(a) = $id_a AND elementId(b) = $id_b
                CREATE (a)-[r:RELATED_TO]->(b)
                SET r.source = 'embedding_similarity',
                    r.layer = 'candidate',
                    r.verified = false,
                    r.candidate_type = $candidate_type,
                    r.confidence = $confidence,
                    r.similarity_score = $similarity,
                    r.created_at = datetime(),
                    r.dimension = $dimension
                """,
                id_a=src_id,
                id_b=tgt_id,
                candidate_type=candidate_type,
                confidence=confidence,
                similarity=similarity,
                dimension=dimension,
            )
            created += 1

        logger.info(
            f"Embedding similarity ({type_a}×{type_b}): "
            f"created={created} RELATED_TO candidates, "
            f"handoff={len(candidates_out)} for L3"
        )

    except Exception as e:
        logger.warning(f"Embedding-based {type_a}×{type_b} inference failed: {e}")

    return created, candidates_out


# ============================================================================
# THIN WRAPPERS (backward-compatible)
# ============================================================================


def infer_decisao_links_by_embedding(
    session,
    similarity_threshold: float | None = None,
    max_links_per_node: int = 5,
    confidence_base: float = 0.7,
    use_adaptive_threshold: bool = True,
) -> int:
    """Wrapper backward-compatible para Decisao×Decisao."""
    count, _ = infer_links_by_embedding_generic(
        session, "Decisao", "Decisao",
        similarity_threshold=similarity_threshold,
        max_links_per_node=max_links_per_node,
        confidence_base=confidence_base,
        use_adaptive_threshold=use_adaptive_threshold,
    )
    return count


def infer_sumula_links_by_embedding(
    session,
    similarity_threshold: float | None = None,
    max_links_per_node: int = 3,
    confidence_base: float = 0.65,
    use_adaptive_threshold: bool = True,
) -> int:
    """Wrapper backward-compatible para Sumula×Sumula."""
    count, _ = infer_links_by_embedding_generic(
        session, "Sumula", "Sumula",
        similarity_threshold=similarity_threshold,
        max_links_per_node=max_links_per_node,
        confidence_base=confidence_base,
        use_adaptive_threshold=use_adaptive_threshold,
    )
    return count


def infer_doutrina_links_by_embedding(
    session,
    similarity_threshold: float | None = None,
    max_links_per_node: int = 4,
    confidence_base: float = 0.6,
    use_adaptive_threshold: bool = True,
) -> int:
    """Wrapper backward-compatible para Doutrina×Doutrina."""
    count, _ = infer_links_by_embedding_generic(
        session, "Doutrina", "Doutrina",
        similarity_threshold=similarity_threshold,
        max_links_per_node=max_links_per_node,
        confidence_base=confidence_base,
        use_adaptive_threshold=use_adaptive_threshold,
    )
    return count


# ============================================================================
# ORCHESTRATOR
# ============================================================================


def run_embedding_based_inference(
    session,
    enable_decisao: bool = True,
    enable_sumula: bool = True,
    enable_doutrina: bool = True,
    enable_artigo: bool = False,
    enable_cross_type: bool = False,
    decisao_threshold: float | None = None,
    sumula_threshold: float | None = None,
    doutrina_threshold: float | None = None,
    use_adaptive_threshold: bool = True,
    use_budget_allocation: bool = True,
    total_budget: int = 10000,
    pass_to_l3: bool = False,
) -> EmbeddingSimilarityStats:
    """
    Executa inferência de links baseada em similaridade de embeddings.

    Args:
        session: Neo4j session
        enable_*: flags para habilitar/desabilitar cada tipo
        *_threshold: thresholds de similaridade por tipo
        use_adaptive_threshold: se True, calcula thresholds via percentis
        use_budget_allocation: se True, aloca budget por potencial
        total_budget: budget total de links a criar
        pass_to_l3: se True, retorna candidatos em stats.candidates_for_l3
                    para handoff L2→L3 (não escreve no grafo para esses candidatos)

    Returns:
        Estatísticas de links criados (e candidatos para L3 se pass_to_l3=True)
    """
    stats = EmbeddingSimilarityStats()

    logger.info(
        f"Starting embedding-based link prediction (Phase 2) with "
        f"{'adaptive' if use_adaptive_threshold else 'fixed'} thresholds, "
        f"pass_to_l3={pass_to_l3}..."
    )

    # Determinar pares ativos
    type_pairs: list[tuple[str, str]] = []
    if enable_decisao:
        type_pairs.append(("Decisao", "Decisao"))
    if enable_sumula:
        type_pairs.append(("Sumula", "Sumula"))
    if enable_doutrina:
        type_pairs.append(("Doutrina", "Doutrina"))
    if enable_artigo:
        type_pairs.append(("Artigo", "Artigo"))
    if enable_cross_type:
        type_pairs.append(("Decisao", "Sumula"))
        type_pairs.append(("Decisao", "Artigo"))

    # Alocar budget
    budget_allocs = {}
    if use_budget_allocation and type_pairs:
        budget_allocs = allocate_budget_by_potential(
            session, total_budget=total_budget, type_pairs=type_pairs
        )

    # Mapeamento de thresholds explícitos
    explicit_thresholds = {
        ("Decisao", "Decisao"): decisao_threshold,
        ("Sumula", "Sumula"): sumula_threshold,
        ("Doutrina", "Doutrina"): doutrina_threshold,
    }

    # Executar cada par
    for pair in type_pairs:
        max_per_node = budget_allocs.get(pair, {}).get("max_links_per_node", 5)
        threshold = explicit_thresholds.get(pair)
        config = TYPE_PAIR_CONFIG.get(pair, {})
        confidence_base = {
            ("Decisao", "Decisao"): 0.7,
            ("Sumula", "Sumula"): 0.65,
            ("Doutrina", "Doutrina"): 0.6,
            ("Artigo", "Artigo"): 0.6,
        }.get(pair, 0.65)

        count, candidates = infer_links_by_embedding_generic(
            session,
            type_a=pair[0],
            type_b=pair[1],
            similarity_threshold=threshold,
            max_links_per_node=max_per_node,
            confidence_base=confidence_base,
            use_adaptive_threshold=use_adaptive_threshold,
            return_candidates=pass_to_l3,
        )

        # Atualizar stats
        if pair == ("Decisao", "Decisao"):
            stats.decisao_cita_by_similarity = count
        elif pair == ("Sumula", "Sumula"):
            stats.sumula_cita_by_similarity = count
        elif pair == ("Doutrina", "Doutrina"):
            stats.doutrina_cita_by_similarity = count
        elif pair == ("Artigo", "Artigo"):
            stats.artigo_by_similarity = count
        else:
            stats.cross_type_by_similarity += count

        if pass_to_l3:
            stats.candidates_for_l3.extend(candidates)

    stats.total_inferred = (
        stats.decisao_cita_by_similarity +
        stats.sumula_cita_by_similarity +
        stats.doutrina_cita_by_similarity +
        stats.artigo_by_similarity +
        stats.cross_type_by_similarity
    )

    logger.info(
        f"Embedding-based inference complete: {stats.total_inferred} RELATED_TO candidates created "
        f"(decisao={stats.decisao_cita_by_similarity}, "
        f"sumula={stats.sumula_cita_by_similarity}, "
        f"doutrina={stats.doutrina_cita_by_similarity}, "
        f"artigo={stats.artigo_by_similarity}, "
        f"cross_type={stats.cross_type_by_similarity}, "
        f"l3_handoff={len(stats.candidates_for_l3)})"
    )

    return stats
