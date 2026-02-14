"""
Fase 1: Inferência estrutural determinística de relacionamentos.

Este módulo implementa regras lógicas para descobrir relações implícitas
baseadas na estrutura do grafo, sem necessidade de LLM ou embeddings.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class LinkInferenceStats:
    """Estatísticas de inferência de links."""
    transitive_remete_a: int = 0
    transitive_cita: int = 0
    co_citation_cita: int = 0
    parent_inheritance_remete_a: int = 0
    symmetric_cita: int = 0
    jurisprudence_cluster: int = 0
    total_inferred: int = 0


def infer_transitive_remete_a(
    session,
    max_depth: int = 2,
    min_confidence: float = 0.6,
) -> int:
    """
    Fechamento transitivo para REMETE_A: se A->B e B->C, inferir A->C.

    Args:
        max_depth: profundidade máxima da transitividade (2 = A->B->C)
        min_confidence: confiança mínima para criar aresta (reduz com depth)

    Returns:
        Número de links criados
    """
    created = 0
    confidence = min_confidence

    try:
        # Depth 2: A -REMETE_A-> B -REMETE_A-> C
        result = session.run(
            """
            MATCH (a:Artigo)-[:REMETE_A]->(b:Artigo)-[:REMETE_A]->(c:Artigo)
            WHERE a <> c
              AND NOT (a)-[:REMETE_A]-(c)
              AND NOT EXISTS((a)-[:REMETE_A {derived: true}]->(c))
            WITH a, c, count(DISTINCT b) AS bridge_count
            WHERE bridge_count >= 1
            CREATE (a)-[r:REMETE_A]->(c)
            SET r.source = 'transitive_closure',
                r.derived = true,
                r.confidence = $confidence,
                r.bridge_count = bridge_count,
                r.created_at = datetime(),
                r.dimension = 'remissiva'
            RETURN count(r) AS created
            """,
            confidence=confidence
        ).single()

        created = int(result["created"] or 0) if result else 0

        if created > 0:
            logger.info(f"Transitive REMETE_A: created {created} inferred links")

    except Exception as e:
        logger.warning(f"Transitive REMETE_A inference failed: {e}")

    return created


def infer_transitive_cita(
    session,
    min_confidence: float = 0.5,
) -> int:
    """
    Fechamento transitivo para CITA: se Decisão A cita B, e B cita C, inferir A->C.

    Útil para descobrir precedentes indiretos.
    """
    created = 0

    try:
        result = session.run(
            """
            MATCH (a:Decisao)-[:CITA]->(b:Decisao)-[:CITA]->(c:Decisao)
            WHERE a <> c
              AND NOT (a)-[:CITA]-(c)
              AND NOT EXISTS((a)-[:CITA {derived: true}]->(c))
            WITH a, c, count(DISTINCT b) AS bridge_count
            WHERE bridge_count >= 1
            CREATE (a)-[r:CITA]->(c)
            SET r.source = 'transitive_precedent',
                r.derived = true,
                r.confidence = $confidence,
                r.bridge_count = bridge_count,
                r.created_at = datetime(),
                r.dimension = 'horizontal'
            RETURN count(r) AS created
            """,
            confidence=min_confidence
        ).single()

        created = int(result["created"] or 0) if result else 0

        if created > 0:
            logger.info(f"Transitive CITA: created {created} inferred links")

    except Exception as e:
        logger.warning(f"Transitive CITA inference failed: {e}")

    return created


def infer_co_citation_links(
    session,
    min_shared_artigos: int = 3,
    confidence: float = 0.65,
) -> int:
    """
    Co-citação implícita: se Decisão A e B interpretam os mesmos artigos,
    inferir que A e B estão relacionadas.

    Args:
        min_shared_artigos: mínimo de artigos compartilhados para inferir link
        confidence: confiança da aresta inferida
    """
    created = 0

    try:
        result = session.run(
            """
            MATCH (d1:Decisao)-[:INTERPRETA]->(a:Artigo)<-[:INTERPRETA]-(d2:Decisao)
            WHERE d1 <> d2
              AND id(d1) < id(d2)  // Evita duplicatas
              AND NOT (d1)-[:CITA]-(d2)
              AND NOT EXISTS((d1)-[:CITA {derived: true}]-(d2))
            WITH d1, d2, collect(DISTINCT a.name) AS shared_artigos
            WHERE size(shared_artigos) >= $min_shared
            CREATE (d1)-[r:CITA]->(d2)
            SET r.source = 'co_citation',
                r.derived = true,
                r.confidence = $confidence,
                r.shared_entities = size(shared_artigos),
                r.shared_artigos = shared_artigos[0..5],  // Top 5 para metadata
                r.created_at = datetime(),
                r.dimension = 'horizontal'
            RETURN count(r) AS created
            """,
            min_shared=min_shared_artigos,
            confidence=confidence
        ).single()

        created = int(result["created"] or 0) if result else 0

        if created > 0:
            logger.info(f"Co-citation: created {created} inferred CITA links")

    except Exception as e:
        logger.warning(f"Co-citation inference failed: {e}")

    return created


def infer_parent_inheritance(
    session,
    confidence: float = 0.75,
) -> int:
    """
    Herança hierárquica: se inciso não tem REMETE_A mas artigo-pai tem,
    inferir que o inciso herda a relação.

    Exemplo: Art. 135, III CTN herda as remissões do Art. 135 CTN.
    """
    created = 0

    try:
        result = session.run(
            """
            MATCH (filho:Artigo)-[:SUBDISPOSITIVO_DE]->(pai:Artigo)
                  -[:REMETE_A]->(alvo:Artigo)
            WHERE NOT (filho)-[:REMETE_A]->(alvo)
              AND NOT EXISTS((filho)-[:REMETE_A {derived: true}]->(alvo))
              AND filho <> alvo
            CREATE (filho)-[r:REMETE_A]->(alvo)
            SET r.source = 'parent_inheritance',
                r.derived = true,
                r.confidence = $confidence,
                r.inherited_from = pai.name,
                r.created_at = datetime(),
                r.dimension = 'remissiva'
            RETURN count(r) AS created
            """,
            confidence=confidence
        ).single()

        created = int(result["created"] or 0) if result else 0

        if created > 0:
            logger.info(f"Parent inheritance: created {created} inferred REMETE_A links")

    except Exception as e:
        logger.warning(f"Parent inheritance inference failed: {e}")

    return created


def infer_symmetric_cita(
    session,
    confidence: float = 0.7,
) -> int:
    """
    Simetria implícita em CITA: se A cita B explicitamente, e B cita C explicitamente,
    e A também interpreta C, inferir que A deveria citar C.

    Caso de uso: decisões que aplicam mesma súmula tendem a se citar.
    """
    created = 0

    try:
        result = session.run(
            """
            MATCH (d1:Decisao)-[:APLICA_SUMULA]->(s:Sumula)<-[:APLICA_SUMULA]-(d2:Decisao)
            WHERE d1 <> d2
              AND id(d1) < id(d2)  // Evita duplicatas
              AND NOT (d1)-[:CITA]-(d2)
              AND NOT EXISTS((d1)-[:CITA {derived: true}]-(d2))
            WITH d1, d2, collect(s.name) AS shared_sumulas
            WHERE size(shared_sumulas) >= 1
            CREATE (d1)-[r:CITA]->(d2)
            SET r.source = 'symmetric_sumula_application',
                r.derived = true,
                r.confidence = $confidence,
                r.shared_sumulas = shared_sumulas,
                r.created_at = datetime(),
                r.dimension = 'horizontal'
            RETURN count(r) AS created
            """,
            confidence=confidence
        ).single()

        created = int(result["created"] or 0) if result else 0

        if created > 0:
            logger.info(f"Symmetric CITA: created {created} inferred links via shared súmulas")

    except Exception as e:
        logger.warning(f"Symmetric CITA inference failed: {e}")

    return created


def infer_jurisprudence_clusters(
    session,
    min_cluster_size: int = 3,
    confidence: float = 0.6,
) -> int:
    """
    Clustering de jurisprudência: se múltiplas decisões fixam teses sobre o mesmo tema,
    inferir que essas decisões formam um cluster e devem estar conectadas.
    """
    created = 0

    try:
        result = session.run(
            """
            MATCH (d:Decisao)-[:JULGA_TEMA]->(tema:Tema)
            WITH tema, collect(d) AS decisoes
            WHERE size(decisoes) >= $min_size
            UNWIND decisoes AS d1
            UNWIND decisoes AS d2
            WITH d1, d2, tema
            WHERE d1 <> d2
              AND id(d1) < id(d2)  // Evita duplicatas
              AND NOT (d1)-[:CITA]-(d2)
              AND NOT EXISTS((d1)-[:CITA {derived: true}]-(d2))
            CREATE (d1)-[r:CITA]->(d2)
            SET r.source = 'jurisprudence_cluster',
                r.derived = true,
                r.confidence = $confidence,
                r.cluster_tema = tema.name,
                r.created_at = datetime(),
                r.dimension = 'horizontal'
            RETURN count(r) AS created
            """,
            min_size=min_cluster_size,
            confidence=confidence
        ).single()

        created = int(result["created"] or 0) if result else 0

        if created > 0:
            logger.info(f"Jurisprudence clusters: created {created} inferred links")

    except Exception as e:
        logger.warning(f"Jurisprudence clustering inference failed: {e}")

    return created


def run_structural_inference(
    session,
    enable_transitive: bool = True,
    enable_co_citation: bool = True,
    enable_inheritance: bool = True,
    enable_symmetric: bool = True,
    enable_clustering: bool = True,
) -> LinkInferenceStats:
    """
    Executa todas as regras de inferência estrutural.

    Args:
        session: Neo4j session
        enable_*: flags para habilitar/desabilitar cada tipo de inferência

    Returns:
        Estatísticas de links criados
    """
    stats = LinkInferenceStats()

    logger.info("Starting structural link inference (Phase 1)...")

    if enable_transitive:
        stats.transitive_remete_a = infer_transitive_remete_a(session)
        stats.transitive_cita = infer_transitive_cita(session)

    if enable_co_citation:
        stats.co_citation_cita = infer_co_citation_links(session)

    if enable_inheritance:
        stats.parent_inheritance_remete_a = infer_parent_inheritance(session)

    if enable_symmetric:
        stats.symmetric_cita = infer_symmetric_cita(session)

    if enable_clustering:
        stats.jurisprudence_cluster = infer_jurisprudence_clusters(session)

    stats.total_inferred = (
        stats.transitive_remete_a +
        stats.transitive_cita +
        stats.co_citation_cita +
        stats.parent_inheritance_remete_a +
        stats.symmetric_cita +
        stats.jurisprudence_cluster
    )

    logger.info(
        f"Structural inference complete: {stats.total_inferred} total links created "
        f"(transitive_remete={stats.transitive_remete_a}, "
        f"transitive_cita={stats.transitive_cita}, "
        f"co_citation={stats.co_citation_cita}, "
        f"inheritance={stats.parent_inheritance_remete_a}, "
        f"symmetric={stats.symmetric_cita}, "
        f"clustering={stats.jurisprudence_cluster})"
    )

    return stats
