"""
Chain Analysis for the legal Neo4j knowledge graph.

Ported from the standalone `ingest_v2.py` analyze_chains() function.
Runs 6 Cypher queries to measure 4-5 hop chains and component counts.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


@dataclass
class ChainAnalysisResult:
    """Results from chain analysis queries."""

    chains: Dict[str, int] = field(default_factory=dict)
    component_counts: Dict[str, int] = field(default_factory=dict)
    total_chains: int = 0
    errors: List[str] = field(default_factory=list)


# 6 chain queries identical to ingest_v2.py analyze_chains()
CHAIN_QUERIES: Dict[str, str] = {
    "4h_art_art_decisao_tese": (
        "MATCH (a1:Artigo)-[:REMETE_A]->(a2:Artigo)"
        "<-[:INTERPRETA]-(d:Decisao)-[:FIXA_TESE]->(t:Tese) "
        "WHERE a1 <> a2 "
        "RETURN count(*) AS c"
    ),
    "4h_decisao_sumula_art_art": (
        "MATCH (d:Decisao)-[:APLICA_SUMULA]->(su:Sumula)"
        "-[:FUNDAMENTA]->(a1:Artigo)-[:REMETE_A]->(a2:Artigo) "
        "WHERE a1 <> a2 "
        "RETURN count(*) AS c"
    ),
    "4h_decisao_decisao_art_lei": (
        "MATCH (d1:Decisao)-[:CITA]->(d2:Decisao)"
        "-[:INTERPRETA]->(a:Artigo)-[:PERTENCE_A]->(l:Lei) "
        "RETURN count(*) AS c"
    ),
    "4h_sumula_art_decisao_tese": (
        "MATCH (su:Sumula)-[:FUNDAMENTA|INTERPRETA]->(a:Artigo)"
        "<-[:INTERPRETA]-(d:Decisao)-[:FIXA_TESE]->(t:Tese) "
        "RETURN count(*) AS c"
    ),
    "5h_art_art_sumula_decisao_tese": (
        "MATCH (a1:Artigo)-[:REMETE_A]->(a2:Artigo)"
        "<-[:FUNDAMENTA|INTERPRETA]-(su:Sumula)"
        "<-[:APLICA_SUMULA]-(d:Decisao)-[:FIXA_TESE]->(t:Tese) "
        "WHERE a1 <> a2 "
        "RETURN count(*) AS c"
    ),
    "5h_dec_dec_art_art_lei": (
        "MATCH (d1:Decisao)-[:CITA]->(d2:Decisao)"
        "-[:INTERPRETA]->(a1:Artigo)-[:REMETE_A]->(a2:Artigo)"
        "-[:PERTENCE_A]->(l:Lei) "
        "WHERE a1 <> a2 "
        "RETURN count(*) AS c"
    ),
}

# Component count queries (node + relationship counts)
COMPONENT_QUERIES: Dict[str, str] = {
    "Artigo": "MATCH (n:Artigo) RETURN count(n) AS c",
    "Decisao": "MATCH (n:Decisao) RETURN count(n) AS c",
    "Sumula": "MATCH (n:Sumula) RETURN count(n) AS c",
    "Tese": "MATCH (n:Tese) RETURN count(n) AS c",
    "Tema": "MATCH (n:Tema) RETURN count(n) AS c",
    "Tribunal": "MATCH (n:Tribunal) RETURN count(n) AS c",
    "Lei": "MATCH (n:Lei) RETURN count(n) AS c",
    "REMETE_A": "MATCH (:Artigo)-[r:REMETE_A]->(:Artigo) RETURN count(r) AS c",
    "INTERPRETA_Dec_Art": "MATCH (:Decisao)-[r:INTERPRETA]->(:Artigo) RETURN count(r) AS c",
    "FIXA_TESE": "MATCH (:Decisao)-[r:FIXA_TESE]->(:Tese) RETURN count(r) AS c",
    "JULGA_TEMA": "MATCH (:Decisao)-[r:JULGA_TEMA]->(:Tema) RETURN count(r) AS c",
    "APLICA_SUMULA": "MATCH (:Decisao)-[r:APLICA_SUMULA]->(:Sumula) RETURN count(r) AS c",
    "FUNDAMENTA_Sum_Art": "MATCH (:Sumula)-[r:FUNDAMENTA]->(:Artigo) RETURN count(r) AS c",
    "CITA_Dec_Dec": "MATCH (:Decisao)-[r:CITA]->(:Decisao) RETURN count(r) AS c",
    "CONFIRMA_Dec_Dec": "MATCH (:Decisao)-[r:CONFIRMA]->(:Decisao) RETURN count(r) AS c",
    "SUPERA_Dec_Dec": "MATCH (:Decisao)-[r:SUPERA]->(:Decisao) RETURN count(r) AS c",
    "PERTENCE_A": "MATCH (:Artigo)-[r:PERTENCE_A]->(:Lei) RETURN count(r) AS c",
}


def analyze_chains(driver, *, database: str) -> ChainAnalysisResult:
    """
    Run chain analysis queries against the Neo4j knowledge graph.

    Returns a ChainAnalysisResult with chain counts and component counts.
    """
    result = ChainAnalysisResult()

    with driver.session(database=database) as session:
        # Run chain queries
        for name, query in CHAIN_QUERIES.items():
            try:
                r = session.run(query).single()
                count = int(r["c"] or 0) if r else 0
                result.chains[name] = count
                result.total_chains += count
            except Exception as e:
                result.errors.append(f"chain_{name}:{e}")
                result.chains[name] = 0

        # Run component count queries
        for name, query in COMPONENT_QUERIES.items():
            try:
                r = session.run(query).single()
                result.component_counts[name] = int(r["c"] or 0) if r else 0
            except Exception as e:
                result.errors.append(f"component_{name}:{e}")
                result.component_counts[name] = 0

    logger.info(
        "Chain analysis: total_chains=%d chains=%s errors=%d",
        result.total_chains,
        {k: v for k, v in result.chains.items() if v > 0},
        len(result.errors),
    )
    return result
