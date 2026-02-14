"""
Graph Ask Service — Consultas ao grafo via operações tipadas.

Este serviço implementa a abordagem segura de NL → Intent → Template Cypher,
evitando Cypher arbitrário e garantindo segurança multi-tenant.

Operações suportadas:
- path: Caminho mais curto entre duas entidades
- neighbors: Vizinhos semânticos de uma entidade
- cooccurrence: Co-ocorrência entre entidades em chunks
- search: Busca de entidades por nome/tipo
- count: Contagem de entidades/documentos
- ranking: Ranking de entidades por PageRank (tenant-scoped)
- legal_chain: Cadeias semânticas entre dispositivos legais (multi-hop)
- precedent_network: Rede de precedentes que influenciam uma decisão
- judge_decisions: Decisões relacionadas ao mesmo juiz/ministro
- fraud_signals: Sinais de risco em conexões órgão/empresa/processo
- process_network: Rede processual conectada a um processo
- process_timeline: Timeline processual (prazos/eventos/documentos)
- related_entities: Entidades conectadas por arestas diretas do grafo
- entity_stats: Estatísticas gerais do grafo (contagens por tipo, relações)

Todas as operações aplicam filtros de tenant_id/scope automaticamente.
"""

from __future__ import annotations

import os
import re
import asyncio
import time
import json
import hmac
import hashlib
import base64
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Union

from loguru import logger


class GraphOperation(str, Enum):
    """Operações suportadas pelo Graph Ask."""
    PATH = "path"
    NEIGHBORS = "neighbors"
    COOCCURRENCE = "cooccurrence"
    SEARCH = "search"
    COUNT = "count"
    TEXT2CYPHER = "text2cypher"
    RANKING = "ranking"
    LEGAL_CHAIN = "legal_chain"
    PRECEDENT_NETWORK = "precedent_network"
    JUDGE_DECISIONS = "judge_decisions"
    FRAUD_SIGNALS = "fraud_signals"
    PROCESS_NETWORK = "process_network"
    PROCESS_TIMELINE = "process_timeline"
    LEGAL_DIAGNOSTICS = "legal_diagnostics"
    LINK_ENTITIES = "link_entities"
    DISCOVER_HUBS = "discover_hubs"
    RELATED_ENTITIES = "related_entities"
    ENTITY_STATS = "entity_stats"
    RECOMPUTE_CO_MENCIONA = "recompute_co_menciona"
    # GDS (Graph Data Science) operations
    BETWEENNESS_CENTRALITY = "betweenness_centrality"
    COMMUNITY_DETECTION = "community_detection"
    NODE_SIMILARITY = "node_similarity"
    PAGERANK_PERSONALIZED = "pagerank_personalized"
    WEAKLY_CONNECTED_COMPONENTS = "weakly_connected_components"
    SHORTEST_PATH_WEIGHTED = "shortest_path_weighted"
    TRIANGLE_COUNT = "triangle_count"
    DEGREE_CENTRALITY = "degree_centrality"
    # GDS Fase 1: Prioridade Máxima
    CLOSENESS_CENTRALITY = "closeness_centrality"
    EIGENVECTOR_CENTRALITY = "eigenvector_centrality"
    LEIDEN = "leiden"
    K_CORE_DECOMPOSITION = "k_core_decomposition"
    KNN = "knn"
    # GDS Fase 2: Casos Específicos
    BRIDGES = "bridges"
    ARTICULATION_POINTS = "articulation_points"
    STRONGLY_CONNECTED_COMPONENTS = "strongly_connected_components"
    YENS_K_SHORTEST_PATHS = "yens_k_shortest_paths"
    # GDS Fase 3: Avançado
    ADAMIC_ADAR = "adamic_adar"
    NODE2VEC = "node2vec"
    ALL_PAIRS_SHORTEST_PATH = "all_pairs_shortest_path"
    HARMONIC_CENTRALITY = "harmonic_centrality"


@dataclass
class GraphAskResult:
    """Resultado de uma consulta ao grafo."""
    success: bool
    operation: str
    results: List[Dict[str, Any]]
    result_count: int
    execution_time_ms: int
    cypher_template: Optional[str] = None  # Para debug (admin only)
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        d = {
            "success": self.success,
            "operation": self.operation,
            "results": self.results,
            "result_count": self.result_count,
            "execution_time_ms": self.execution_time_ms,
        }
        if self.error:
            d["error"] = self.error
        if self.cypher_template:
            d["cypher_template"] = self.cypher_template
        if self.metadata:
            d["metadata"] = self.metadata
        return d


# =============================================================================
# LINK_ENTITIES PRE-FLIGHT TOKEN (HMAC) — "cryptographically binding" confirm
# =============================================================================


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_decode(raw: str) -> bytes:
    raw = (raw or "").strip()
    if not raw:
        return b""
    pad = "=" * ((4 - (len(raw) % 4)) % 4)
    return base64.urlsafe_b64decode((raw + pad).encode("ascii"))


def _link_entities_token_secret() -> bytes:
    # Prefer a dedicated secret; fall back to app secrets in dev.
    secret = (
        os.getenv("LINK_ENTITIES_TOKEN_SECRET")
        or os.getenv("JWT_SECRET_KEY")
        or os.getenv("SECRET_KEY")
        or ""
    ).strip()
    # If secrets are not configured, the app is already misconfigured; still avoid crashing.
    if not secret:
        secret = "dev_insecure_secret_change_me"
    return secret.encode("utf-8")


def _sign_preflight(payload_b64: str) -> str:
    mac = hmac.new(_link_entities_token_secret(), payload_b64.encode("ascii"), hashlib.sha256).digest()
    return _b64url_encode(mac)


def _make_preflight_token(payload: Dict[str, Any]) -> str:
    blob = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_b64 = _b64url_encode(blob)
    sig_b64 = _sign_preflight(payload_b64)
    return f"{payload_b64}.{sig_b64}"


def _verify_preflight_token(token: str) -> Dict[str, Any]:
    token = (token or "").strip()
    if not token or "." not in token:
        raise ValueError("preflight_token inválido")
    payload_b64, sig_b64 = token.split(".", 1)
    expected = _sign_preflight(payload_b64)
    if not hmac.compare_digest(expected, sig_b64):
        raise ValueError("preflight_token com assinatura inválida")
    payload_raw = _b64url_decode(payload_b64)
    if not payload_raw:
        raise ValueError("preflight_token vazio")
    payload = json.loads(payload_raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("preflight_token malformado")
    return payload


# =============================================================================
# CYPHER TEMPLATES — Seguros e com placeholders para tenant_id
# =============================================================================

_MAX_HOPS_TOKEN = "__MAX_HOPS__"
_REL_TYPES_TOKEN = "__REL_TYPES__"

_DEFAULT_LEGAL_CHAIN_RELATION_TYPES: tuple[str, ...] = (
    "RELATED_TO",
    "CITA",
    "CITES",
    "APLICA",
    "FUNDAMENTA",
    "INTERPRETA",
    "PERTENCE_A",
    "REMETE_A",
    "CO_MENCIONA",
    "COMPLEMENTA",
    "EXCEPCIONA",
    "REGULAMENTA",
    "ESPECIALIZA",
    "PROFERIDA_POR",
    "FIXA_TESE",
    "JULGA_TEMA",
    "VINCULA",
    "CONFIRMA",
    "SUPERA",
    "DISTINGUE",
    "CANCELA",
    "SUBSTITUI",
    "REVOGA",
    "ALTERA",
)


def _build_allowed_relationship_labels() -> Set[str]:
    labels = set(_DEFAULT_LEGAL_CHAIN_RELATION_TYPES)
    labels.update({"MENTIONS", "SUPPORTS", "OPPOSES", "EVIDENCES", "ARGUES", "RAISES", "BELONGS_TO"})
    try:
        from app.services.rag.core.kg_builder.legal_schema import LEGAL_RELATIONSHIP_TYPES

        for rel in LEGAL_RELATIONSHIP_TYPES:
            label = str(rel.get("label", "")).strip().upper()
            if label and re.fullmatch(r"[A-Z][A-Z0-9_]{0,40}", label):
                labels.add(label)
    except Exception:
        pass
    return labels


_ALLOWED_RELATIONSHIP_LABELS = _build_allowed_relationship_labels()

_PATH_QUERY_TEMPLATE = f"""
    MATCH (source:Entity {{entity_id: $source_id}})
    MATCH (target:Entity {{entity_id: $target_id}})
    MATCH path = shortestPath((source)-[:MENTIONS|RELATED_TO|ASSERTS|REFERS_TO*1..{_MAX_HOPS_TOKEN}]-(target))
    WHERE all(n IN nodes(path) WHERE NOT n:Chunk OR exists {{
        MATCH (d:Document)-[:HAS_CHUNK]->(n)
        WHERE (d.tenant_id = $tenant_id OR ($include_global = true AND d.scope = 'global'))
          AND (d.sigilo IS NULL OR d.sigilo = false)
          AND ($case_id IS NOT NULL OR d.scope <> 'local')
          AND ($scope IS NULL OR d.scope = $scope)
          AND ($case_id IS NULL OR d.case_id = $case_id)
    }})
    RETURN
        [n IN nodes(path) | coalesce(n.name, n.entity_id, n.chunk_uid, n.doc_hash)] AS path,
        [n IN nodes(path) | coalesce(n.entity_id, n.chunk_uid, n.doc_hash)] AS path_ids,
        [r IN relationships(path) | type(r)] AS relationships,
        length(path) AS hops
    LIMIT $limit
"""

CYPHER_TEMPLATES = {
    # -------------------------------------------------------------------------
    # PATH: Caminho mais curto entre duas entidades
    # -------------------------------------------------------------------------
    # NOTE: relationship length can't be parameterized in Cypher; we sanitize and inject it.
    "path": _PATH_QUERY_TEMPLATE,

    # -------------------------------------------------------------------------
    # NEIGHBORS: Vizinhos semânticos (via co-ocorrência em chunks)
    # -------------------------------------------------------------------------
    "neighbors": """
        MATCH (e:Entity {entity_id: $entity_id})<-[:MENTIONS]-(c:Chunk)-[:MENTIONS]->(neighbor:Entity)
        MATCH (d:Document)-[:HAS_CHUNK]->(c)
        WHERE neighbor.entity_id <> $entity_id
          AND (d.tenant_id = $tenant_id OR ($include_global = true AND d.scope = 'global'))
          AND (d.sigilo IS NULL OR d.sigilo = false)
          AND ($case_id IS NOT NULL OR d.scope <> 'local')
          AND ($scope IS NULL OR d.scope = $scope)
          AND ($case_id IS NULL OR d.case_id = $case_id)
        OPTIONAL MATCH (neighbor)-[:HAS_TENANT_METRIC]->(metric:TenantEntityMetric {tenant_id: $tenant_id})
        WITH neighbor, metric, count(DISTINCT c) AS co_occurrences,
             collect(DISTINCT left(c.text_preview, 150))[0..3] AS sample_contexts
        RETURN
            neighbor.entity_id AS entity_id,
            neighbor.name AS name,
            neighbor.entity_type AS type,
            co_occurrences,
            coalesce(metric.pagerank_score, 0.0) AS pagerank_score,
            sample_contexts
        ORDER BY co_occurrences DESC
        LIMIT $limit
    """,

    # -------------------------------------------------------------------------
    # COOCCURRENCE: Co-ocorrência entre duas entidades específicas
    # -------------------------------------------------------------------------
    "cooccurrence": """
        MATCH (e1:Entity {entity_id: $entity1_id})<-[:MENTIONS]-(c:Chunk)-[:MENTIONS]->(e2:Entity {entity_id: $entity2_id})
        MATCH (d:Document)-[:HAS_CHUNK]->(c)
        WHERE (d.tenant_id = $tenant_id OR ($include_global = true AND d.scope = 'global'))
          AND (d.sigilo IS NULL OR d.sigilo = false)
          AND ($case_id IS NOT NULL OR d.scope <> 'local')
          AND ($scope IS NULL OR d.scope = $scope)
          AND ($case_id IS NULL OR d.case_id = $case_id)
        WITH c, d, e1, e2
        RETURN
            e1.name AS entity1_name,
            e2.name AS entity2_name,
            count(DISTINCT c) AS co_occurrence_count,
            collect(DISTINCT d.title)[0..5] AS documents,
            collect(DISTINCT left(c.text_preview, 200))[0..3] AS sample_contexts
        LIMIT 1
    """,

    # -------------------------------------------------------------------------
    # SEARCH: Busca entidades por nome (com filtro de tipo opcional)
    # -------------------------------------------------------------------------
    "search": """
        MATCH (e:Entity)
        WHERE (toLower(e.name) CONTAINS toLower($query) OR toLower(e.normalized) CONTAINS toLower($query))
          AND ($entity_type IS NULL OR e.entity_type = $entity_type)
        OPTIONAL MATCH (e)<-[:MENTIONS]-(c:Chunk)<-[:HAS_CHUNK]-(d:Document)
        WHERE (d.tenant_id = $tenant_id OR ($include_global = true AND d.scope = 'global'))
          AND (d.sigilo IS NULL OR d.sigilo = false)
          AND ($case_id IS NOT NULL OR d.scope <> 'local')
          AND ($scope IS NULL OR d.scope = $scope)
          AND ($case_id IS NULL OR d.case_id = $case_id)
        WITH e, count(DISTINCT c) AS mention_count
        WHERE mention_count > 0
        RETURN
            e.entity_id AS entity_id,
            e.name AS name,
            e.entity_type AS type,
            e.normalized AS normalized,
            mention_count
        ORDER BY mention_count DESC
        LIMIT $limit
    """,

    # -------------------------------------------------------------------------
    # RANKING: Entidades mais importantes por PageRank (requer GDS compute_pagerank)
    # -------------------------------------------------------------------------
    "ranking": """
        MATCH (e:Entity)-[:HAS_TENANT_METRIC]->(metric:TenantEntityMetric {tenant_id: $tenant_id})
        WHERE metric.pagerank_score IS NOT NULL AND metric.pagerank_score > 0
          AND ($entity_type IS NULL OR e.entity_type = $entity_type)
        OPTIONAL MATCH (e)<-[:MENTIONS]-(c:Chunk)<-[:HAS_CHUNK]-(d:Document)
        WHERE (d.tenant_id = $tenant_id OR ($include_global = true AND d.scope = 'global'))
          AND (d.sigilo IS NULL OR d.sigilo = false)
          AND ($case_id IS NOT NULL OR d.scope <> 'local')
          AND ($scope IS NULL OR d.scope = $scope)
          AND ($case_id IS NULL OR d.case_id = $case_id)
        WITH e, count(DISTINCT d) AS doc_count
        WHERE doc_count > 0
        RETURN
            e.entity_id AS entity_id,
            e.name AS name,
            e.entity_type AS type,
            metric.pagerank_score AS pagerank_score,
            doc_count
        ORDER BY metric.pagerank_score DESC
        LIMIT $limit
    """,

    # -------------------------------------------------------------------------
    # LEGAL_CHAIN: Cadeias semânticas entre dispositivos legais (multi-hop)
    # -------------------------------------------------------------------------
    "legal_chain": f"""
        MATCH (source:Entity {{entity_id: $source_id}})
        OPTIONAL MATCH (target:Entity {{entity_id: $target_id}})
        WITH source, target
        MATCH p = (source)-[rels:{_REL_TYPES_TOKEN}*1..{_MAX_HOPS_TOKEN}]-(dest:Entity)
        WHERE ($target_id IS NULL OR dest = target)
          AND ($include_candidates = true OR all(r IN rels WHERE coalesce(r.layer, 'verified') <> 'candidate'))
          AND all(n IN nodes(p) WHERE exists {{
            MATCH (d:Document)-[:HAS_CHUNK]->(:Chunk)-[:MENTIONS]->(n)
            WHERE (d.tenant_id = $tenant_id OR ($include_global = true AND d.scope = 'global'))
              AND (d.sigilo IS NULL OR d.sigilo = false)
              AND ($case_id IS NOT NULL OR d.scope <> 'local')
              AND ($scope IS NULL OR d.scope = $scope)
              AND ($case_id IS NULL OR d.case_id = $case_id)
          }})
        RETURN
            source.entity_id AS source_id,
            dest.entity_id AS target_id,
            [n IN nodes(p) | coalesce(n.name, n.entity_id)] AS chain,
            [n IN nodes(p) | n.entity_id] AS chain_ids,
            [r IN relationships(p) | type(r)] AS relation_types,
            [r IN relationships(p) | {{
                type: type(r),
                dimension: coalesce(r.dimension, null),
                evidence: left(coalesce(r.evidence, ''), 160)
            }}] AS relation_details,
            length(p) AS hops
        ORDER BY hops ASC
        LIMIT $limit
    """,

    # -------------------------------------------------------------------------
    # PRECEDENT_NETWORK: Rede de precedentes/citações de uma decisão
    # -------------------------------------------------------------------------
    "precedent_network": f"""
        MATCH (decision:Entity {{entity_id: $decision_id}})
        MATCH p = (precedent:Entity)-[:CITA|CITES|FUNDAMENTA|APLICA|INTERPRETA|RELATED_TO*1..{_MAX_HOPS_TOKEN}]->(decision)
        WHERE ($include_candidates = true OR all(r IN relationships(p) WHERE coalesce(r.layer, 'verified') <> 'candidate'))
          AND all(n IN nodes(p) WHERE exists {{
            MATCH (d:Document)-[:HAS_CHUNK]->(:Chunk)-[:MENTIONS]->(n)
            WHERE (d.tenant_id = $tenant_id OR ($include_global = true AND d.scope = 'global'))
              AND (d.sigilo IS NULL OR d.sigilo = false)
              AND ($case_id IS NOT NULL OR d.scope <> 'local')
              AND ($scope IS NULL OR d.scope = $scope)
              AND ($case_id IS NULL OR d.case_id = $case_id)
        }})
        WITH precedent, decision, p, length(p) AS hops
        OPTIONAL MATCH (precedent)<-[:MENTIONS]-(c:Chunk)<-[:HAS_CHUNK]-(d:Document)
        WHERE (d.tenant_id = $tenant_id OR ($include_global = true AND d.scope = 'global'))
          AND (d.sigilo IS NULL OR d.sigilo = false)
          AND ($case_id IS NOT NULL OR d.scope <> 'local')
          AND ($scope IS NULL OR d.scope = $scope)
          AND ($case_id IS NULL OR d.case_id = $case_id)
        RETURN
            precedent.entity_id AS precedent_id,
            precedent.name AS precedent_name,
            precedent.entity_type AS precedent_type,
            decision.entity_id AS decision_id,
            hops,
            [n IN nodes(p) | coalesce(n.name, n.entity_id)] AS influence_path,
            [r IN relationships(p) | type(r)] AS relation_types,
            [r IN relationships(p) | {{
                type: type(r),
                dimension: coalesce(r.dimension, null),
                evidence: left(coalesce(r.evidence, ''), 160)
            }}] AS relation_details,
            count(DISTINCT d) AS supporting_documents
        ORDER BY hops ASC, supporting_documents DESC
        LIMIT $limit
    """,

    # -------------------------------------------------------------------------
    # JUDGE_DECISIONS: Decisões do mesmo juiz/ministro em contexto similar
    # -------------------------------------------------------------------------
    "judge_decisions": """
        MATCH (judge:Entity)<-[:MENTIONS]-(c:Chunk)<-[:HAS_CHUNK]-(d:Document)
        WHERE toLower(judge.name) CONTAINS toLower($judge_query)
          AND (d.tenant_id = $tenant_id OR ($include_global = true AND d.scope = 'global'))
          AND (d.sigilo IS NULL OR d.sigilo = false)
          AND ($case_id IS NOT NULL OR d.scope <> 'local')
          AND ($scope IS NULL OR d.scope = $scope)
          AND ($case_id IS NULL OR d.case_id = $case_id)
        MATCH (d)-[:HAS_CHUNK]->(dc:Chunk)-[:MENTIONS]->(decision:Entity)
        WHERE decision.entity_id <> judge.entity_id
          AND ($decision_type IS NULL OR decision.entity_type = $decision_type)
          AND (
            decision.entity_type IN ['processo', 'acordao', 'jurisprudencia', 'decisao', 'tema', 'sumula']
            OR toLower(decision.name) CONTAINS 'acórdão'
            OR toLower(decision.name) CONTAINS 'decisão'
          )
        OPTIONAL MATCH (decision)-[r:CITA|CITES|FUNDAMENTA|APLICA|INTERPRETA|RELATED_TO]->(ref:Entity)
        WHERE ($include_candidates = true OR coalesce(r.layer, 'verified') <> 'candidate')
        RETURN
            judge.entity_id AS judge_id,
            judge.name AS judge_name,
            decision.entity_id AS decision_id,
            decision.name AS decision_name,
            decision.entity_type AS decision_type,
            count(DISTINCT d) AS supporting_documents,
            collect(DISTINCT ref.name)[0..6] AS related_references
        ORDER BY supporting_documents DESC
        LIMIT $limit
    """,

    # -------------------------------------------------------------------------
    # FRAUD_SIGNALS: Conexões suspeitas entre órgão, empresa, processo
    # -------------------------------------------------------------------------
    "fraud_signals": """
        MATCH (orgao:Entity)<-[:MENTIONS]-(c:Chunk)-[:MENTIONS]->(empresa:Entity)
        MATCH (d:Document)-[:HAS_CHUNK]->(c)
        WHERE orgao.entity_id <> empresa.entity_id
          AND (d.tenant_id = $tenant_id OR ($include_global = true AND d.scope = 'global'))
          AND (d.sigilo IS NULL OR d.sigilo = false)
          AND ($case_id IS NOT NULL OR d.scope <> 'local')
          AND ($scope IS NULL OR d.scope = $scope)
          AND ($case_id IS NULL OR d.case_id = $case_id)
          AND (
            toLower(orgao.entity_type) IN ['orgaopublico', 'orgao_publico', 'tribunal', 'actor', 'semanticentity']
            OR toLower(orgao.name) CONTAINS 'prefeitura'
            OR toLower(orgao.name) CONTAINS 'secretaria'
            OR toLower(orgao.name) CONTAINS 'tribunal'
          )
          AND (
            toLower(empresa.entity_type) IN ['empresa', 'actor', 'semanticentity']
            OR toLower(empresa.name) CONTAINS 'ltda'
            OR toLower(empresa.name) CONTAINS 's/a'
            OR toLower(empresa.name) CONTAINS 'me'
          )
        OPTIONAL MATCH (c)-[:MENTIONS]->(proc:Entity)
        WHERE toLower(proc.entity_type) IN ['processo', 'licitacao', 'contrato']
        WITH orgao, empresa, count(DISTINCT d) AS shared_documents,
             collect(DISTINCT proc.entity_id)[0..10] AS linked_processes
        WHERE shared_documents >= $min_shared_docs
        RETURN
            orgao.entity_id AS orgao_id,
            orgao.name AS orgao_name,
            empresa.entity_id AS empresa_id,
            empresa.name AS empresa_name,
            shared_documents,
            size(linked_processes) AS linked_process_count,
            linked_processes,
            (shared_documents * 1.0 + size(linked_processes) * 0.5) AS risk_score
        ORDER BY risk_score DESC, shared_documents DESC
        LIMIT $limit
    """,

    # -------------------------------------------------------------------------
    # PROCESS_NETWORK: Conexões multi-hop de um processo com outras entidades
    # -------------------------------------------------------------------------
    "process_network": f"""
        MATCH (root:Entity {{entity_id: $process_id}})
        MATCH p = (root)-[:RELATED_TO|CITA|CITES|APLICA|FUNDAMENTA|INTERPRETA|REVOGA|ALTERA*1..{_MAX_HOPS_TOKEN}]-(neighbor:Entity)
        WHERE ($include_candidates = true OR all(r IN relationships(p) WHERE coalesce(r.layer, 'verified') <> 'candidate'))
          AND all(n IN nodes(p) WHERE exists {{
            MATCH (d:Document)-[:HAS_CHUNK]->(:Chunk)-[:MENTIONS]->(n)
            WHERE (d.tenant_id = $tenant_id OR ($include_global = true AND d.scope = 'global'))
              AND (d.sigilo IS NULL OR d.sigilo = false)
              AND ($case_id IS NOT NULL OR d.scope <> 'local')
              AND ($scope IS NULL OR d.scope = $scope)
              AND ($case_id IS NULL OR d.case_id = $case_id)
        }})
        RETURN
            root.entity_id AS process_id,
            neighbor.entity_id AS neighbor_id,
            neighbor.name AS neighbor_name,
            neighbor.entity_type AS neighbor_type,
            [n IN nodes(p) | coalesce(n.name, n.entity_id)] AS path,
            [r IN relationships(p) | type(r)] AS relation_types,
            length(p) AS hops
        ORDER BY hops ASC
        LIMIT $limit
    """,

    # -------------------------------------------------------------------------
    # PROCESS_TIMELINE: Timeline documental/eventos de um processo
    # -------------------------------------------------------------------------
    "process_timeline": """
        MATCH (proc:Entity {entity_id: $process_id})<-[:MENTIONS]-(c:Chunk)<-[:HAS_CHUNK]-(d:Document)
        WHERE (d.tenant_id = $tenant_id OR ($include_global = true AND d.scope = 'global'))
          AND (d.sigilo IS NULL OR d.sigilo = false)
          AND ($case_id IS NOT NULL OR d.scope <> 'local')
          AND ($scope IS NULL OR d.scope = $scope)
          AND ($case_id IS NULL OR d.case_id = $case_id)
        OPTIONAL MATCH (c)-[:MENTIONS]->(related:Entity)
        WHERE related.entity_id <> $process_id
        WITH d, c, collect(DISTINCT {
            entity_id: related.entity_id,
            name: related.name,
            type: related.entity_type
        })[0..8] AS related_entities
        RETURN
            d.doc_hash AS doc_hash,
            coalesce(d.title, d.source, d.doc_hash) AS document,
            coalesce(d.decision_date, d.data_julgamento, d.published_at, d.created_at, d.ingested_at, d.timestamp, '') AS event_date,
            left(coalesce(c.text_preview, ''), 250) AS context,
            related_entities
        ORDER BY event_date DESC
        LIMIT $limit
    """,

    # -------------------------------------------------------------------------
    # COUNT: Contagem de entidades/documentos com filtros
    # -------------------------------------------------------------------------
    "count": """
        MATCH (e:Entity)
        WHERE ($entity_type IS NULL OR e.entity_type = $entity_type)
          AND ($query IS NULL OR toLower(e.name) CONTAINS toLower($query))
        OPTIONAL MATCH (e)<-[:MENTIONS]-(c:Chunk)<-[:HAS_CHUNK]-(d:Document)
        WHERE (d.tenant_id = $tenant_id OR ($include_global = true AND d.scope = 'global'))
          AND (d.sigilo IS NULL OR d.sigilo = false)
          AND ($case_id IS NOT NULL OR d.scope <> 'local')
          AND ($scope IS NULL OR d.scope = $scope)
          AND ($case_id IS NULL OR d.case_id = $case_id)
        WITH e, count(DISTINCT d) AS doc_count
        WHERE doc_count > 0
        RETURN
            count(DISTINCT e) AS entity_count,
            sum(doc_count) AS total_document_references
    """,

    # -------------------------------------------------------------------------
    # RELATED_ENTITIES: Entidades conectadas por arestas diretas do grafo
    # -------------------------------------------------------------------------
    "related_entities": """
        MATCH (e:Entity {entity_id: $entity_id})-[r]->(target:Entity)
        WHERE type(r) <> 'FROM_CHUNK' AND type(r) <> 'FROM_DOCUMENT' AND type(r) <> 'NEXT_CHUNK'
          AND type(r) <> 'MENTIONS' AND type(r) <> 'HAS_CHUNK' AND type(r) <> 'HAS_TENANT_METRIC'
          AND ($relation_filter IS NULL OR type(r) = $relation_filter)
        OPTIONAL MATCH (target)<-[:MENTIONS]-(c:Chunk)<-[:HAS_CHUNK]-(d:Document)
        WHERE (d.tenant_id = $tenant_id OR ($include_global = true AND d.scope = 'global'))
          AND (d.sigilo IS NULL OR d.sigilo = false)
          AND ($case_id IS NOT NULL OR d.scope <> 'local')
          AND ($scope IS NULL OR d.scope = $scope)
          AND ($case_id IS NULL OR d.case_id = $case_id)
        WITH target, r, count(DISTINCT d) AS doc_count
        RETURN
            target.entity_id AS entity_id,
            target.name AS name,
            target.entity_type AS type,
            type(r) AS relation_type,
            'outgoing' AS direction,
            coalesce(r.dimension, null) AS dimension,
            left(coalesce(r.evidence, ''), 200) AS evidence,
            coalesce(r.layer, 'unknown') AS layer,
            doc_count
        ORDER BY doc_count DESC
        LIMIT $limit

        UNION ALL

        MATCH (source:Entity)-[r]->(e:Entity {entity_id: $entity_id})
        WHERE type(r) <> 'FROM_CHUNK' AND type(r) <> 'FROM_DOCUMENT' AND type(r) <> 'NEXT_CHUNK'
          AND type(r) <> 'MENTIONS' AND type(r) <> 'HAS_CHUNK' AND type(r) <> 'HAS_TENANT_METRIC'
          AND ($relation_filter IS NULL OR type(r) = $relation_filter)
        OPTIONAL MATCH (source)<-[:MENTIONS]-(c:Chunk)<-[:HAS_CHUNK]-(d:Document)
        WHERE (d.tenant_id = $tenant_id OR ($include_global = true AND d.scope = 'global'))
          AND (d.sigilo IS NULL OR d.sigilo = false)
          AND ($case_id IS NOT NULL OR d.scope <> 'local')
          AND ($scope IS NULL OR d.scope = $scope)
          AND ($case_id IS NULL OR d.case_id = $case_id)
        WITH source, r, count(DISTINCT d) AS doc_count
        RETURN
            source.entity_id AS entity_id,
            source.name AS name,
            source.entity_type AS type,
            type(r) AS relation_type,
            'incoming' AS direction,
            coalesce(r.dimension, null) AS dimension,
            left(coalesce(r.evidence, ''), 200) AS evidence,
            coalesce(r.layer, 'unknown') AS layer,
            doc_count
        ORDER BY doc_count DESC
        LIMIT $limit
    """,
}


class GraphAskService:
    """
    Serviço para consultas seguras ao grafo Neo4j.

    Usa templates Cypher pré-definidos com parâmetros tipados,
    garantindo segurança multi-tenant e evitando injection.
    """

    def __init__(self):
        """Inicializa o serviço."""
        self._neo4j = None
        self._gds_available = None  # Lazy check

    async def _get_neo4j(self):
        """Obtém instância do Neo4j service (lazy loading)."""
        if self._neo4j is None:
            try:
                from app.services.rag.core.neo4j_mvp import get_neo4j_mvp
                self._neo4j = get_neo4j_mvp()
            except Exception as e:
                logger.error(f"Failed to get Neo4j service: {e}")
                raise RuntimeError("Neo4j service not available")
        return self._neo4j

    async def _check_gds_available(self) -> bool:
        """Verifica se o plugin GDS está instalado e habilitado."""
        if self._gds_available is not None:
            return self._gds_available

        # Check env var first
        if not _env_bool("NEO4J_GDS_ENABLED", False):
            self._gds_available = False
            return False

        try:
            neo4j = await self._get_neo4j()
            # Try to call gds.version() to verify GDS is installed
            result = await neo4j.execute_cypher(
                "RETURN gds.version() AS version",
                {},
                tenant_id="system",  # System query, no tenant filter
            )
            if result and len(result) > 0 and "version" in result[0]:
                self._gds_available = True
                logger.info(f"GDS plugin detected: version {result[0]['version']}")
                return True
            self._gds_available = False
            return False
        except Exception as e:
            logger.warning(f"GDS check failed: {e}. Set NEO4J_GDS_ENABLED=true if installed.")
            self._gds_available = False
            return False

    async def ask(
        self,
        operation: Union[str, GraphOperation],
        params: Dict[str, Any],
        tenant_id: str,
        scope: Optional[str] = None,
        case_id: Optional[str] = None,
        include_global: bool = True,
        show_template: bool = False,
        timeout_ms: int = 5000,
    ) -> GraphAskResult:
        """
        Executa uma consulta tipada ao grafo.

        Args:
            operation: Operação a executar (path, neighbors, cooccurrence, search, count, ranking, legal_chain, ...)
            params: Parâmetros específicos da operação
            tenant_id: ID do tenant para filtro de segurança
            scope: Escopo opcional (global, private, group, local)
            case_id: ID do caso opcional
            show_template: Se True, inclui template Cypher no resultado (admin only)
            timeout_ms: Timeout em milissegundos

        Returns:
            GraphAskResult com resultados ou erro
        """
        start_time = time.time()

        normalized_scope = (scope or "").strip().lower() or None
        if normalized_scope == "group":
            return GraphAskResult(
                success=False,
                operation=str(operation),
                results=[],
                result_count=0,
                execution_time_ms=0,
                error="Escopo 'group' não suportado nesta versão do GraphAsk (evita bypass de RBAC).",
            )
        if normalized_scope == "local" and not case_id:
            return GraphAskResult(
                success=False,
                operation=str(operation),
                results=[],
                result_count=0,
                execution_time_ms=0,
                error="Escopo 'local' requer case_id.",
            )

        # Normalizar operação
        if isinstance(operation, str):
            try:
                operation = GraphOperation(operation.lower())
            except ValueError:
                return GraphAskResult(
                    success=False,
                    operation=operation,
                    results=[],
                    result_count=0,
                    execution_time_ms=0,
                    error=f"Operação inválida: {operation}. Válidas: {[o.value for o in GraphOperation]}"
                )

        # Text2Cypher: rota especial (sem template, usa LLM)
        if operation == GraphOperation.TEXT2CYPHER:
            question = params.get("question", "")
            if not question:
                return GraphAskResult(
                    success=False,
                    operation="text2cypher",
                    results=[],
                    result_count=0,
                    execution_time_ms=0,
                    error="Parâmetro 'question' é obrigatório para text2cypher",
                )
            return await self.text2cypher(
                question=question,
                tenant_id=tenant_id,
                scope=scope,
                case_id=case_id,
                include_global=include_global,
                show_template=show_template,
            )

        # Legal diagnostics: rota especial (multi-query, templates fixos)
        if operation == GraphOperation.LEGAL_DIAGNOSTICS:
            return await self.legal_diagnostics(
                tenant_id=tenant_id,
                scope=scope,
                case_id=case_id,
                include_global=include_global,
                timeout_ms=timeout_ms,
            )

        # Link entities: rota especial (escrita segura via primitiva)
        if operation == GraphOperation.LINK_ENTITIES:
            return await self._handle_link_entities(
                params=params,
                tenant_id=tenant_id,
                scope=normalized_scope,
                case_id=case_id,
                include_global=include_global,
                timeout_ms=timeout_ms,
            )

        # Recompute candidate CO_MENCIONA edges: rota especial (escrita determinística, tenant-scoped)
        if operation == GraphOperation.RECOMPUTE_CO_MENCIONA:
            return await self._handle_recompute_co_menciona(
                params=params,
                tenant_id=tenant_id,
                include_global=include_global,
            )

        # Discover hubs: rota especial (5 queries categorizadas)
        if operation == GraphOperation.DISCOVER_HUBS:
            return await self._handle_discover_hubs(
                params=params,
                tenant_id=tenant_id,
            )

        # Entity stats: rota especial (multi-query overview)
        if operation == GraphOperation.ENTITY_STATS:
            return await self._handle_entity_stats(
                params=params,
                tenant_id=tenant_id,
            )

        # GDS operations: require GDS plugin installed
        gds_operations = [
            GraphOperation.BETWEENNESS_CENTRALITY,
            GraphOperation.COMMUNITY_DETECTION,
            GraphOperation.NODE_SIMILARITY,
            GraphOperation.PAGERANK_PERSONALIZED,
            GraphOperation.WEAKLY_CONNECTED_COMPONENTS,
            GraphOperation.SHORTEST_PATH_WEIGHTED,
            GraphOperation.TRIANGLE_COUNT,
            GraphOperation.DEGREE_CENTRALITY,
            # Fase 1: Prioridade Máxima
            GraphOperation.CLOSENESS_CENTRALITY,
            GraphOperation.EIGENVECTOR_CENTRALITY,
            GraphOperation.LEIDEN,
            GraphOperation.K_CORE_DECOMPOSITION,
            GraphOperation.KNN,
            # Fase 2: Casos Específicos
            GraphOperation.BRIDGES,
            GraphOperation.ARTICULATION_POINTS,
            GraphOperation.STRONGLY_CONNECTED_COMPONENTS,
            GraphOperation.YENS_K_SHORTEST_PATHS,
            # Fase 3: Link Prediction & Embeddings
            GraphOperation.ADAMIC_ADAR,
            GraphOperation.NODE2VEC,
            GraphOperation.ALL_PAIRS_SHORTEST_PATH,
            GraphOperation.HARMONIC_CENTRALITY,
        ]
        if operation in gds_operations:
            gds_available = await self._check_gds_available()
            if not gds_available:
                return GraphAskResult(
                    success=False,
                    operation=operation.value,
                    results=[],
                    result_count=0,
                    execution_time_ms=0,
                    error="GDS plugin não instalado. Defina NEO4J_GDS_ENABLED=true e instale neo4j-gds.",
                )

            if operation == GraphOperation.BETWEENNESS_CENTRALITY:
                return await self._handle_betweenness_centrality(
                    params=params,
                    tenant_id=tenant_id,
                    show_template=show_template,
                )
            elif operation == GraphOperation.COMMUNITY_DETECTION:
                return await self._handle_community_detection(
                    params=params,
                    tenant_id=tenant_id,
                    show_template=show_template,
                )
            elif operation == GraphOperation.NODE_SIMILARITY:
                return await self._handle_node_similarity(
                    params=params,
                    tenant_id=tenant_id,
                    show_template=show_template,
                )
            elif operation == GraphOperation.PAGERANK_PERSONALIZED:
                return await self._handle_pagerank_personalized(
                    params=params,
                    tenant_id=tenant_id,
                    show_template=show_template,
                )
            elif operation == GraphOperation.WEAKLY_CONNECTED_COMPONENTS:
                return await self._handle_weakly_connected_components(
                    params=params,
                    tenant_id=tenant_id,
                    show_template=show_template,
                )
            elif operation == GraphOperation.SHORTEST_PATH_WEIGHTED:
                return await self._handle_shortest_path_weighted(
                    params=params,
                    tenant_id=tenant_id,
                    show_template=show_template,
                )
            elif operation == GraphOperation.TRIANGLE_COUNT:
                return await self._handle_triangle_count(
                    params=params,
                    tenant_id=tenant_id,
                    show_template=show_template,
                )
            elif operation == GraphOperation.DEGREE_CENTRALITY:
                return await self._handle_degree_centrality(
                    params=params,
                    tenant_id=tenant_id,
                    show_template=show_template,
                )
            # Fase 1: Prioridade Máxima
            elif operation == GraphOperation.CLOSENESS_CENTRALITY:
                return await self._handle_closeness_centrality(
                    params=params,
                    tenant_id=tenant_id,
                    show_template=show_template,
                )
            elif operation == GraphOperation.EIGENVECTOR_CENTRALITY:
                return await self._handle_eigenvector_centrality(
                    params=params,
                    tenant_id=tenant_id,
                    show_template=show_template,
                )
            elif operation == GraphOperation.LEIDEN:
                return await self._handle_leiden(
                    params=params,
                    tenant_id=tenant_id,
                    show_template=show_template,
                )
            elif operation == GraphOperation.K_CORE_DECOMPOSITION:
                return await self._handle_k_core_decomposition(
                    params=params,
                    tenant_id=tenant_id,
                    show_template=show_template,
                )
            elif operation == GraphOperation.KNN:
                return await self._handle_knn(
                    params=params,
                    tenant_id=tenant_id,
                    show_template=show_template,
                )
            elif operation == GraphOperation.BRIDGES:
                return await self._handle_bridges(
                    params=params,
                    tenant_id=tenant_id,
                    show_template=show_template,
                )
            elif operation == GraphOperation.ARTICULATION_POINTS:
                return await self._handle_articulation_points(
                    params=params,
                    tenant_id=tenant_id,
                    show_template=show_template,
                )
            elif operation == GraphOperation.STRONGLY_CONNECTED_COMPONENTS:
                return await self._handle_strongly_connected_components(
                    params=params,
                    tenant_id=tenant_id,
                    show_template=show_template,
                )
            elif operation == GraphOperation.YENS_K_SHORTEST_PATHS:
                return await self._handle_yens_k_shortest_paths(
                    params=params,
                    tenant_id=tenant_id,
                    show_template=show_template,
                )
            elif operation == GraphOperation.ADAMIC_ADAR:
                return await self._handle_adamic_adar(
                    params=params,
                    tenant_id=tenant_id,
                    show_template=show_template,
                )
            elif operation == GraphOperation.NODE2VEC:
                return await self._handle_node2vec(
                    params=params,
                    tenant_id=tenant_id,
                    show_template=show_template,
                )
            elif operation == GraphOperation.ALL_PAIRS_SHORTEST_PATH:
                return await self._handle_all_pairs_shortest_path(
                    params=params,
                    tenant_id=tenant_id,
                    show_template=show_template,
                )
            elif operation == GraphOperation.HARMONIC_CENTRALITY:
                return await self._handle_harmonic_centrality(
                    params=params,
                    tenant_id=tenant_id,
                    show_template=show_template,
                )

        # Obter template
        template = CYPHER_TEMPLATES.get(operation.value)
        if not template:
            return GraphAskResult(
                success=False,
                operation=operation.value,
                results=[],
                result_count=0,
                execution_time_ms=0,
                error=f"Template não encontrado para operação: {operation.value}"
            )

        # Validar parâmetros obrigatórios por operação
        validation_error = self._validate_params(operation, params)
        if validation_error:
            return GraphAskResult(
                success=False,
                operation=operation.value,
                results=[],
                result_count=0,
                execution_time_ms=0,
                error=validation_error
            )

        # Preparar parâmetros com defaults e segurança
        cypher_params = self._prepare_params(
            operation=operation,
            params=params,
            tenant_id=tenant_id,
            scope=normalized_scope,
            case_id=case_id,
            include_global=include_global,
        )
        query_text = self._build_query_text(operation, template, cypher_params)

        try:
            # Executar query
            neo4j = await self._get_neo4j()

            # Usar método de execução do Neo4j MVP
            results = await self._execute_query(neo4j, query_text, cypher_params, timeout_ms)

            execution_time = int((time.time() - start_time) * 1000)

            return GraphAskResult(
                success=True,
                operation=operation.value,
                results=results,
                result_count=len(results),
                execution_time_ms=execution_time,
                cypher_template=template.strip() if show_template else None,
                metadata={"params_used": list(cypher_params.keys())}
            )

        except Exception as e:
            logger.error(f"GraphAskService.ask failed: {e}")
            execution_time = int((time.time() - start_time) * 1000)
            return GraphAskResult(
                success=False,
                operation=operation.value,
                results=[],
                result_count=0,
                execution_time_ms=execution_time,
                error=str(e)
            )

    async def legal_diagnostics(
        self,
        *,
        tenant_id: str,
        scope: Optional[str] = None,
        case_id: Optional[str] = None,
        include_global: bool = True,
        timeout_ms: int = 120000,
    ) -> GraphAskResult:
        """
        Produce a deterministic diagnostic report for the legal KG.

        Goals:
        - Validate whether the graph contains multi-hop legal chains (4-5 hops)
        - Quantify remissions Artigo->Artigo and cross-law remissions
        - Provide small samples for manual inspection

        Security: fixed Cypher queries only (no user-provided Cypher).
        """
        start_time = time.time()

        try:
            neo4j = await self._get_neo4j()

            async def run(q: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
                return await self._execute_query(neo4j, q, params, timeout_ms)

            # Base params (same as other operations)
            base_params: Dict[str, Any] = {
                "tenant_id": tenant_id,
                "scope": (scope or "").strip().lower() or None,
                "case_id": case_id,
                "include_global": bool(include_global),
            }

            # Detect whether the graph has Document/Chunk tenancy anchors.
            # If absent (e.g., standalone ingestor graph), fall back to unscoped queries.
            doc_probe = await run(
                "MATCH (d:Document {tenant_id: $tenant_id}) RETURN count(d) AS c",
                base_params,
            )
            has_docs = bool(doc_probe and int(doc_probe[0].get("c") or 0) > 0)

            # Tenant-scoped “universe” for legal nodes: only those mentioned by the tenant’s docs.
            tenant_filter = ""
            tenant_collect = ""
            if has_docs:
                tenant_collect = (
                    "MATCH (d:Document {tenant_id: $tenant_id})-[:HAS_CHUNK]->(:Chunk)-[:MENTIONS]->(n) "
                    "WITH collect(DISTINCT n) AS tenant_nodes "
                )
                tenant_filter = "WHERE a1 IN tenant_nodes AND a2 IN tenant_nodes "

            # 1) Component counts (labels + key relationships)
            component_queries: Dict[str, str] = {
                "Artigo": "MATCH (n:Artigo) RETURN count(n) AS c",
                "Lei": "MATCH (n:Lei) RETURN count(n) AS c",
                "Sumula": "MATCH (n:Sumula) RETURN count(n) AS c",
                "Decisao": "MATCH (n:Decisao) RETURN count(n) AS c",
                "Tese": "MATCH (n:Tese) RETURN count(n) AS c",
                "REMETE_A": "MATCH (:Artigo)-[r:REMETE_A]->(:Artigo) RETURN count(r) AS c",
                "PERTENCE_A": "MATCH (:Artigo)-[r:PERTENCE_A]->(:Lei) RETURN count(r) AS c",
                "INTERPRETA_Dec_Art": "MATCH (:Decisao)-[r:INTERPRETA]->(:Artigo) RETURN count(r) AS c",
                "FIXA_TESE": "MATCH (:Decisao)-[r:FIXA_TESE]->(:Tese) RETURN count(r) AS c",
                "JULGA_TEMA": "MATCH (:Decisao)-[r:JULGA_TEMA]->(:Tema) RETURN count(r) AS c",
                "APLICA_SUMULA": "MATCH (:Decisao)-[r:APLICA_SUMULA]->(:Sumula) RETURN count(r) AS c",
                "CITA_Dec_Dec": "MATCH (:Decisao)-[r:CITA]->(:Decisao) RETURN count(r) AS c",
            }

            components: Dict[str, int] = {}
            for key, q in component_queries.items():
                rows = await run(q, base_params)
                components[key] = int(rows[0].get("c") or 0) if rows else 0

            # 2) Artigo -> Artigo remissions (tenant-scoped when possible)
            rem_count_q = (
                tenant_collect
                + "MATCH (a1:Artigo)-[r:REMETE_A]->(a2:Artigo) "
                + (tenant_filter if has_docs else "")
                + "RETURN count(DISTINCT r) AS c"
            )
            rem_total = await run(rem_count_q, base_params)
            rem_total_n = int(rem_total[0].get("c") or 0) if rem_total else 0

            # Cross-law remissions: Artigo->Lei differ
            cross_law_q = (
                tenant_collect
                + "MATCH (a1:Artigo)-[:REMETE_A]->(a2:Artigo) "
                + (tenant_filter if has_docs else "")
                + "OPTIONAL MATCH (a1)-[:PERTENCE_A]->(l1:Lei) "
                + "OPTIONAL MATCH (a2)-[:PERTENCE_A]->(l2:Lei) "
                + "WHERE l1 IS NOT NULL AND l2 IS NOT NULL AND l1 <> l2 "
                + "RETURN count(DISTINCT [a1,a2]) AS c"
            )
            cross_law = await run(cross_law_q, base_params)
            cross_law_n = int(cross_law[0].get("c") or 0) if cross_law else 0

            # Top remissions (most frequent edges; works even if duplicates exist)
            rem_top_q = (
                tenant_collect
                + "MATCH (a1:Artigo)-[r:REMETE_A]->(a2:Artigo) "
                + (tenant_filter if has_docs else "")
                + "WITH a1, a2, count(r) AS c, collect(DISTINCT left(coalesce(r.evidence, ''), 160))[0] AS evidence "
                + "ORDER BY c DESC "
                + "LIMIT 20 "
                + "RETURN a1.name AS origem, a2.name AS destino, evidence, c"
            )
            rem_top = await run(rem_top_q, base_params)

            # 3) 3-hop chains Art->Art->Art
            rem_3hop_count_q = (
                tenant_collect
                + "MATCH (a1:Artigo)-[:REMETE_A]->(a2:Artigo)-[:REMETE_A]->(a3:Artigo) "
                + ("WHERE a1 IN tenant_nodes AND a2 IN tenant_nodes AND a3 IN tenant_nodes " if has_docs else "")
                + "RETURN count(*) AS c"
            )
            rem_3hop = await run(rem_3hop_count_q, base_params)
            rem_3hop_n = int(rem_3hop[0].get("c") or 0) if rem_3hop else 0

            rem_3hop_sample_q = (
                tenant_collect
                + "MATCH (a1:Artigo)-[r1:REMETE_A]->(a2:Artigo)-[r2:REMETE_A]->(a3:Artigo) "
                + ("WHERE a1 IN tenant_nodes AND a2 IN tenant_nodes AND a3 IN tenant_nodes " if has_docs else "")
                + "RETURN a1.name AS a1, a2.name AS a2, a3.name AS a3, "
                + "       left(coalesce(r1.evidence, ''), 160) AS evidence1, "
                + "       left(coalesce(r2.evidence, ''), 160) AS evidence2 "
                + "LIMIT 30"
            )
            rem_3hop_samples = await run(rem_3hop_sample_q, base_params)

            # 4) Chains like the ingest_v2 diagnostics (4-5 hops)
            from app.services.rag.core.kg_builder.chain_analyzer import CHAIN_QUERIES

            chain_counts: Dict[str, int] = {}
            for key, q in CHAIN_QUERIES.items():
                rows = await run(q, base_params)
                chain_counts[key] = int(rows[0].get("c") or 0) if rows else 0

            # 5) “Most interpreted articles” (Artigo <- INTERPRETA - Decisao)
            top_interpreted_q = (
                tenant_collect
                + "MATCH (a:Artigo)<-[:INTERPRETA]-(d:Decisao) "
                + ("WHERE a IN tenant_nodes AND d IN tenant_nodes " if has_docs else "")
                + "WITH a, collect(DISTINCT d.name)[0..10] AS decisoes, count(DISTINCT d) AS c "
                + "ORDER BY c DESC "
                + "LIMIT 20 "
                + "RETURN a.name AS artigo, c AS decisoes_count, decisoes"
            )
            top_interpreted = await run(top_interpreted_q, base_params)

            # 6) Sumula -> Art -> Art chains (count + sample)
            sum_art_art_count_q = (
                tenant_collect
                + "MATCH (s:Sumula)-[:FUNDAMENTA|INTERPRETA]->(a1:Artigo)-[:REMETE_A]->(a2:Artigo) "
                + ("WHERE s IN tenant_nodes AND a1 IN tenant_nodes AND a2 IN tenant_nodes " if has_docs else "")
                + "RETURN count(*) AS c"
            )
            sum_art_art_count = await run(sum_art_art_count_q, base_params)
            sum_art_art_n = int(sum_art_art_count[0].get("c") or 0) if sum_art_art_count else 0

            sum_art_art_sample_q = (
                tenant_collect
                + "MATCH (s:Sumula)-[r0:FUNDAMENTA|INTERPRETA]->(a1:Artigo)-[r1:REMETE_A]->(a2:Artigo) "
                + ("WHERE s IN tenant_nodes AND a1 IN tenant_nodes AND a2 IN tenant_nodes " if has_docs else "")
                + "RETURN s.name AS sumula, a1.name AS a1, a2.name AS a2, "
                + "       type(r0) AS rel0, "
                + "       left(coalesce(r0.evidence, ''), 160) AS evidence0, "
                + "       left(coalesce(r1.evidence, ''), 160) AS evidence1 "
                + "LIMIT 30"
            )
            sum_art_art_samples = await run(sum_art_art_sample_q, base_params)

            payload: Dict[str, Any] = {
                "has_tenant_docs": has_docs,
                "components": components,
                "remissoes_art_art_total": rem_total_n,
                "remissoes_cross_law_total": cross_law_n,
                "remissoes_top": rem_top,
                "cadeias_3_hops_total": rem_3hop_n,
                "cadeias_3_hops_samples": rem_3hop_samples,
                "chain_counts_4_5_hops": chain_counts,
                "artigos_mais_interpretados": top_interpreted,
                "sumula_art_art_total": sum_art_art_n,
                "sumula_art_art_samples": sum_art_art_samples,
            }

            execution_time = int((time.time() - start_time) * 1000)
            return GraphAskResult(
                success=True,
                operation=GraphOperation.LEGAL_DIAGNOSTICS.value,
                results=[payload],
                result_count=1,
                execution_time_ms=execution_time,
                metadata={"note": "Relatorio deterministico; conteudos e samples limitados."},
            )
        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            logger.error(f"GraphAskService.legal_diagnostics failed: {e}")
            return GraphAskResult(
                success=False,
                operation=GraphOperation.LEGAL_DIAGNOSTICS.value,
                results=[],
                result_count=0,
                execution_time_ms=execution_time,
                error=str(e),
            )

    async def _handle_link_entities(
        self,
        *,
        params: Dict[str, Any],
        tenant_id: str,
        scope: Optional[str],
        case_id: Optional[str],
        include_global: bool,
        timeout_ms: int,
    ) -> GraphAskResult:
        """
        Create a typed relationship between two existing entities.

        Security layers:
        1. _sanitize_relation_type() — whitelist + regex validation
        2. MATCH on both entities (must exist) — no blind creation
        3. Immutable audit properties: source, layer, created_by, created_via
        """
        start_time = time.time()

        source_id = (params.get("source_id") or "").strip()
        target_id = (params.get("target_id") or "").strip()
        relation_type = (params.get("relation_type") or "RELATED_TO").strip()
        confirm = bool(params.get("confirm", False))
        preflight_token = (params.get("preflight_token") or "").strip()
        user_props = dict(params.get("properties") or {})

        if not source_id or not target_id:
            return GraphAskResult(
                success=False,
                operation=GraphOperation.LINK_ENTITIES.value,
                results=[],
                result_count=0,
                execution_time_ms=0,
                error="Parâmetros obrigatórios: source_id, target_id",
            )

        try:
            neo4j = await self._get_neo4j()

            sanitized_type = neo4j._sanitize_relation_type(relation_type)

            # Immutable audit properties (cannot be overridden by user)
            audit_props = {
                "source": "user_chat",
                "layer": "user_curated",
                "verified": True,
                "created_by": tenant_id,
                "created_via": "chat",
                "tenant_id": tenant_id,
            }
            # User properties merged, but audit props take precedence
            merged_props = {**user_props, **audit_props}

            require_confirm = _env_bool("LINK_ENTITIES_REQUIRE_CONFIRM", True)

            # Confirm mode with token: cryptographically bind the write to the preflight preview.
            if require_confirm and confirm:
                if not preflight_token:
                    return GraphAskResult(
                        success=False,
                        operation=GraphOperation.LINK_ENTITIES.value,
                        results=[],
                        result_count=0,
                        execution_time_ms=0,
                        error="confirm=true requer preflight_token (faça preflight primeiro).",
                    )
                try:
                    tok = _verify_preflight_token(preflight_token)
                except Exception as e:
                    return GraphAskResult(
                        success=False,
                        operation=GraphOperation.LINK_ENTITIES.value,
                        results=[],
                        result_count=0,
                        execution_time_ms=0,
                        error=f"preflight_token inválido: {e}",
                    )

                # Tenant binding
                if str(tok.get("tenant_id") or "") != str(tenant_id):
                    return GraphAskResult(
                        success=False,
                        operation=GraphOperation.LINK_ENTITIES.value,
                        results=[],
                        result_count=0,
                        execution_time_ms=0,
                        error="preflight_token não pertence a este tenant.",
                    )

                now_s = int(time.time())
                exp = int(tok.get("exp") or 0)
                if exp and now_s > exp:
                    return GraphAskResult(
                        success=False,
                        operation=GraphOperation.LINK_ENTITIES.value,
                        results=[],
                        result_count=0,
                        execution_time_ms=0,
                        error="preflight_token expirado (refaça preflight).",
                    )

                # Override everything from token (binding).
                source_id = str(tok.get("source_id") or source_id).strip()
                target_id = str(tok.get("target_id") or target_id).strip()
                sanitized_type = str(tok.get("relation_type") or sanitized_type).strip()
                merged_props = dict(tok.get("properties") or merged_props)

                # When using token binding, ignore any caller-provided relation_type.
                relation_type = sanitized_type

            # Preflight mode: return a preview and require an explicit confirm=true to write.
            if require_confirm and not confirm:
                base_doc_filter = (
                    "WHERE (d.tenant_id = $tenant_id OR ($include_global = true AND d.scope = 'global')) "
                    "  AND (d.sigilo IS NULL OR d.sigilo = false) "
                    "  AND ($case_id IS NOT NULL OR d.scope <> 'local') "
                    "  AND ($scope IS NULL OR d.scope = $scope) "
                    "  AND ($case_id IS NULL OR d.case_id = $case_id) "
                )

                info_q = (
                    "MATCH (e:Entity {entity_id: $eid}) "
                    "RETURN e.entity_id AS entity_id, e.name AS name, e.entity_type AS entity_type "
                    "LIMIT 1"
                )
                docs_q = (
                    "MATCH (e:Entity {entity_id: $eid}) "
                    "OPTIONAL MATCH (d:Document)-[:HAS_CHUNK]->(:Chunk)-[:MENTIONS]->(e) "
                    + base_doc_filter +
                    "RETURN count(DISTINCT d) AS docs"
                )

                async def fetch_preview(eid: str) -> Dict[str, Any]:
                    info = await self._execute_query(
                        neo4j,
                        info_q,
                        {"eid": eid},
                        timeout_ms=timeout_ms,
                    )
                    row = info[0] if info else {}
                    docs = await self._execute_query(
                        neo4j,
                        docs_q,
                        {
                            "eid": eid,
                            "tenant_id": tenant_id,
                            "include_global": bool(include_global),
                            "scope": scope,
                            "case_id": case_id,
                        },
                        timeout_ms=timeout_ms,
                    )
                    docs_n = int((docs[0] or {}).get("docs") or 0) if docs else 0

                    found = bool(row.get("entity_id"))
                    return {
                        "entity_id": eid,
                        "name": row.get("name") if found else None,
                        "entity_type": row.get("entity_type") if found else None,
                        "found": found,
                        "supporting_documents": docs_n,
                    }

                src_preview = await fetch_preview(source_id)
                tgt_preview = await fetch_preview(target_id)

                # Issue a short-lived preflight token.
                ttl_s = int(os.getenv("LINK_ENTITIES_PREFLIGHT_TTL_SECONDS", "900") or 900)
                now_s = int(time.time())
                token_payload = {
                    "v": 1,
                    "iat": now_s,
                    "exp": now_s + max(60, min(ttl_s, 3600)),
                    "tenant_id": tenant_id,
                    "source_id": source_id,
                    "target_id": target_id,
                    # Bind to sanitized relation type and final merged properties.
                    "relation_type": sanitized_type,
                    "properties": merged_props,
                }
                token = _make_preflight_token(token_payload)

                execution_time = int((time.time() - start_time) * 1000)
                return GraphAskResult(
                    success=True,
                    operation=GraphOperation.LINK_ENTITIES.value,
                    results=[{
                        "source": src_preview,
                        "target": tgt_preview,
                        "relation_type_requested": relation_type,
                        "relation_type_sanitized": sanitized_type,
                        "properties_preview": merged_props,
                        "preflight_token": token,
                        "message": "Preflight: confirme para escrever enviando confirm=true.",
                    }],
                    result_count=1,
                    execution_time_ms=execution_time,
                    metadata={"requires_confirmation": True, "write_operation": False},
                )

            success = await neo4j.link_entities_async(
                entity1_id=source_id,
                entity2_id=target_id,
                relation_type=relation_type,
                properties=merged_props,
            )
            execution_time = int((time.time() - start_time) * 1000)

            if success:
                return GraphAskResult(
                    success=True,
                    operation=GraphOperation.LINK_ENTITIES.value,
                    results=[{
                        "source_id": source_id,
                        "target_id": target_id,
                        "relation_type": sanitized_type,
                        "layer": "user_curated",
                    }],
                    result_count=1,
                    execution_time_ms=execution_time,
                    metadata={"write_operation": True},
                )
            else:
                return GraphAskResult(
                    success=False,
                    operation=GraphOperation.LINK_ENTITIES.value,
                    results=[],
                    result_count=0,
                    execution_time_ms=execution_time,
                    error=(
                        f"Falha ao criar aresta {sanitized_type} entre "
                        f"'{source_id}' e '{target_id}'. "
                        "Verifique se ambas entidades existem no grafo."
                    ),
                )
        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            logger.error(f"GraphAskService.link_entities failed: {e}")
            return GraphAskResult(
                success=False,
                operation=GraphOperation.LINK_ENTITIES.value,
                results=[],
                result_count=0,
                execution_time_ms=execution_time,
                error=str(e),
            )

    async def _handle_recompute_co_menciona(
        self,
        *,
        params: Dict[str, Any],
        tenant_id: str,
        include_global: bool,
    ) -> GraphAskResult:
        """
        Recompute candidate Artigo–Artigo co-mention edges (CO_MENCIONA).

        This is a deterministic, tenant-scoped write operation intended for exploration only.
        Candidate edges are excluded by default in chain/path operations unless include_candidates=true.
        """
        start_time = time.time()

        try:
            min_co = int(params.get("min_cooccurrences", 2) or 2)
        except Exception:
            min_co = 2
        try:
            max_pairs = int(params.get("max_pairs", 20000) or 20000)
        except Exception:
            max_pairs = 20000

        min_co = max(1, min(min_co, 20))
        max_pairs = max(1, min(max_pairs, 200000))

        try:
            neo4j = await self._get_neo4j()
            res = await asyncio.to_thread(
                neo4j.recompute_candidate_comentions,
                tenant_id=tenant_id,
                include_global=bool(include_global),
                min_cooccurrences=min_co,
                max_pairs=max_pairs,
            )
            execution_time = int((time.time() - start_time) * 1000)
            ok = bool(res.get("ok")) if isinstance(res, dict) else False
            err = None
            if not ok:
                err = str(res.get("error", "Falha ao recomputar CO_MENCIONA")) if isinstance(res, dict) else "Falha ao recomputar CO_MENCIONA"

            return GraphAskResult(
                success=ok,
                operation=GraphOperation.RECOMPUTE_CO_MENCIONA.value,
                results=[res] if isinstance(res, dict) else [],
                result_count=1 if isinstance(res, dict) else 0,
                execution_time_ms=execution_time,
                error=err,
                metadata={"write_operation": True, "layer": "candidate"},
            )
        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            logger.error(f"GraphAskService.recompute_co_menciona failed: {e}")
            return GraphAskResult(
                success=False,
                operation=GraphOperation.RECOMPUTE_CO_MENCIONA.value,
                results=[],
                result_count=0,
                execution_time_ms=execution_time,
                error=str(e),
            )

    async def _handle_discover_hubs(
        self,
        *,
        params: Dict[str, Any],
        tenant_id: str,
    ) -> GraphAskResult:
        """
        Identify the most connected nodes (hubs) in the knowledge graph.

        Returns categorized hub lists: most referenced articles, articles with
        most outgoing references, most connected articles (total degree),
        decisions with most theses, and laws with most articles.
        """
        start_time = time.time()
        top_n = min(int(params.get("top_n", 10)), 50)

        _HUB_QUERIES: Dict[str, str] = {
            "artigos_mais_referenciados": (
                "MATCH ()-[:REMETE_A]->(a:Artigo) "
                "WITH a.name AS artigo, count(*) AS referencias "
                "RETURN artigo, referencias ORDER BY referencias DESC LIMIT $top_n"
            ),
            "artigos_que_mais_referenciam": (
                "MATCH (a:Artigo)-[:REMETE_A]->() "
                "WITH a.name AS artigo, count(*) AS saidas "
                "RETURN artigo, saidas ORDER BY saidas DESC LIMIT $top_n"
            ),
            "artigos_mais_conectados": (
                "MATCH (a:Artigo)-[r]-() "
                "WHERE type(r) <> 'FROM_CHUNK' AND type(r) <> 'PERTENCE_A' "
                "WITH a.name AS artigo, count(r) AS conexoes "
                "RETURN artigo, conexoes ORDER BY conexoes DESC LIMIT $top_n"
            ),
            "decisoes_com_mais_teses": (
                "MATCH (d:Decisao)-[:FIXA_TESE]->(t:Tese) "
                "WITH d.name AS decisao, count(t) AS teses "
                "RETURN decisao, teses ORDER BY teses DESC LIMIT $top_n"
            ),
            "leis_com_mais_artigos": (
                "MATCH (a:Artigo)-[:PERTENCE_A]->(l:Lei) "
                "WITH l.name AS lei, count(a) AS artigos "
                "RETURN lei, artigos ORDER BY artigos DESC LIMIT $top_n"
            ),
        }

        try:
            neo4j = await self._get_neo4j()
            all_hubs: List[Dict[str, Any]] = []

            for category, query in _HUB_QUERIES.items():
                try:
                    records = await neo4j._execute_read_async(
                        query, {"top_n": top_n}
                    )
                    for rec in records:
                        entry = dict(rec)
                        entry["category"] = category
                        all_hubs.append(entry)
                except Exception as e:
                    logger.warning("Hub query %s failed: %s", category, e)

            execution_time = int((time.time() - start_time) * 1000)
            return GraphAskResult(
                success=True,
                operation=GraphOperation.DISCOVER_HUBS.value,
                results=all_hubs,
                result_count=len(all_hubs),
                execution_time_ms=execution_time,
                metadata={"top_n": top_n},
            )
        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            logger.error("GraphAskService.discover_hubs failed: %s", e)
            return GraphAskResult(
                success=False,
                operation=GraphOperation.DISCOVER_HUBS.value,
                results=[],
                result_count=0,
                execution_time_ms=execution_time,
                error=str(e),
            )

    async def _handle_entity_stats(
        self,
        params: Dict[str, Any],
        tenant_id: str,
    ) -> GraphAskResult:
        """Estatísticas gerais do grafo por tipo de entidade e relação."""
        start_time = time.time()

        # Infra rel types to exclude from stats
        _INFRA_RELS = (
            "FROM_CHUNK", "FROM_DOCUMENT", "NEXT_CHUNK",
            "MENTIONS", "HAS_CHUNK", "HAS_TENANT_METRIC",
        )
        infra_filter = " AND ".join(f"type(r) <> '{t}'" for t in _INFRA_RELS)

        queries = {
            "total_entities": "MATCH (e:Entity) RETURN count(e) AS c",
            "by_type": (
                "MATCH (e:Entity) "
                "RETURN e.entity_type AS type, count(e) AS c "
                "ORDER BY c DESC"
            ),
            "total_relationships": (
                f"MATCH ()-[r]->() WHERE {infra_filter} "
                "RETURN count(r) AS c"
            ),
            "rel_types": (
                f"MATCH ()-[r]->() WHERE {infra_filter} "
                "RETURN type(r) AS type, count(r) AS c "
                "ORDER BY c DESC"
            ),
        }

        try:
            neo4j = await self._get_neo4j()
            results: List[Dict[str, Any]] = []

            for key, q in queries.items():
                try:
                    rows = await neo4j._execute_read_async(q, {"tenant_id": tenant_id})
                    results.append({"category": key, "data": rows})
                except Exception as e:
                    logger.warning("entity_stats query '%s' failed: %s", key, e)
                    results.append({"category": key, "data": [], "error": str(e)})

            execution_time = int((time.time() - start_time) * 1000)
            return GraphAskResult(
                success=True,
                operation=GraphOperation.ENTITY_STATS.value,
                results=results,
                result_count=len(results),
                execution_time_ms=execution_time,
                metadata={"categories": list(queries.keys())},
            )

        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            logger.error("GraphAskService.entity_stats failed: %s", e)
            return GraphAskResult(
                success=False,
                operation=GraphOperation.ENTITY_STATS.value,
                results=[],
                result_count=0,
                execution_time_ms=execution_time,
                error=str(e),
            )

    def _validate_params(self, operation: GraphOperation, params: Dict[str, Any]) -> Optional[str]:
        """Valida parâmetros obrigatórios por operação."""
        required = {
            GraphOperation.PATH: ["source_id", "target_id"],
            GraphOperation.NEIGHBORS: ["entity_id"],
            GraphOperation.COOCCURRENCE: ["entity1_id", "entity2_id"],
            GraphOperation.SEARCH: ["query"],
            GraphOperation.COUNT: [],  # Todos opcionais
            GraphOperation.RANKING: [],  # Todos opcionais (entity_type filter)
            GraphOperation.LEGAL_CHAIN: ["source_id"],
            GraphOperation.PRECEDENT_NETWORK: ["decision_id"],
            GraphOperation.JUDGE_DECISIONS: ["judge_query"],
            GraphOperation.FRAUD_SIGNALS: [],
            GraphOperation.PROCESS_NETWORK: ["process_id"],
            GraphOperation.PROCESS_TIMELINE: ["process_id"],
            GraphOperation.TEXT2CYPHER: ["question"],
            GraphOperation.LINK_ENTITIES: ["source_id", "target_id"],
            GraphOperation.DISCOVER_HUBS: [],  # top_n é opcional
            GraphOperation.RELATED_ENTITIES: ["entity_id"],
            GraphOperation.ENTITY_STATS: [],  # sem params obrigatórios
            GraphOperation.RECOMPUTE_CO_MENCIONA: [],  # min_cooccurrences/max_pairs opcionais
        }

        missing = [p for p in required.get(operation, []) if p not in params or not params[p]]
        if missing:
            return f"Parâmetros obrigatórios faltando: {missing}"

        return None

    def _prepare_params(
        self,
        operation: GraphOperation,
        params: Dict[str, Any],
        tenant_id: str,
        scope: Optional[str],
        case_id: Optional[str],
        include_global: bool,
    ) -> Dict[str, Any]:
        """Prepara parâmetros com defaults e filtros de segurança."""

        # Base: sempre inclui tenant_id e scope
        cypher_params = {
            "tenant_id": tenant_id,
            "scope": scope,
            "case_id": case_id,
            "include_global": bool(include_global),
            # Candidate graph is excluded by default (transparency-first).
            "include_candidates": False,
        }

        # Defaults por operação
        defaults = {
            GraphOperation.PATH: {"max_hops": 4, "limit": 5},
            GraphOperation.NEIGHBORS: {"limit": 20},
            GraphOperation.COOCCURRENCE: {},
            GraphOperation.SEARCH: {"limit": 30, "entity_type": None},
            GraphOperation.COUNT: {"entity_type": None, "query": None},
            GraphOperation.RANKING: {"limit": 20, "entity_type": None},
            GraphOperation.LEGAL_CHAIN: {
                "max_hops": 4,
                "limit": 20,
                "target_id": None,
                "relation_types": None,
            },
            GraphOperation.PRECEDENT_NETWORK: {"max_hops": 4, "limit": 20},
            GraphOperation.JUDGE_DECISIONS: {"limit": 20, "decision_type": None},
            GraphOperation.FRAUD_SIGNALS: {"limit": 20, "min_shared_docs": 2},
            GraphOperation.PROCESS_NETWORK: {"max_hops": 4, "limit": 20},
            GraphOperation.PROCESS_TIMELINE: {"limit": 30},
            GraphOperation.RELATED_ENTITIES: {"limit": 30, "relation_filter": None},
        }

        # Aplicar defaults
        for key, value in defaults.get(operation, {}).items():
            if key not in params:
                cypher_params[key] = value

        # Copiar parâmetros do usuário (com sanitização básica)
        for key, value in params.items():
            if isinstance(value, str):
                # Limitar tamanho de strings para evitar abuse
                cypher_params[key] = value[:500]
            elif isinstance(value, (int, float)):
                # Limitar valores numéricos
                if key == "limit":
                    cypher_params[key] = min(int(value), 100)
                elif key == "max_hops":
                    cypher_params[key] = min(int(value), 6)
                elif key == "min_shared_docs":
                    cypher_params[key] = max(1, min(int(value), 20))
                else:
                    cypher_params[key] = value
            else:
                cypher_params[key] = value

        return cypher_params

    def _build_query_text(
        self,
        operation: GraphOperation,
        template: str,
        params: Dict[str, Any],
    ) -> str:
        """
        Build final query text for a given operation.

        Some Cypher fragments can't be parameterized (e.g., relationship-length ranges),
        so we inject sanitized integers.
        """
        hop_ops = {
            GraphOperation.PATH,
            GraphOperation.LEGAL_CHAIN,
            GraphOperation.PRECEDENT_NETWORK,
            GraphOperation.PROCESS_NETWORK,
        }

        query = template
        if operation in hop_ops:
            hops_raw = params.get("max_hops", 4)
            try:
                hops = int(hops_raw)
            except (TypeError, ValueError):
                hops = 4
            hops = max(1, min(hops, 6))
            query = query.replace(_MAX_HOPS_TOKEN, str(hops))

        if operation == GraphOperation.LEGAL_CHAIN:
            rel_types = self._resolve_relation_types(params.get("relation_types"))
            query = query.replace(_REL_TYPES_TOKEN, rel_types)

        return query

    def _resolve_relation_types(self, raw_value: Any) -> str:
        """
        Resolve relationship type filter for LEGAL_CHAIN safely.

        Accepts comma-separated string or list[str]. Any non-whitelisted
        relationship type is ignored.
        """
        if isinstance(raw_value, str):
            requested = [part.strip().upper() for part in raw_value.split(",") if part.strip()]
        elif isinstance(raw_value, list):
            requested = [str(part).strip().upper() for part in raw_value if str(part).strip()]
        else:
            requested = []

        sanitized: List[str] = []
        for rel in requested:
            if re.fullmatch(r"[A-Z][A-Z0-9_]{0,40}", rel) and rel in _ALLOWED_RELATIONSHIP_LABELS:
                sanitized.append(rel)

        if not sanitized:
            return "|".join(_DEFAULT_LEGAL_CHAIN_RELATION_TYPES)
        return "|".join(dict.fromkeys(sanitized))

    async def _execute_query(
        self,
        neo4j,
        query_text: str,
        params: Dict[str, Any],
        timeout_ms: int,
    ) -> List[Dict[str, Any]]:
        """Executa query no Neo4j com timeout."""
        import asyncio

        # Executar com timeout usando o driver async para nao bloquear o event loop.
        try:
            return await asyncio.wait_for(
                neo4j._execute_read_async(query_text, params),
                timeout=timeout_ms / 1000.0,
            )
        except asyncio.TimeoutError:
            raise TimeoutError(f"Query excedeu timeout de {timeout_ms}ms")

    # =========================================================================
    # CONVENIENCE METHODS - Atalhos para operações comuns
    # =========================================================================

    async def find_path(
        self,
        source_id: str,
        target_id: str,
        tenant_id: str,
        max_hops: int = 4,
        scope: Optional[str] = None,
        case_id: Optional[str] = None,
        include_global: bool = True,
    ) -> GraphAskResult:
        """Encontra caminho entre duas entidades."""
        return await self.ask(
            operation=GraphOperation.PATH,
            params={"source_id": source_id, "target_id": target_id, "max_hops": max_hops},
            tenant_id=tenant_id,
            scope=scope,
            case_id=case_id,
            include_global=include_global,
        )

    async def get_neighbors(
        self,
        entity_id: str,
        tenant_id: str,
        limit: int = 20,
        scope: Optional[str] = None,
        case_id: Optional[str] = None,
        include_global: bool = True,
    ) -> GraphAskResult:
        """Obtém vizinhos semânticos de uma entidade."""
        return await self.ask(
            operation=GraphOperation.NEIGHBORS,
            params={"entity_id": entity_id, "limit": limit},
            tenant_id=tenant_id,
            scope=scope,
            case_id=case_id,
            include_global=include_global,
        )

    async def find_cooccurrence(
        self,
        entity1_id: str,
        entity2_id: str,
        tenant_id: str,
        scope: Optional[str] = None,
        case_id: Optional[str] = None,
        include_global: bool = True,
    ) -> GraphAskResult:
        """Encontra co-ocorrências entre duas entidades."""
        return await self.ask(
            operation=GraphOperation.COOCCURRENCE,
            params={"entity1_id": entity1_id, "entity2_id": entity2_id},
            tenant_id=tenant_id,
            scope=scope,
            case_id=case_id,
            include_global=include_global,
        )

    async def search_entities(
        self,
        query: str,
        tenant_id: str,
        entity_type: Optional[str] = None,
        limit: int = 30,
        scope: Optional[str] = None,
        case_id: Optional[str] = None,
        include_global: bool = True,
    ) -> GraphAskResult:
        """Busca entidades por nome."""
        return await self.ask(
            operation=GraphOperation.SEARCH,
            params={"query": query, "entity_type": entity_type, "limit": limit},
            tenant_id=tenant_id,
            scope=scope,
            case_id=case_id,
            include_global=include_global,
        )

    async def count_entities(
        self,
        tenant_id: str,
        entity_type: Optional[str] = None,
        query: Optional[str] = None,
        scope: Optional[str] = None,
        case_id: Optional[str] = None,
        include_global: bool = True,
    ) -> GraphAskResult:
        """Conta entidades com filtros."""
        return await self.ask(
            operation=GraphOperation.COUNT,
            params={"entity_type": entity_type, "query": query},
            tenant_id=tenant_id,
            scope=scope,
            case_id=case_id,
            include_global=include_global,
        )

    async def find_legal_chain(
        self,
        source_id: str,
        tenant_id: str,
        target_id: Optional[str] = None,
        relation_types: Optional[Union[str, List[str]]] = None,
        max_hops: int = 4,
        limit: int = 20,
        scope: Optional[str] = None,
        case_id: Optional[str] = None,
        include_global: bool = True,
    ) -> GraphAskResult:
        """Busca cadeia semântica entre dispositivos legais."""
        return await self.ask(
            operation=GraphOperation.LEGAL_CHAIN,
            params={
                "source_id": source_id,
                "target_id": target_id,
                "relation_types": relation_types,
                "max_hops": max_hops,
                "limit": limit,
            },
            tenant_id=tenant_id,
            scope=scope,
            case_id=case_id,
            include_global=include_global,
        )

    async def get_precedent_network(
        self,
        decision_id: str,
        tenant_id: str,
        max_hops: int = 4,
        limit: int = 20,
        scope: Optional[str] = None,
        case_id: Optional[str] = None,
        include_global: bool = True,
    ) -> GraphAskResult:
        """Retorna rede de precedentes de uma decisão."""
        return await self.ask(
            operation=GraphOperation.PRECEDENT_NETWORK,
            params={"decision_id": decision_id, "max_hops": max_hops, "limit": limit},
            tenant_id=tenant_id,
            scope=scope,
            case_id=case_id,
            include_global=include_global,
        )

    async def get_judge_decisions(
        self,
        judge_query: str,
        tenant_id: str,
        decision_type: Optional[str] = None,
        limit: int = 20,
        scope: Optional[str] = None,
        case_id: Optional[str] = None,
        include_global: bool = True,
    ) -> GraphAskResult:
        """Retorna decisões relacionadas ao mesmo juiz/ministro."""
        return await self.ask(
            operation=GraphOperation.JUDGE_DECISIONS,
            params={"judge_query": judge_query, "decision_type": decision_type, "limit": limit},
            tenant_id=tenant_id,
            scope=scope,
            case_id=case_id,
            include_global=include_global,
        )

    async def get_fraud_signals(
        self,
        tenant_id: str,
        min_shared_docs: int = 2,
        limit: int = 20,
        scope: Optional[str] = None,
        case_id: Optional[str] = None,
        include_global: bool = True,
    ) -> GraphAskResult:
        """Retorna possíveis sinais de risco/fraude por conexões no grafo."""
        return await self.ask(
            operation=GraphOperation.FRAUD_SIGNALS,
            params={"min_shared_docs": min_shared_docs, "limit": limit},
            tenant_id=tenant_id,
            scope=scope,
            case_id=case_id,
            include_global=include_global,
        )

    async def get_process_network(
        self,
        process_id: str,
        tenant_id: str,
        max_hops: int = 4,
        limit: int = 20,
        scope: Optional[str] = None,
        case_id: Optional[str] = None,
        include_global: bool = True,
    ) -> GraphAskResult:
        """Retorna rede de conexões multi-hop de um processo."""
        return await self.ask(
            operation=GraphOperation.PROCESS_NETWORK,
            params={"process_id": process_id, "max_hops": max_hops, "limit": limit},
            tenant_id=tenant_id,
            scope=scope,
            case_id=case_id,
            include_global=include_global,
        )

    async def get_process_timeline(
        self,
        process_id: str,
        tenant_id: str,
        limit: int = 30,
        scope: Optional[str] = None,
        case_id: Optional[str] = None,
        include_global: bool = True,
    ) -> GraphAskResult:
        """Retorna timeline documental/eventos associados ao processo."""
        return await self.ask(
            operation=GraphOperation.PROCESS_TIMELINE,
            params={"process_id": process_id, "limit": limit},
            tenant_id=tenant_id,
            scope=scope,
            case_id=case_id,
            include_global=include_global,
        )

    async def text2cypher(
        self,
        question: str,
        tenant_id: str,
        scope: Optional[str] = None,
        case_id: Optional[str] = None,
        include_global: bool = True,
        show_template: bool = False,
    ) -> GraphAskResult:
        """
        Converte pergunta em linguagem natural para Cypher e executa.

        Usa LLM para gerar Cypher, depois aplica 3 camadas de segurança:
        1. Blocklist de keywords de escrita
        2. Injeção de filtro tenant_id
        3. Validação estrutural
        """
        start_time = time.time()

        if not _env_bool("TEXT2CYPHER_ENABLED", False):
            return GraphAskResult(
                success=False,
                operation="text2cypher",
                results=[],
                result_count=0,
                execution_time_ms=0,
                error="Text2Cypher está desabilitado. Defina TEXT2CYPHER_ENABLED=true.",
            )

        try:
            neo4j = await self._get_neo4j()
            engine = get_text2cypher_engine()

            result = await engine.generate_and_execute(
                question=question,
                neo4j_service=neo4j,
                tenant_id=tenant_id,
                scope=scope,
                case_id=case_id,
                include_global=include_global,
            )

            execution_time = int((time.time() - start_time) * 1000)

            return GraphAskResult(
                success=True,
                operation="text2cypher",
                results=result["results"],
                result_count=len(result["results"]),
                execution_time_ms=execution_time,
                cypher_template=result.get("cypher") if show_template else None,
                metadata={
                    "original_question": question,
                    "cypher_generated": result.get("cypher_sanitized", ""),
                },
            )

        except CypherSecurityError as e:
            execution_time = int((time.time() - start_time) * 1000)
            logger.warning(f"Text2Cypher security rejection: {e}")
            return GraphAskResult(
                success=False,
                operation="text2cypher",
                results=[],
                result_count=0,
                execution_time_ms=execution_time,
                error=f"Query rejeitada por segurança: {e}",
            )
        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            logger.error(f"Text2Cypher failed: {e}")
            return GraphAskResult(
                success=False,
                operation="text2cypher",
                results=[],
                result_count=0,
                execution_time_ms=execution_time,
                error=str(e),
            )

    # =========================================================================
    # GDS (Graph Data Science) Operations
    # =========================================================================

    async def _handle_betweenness_centrality(
        self,
        params: Dict[str, Any],
        tenant_id: str,
        show_template: bool = False,
    ) -> GraphAskResult:
        """Calcula centralidade de intermediação (betweenness) para nós.

        Identifica artigos/entidades que servem de "ponte" entre diferentes áreas.
        Útil para descobrir dispositivos que conectam temas distintos.
        """
        start_time = time.time()

        entity_type = params.get("entity_type", "Artigo")  # Default: Artigo
        limit = min(int(params.get("limit", 20)), 100)

        try:
            neo4j = await self._get_neo4j()

            # Cypher usando GDS betweenness centrality
            # Projeta subgrafo filtrado por tenant, calcula betweenness, retorna top N
            cypher = """
            CALL gds.graph.project(
                'betweenness-graph-' + randomUUID(),
                {__TYPE_LABEL__: {
                    label: '__TYPE_LABEL__',
                    properties: ['tenant_id']
                }},
                '*'
            )
            YIELD graphName
            CALL gds.betweenness.stream(graphName)
            YIELD nodeId, score
            WITH gds.util.asNode(nodeId) AS node, score
            WHERE node.tenant_id = $tenant_id AND score > 0
            CALL gds.graph.drop(graphName) YIELD graphName AS dropped
            RETURN node.entity_id AS entity_id, node.name AS name, score
            ORDER BY score DESC
            LIMIT $limit
            """

            cypher = cypher.replace("__TYPE_LABEL__", entity_type)

            results = await neo4j.execute_cypher(
                cypher,
                {"tenant_id": tenant_id, "limit": limit},
                tenant_id=tenant_id,
            )

            execution_time = int((time.time() - start_time) * 1000)

            return GraphAskResult(
                success=True,
                operation="betweenness_centrality",
                results=results,
                result_count=len(results),
                execution_time_ms=execution_time,
                cypher_template=cypher if show_template else None,
                metadata={"entity_type": entity_type, "algorithm": "betweenness"},
            )

        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            logger.error(f"Betweenness centrality failed: {e}")
            return GraphAskResult(
                success=False,
                operation="betweenness_centrality",
                results=[],
                result_count=0,
                execution_time_ms=execution_time,
                error=str(e),
            )

    async def _handle_community_detection(
        self,
        params: Dict[str, Any],
        tenant_id: str,
        show_template: bool = False,
    ) -> GraphAskResult:
        """Detecta comunidades temáticas usando Louvain.

        Agrupa artigos/entidades por conexões implícitas, revelando "temas".
        Útil para descobrir agrupamentos automáticos no grafo jurídico.
        """
        start_time = time.time()

        entity_type = params.get("entity_type", "Artigo")
        limit = min(int(params.get("limit", 50)), 200)

        try:
            neo4j = await self._get_neo4j()

            # Cypher usando GDS Louvain para detecção de comunidades
            cypher = """
            CALL gds.graph.project(
                'community-graph-' + randomUUID(),
                {__TYPE_LABEL__: {
                    label: '__TYPE_LABEL__',
                    properties: ['tenant_id']
                }},
                '*'
            )
            YIELD graphName
            CALL gds.louvain.stream(graphName)
            YIELD nodeId, communityId
            WITH gds.util.asNode(nodeId) AS node, communityId
            WHERE node.tenant_id = $tenant_id
            CALL gds.graph.drop(graphName) YIELD graphName AS dropped
            WITH communityId, collect(node.entity_id) AS members, collect(node.name) AS names, count(*) AS size
            RETURN communityId, members[0..10] AS sample_members, names[0..10] AS sample_names, size
            ORDER BY size DESC
            LIMIT $limit
            """

            cypher = cypher.replace("__TYPE_LABEL__", entity_type)

            results = await neo4j.execute_cypher(
                cypher,
                {"tenant_id": tenant_id, "limit": limit},
                tenant_id=tenant_id,
            )

            execution_time = int((time.time() - start_time) * 1000)

            return GraphAskResult(
                success=True,
                operation="community_detection",
                results=results,
                result_count=len(results),
                execution_time_ms=execution_time,
                cypher_template=cypher if show_template else None,
                metadata={"entity_type": entity_type, "algorithm": "louvain"},
            )

        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            logger.error(f"Community detection failed: {e}")
            return GraphAskResult(
                success=False,
                operation="community_detection",
                results=[],
                result_count=0,
                execution_time_ms=execution_time,
                error=str(e),
            )

    async def _handle_node_similarity(
        self,
        params: Dict[str, Any],
        tenant_id: str,
        show_template: bool = False,
    ) -> GraphAskResult:
        """Calcula similaridade entre nós baseado em vizinhos compartilhados.

        Encontra artigos/decisões similares por terem conexões em comum.
        Útil para "decisões parecidas" ou "artigos relacionados".
        """
        start_time = time.time()

        entity_type = params.get("entity_type", "Artigo")
        entity_id = params.get("entity_id")  # Optional: similarity from specific node
        limit = min(int(params.get("limit", 20)), 100)
        top_k = min(int(params.get("top_k", 10)), 20)  # K neighbors per node

        try:
            neo4j = await self._get_neo4j()

            # Cypher usando GDS nodeSimilarity
            if entity_id:
                # Similarity from specific node
                cypher = """
                MATCH (source:__TYPE_LABEL__ {entity_id: $entity_id, tenant_id: $tenant_id})
                CALL gds.graph.project(
                    'similarity-graph-' + randomUUID(),
                    {__TYPE_LABEL__: {
                        label: '__TYPE_LABEL__',
                        properties: ['tenant_id']
                    }},
                    '*'
                )
                YIELD graphName
                CALL gds.nodeSimilarity.stream(graphName, {topK: $top_k})
                YIELD node1, node2, similarity
                WITH gds.util.asNode(node1) AS n1, gds.util.asNode(node2) AS n2, similarity
                WHERE (n1.entity_id = $entity_id OR n2.entity_id = $entity_id)
                  AND n1.tenant_id = $tenant_id AND n2.tenant_id = $tenant_id
                  AND similarity > 0
                CALL gds.graph.drop(graphName) YIELD graphName AS dropped
                WITH CASE WHEN n1.entity_id = $entity_id THEN n2 ELSE n1 END AS similar_node, similarity
                RETURN similar_node.entity_id AS entity_id, similar_node.name AS name, similarity
                ORDER BY similarity DESC
                LIMIT $limit
                """
            else:
                # Global similarity pairs
                cypher = """
                CALL gds.graph.project(
                    'similarity-graph-' + randomUUID(),
                    {__TYPE_LABEL__: {
                        label: '__TYPE_LABEL__',
                        properties: ['tenant_id']
                    }},
                    '*'
                )
                YIELD graphName
                CALL gds.nodeSimilarity.stream(graphName, {topK: $top_k})
                YIELD node1, node2, similarity
                WITH gds.util.asNode(node1) AS n1, gds.util.asNode(node2) AS n2, similarity
                WHERE n1.tenant_id = $tenant_id AND n2.tenant_id = $tenant_id AND similarity > 0
                CALL gds.graph.drop(graphName) YIELD graphName AS dropped
                RETURN n1.entity_id AS entity1_id, n1.name AS entity1_name,
                       n2.entity_id AS entity2_id, n2.name AS entity2_name,
                       similarity
                ORDER BY similarity DESC
                LIMIT $limit
                """

            cypher = cypher.replace("__TYPE_LABEL__", entity_type)

            cypher_params = {
                "tenant_id": tenant_id,
                "limit": limit,
                "top_k": top_k,
            }
            if entity_id:
                cypher_params["entity_id"] = entity_id

            results = await neo4j.execute_cypher(cypher, cypher_params, tenant_id=tenant_id)

            execution_time = int((time.time() - start_time) * 1000)

            return GraphAskResult(
                success=True,
                operation="node_similarity",
                results=results,
                result_count=len(results),
                execution_time_ms=execution_time,
                cypher_template=cypher if show_template else None,
                metadata={
                    "entity_type": entity_type,
                    "algorithm": "nodeSimilarity",
                    "entity_id": entity_id,
                },
            )

        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            logger.error(f"Node similarity failed: {e}")
            return GraphAskResult(
                success=False,
                operation="node_similarity",
                results=[],
                result_count=0,
                execution_time_ms=execution_time,
                error=str(e),
            )

    async def _handle_pagerank_personalized(
        self,
        params: Dict[str, Any],
        tenant_id: str,
        show_template: bool = False,
    ) -> GraphAskResult:
        """PageRank personalizado a partir de nós específicos.

        Calcula PageRank priorizando vizinhança de nós seed (ex: Art. 5 CF).
        Útil para "artigos importantes no contexto de X".
        """
        start_time = time.time()

        entity_type = params.get("entity_type", "Artigo")
        source_ids = params.get("source_ids", [])  # List of seed nodes
        if isinstance(source_ids, str):
            source_ids = [source_ids]
        limit = min(int(params.get("limit", 20)), 100)

        try:
            neo4j = await self._get_neo4j()

            # Cypher usando GDS PageRank personalizado
            cypher = """
            MATCH (seed:__TYPE_LABEL__ {tenant_id: $tenant_id})
            WHERE seed.entity_id IN $source_ids
            CALL gds.graph.project(
                'pagerank-graph-' + randomUUID(),
                {__TYPE_LABEL__: {
                    label: '__TYPE_LABEL__',
                    properties: ['tenant_id']
                }},
                '*'
            )
            YIELD graphName
            CALL gds.pageRank.stream(graphName, {sourceNodes: collect(id(seed))})
            YIELD nodeId, score
            WITH gds.util.asNode(nodeId) AS node, score
            WHERE node.tenant_id = $tenant_id AND score > 0
            CALL gds.graph.drop(graphName) YIELD graphName AS dropped
            RETURN node.entity_id AS entity_id, node.name AS name, score
            ORDER BY score DESC
            LIMIT $limit
            """

            cypher = cypher.replace("__TYPE_LABEL__", entity_type)

            results = await neo4j.execute_cypher(
                cypher,
                {"tenant_id": tenant_id, "source_ids": source_ids, "limit": limit},
                tenant_id=tenant_id,
            )

            execution_time = int((time.time() - start_time) * 1000)

            return GraphAskResult(
                success=True,
                operation="pagerank_personalized",
                results=results,
                result_count=len(results),
                execution_time_ms=execution_time,
                cypher_template=cypher if show_template else None,
                metadata={"entity_type": entity_type, "algorithm": "pageRank", "source_ids": source_ids},
            )

        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            logger.error(f"PageRank personalizado failed: {e}")
            return GraphAskResult(
                success=False,
                operation="pagerank_personalized",
                results=[],
                result_count=0,
                execution_time_ms=execution_time,
                error=str(e),
            )

    async def _handle_weakly_connected_components(
        self,
        params: Dict[str, Any],
        tenant_id: str,
        show_template: bool = False,
    ) -> GraphAskResult:
        """Detecta componentes fracamente conectados (ilhas no grafo).

        Identifica grupos de entidades completamente isolados do resto.
        Útil para descobrir "ilhas jurídicas" sem conexão com o grafo principal.
        """
        start_time = time.time()

        entity_type = params.get("entity_type", "Artigo")
        limit = min(int(params.get("limit", 20)), 100)

        try:
            neo4j = await self._get_neo4j()

            # Cypher usando GDS WCC
            cypher = """
            CALL gds.graph.project(
                'wcc-graph-' + randomUUID(),
                {__TYPE_LABEL__: {
                    label: '__TYPE_LABEL__',
                    properties: ['tenant_id']
                }},
                '*'
            )
            YIELD graphName
            CALL gds.wcc.stream(graphName)
            YIELD nodeId, componentId
            WITH gds.util.asNode(nodeId) AS node, componentId
            WHERE node.tenant_id = $tenant_id
            CALL gds.graph.drop(graphName) YIELD graphName AS dropped
            WITH componentId, collect(node.entity_id) AS members, collect(node.name) AS names, count(*) AS size
            RETURN componentId, members[0..10] AS sample_members, names[0..10] AS sample_names, size
            ORDER BY size DESC
            LIMIT $limit
            """

            cypher = cypher.replace("__TYPE_LABEL__", entity_type)

            results = await neo4j.execute_cypher(
                cypher,
                {"tenant_id": tenant_id, "limit": limit},
                tenant_id=tenant_id,
            )

            execution_time = int((time.time() - start_time) * 1000)

            return GraphAskResult(
                success=True,
                operation="weakly_connected_components",
                results=results,
                result_count=len(results),
                execution_time_ms=execution_time,
                cypher_template=cypher if show_template else None,
                metadata={"entity_type": entity_type, "algorithm": "wcc"},
            )

        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            logger.error(f"WCC failed: {e}")
            return GraphAskResult(
                success=False,
                operation="weakly_connected_components",
                results=[],
                result_count=0,
                execution_time_ms=execution_time,
                error=str(e),
            )

    async def _handle_shortest_path_weighted(
        self,
        params: Dict[str, Any],
        tenant_id: str,
        show_template: bool = False,
    ) -> GraphAskResult:
        """Caminho mais curto com pesos (Dijkstra).

        Similar ao `path` básico, mas considera pesos nas arestas.
        Útil para "caminho mais relevante" considerando força das conexões.
        """
        start_time = time.time()

        source_id = params.get("source_id")
        target_id = params.get("target_id")
        weight_property = params.get("weight_property", "weight")  # Default: weight

        if not source_id or not target_id:
            return GraphAskResult(
                success=False,
                operation="shortest_path_weighted",
                results=[],
                result_count=0,
                execution_time_ms=0,
                error="source_id e target_id são obrigatórios",
            )

        try:
            neo4j = await self._get_neo4j()

            # Cypher usando GDS Dijkstra
            cypher = f"""
            MATCH (source {{entity_id: $source_id, tenant_id: $tenant_id}})
            MATCH (target {{entity_id: $target_id, tenant_id: $tenant_id}})
            CALL gds.graph.project(
                'dijkstra-graph-' + randomUUID(),
                '*',
                {{
                    relationshipType: '*',
                    properties: ['{weight_property}']
                }}
            )
            YIELD graphName
            CALL gds.shortestPath.dijkstra.stream(graphName, {{
                sourceNode: id(source),
                targetNode: id(target),
                relationshipWeightProperty: '{weight_property}'
            }})
            YIELD nodeIds, costs, totalCost
            CALL gds.graph.drop(graphName) YIELD graphName AS dropped
            RETURN [nodeId IN nodeIds | gds.util.asNode(nodeId).entity_id] AS path,
                   [nodeId IN nodeIds | gds.util.asNode(nodeId).name] AS path_names,
                   totalCost,
                   size(nodeIds) AS path_length
            """

            results = await neo4j.execute_cypher(
                cypher,
                {
                    "tenant_id": tenant_id,
                    "source_id": source_id,
                    "target_id": target_id,
                },
                tenant_id=tenant_id,
            )

            execution_time = int((time.time() - start_time) * 1000)

            return GraphAskResult(
                success=True,
                operation="shortest_path_weighted",
                results=results,
                result_count=len(results),
                execution_time_ms=execution_time,
                cypher_template=cypher if show_template else None,
                metadata={
                    "algorithm": "dijkstra",
                    "source_id": source_id,
                    "target_id": target_id,
                    "weight_property": weight_property,
                },
            )

        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            logger.error(f"Dijkstra shortest path failed: {e}")
            return GraphAskResult(
                success=False,
                operation="shortest_path_weighted",
                results=[],
                result_count=0,
                execution_time_ms=execution_time,
                error=str(e),
            )

    async def _handle_triangle_count(
        self,
        params: Dict[str, Any],
        tenant_id: str,
        show_template: bool = False,
    ) -> GraphAskResult:
        """Conta triângulos (trios de nós mutuamente conectados).

        Mede coesão local: nós em muitos triângulos = clusters densos.
        Útil para "artigos com alta coesão temática".
        """
        start_time = time.time()

        entity_type = params.get("entity_type", "Artigo")
        limit = min(int(params.get("limit", 20)), 100)

        try:
            neo4j = await self._get_neo4j()

            # Cypher usando GDS triangleCount
            cypher = """
            CALL gds.graph.project(
                'triangle-graph-' + randomUUID(),
                {__TYPE_LABEL__: {
                    label: '__TYPE_LABEL__',
                    properties: ['tenant_id']
                }},
                '*'
            )
            YIELD graphName
            CALL gds.triangleCount.stream(graphName)
            YIELD nodeId, triangleCount
            WITH gds.util.asNode(nodeId) AS node, triangleCount
            WHERE node.tenant_id = $tenant_id AND triangleCount > 0
            CALL gds.graph.drop(graphName) YIELD graphName AS dropped
            RETURN node.entity_id AS entity_id, node.name AS name, triangleCount
            ORDER BY triangleCount DESC
            LIMIT $limit
            """

            cypher = cypher.replace("__TYPE_LABEL__", entity_type)

            results = await neo4j.execute_cypher(
                cypher,
                {"tenant_id": tenant_id, "limit": limit},
                tenant_id=tenant_id,
            )

            execution_time = int((time.time() - start_time) * 1000)

            return GraphAskResult(
                success=True,
                operation="triangle_count",
                results=results,
                result_count=len(results),
                execution_time_ms=execution_time,
                cypher_template=cypher if show_template else None,
                metadata={"entity_type": entity_type, "algorithm": "triangleCount"},
            )

        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            logger.error(f"Triangle count failed: {e}")
            return GraphAskResult(
                success=False,
                operation="triangle_count",
                results=[],
                result_count=0,
                execution_time_ms=execution_time,
                error=str(e),
            )

    async def _handle_degree_centrality(
        self,
        params: Dict[str, Any],
        tenant_id: str,
        show_template: bool = False,
    ) -> GraphAskResult:
        """Centralidade por grau (degree centrality).

        Conta conexões diretas: nós com mais arestas = mais centrais.
        Mais simples que PageRank, útil para "artigos mais referenciados diretamente".
        """
        start_time = time.time()

        entity_type = params.get("entity_type", "Artigo")
        direction = params.get("direction", "BOTH")  # BOTH, INCOMING, OUTGOING
        limit = min(int(params.get("limit", 20)), 100)

        try:
            neo4j = await self._get_neo4j()

            # Cypher usando GDS degreeCentrality
            orientation = "NATURAL" if direction == "BOTH" else ("REVERSE" if direction == "INCOMING" else "NATURAL")

            cypher = f"""
            CALL gds.graph.project(
                'degree-graph-' + randomUUID(),
                {{__TYPE_LABEL__: {{
                    label: '__TYPE_LABEL__',
                    properties: ['tenant_id']
                }}}},
                '*'
            )
            YIELD graphName
            CALL gds.degree.stream(graphName, {{orientation: '{orientation}'}})
            YIELD nodeId, score
            WITH gds.util.asNode(nodeId) AS node, score
            WHERE node.tenant_id = $tenant_id AND score > 0
            CALL gds.graph.drop(graphName) YIELD graphName AS dropped
            RETURN node.entity_id AS entity_id, node.name AS name, score AS degree
            ORDER BY degree DESC
            LIMIT $limit
            """

            cypher = cypher.replace("__TYPE_LABEL__", entity_type)

            results = await neo4j.execute_cypher(
                cypher,
                {"tenant_id": tenant_id, "limit": limit},
                tenant_id=tenant_id,
            )

            execution_time = int((time.time() - start_time) * 1000)

            return GraphAskResult(
                success=True,
                operation="degree_centrality",
                results=results,
                result_count=len(results),
                execution_time_ms=execution_time,
                cypher_template=cypher if show_template else None,
                metadata={
                    "entity_type": entity_type,
                    "algorithm": "degreeCentrality",
                    "direction": direction,
                },
            )

        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            logger.error(f"Degree centrality failed: {e}")
            return GraphAskResult(
                success=False,
                operation="degree_centrality",
                results=[],
                result_count=0,
                execution_time_ms=execution_time,
                error=str(e),
            )

    # =========================================================================
    # GDS FASE 1: PRIORIDADE MÁXIMA
    # =========================================================================

    async def _handle_closeness_centrality(
        self,
        params: Dict[str, Any],
        tenant_id: str,
        show_template: bool = False,
    ) -> GraphAskResult:
        """Centralidade por proximidade (closeness centrality).

        Mede a distância média de um nó a todos os outros nós.
        Nós com maior closeness estão "mais perto" de todos os outros.
        Útil para identificar artigos/entidades que são hubs de acesso rápido.
        """
        start_time = time.time()

        entity_type = params.get("entity_type", "Artigo")
        limit = min(int(params.get("limit", 20)), 100)

        try:
            neo4j = await self._get_neo4j()

            # Cypher usando GDS closeness centrality
            cypher = """
            CALL gds.graph.project(
                'closeness-graph-' + randomUUID(),
                {__TYPE_LABEL__: {
                    label: '__TYPE_LABEL__',
                    properties: ['tenant_id']
                }},
                '*'
            )
            YIELD graphName
            CALL gds.closeness.stream(graphName)
            YIELD nodeId, score
            WITH gds.util.asNode(nodeId) AS node, score
            WHERE node.tenant_id = $tenant_id AND score > 0
            CALL gds.graph.drop(graphName) YIELD graphName AS dropped
            RETURN node.entity_id AS entity_id, node.name AS name, score
            ORDER BY score DESC
            LIMIT $limit
            """

            cypher = cypher.replace("__TYPE_LABEL__", entity_type)

            results = await neo4j.execute_cypher(
                cypher,
                {"tenant_id": tenant_id, "limit": limit},
                tenant_id=tenant_id,
            )

            execution_time = int((time.time() - start_time) * 1000)

            return GraphAskResult(
                success=True,
                operation="closeness_centrality",
                results=results,
                result_count=len(results),
                execution_time_ms=execution_time,
                cypher_template=cypher if show_template else None,
                metadata={"entity_type": entity_type, "algorithm": "closeness"},
            )

        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            logger.error(f"Closeness centrality failed: {e}")
            return GraphAskResult(
                success=False,
                operation="closeness_centrality",
                results=[],
                result_count=0,
                execution_time_ms=execution_time,
                error=str(e),
            )

    async def _handle_eigenvector_centrality(
        self,
        params: Dict[str, Any],
        tenant_id: str,
        show_template: bool = False,
    ) -> GraphAskResult:
        """Centralidade por autovetor (eigenvector centrality).

        Similar ao PageRank, mas sem dampingFactor. Mede importância baseada
        em conexões com outros nós importantes (recursivamente).
        Útil para identificar artigos/entidades centrais em redes de prestígio.
        """
        start_time = time.time()

        entity_type = params.get("entity_type", "Artigo")
        limit = min(int(params.get("limit", 20)), 100)
        max_iterations = min(int(params.get("max_iterations", 20)), 100)

        try:
            neo4j = await self._get_neo4j()

            # Cypher usando GDS eigenvector centrality
            cypher = f"""
            CALL gds.graph.project(
                'eigenvector-graph-' + randomUUID(),
                {{__TYPE_LABEL__: {{
                    label: '__TYPE_LABEL__',
                    properties: ['tenant_id']
                }}}},
                '*'
            )
            YIELD graphName
            CALL gds.eigenvector.stream(graphName, {{maxIterations: {max_iterations}}})
            YIELD nodeId, score
            WITH gds.util.asNode(nodeId) AS node, score
            WHERE node.tenant_id = $tenant_id AND score > 0
            CALL gds.graph.drop(graphName) YIELD graphName AS dropped
            RETURN node.entity_id AS entity_id, node.name AS name, score
            ORDER BY score DESC
            LIMIT $limit
            """

            cypher = cypher.replace("__TYPE_LABEL__", entity_type)

            results = await neo4j.execute_cypher(
                cypher,
                {"tenant_id": tenant_id, "limit": limit},
                tenant_id=tenant_id,
            )

            execution_time = int((time.time() - start_time) * 1000)

            return GraphAskResult(
                success=True,
                operation="eigenvector_centrality",
                results=results,
                result_count=len(results),
                execution_time_ms=execution_time,
                cypher_template=cypher if show_template else None,
                metadata={
                    "entity_type": entity_type,
                    "algorithm": "eigenvector",
                    "max_iterations": max_iterations,
                },
            )

        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            logger.error(f"Eigenvector centrality failed: {e}")
            return GraphAskResult(
                success=False,
                operation="eigenvector_centrality",
                results=[],
                result_count=0,
                execution_time_ms=execution_time,
                error=str(e),
            )

    async def _handle_leiden(
        self,
        params: Dict[str, Any],
        tenant_id: str,
        show_template: bool = False,
    ) -> GraphAskResult:
        """Detecção de comunidades com Leiden.

        Sucessor do algoritmo Louvain, com melhor qualidade de particionamento.
        Agrupa nós em comunidades maximizando modularidade.
        Útil para descobrir clusters temáticos no grafo jurídico.
        """
        start_time = time.time()

        entity_type = params.get("entity_type", "Artigo")
        limit = min(int(params.get("limit", 50)), 200)

        try:
            neo4j = await self._get_neo4j()

            # Cypher usando GDS Leiden
            cypher = """
            CALL gds.graph.project(
                'leiden-graph-' + randomUUID(),
                {__TYPE_LABEL__: {
                    label: '__TYPE_LABEL__',
                    properties: ['tenant_id']
                }},
                '*'
            )
            YIELD graphName
            CALL gds.leiden.stream(graphName)
            YIELD nodeId, communityId
            WITH gds.util.asNode(nodeId) AS node, communityId
            WHERE node.tenant_id = $tenant_id
            CALL gds.graph.drop(graphName) YIELD graphName AS dropped
            RETURN node.entity_id AS entity_id, node.name AS name, communityId AS community_id
            ORDER BY community_id, node.name
            LIMIT $limit
            """

            cypher = cypher.replace("__TYPE_LABEL__", entity_type)

            results = await neo4j.execute_cypher(
                cypher,
                {"tenant_id": tenant_id, "limit": limit},
                tenant_id=tenant_id,
            )

            execution_time = int((time.time() - start_time) * 1000)

            return GraphAskResult(
                success=True,
                operation="leiden",
                results=results,
                result_count=len(results),
                execution_time_ms=execution_time,
                cypher_template=cypher if show_template else None,
                metadata={"entity_type": entity_type, "algorithm": "leiden"},
            )

        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            logger.error(f"Leiden community detection failed: {e}")
            return GraphAskResult(
                success=False,
                operation="leiden",
                results=[],
                result_count=0,
                execution_time_ms=execution_time,
                error=str(e),
            )

    async def _handle_k_core_decomposition(
        self,
        params: Dict[str, Any],
        tenant_id: str,
        show_template: bool = False,
    ) -> GraphAskResult:
        """Decomposição k-core.

        Identifica subgrafos densos onde cada nó tem pelo menos k conexões.
        coreValue maior = nó está em núcleos mais densos/coesos.
        Útil para identificar clusters fortemente conectados.
        """
        start_time = time.time()

        entity_type = params.get("entity_type", "Artigo")
        limit = min(int(params.get("limit", 50)), 200)

        try:
            neo4j = await self._get_neo4j()

            # Cypher usando GDS k-core
            cypher = """
            CALL gds.graph.project(
                'kcore-graph-' + randomUUID(),
                {__TYPE_LABEL__: {
                    label: '__TYPE_LABEL__',
                    properties: ['tenant_id']
                }},
                '*'
            )
            YIELD graphName
            CALL gds.kcore.stream(graphName)
            YIELD nodeId, coreValue
            WITH gds.util.asNode(nodeId) AS node, coreValue
            WHERE node.tenant_id = $tenant_id AND coreValue > 0
            CALL gds.graph.drop(graphName) YIELD graphName AS dropped
            RETURN node.entity_id AS entity_id, node.name AS name, coreValue AS core_value
            ORDER BY core_value DESC, node.name
            LIMIT $limit
            """

            cypher = cypher.replace("__TYPE_LABEL__", entity_type)

            results = await neo4j.execute_cypher(
                cypher,
                {"tenant_id": tenant_id, "limit": limit},
                tenant_id=tenant_id,
            )

            execution_time = int((time.time() - start_time) * 1000)

            return GraphAskResult(
                success=True,
                operation="k_core_decomposition",
                results=results,
                result_count=len(results),
                execution_time_ms=execution_time,
                cypher_template=cypher if show_template else None,
                metadata={"entity_type": entity_type, "algorithm": "k-core"},
            )

        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            logger.error(f"K-core decomposition failed: {e}")
            return GraphAskResult(
                success=False,
                operation="k_core_decomposition",
                results=[],
                result_count=0,
                execution_time_ms=execution_time,
                error=str(e),
            )

    async def _handle_knn(
        self,
        params: Dict[str, Any],
        tenant_id: str,
        show_template: bool = False,
    ) -> GraphAskResult:
        """K-Nearest Neighbors (KNN) via GDS.

        Encontra os top-K nós mais similares a cada nó, baseado em vizinhança.
        Útil para recomendações e descoberta de entidades relacionadas.
        """
        start_time = time.time()

        entity_type = params.get("entity_type", "Artigo")
        top_k = min(int(params.get("top_k", 10)), 50)
        limit = min(int(params.get("limit", 50)), 200)

        try:
            neo4j = await self._get_neo4j()

            # Cypher usando GDS KNN
            # Nota: KNN retorna pares (node1, node2, similarity)
            cypher = f"""
            CALL gds.graph.project(
                'knn-graph-' + randomUUID(),
                {{__TYPE_LABEL__: {{
                    label: '__TYPE_LABEL__',
                    properties: ['tenant_id']
                }}}},
                '*'
            )
            YIELD graphName
            CALL gds.knn.stream(graphName, {{topK: {top_k}}})
            YIELD node1, node2, similarity
            WITH gds.util.asNode(node1) AS n1, gds.util.asNode(node2) AS n2, similarity
            WHERE n1.tenant_id = $tenant_id AND n2.tenant_id = $tenant_id AND similarity > 0
            CALL gds.graph.drop(graphName) YIELD graphName AS dropped
            RETURN n1.entity_id AS node1_id, n1.name AS node1_name,
                   n2.entity_id AS node2_id, n2.name AS node2_name,
                   similarity
            ORDER BY similarity DESC
            LIMIT $limit
            """

            cypher = cypher.replace("__TYPE_LABEL__", entity_type)

            results = await neo4j.execute_cypher(
                cypher,
                {"tenant_id": tenant_id, "limit": limit},
                tenant_id=tenant_id,
            )

            execution_time = int((time.time() - start_time) * 1000)

            return GraphAskResult(
                success=True,
                operation="knn",
                results=results,
                result_count=len(results),
                execution_time_ms=execution_time,
                cypher_template=cypher if show_template else None,
                metadata={
                    "entity_type": entity_type,
                    "algorithm": "knn",
                    "top_k": top_k,
                },
            )

        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            logger.error(f"KNN failed: {e}")
            return GraphAskResult(
                success=False,
                operation="knn",
                results=[],
                result_count=0,
                execution_time_ms=execution_time,
                error=str(e),
            )

    async def _handle_bridges(
        self,
        params: Dict[str, Any],
        tenant_id: str,
        show_template: bool = False,
    ) -> GraphAskResult:
        """Identifica arestas cuja remoção desconecta o grafo (pontes).

        Bridges são conexões críticas: se removidas, partem o grafo em componentes desconexos.
        Útil para "quais relações são indispensáveis para conectividade".
        """
        start_time = time.time()

        entity_type = params.get("entity_type", "Artigo")
        limit = min(int(params.get("limit", 50)), 200)

        try:
            neo4j = await self._get_neo4j()

            # Cypher usando GDS bridges
            cypher = """
            CALL gds.graph.project(
                'bridges-graph-' + randomUUID(),
                {__TYPE_LABEL__: {
                    label: '__TYPE_LABEL__',
                    properties: ['tenant_id']
                }},
                '*'
            )
            YIELD graphName
            CALL gds.bridges.stream(graphName)
            YIELD from, to
            WITH gds.util.asNode(from) AS fromNode, gds.util.asNode(to) AS toNode
            WHERE fromNode.tenant_id = $tenant_id AND toNode.tenant_id = $tenant_id
            CALL gds.graph.drop(graphName) YIELD graphName AS dropped
            RETURN fromNode.entity_id AS from_entity_id, fromNode.name AS from_name,
                   toNode.entity_id AS to_entity_id, toNode.name AS to_name
            LIMIT $limit
            """

            cypher = cypher.replace("__TYPE_LABEL__", entity_type)

            results = await neo4j.execute_cypher(
                cypher,
                {"tenant_id": tenant_id, "limit": limit},
                tenant_id=tenant_id,
            )

            execution_time = int((time.time() - start_time) * 1000)

            return GraphAskResult(
                success=True,
                operation="bridges",
                results=results,
                result_count=len(results),
                execution_time_ms=execution_time,
                cypher_template=cypher if show_template else None,
                metadata={
                    "entity_type": entity_type,
                    "algorithm": "bridges",
                },
            )

        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            logger.error(f"Bridges detection failed: {e}")
            return GraphAskResult(
                success=False,
                operation="bridges",
                results=[],
                result_count=0,
                execution_time_ms=execution_time,
                error=str(e),
            )

    async def _handle_articulation_points(
        self,
        params: Dict[str, Any],
        tenant_id: str,
        show_template: bool = False,
    ) -> GraphAskResult:
        """Identifica nós cuja remoção desconecta o grafo (pontos de articulação).

        Articulation points são nós críticos: se removidos, aumentam o número de componentes.
        Útil para "quais artigos/conceitos são pontos únicos de falha na conectividade".
        """
        start_time = time.time()

        entity_type = params.get("entity_type", "Artigo")
        limit = min(int(params.get("limit", 50)), 200)

        try:
            neo4j = await self._get_neo4j()

            # Cypher usando GDS articulationPoints
            cypher = """
            CALL gds.graph.project(
                'articulation-graph-' + randomUUID(),
                {__TYPE_LABEL__: {
                    label: '__TYPE_LABEL__',
                    properties: ['tenant_id']
                }},
                '*'
            )
            YIELD graphName
            CALL gds.articulationPoints.stream(graphName)
            YIELD nodeId
            WITH gds.util.asNode(nodeId) AS node
            WHERE node.tenant_id = $tenant_id
            CALL gds.graph.drop(graphName) YIELD graphName AS dropped
            RETURN node.entity_id AS entity_id, node.name AS name
            LIMIT $limit
            """

            cypher = cypher.replace("__TYPE_LABEL__", entity_type)

            results = await neo4j.execute_cypher(
                cypher,
                {"tenant_id": tenant_id, "limit": limit},
                tenant_id=tenant_id,
            )

            execution_time = int((time.time() - start_time) * 1000)

            return GraphAskResult(
                success=True,
                operation="articulation_points",
                results=results,
                result_count=len(results),
                execution_time_ms=execution_time,
                cypher_template=cypher if show_template else None,
                metadata={
                    "entity_type": entity_type,
                    "algorithm": "articulationPoints",
                },
            )

        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            logger.error(f"Articulation points detection failed: {e}")
            return GraphAskResult(
                success=False,
                operation="articulation_points",
                results=[],
                result_count=0,
                execution_time_ms=execution_time,
                error=str(e),
            )

    async def _handle_strongly_connected_components(
        self,
        params: Dict[str, Any],
        tenant_id: str,
        show_template: bool = False,
    ) -> GraphAskResult:
        """Identifica componentes fortemente conectados (SCCs) em grafos direcionados.

        SCCs são subgrafos onde qualquer nó alcança qualquer outro nó.
        Útil para detectar ciclos de referência mútua (ex: Art. A → B → C → A).
        """
        start_time = time.time()

        entity_type = params.get("entity_type", "Artigo")
        limit = min(int(params.get("limit", 100)), 500)

        try:
            neo4j = await self._get_neo4j()

            # Cypher usando GDS alpha.scc (ou gds.scc se disponível na versão)
            # Nota: gds.scc.stream pode variar entre versões, tentamos alpha.scc primeiro
            cypher = """
            CALL gds.graph.project(
                'scc-graph-' + randomUUID(),
                {__TYPE_LABEL__: {
                    label: '__TYPE_LABEL__',
                    properties: ['tenant_id']
                }},
                '*'
            )
            YIELD graphName
            CALL gds.alpha.scc.stream(graphName)
            YIELD nodeId, componentId
            WITH gds.util.asNode(nodeId) AS node, componentId
            WHERE node.tenant_id = $tenant_id
            CALL gds.graph.drop(graphName) YIELD graphName AS dropped
            RETURN node.entity_id AS entity_id, node.name AS name, componentId AS component_id
            ORDER BY component_id, entity_id
            LIMIT $limit
            """

            cypher = cypher.replace("__TYPE_LABEL__", entity_type)

            results = await neo4j.execute_cypher(
                cypher,
                {"tenant_id": tenant_id, "limit": limit},
                tenant_id=tenant_id,
            )

            execution_time = int((time.time() - start_time) * 1000)

            return GraphAskResult(
                success=True,
                operation="strongly_connected_components",
                results=results,
                result_count=len(results),
                execution_time_ms=execution_time,
                cypher_template=cypher if show_template else None,
                metadata={
                    "entity_type": entity_type,
                    "algorithm": "scc",
                },
            )

        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            logger.error(f"Strongly connected components detection failed: {e}")
            return GraphAskResult(
                success=False,
                operation="strongly_connected_components",
                results=[],
                result_count=0,
                execution_time_ms=execution_time,
                error=str(e),
            )

    async def _handle_yens_k_shortest_paths(
        self,
        params: Dict[str, Any],
        tenant_id: str,
        show_template: bool = False,
    ) -> GraphAskResult:
        """Calcula K caminhos mais curtos alternativos entre dois nós (Yen's algorithm).

        Diferente de shortest_path (que retorna apenas 1), este retorna múltiplas rotas.
        Útil para "quais são os 3 caminhos mais curtos entre Art. X e Art. Y".
        """
        start_time = time.time()

        source_id = params.get("source_id")
        target_id = params.get("target_id")
        k = min(int(params.get("k", 3)), 10)  # Máximo 10 caminhos
        entity_type = params.get("entity_type", "Artigo")

        # Validação de parâmetros obrigatórios
        if not source_id or not target_id:
            return GraphAskResult(
                success=False,
                operation="yens_k_shortest_paths",
                results=[],
                result_count=0,
                execution_time_ms=0,
                error="source_id e target_id são obrigatórios para Yen's K Shortest Paths",
            )

        try:
            neo4j = await self._get_neo4j()

            # Cypher usando GDS shortestPath.yens
            cypher = """
            MATCH (source:__TYPE_LABEL__ {entity_id: $source_id, tenant_id: $tenant_id})
            MATCH (target:__TYPE_LABEL__ {entity_id: $target_id, tenant_id: $tenant_id})
            CALL gds.graph.project(
                'yens-graph-' + randomUUID(),
                {__TYPE_LABEL__: {
                    label: '__TYPE_LABEL__',
                    properties: ['tenant_id']
                }},
                '*'
            )
            YIELD graphName
            CALL gds.shortestPath.yens.stream(graphName, {
                sourceNode: source,
                targetNode: target,
                k: $k
            })
            YIELD index, nodeIds, costs, totalCost
            CALL gds.graph.drop(graphName) YIELD graphName AS dropped
            WITH index, [nodeId IN nodeIds | gds.util.asNode(nodeId).entity_id] AS path, totalCost
            RETURN index AS path_index, path, totalCost AS total_cost
            ORDER BY index
            """

            cypher = cypher.replace("__TYPE_LABEL__", entity_type)

            results = await neo4j.execute_cypher(
                cypher,
                {"tenant_id": tenant_id, "source_id": source_id, "target_id": target_id, "k": k},
                tenant_id=tenant_id,
            )

            execution_time = int((time.time() - start_time) * 1000)

            return GraphAskResult(
                success=True,
                operation="yens_k_shortest_paths",
                results=results,
                result_count=len(results),
                execution_time_ms=execution_time,
                cypher_template=cypher if show_template else None,
                metadata={
                    "entity_type": entity_type,
                    "algorithm": "yens",
                    "source_id": source_id,
                    "target_id": target_id,
                    "k": k,
                },
            )

        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            logger.error(f"Yen's K shortest paths failed: {e}")
            return GraphAskResult(
                success=False,
                operation="yens_k_shortest_paths",
                results=[],
                result_count=0,
                execution_time_ms=execution_time,
                error=str(e),
            )


    async def _handle_adamic_adar(
        self,
        params: Dict[str, Any],
        tenant_id: str,
        show_template: bool = False,
    ) -> GraphAskResult:
        """Adamic-Adar coefficient para link prediction.

        Mede "força" de ligação potencial entre dois nós baseada em vizinhos comuns ponderados.
        Score alto = muitos vizinhos comuns raros (mais indicativo de link).
        """
        start_time = time.time()

        node1_id = params.get("node1_id")
        node2_id = params.get("node2_id")

        if not node1_id or not node2_id:
            return GraphAskResult(
                success=False,
                operation="adamic_adar",
                results=[],
                result_count=0,
                execution_time_ms=0,
                error="Parâmetros obrigatórios: node1_id, node2_id",
            )

        try:
            # Verificar disponibilidade GDS
            if not await self._check_gds_available():
                return GraphAskResult(
                    success=False,
                    operation="adamic_adar",
                    results=[],
                    result_count=0,
                    execution_time_ms=0,
                    error="GDS plugin não disponível",
                )

            neo4j = await self._get_neo4j()

            # adamic_adar é uma FUNÇÃO, não stream
            cypher = """
            MATCH (n1 {tenant_id: $tenant_id, entity_id: $node1_id})
            MATCH (n2 {tenant_id: $tenant_id, entity_id: $node2_id})
            CALL gds.graph.project(
                'adamic-adar-graph-' + randomUUID(),
                {properties: ['tenant_id']},
                '*'
            )
            YIELD graphName
            WITH graphName, n1, n2
            CALL gds.linkPrediction.adamicAdar(graphName, id(n1), id(n2))
            YIELD score
            CALL gds.graph.drop(graphName) YIELD graphName AS dropped
            RETURN $node1_id AS node1, $node2_id AS node2, score
            """

            results = await neo4j.execute_cypher(
                cypher,
                {
                    "tenant_id": tenant_id,
                    "node1_id": node1_id,
                    "node2_id": node2_id,
                },
                tenant_id=tenant_id,
            )

            execution_time = int((time.time() - start_time) * 1000)

            return GraphAskResult(
                success=True,
                operation="adamic_adar",
                results=results,
                result_count=len(results),
                execution_time_ms=execution_time,
                cypher_template=cypher if show_template else None,
                metadata={
                    "algorithm": "adamicAdar",
                    "node1_id": node1_id,
                    "node2_id": node2_id,
                },
            )

        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            logger.error(f"Adamic-Adar failed: {e}")
            return GraphAskResult(
                success=False,
                operation="adamic_adar",
                results=[],
                result_count=0,
                execution_time_ms=execution_time,
                error=str(e),
            )

    async def _handle_node2vec(
        self,
        params: Dict[str, Any],
        tenant_id: str,
        show_template: bool = False,
    ) -> GraphAskResult:
        """Node2Vec: embeddings vetoriais para ML.

        Gera representações vetoriais (embeddings) de nós via random walks.
        Útil para: similaridade, classificação, clustering de entidades.
        """
        start_time = time.time()

        entity_type = params.get("entity_type", "Artigo")
        embedding_dimension = int(params.get("embedding_dimension", 128))
        iterations = int(params.get("iterations", 10))
        limit = min(int(params.get("limit", 100)), 500)

        try:
            # Verificar disponibilidade GDS
            if not await self._check_gds_available():
                return GraphAskResult(
                    success=False,
                    operation="node2vec",
                    results=[],
                    result_count=0,
                    execution_time_ms=0,
                    error="GDS plugin não disponível",
                )

            neo4j = await self._get_neo4j()

            cypher = f"""
            CALL gds.graph.project(
                'node2vec-graph-' + randomUUID(),
                {{__TYPE_LABEL__: {{
                    label: '__TYPE_LABEL__',
                    properties: ['tenant_id']
                }}}},
                '*'
            )
            YIELD graphName
            CALL gds.node2vec.stream(graphName, {{
                embeddingDimension: $embedding_dimension,
                iterations: $iterations
            }})
            YIELD nodeId, embedding
            WITH gds.util.asNode(nodeId) AS node, embedding
            WHERE node.tenant_id = $tenant_id
            CALL gds.graph.drop(graphName) YIELD graphName AS dropped
            RETURN node.entity_id AS entity_id, node.name AS name, embedding
            LIMIT $limit
            """

            cypher = cypher.replace("__TYPE_LABEL__", entity_type)

            results = await neo4j.execute_cypher(
                cypher,
                {
                    "tenant_id": tenant_id,
                    "embedding_dimension": embedding_dimension,
                    "iterations": iterations,
                    "limit": limit,
                },
                tenant_id=tenant_id,
            )

            execution_time = int((time.time() - start_time) * 1000)

            return GraphAskResult(
                success=True,
                operation="node2vec",
                results=results,
                result_count=len(results),
                execution_time_ms=execution_time,
                cypher_template=cypher if show_template else None,
                metadata={
                    "algorithm": "node2vec",
                    "entity_type": entity_type,
                    "embedding_dimension": embedding_dimension,
                    "iterations": iterations,
                },
            )

        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            logger.error(f"Node2Vec failed: {e}")
            return GraphAskResult(
                success=False,
                operation="node2vec",
                results=[],
                result_count=0,
                execution_time_ms=execution_time,
                error=str(e),
            )

    async def _handle_all_pairs_shortest_path(
        self,
        params: Dict[str, Any],
        tenant_id: str,
        show_template: bool = False,
    ) -> GraphAskResult:
        """All-Pairs Shortest Path: matriz de distâncias completa.

        Calcula caminho mais curto entre TODOS os pares de nós.
        Útil para análise de conectividade global e grafos de distâncias.
        """
        start_time = time.time()

        entity_type = params.get("entity_type", "Artigo")
        limit = min(int(params.get("limit", 1000)), 10000)  # Pode retornar muitos pares

        try:
            # Verificar disponibilidade GDS
            if not await self._check_gds_available():
                return GraphAskResult(
                    success=False,
                    operation="all_pairs_shortest_path",
                    results=[],
                    result_count=0,
                    execution_time_ms=0,
                    error="GDS plugin não disponível",
                )

            neo4j = await self._get_neo4j()

            cypher = """
            CALL gds.graph.project(
                'allpairs-graph-' + randomUUID(),
                {__TYPE_LABEL__: {
                    label: '__TYPE_LABEL__',
                    properties: ['tenant_id']
                }},
                '*'
            )
            YIELD graphName
            CALL gds.allShortestPaths.stream(graphName)
            YIELD sourceNodeId, targetNodeId, distance
            WITH
                gds.util.asNode(sourceNodeId) AS source,
                gds.util.asNode(targetNodeId) AS target,
                distance
            WHERE source.tenant_id = $tenant_id AND target.tenant_id = $tenant_id
            WITH graphName, source.entity_id AS source, target.entity_id AS target, distance
            CALL gds.graph.drop(graphName) YIELD graphName AS dropped
            RETURN source, target, distance
            ORDER BY distance ASC
            LIMIT $limit
            """

            cypher = cypher.replace("__TYPE_LABEL__", entity_type)

            results = await neo4j.execute_cypher(
                cypher,
                {"tenant_id": tenant_id, "limit": limit},
                tenant_id=tenant_id,
            )

            execution_time = int((time.time() - start_time) * 1000)

            return GraphAskResult(
                success=True,
                operation="all_pairs_shortest_path",
                results=results,
                result_count=len(results),
                execution_time_ms=execution_time,
                cypher_template=cypher if show_template else None,
                metadata={
                    "algorithm": "allShortestPaths",
                    "entity_type": entity_type,
                },
            )

        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            logger.error(f"All-pairs shortest path failed: {e}")
            return GraphAskResult(
                success=False,
                operation="all_pairs_shortest_path",
                results=[],
                result_count=0,
                execution_time_ms=execution_time,
                error=str(e),
            )

    async def _handle_harmonic_centrality(
        self,
        params: Dict[str, Any],
        tenant_id: str,
        show_template: bool = False,
    ) -> GraphAskResult:
        """Harmonic Centrality: closeness robusta para grafos desconectados.

        Variante de closeness que funciona bem em grafos com componentes desconectados.
        Usa média harmônica das distâncias (distância infinita → contribuição 0).
        """
        start_time = time.time()

        entity_type = params.get("entity_type", "Artigo")
        limit = min(int(params.get("limit", 20)), 100)

        try:
            # Verificar disponibilidade GDS
            if not await self._check_gds_available():
                return GraphAskResult(
                    success=False,
                    operation="harmonic_centrality",
                    results=[],
                    result_count=0,
                    execution_time_ms=0,
                    error="GDS plugin não disponível",
                )

            neo4j = await self._get_neo4j()

            cypher = """
            CALL gds.graph.project(
                'harmonic-graph-' + randomUUID(),
                {__TYPE_LABEL__: {
                    label: '__TYPE_LABEL__',
                    properties: ['tenant_id']
                }},
                '*'
            )
            YIELD graphName
            CALL gds.closeness.harmonic.stream(graphName)
            YIELD nodeId, score
            WITH gds.util.asNode(nodeId) AS node, score
            WHERE node.tenant_id = $tenant_id AND score > 0
            CALL gds.graph.drop(graphName) YIELD graphName AS dropped
            RETURN node.entity_id AS entity_id, node.name AS name, score
            ORDER BY score DESC
            LIMIT $limit
            """

            cypher = cypher.replace("__TYPE_LABEL__", entity_type)

            results = await neo4j.execute_cypher(
                cypher,
                {"tenant_id": tenant_id, "limit": limit},
                tenant_id=tenant_id,
            )

            execution_time = int((time.time() - start_time) * 1000)

            return GraphAskResult(
                success=True,
                operation="harmonic_centrality",
                results=results,
                result_count=len(results),
                execution_time_ms=execution_time,
                cypher_template=cypher if show_template else None,
                metadata={
                    "algorithm": "harmonicCentrality",
                    "entity_type": entity_type,
                },
            )

        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            logger.error(f"Harmonic centrality failed: {e}")
            return GraphAskResult(
                success=False,
                operation="harmonic_centrality",
                results=[],
                result_count=0,
                execution_time_ms=execution_time,
                error=str(e),
            )

# =============================================================================
# TEXT2CYPHER ENGINE — 3 camadas de segurança multi-tenant
# =============================================================================


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.lower() in ("1", "true", "yes", "on")


class CypherSecurityError(Exception):
    """Raised when generated Cypher fails security validation."""


_WRITE_KEYWORDS: Set[str] = {
    "CREATE", "MERGE", "DELETE", "DETACH", "SET", "REMOVE",
    "DROP", "CALL", "FOREACH", "LOAD",
}

_ALLOWED_STARTS = {"MATCH", "OPTIONAL", "WITH", "RETURN", "UNWIND"}


def validate_cypher_readonly(cypher: str) -> Optional[str]:
    """
    Valida que Cypher é read-only. Retorna mensagem de erro ou None se OK.

    Camada 1: Keyword blocklist (rejeita qualquer keyword de escrita).
    Camada 3: Validação estrutural (deve começar com MATCH/WITH/RETURN e conter RETURN).
    """
    if not cypher or not cypher.strip():
        return "Cypher vazio"

    upper = cypher.upper().strip()

    # Camada 1: Blocklist de keywords de escrita
    # Tokeniza para evitar falsos positivos (ex: "CREATED_AT" não deve triggar "CREATE")
    tokens = set(re.findall(r'\b[A-Z_]+\b', upper))
    blocked = tokens & _WRITE_KEYWORDS
    if blocked:
        return f"Keywords de escrita detectadas: {blocked}"

    # Camada 3: Validação estrutural
    first_word = upper.split()[0] if upper.split() else ""
    if first_word not in _ALLOWED_STARTS:
        return f"Cypher deve começar com {_ALLOWED_STARTS}, mas começa com '{first_word}'"

    if "RETURN" not in upper:
        return "Cypher deve conter RETURN"

    return None


def inject_tenant_filter(
    cypher: str,
    tenant_id: str,
    scope: Optional[str] = None,
    case_id: Optional[str] = None,
    include_global: bool = True,
) -> str:
    """
    Camada 2: Injeta filtro de tenant_id no Cypher gerado.

    Encontra padrões (var:Document) e adiciona WHERE clauses de segurança.
    Se não encontrar Document, envolve com prefix filter via _allowed_docs.
    """
    doc_pattern = re.compile(r'\((\w+):Document\b', re.IGNORECASE)
    matches = doc_pattern.findall(cypher)

    if not matches:
        return _wrap_with_tenant_prefix(cypher, scope, case_id, include_global)

    # Para cada variável Document, injetar filtros via WHERE append
    for var_name in set(matches):
        clauses = _build_tenant_clauses(var_name, include_global, scope, case_id)
        # Encontrar WHERE existente para este bloco ou adicionar novo
        cypher = _append_where_clauses(cypher, var_name, clauses)

    return cypher


def _build_tenant_clauses(
    var_name: str,
    include_global: bool,
    scope: Optional[str],
    case_id: Optional[str],
) -> List[str]:
    """Constrói lista de clauses de filtro para nó Document."""
    clauses = []
    if include_global:
        clauses.append(f"({var_name}.tenant_id = $tenant_id OR {var_name}.scope = 'global')")
    else:
        clauses.append(f"{var_name}.tenant_id = $tenant_id")

    clauses.append(f"({var_name}.sigilo IS NULL OR {var_name}.sigilo = false)")

    if scope:
        clauses.append(f"{var_name}.scope = $scope")

    if case_id:
        clauses.append(f"{var_name}.case_id = $case_id")

    return clauses


def _append_where_clauses(cypher: str, var_name: str, clauses: List[str]) -> str:
    """Adiciona clauses de filtro ao Cypher, respeitando WHERE existente."""
    if not clauses:
        return cypher

    filter_str = " AND ".join(clauses)

    # Procurar WHERE existente após o MATCH com este Document
    # Estratégia: encontrar o próximo WHERE ou RETURN/WITH/ORDER e inserir antes
    doc_match = re.search(rf'\({var_name}:Document\b[^)]*\)', cypher, re.IGNORECASE)
    if not doc_match:
        return cypher

    after_doc = cypher[doc_match.end():]

    # Se já tem WHERE, adicionar com AND
    where_match = re.search(r'\bWHERE\b', after_doc, re.IGNORECASE)
    if where_match:
        insert_pos = doc_match.end() + where_match.end()
        cypher = cypher[:insert_pos] + f" {filter_str} AND" + cypher[insert_pos:]
    else:
        # Adicionar WHERE antes do próximo keyword (RETURN, WITH, ORDER)
        next_keyword = re.search(r'\b(RETURN|WITH|ORDER|LIMIT)\b', after_doc, re.IGNORECASE)
        if next_keyword:
            insert_pos = doc_match.end() + next_keyword.start()
            cypher = cypher[:insert_pos] + f"\n  WHERE {filter_str}\n  " + cypher[insert_pos:]
        else:
            # Fallback: append no final
            cypher += f"\n  WHERE {filter_str}"

    return cypher


def _wrap_with_tenant_prefix(
    cypher: str,
    scope: Optional[str],
    case_id: Optional[str],
    include_global: bool,
) -> str:
    """Envolve query com prefix filter quando não há Document no Cypher."""
    if include_global:
        scope_filter = "(d.tenant_id = $tenant_id OR d.scope = 'global')"
    else:
        scope_filter = "d.tenant_id = $tenant_id"

    extra_filters = " AND (d.sigilo IS NULL OR d.sigilo = false)"
    if scope:
        extra_filters += " AND d.scope = $scope"
    if case_id:
        extra_filters += " AND d.case_id = $case_id"

    prefix = (
        f"MATCH (d:Document) WHERE {scope_filter}{extra_filters}\n"
        f"WITH collect(DISTINCT d.doc_hash) AS _allowed_docs\n"
    )
    return prefix + cypher


_TEXT2CYPHER_SYSTEM_PROMPT = """You are a Cypher query generator for a Brazilian legal knowledge graph in Neo4j.

You MUST generate ONLY read-only Cypher queries (MATCH/RETURN). NEVER use CREATE, MERGE, DELETE, SET, REMOVE, or DROP.

{schema}

IMPORTANT RULES:
1. Always use parameterized queries with $tenant_id, $scope, $case_id, $include_global
2. Filter Document nodes: (d.tenant_id = $tenant_id OR ($include_global = true AND d.scope = 'global'))
3. Always add: (d.sigilo IS NULL OR d.sigilo = false)
4. Use LIMIT to cap results (max 50)
5. Return meaningful columns with aliases
6. For entity search, use toLower() + CONTAINS for fuzzy matching
7. The graph is in Portuguese (Brazilian legal domain)

Example queries:
- "Quais leis são mais citadas?" →
  MATCH (e:Entity)<-[:MENTIONS]-(c:Chunk)<-[:HAS_CHUNK]-(d:Document)
  WHERE e.entity_type = 'lei'
    AND (d.tenant_id = $tenant_id OR ($include_global = true AND d.scope = 'global'))
    AND (d.sigilo IS NULL OR d.sigilo = false)
  RETURN e.name AS lei, count(DISTINCT c) AS mencoes
  ORDER BY mencoes DESC LIMIT 20

- "Relação entre Lei 8.666 e Súmula 331" →
  MATCH (e1:Entity)<-[:MENTIONS]-(c:Chunk)-[:MENTIONS]->(e2:Entity)
  MATCH (d:Document)-[:HAS_CHUNK]->(c)
  WHERE toLower(e1.name) CONTAINS '8.666' AND toLower(e2.name) CONTAINS '331'
    AND (d.tenant_id = $tenant_id OR ($include_global = true AND d.scope = 'global'))
    AND (d.sigilo IS NULL OR d.sigilo = false)
  RETURN e1.name AS entity1, e2.name AS entity2, count(c) AS cooccurrences,
         collect(DISTINCT left(c.text_preview, 200))[0..3] AS contextos
  LIMIT 10
"""


class Text2CypherEngine:
    """Engine que converte linguagem natural em Cypher seguro."""

    def __init__(self):
        self._llm_client = None

    def _get_llm_client(self):
        """Obtém cliente LLM para geração de Cypher."""
        if self._llm_client is not None:
            return self._llm_client

        provider = os.getenv("TEXT2CYPHER_LLM_PROVIDER", "openai").lower()
        model = os.getenv("TEXT2CYPHER_MODEL", "gpt-4o-mini")

        if provider == "openai":
            import openai
            self._llm_client = ("openai", openai.AsyncOpenAI(), model)
        elif provider in ("gemini", "google"):
            from google import genai
            client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY", ""))
            self._llm_client = ("gemini", client, model or "gemini-2.0-flash")
        elif provider == "anthropic":
            import anthropic
            self._llm_client = ("anthropic", anthropic.AsyncAnthropic(), model or "claude-sonnet-4-5-20250929")
        else:
            raise ValueError(f"TEXT2CYPHER_LLM_PROVIDER não suportado: {provider}")

        return self._llm_client

    async def _generate_cypher(self, question: str) -> str:
        """Gera Cypher a partir de pergunta usando LLM."""
        from app.services.rag.core.kg_builder.legal_schema import get_schema_description

        schema_desc = get_schema_description()
        system_prompt = _TEXT2CYPHER_SYSTEM_PROMPT.format(schema=schema_desc)

        provider, client, model = self._get_llm_client()

        if provider == "openai":
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Pergunta: {question}\n\nGere APENAS o Cypher, sem explicação:"},
                ],
                temperature=0.0,
                max_tokens=500,
            )
            return response.choices[0].message.content.strip()

        elif provider == "gemini":
            response = client.models.generate_content(
                model=model,
                contents=f"{system_prompt}\n\nPergunta: {question}\n\nGere APENAS o Cypher, sem explicação:",
            )
            return response.text.strip()

        elif provider == "anthropic":
            response = await client.messages.create(
                model=model,
                max_tokens=500,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": f"Pergunta: {question}\n\nGere APENAS o Cypher, sem explicação:"},
                ],
            )
            return response.content[0].text.strip()

        raise ValueError(f"Provider desconhecido: {provider}")

    async def generate_and_execute(
        self,
        question: str,
        neo4j_service,
        tenant_id: str,
        scope: Optional[str] = None,
        case_id: Optional[str] = None,
        include_global: bool = True,
    ) -> Dict[str, Any]:
        """
        Gera Cypher, valida segurança, injeta filtros e executa.

        Returns:
            Dict com 'results', 'cypher', 'cypher_sanitized'
        """
        import asyncio

        # 1. Gerar Cypher via LLM
        raw_cypher = await self._generate_cypher(question)

        # Limpar markdown code fences
        cypher = raw_cypher.strip()
        if cypher.startswith("```"):
            cypher = re.sub(r'^```(?:cypher)?\s*', '', cypher)
            cypher = re.sub(r'\s*```$', '', cypher)

        # 2. Camada 1+3: Validar read-only + estrutura
        validation_error = validate_cypher_readonly(cypher)
        if validation_error:
            raise CypherSecurityError(validation_error)

        # 3. Camada 2: Injetar filtros de tenant
        sanitized_cypher = inject_tenant_filter(
            cypher, tenant_id, scope, case_id, include_global,
        )

        # 4. Garantir LIMIT
        if "LIMIT" not in sanitized_cypher.upper():
            sanitized_cypher += "\nLIMIT 50"

        # 5. Executar
        params = {
            "tenant_id": tenant_id,
            "scope": scope,
            "case_id": case_id,
            "include_global": bool(include_global),
        }

        try:
            results = await asyncio.wait_for(
                neo4j_service._execute_read_async(sanitized_cypher, params),
                timeout=10.0,
            )
        except asyncio.TimeoutError:
            raise TimeoutError("Text2Cypher query excedeu timeout de 10s")

        return {
            "results": results or [],
            "cypher": raw_cypher,
            "cypher_sanitized": sanitized_cypher,
        }


# =============================================================================
# SINGLETONS
# =============================================================================

_graph_ask_service: Optional[GraphAskService] = None
_text2cypher_engine: Optional[Text2CypherEngine] = None


def get_graph_ask_service() -> GraphAskService:
    """Obtém instância singleton do GraphAskService."""
    global _graph_ask_service
    if _graph_ask_service is None:
        _graph_ask_service = GraphAskService()
    return _graph_ask_service


def get_text2cypher_engine() -> Text2CypherEngine:
    """Obtém instância singleton do Text2CypherEngine."""
    global _text2cypher_engine
    if _text2cypher_engine is None:
        _text2cypher_engine = Text2CypherEngine()
    return _text2cypher_engine
