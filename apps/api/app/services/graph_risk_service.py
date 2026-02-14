"""
Graph Risk Service — Fraud discovery and audit helpers on top of GraphRAG.

This service is deterministic and tenant-scoped (via Document-based visibility),
and it can optionally persist scan reports for later review.
"""

from __future__ import annotations

import asyncio
import time
from datetime import timedelta
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy import and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.time_utils import utcnow
from app.models.graph_risk_report import GraphRiskReport
from app.schemas.graph_risk import (
    AuditChainRequest,
    AuditChainResponse,
    AuditEdgeRequest,
    AuditEdgeResponse,
    RiskEntity,
    RiskFocus,
    RiskProfile,
    RiskScanRequest,
    RiskScanResponse,
    RiskSignal,
    SupportingDocs,
)
from app.services.graph_ask_service import get_graph_ask_service, GraphOperation
from app.services.graph_risk_detectors import default_include_candidates, default_limits, filter_detectors, Detector


_REL_FILTER_AUDIT = (
    "RELATED_TO|REMETE_A|PERTENCE_A|INTERPRETA|APLICA|APLICA_SUMULA|FUNDAMENTA|"
    "CITA|CITES|REVOGA|ALTERA|COMPLEMENTA|EXCEPCIONA|REGULAMENTA|ESPECIALIZA|"
    "PROFERIDA_POR|FIXA_TESE|JULGA_TEMA|PARTICIPA_DE|REPRESENTA|CO_MENCIONA"
)


def _doc_visibility_where() -> str:
    # NOTE: scope='group' is blocked upstream in GraphAskService; keep consistent here.
    return (
        "WHERE (d.tenant_id = $tenant_id OR ($include_global = true AND d.scope = 'global')) "
        "  AND (d.sigilo IS NULL OR d.sigilo = false) "
        "  AND ($case_id IS NOT NULL OR d.scope <> 'local') "
        "  AND ($scope IS NULL OR d.scope = $scope) "
        "  AND ($case_id IS NULL OR d.case_id = $case_id) "
    )


class GraphRiskService:
    def __init__(self):
        self._graph_ask = get_graph_ask_service()

    async def _get_neo4j(self):
        return await self._graph_ask._get_neo4j()  # reuse lazy init and config

    async def _read(self, neo4j, query_text: str, params: Dict[str, Any], timeout_ms: int = 6000) -> List[Dict[str, Any]]:
        try:
            return await asyncio.wait_for(
                neo4j._execute_read_async(query_text, params),
                timeout=timeout_ms / 1000.0,
            )
        except asyncio.TimeoutError:
            raise TimeoutError(f"Query excedeu timeout de {timeout_ms}ms")

    async def _sample_co_mentions(
        self,
        *,
        neo4j,
        tenant_id: str,
        include_global: bool,
        scope: Optional[str],
        case_id: Optional[str],
        source_id: str,
        target_id: str,
        limit_docs: int = 5,
        timeout_ms: int = 6000,
    ) -> SupportingDocs:
        q = (
            "MATCH (a:Entity {entity_id: $a_id}) "
            "MATCH (b:Entity {entity_id: $b_id}) "
            "MATCH (a)<-[:MENTIONS]-(c:Chunk)-[:MENTIONS]->(b) "
            "MATCH (d:Document)-[:HAS_CHUNK]->(c) "
            + _doc_visibility_where() +
            "RETURN d.id AS doc_id, left(coalesce(c.text_preview, ''), 220) AS preview "
            "ORDER BY d.id "
            "LIMIT $limit_docs"
        )
        rows = await self._read(
            neo4j,
            q,
            {
                "a_id": source_id,
                "b_id": target_id,
                "tenant_id": tenant_id,
                "include_global": bool(include_global),
                "scope": scope,
                "case_id": case_id,
                "limit_docs": int(limit_docs),
            },
            timeout_ms=timeout_ms,
        )
        doc_ids = [str(r.get("doc_id")) for r in rows if r.get("doc_id")]
        previews = [str(r.get("preview") or "") for r in rows if str(r.get("preview") or "").strip()]
        return SupportingDocs(count=len(doc_ids), doc_ids_sample=doc_ids[:5], chunk_previews_sample=previews[:5])

    async def scan(
        self,
        *,
        tenant_id: str,
        user_id: str,
        db: AsyncSession,
        request: RiskScanRequest,
    ) -> RiskScanResponse:
        start_time = time.time()

        limits = default_limits(request.profile)
        limit = int(request.limit or limits["limit"])
        min_shared_docs = int(request.min_shared_docs or limits["min_shared_docs"])
        include_candidates = (
            bool(request.include_candidates)
            if request.include_candidates is not None
            else default_include_candidates(request.profile)
        )

        scope = (request.scope or "").strip().lower() or None
        case_id = request.case_id
        include_global = bool(request.include_global)

        neo4j = await self._get_neo4j()

        async def d_orgao_empresa() -> List[RiskSignal]:
            res = await self._graph_ask.ask(
                operation=GraphOperation.FRAUD_SIGNALS,
                params={"min_shared_docs": min_shared_docs, "limit": limit, "include_candidates": include_candidates},
                tenant_id=tenant_id,
                scope=scope,
                case_id=case_id,
                include_global=include_global,
                timeout_ms=8000,
            )
            out: List[RiskSignal] = []
            for row in (res.results or [])[:limit]:
                orgao_id = str(row.get("orgao_id") or "")
                empresa_id = str(row.get("empresa_id") or "")
                if not orgao_id or not empresa_id:
                    continue
                supporting = await self._sample_co_mentions(
                    neo4j=neo4j,
                    tenant_id=tenant_id,
                    include_global=include_global,
                    scope=scope,
                    case_id=case_id,
                    source_id=orgao_id,
                    target_id=empresa_id,
                    limit_docs=5,
                )
                out.append(
                    RiskSignal(
                        scenario="orgao_empresa_comention",
                        title="Órgão ↔ Empresa (co-menções)",
                        score=float(row.get("risk_score") or 0.0),
                        entities=[
                            RiskEntity(entity_id=orgao_id, name=row.get("orgao_name"), entity_type="orgao"),
                            RiskEntity(entity_id=empresa_id, name=row.get("empresa_name"), entity_type="empresa"),
                        ],
                        supporting_docs=supporting,
                        explain=(
                            f"Co-menções em chunks (docs compartilhados={int(row.get('shared_documents') or 0)}; "
                            f"processos vinculados={int(row.get('linked_process_count') or 0)})."
                        ),
                        focus=RiskFocus(source_id=orgao_id, target_id=empresa_id),
                        raw=row,
                    )
                )
            return out

        async def d_comenciona_hotspots() -> List[RiskSignal]:
            q = (
                "MATCH (a1:Entity)-[r:CO_MENCIONA]->(a2:Entity) "
                "WHERE r.layer = 'candidate' AND r.tenant_id = $tenant_id "
                "RETURN "
                "  a1.entity_id AS a1_id, a1.name AS a1_name, a1.entity_type AS a1_type, "
                "  a2.entity_id AS a2_id, a2.name AS a2_name, a2.entity_type AS a2_type, "
                "  coalesce(r.co_occurrences, 0) AS co, "
                "  coalesce(r.weight, toFloat(coalesce(r.co_occurrences, 0))) AS weight, "
                "  coalesce(r.samples, []) AS samples "
                "ORDER BY weight DESC, co DESC "
                "LIMIT $limit"
            )
            rows = await self._read(neo4j, q, {"tenant_id": tenant_id, "limit": limit}, timeout_ms=8000)
            out: List[RiskSignal] = []
            for row in rows:
                a1_id = str(row.get("a1_id") or "")
                a2_id = str(row.get("a2_id") or "")
                if not a1_id or not a2_id:
                    continue
                samples = [str(s) for s in (row.get("samples") or []) if str(s).strip()]
                out.append(
                    RiskSignal(
                        scenario="comenciona_hotspots",
                        title="Artigo ↔ Artigo (CO_MENCIONA hotspots)",
                        score=float(row.get("weight") or 0.0),
                        entities=[
                            RiskEntity(entity_id=a1_id, name=row.get("a1_name"), entity_type=row.get("a1_type")),
                            RiskEntity(entity_id=a2_id, name=row.get("a2_name"), entity_type=row.get("a2_type")),
                        ],
                        supporting_docs=SupportingDocs(
                            count=int(row.get("co") or 0),
                            doc_ids_sample=[],
                            chunk_previews_sample=samples[:3],
                        ),
                        explain=f"Co-ocorrências em chunks (co={int(row.get('co') or 0)}). Relação candidata (exploração).",
                        focus=RiskFocus(source_id=a1_id, target_id=a2_id),
                        raw=row,
                    )
                )
            return out

        async def d_multi_process_actor() -> List[RiskSignal]:
            # Prefer explicit PARTICIPA_DE when present; otherwise fall back to co-mentions actor<->processo in chunks.
            q = (
                "MATCH (a:Entity)-[:PARTICIPA_DE]->(p:Entity) "
                "WHERE toLower(coalesce(p.entity_type,'')) IN ['processo','licitacao','contrato'] "
                "WITH a, count(DISTINCT p) AS proc_count, collect(DISTINCT p.entity_id)[0..8] AS procs "
                "WHERE proc_count >= 3 "
                "RETURN a.entity_id AS actor_id, a.name AS actor_name, a.entity_type AS actor_type, proc_count, procs "
                "ORDER BY proc_count DESC "
                "LIMIT $limit"
            )
            rows = await self._read(neo4j, q, {"limit": limit}, timeout_ms=8000)
            out: List[RiskSignal] = []
            for row in rows:
                actor_id = str(row.get("actor_id") or "")
                if not actor_id:
                    continue
                proc_count = int(row.get("proc_count") or 0)
                score = float(proc_count)
                out.append(
                    RiskSignal(
                        scenario="multi_process_actor",
                        title="Entidade em muitos processos",
                        score=score,
                        entities=[
                            RiskEntity(entity_id=actor_id, name=row.get("actor_name"), entity_type=row.get("actor_type")),
                        ] + [RiskEntity(entity_id=str(pid), name=None, entity_type="processo") for pid in (row.get("procs") or [])],
                        supporting_docs=SupportingDocs(count=0),
                        explain=f"Participa de {proc_count} processos (via PARTICIPA_DE).",
                        focus=None,
                        raw=row,
                    )
                )
            return out

        async def d_representacao_massiva() -> List[RiskSignal]:
            q = (
                "MATCH (a:Entity)-[:REPRESENTA]->(c:Entity) "
                "WITH a, count(DISTINCT c) AS client_count, collect(DISTINCT c.entity_id)[0..8] AS clients "
                "WHERE client_count >= 5 "
                "RETURN a.entity_id AS rep_id, a.name AS rep_name, a.entity_type AS rep_type, client_count, clients "
                "ORDER BY client_count DESC "
                "LIMIT $limit"
            )
            rows = await self._read(neo4j, q, {"limit": limit}, timeout_ms=8000)
            out: List[RiskSignal] = []
            for row in rows:
                rep_id = str(row.get("rep_id") or "")
                if not rep_id:
                    continue
                client_count = int(row.get("client_count") or 0)
                out.append(
                    RiskSignal(
                        scenario="representacao_massiva",
                        title="Representação massiva (REPRESENTA)",
                        score=float(client_count),
                        entities=[
                            RiskEntity(entity_id=rep_id, name=row.get("rep_name"), entity_type=row.get("rep_type")),
                        ] + [RiskEntity(entity_id=str(cid), name=None, entity_type=None) for cid in (row.get("clients") or [])],
                        supporting_docs=SupportingDocs(count=0),
                        explain=f"Representa {client_count} entidades (via REPRESENTA).",
                        focus=None,
                        raw=row,
                    )
                )
            return out

        async def d_process_network_hubs() -> List[RiskSignal]:
            # Reuse discover_hubs and normalize top entries as signals.
            res = await self._graph_ask.ask(
                operation=GraphOperation.DISCOVER_HUBS,
                params={"top_n": min(10, max(3, limit // 3))},
                tenant_id=tenant_id,
                scope=scope,
                case_id=case_id,
                include_global=include_global,
                timeout_ms=8000,
            )
            payload = (res.results or [{}])[0] if res.success and res.results else {}
            out: List[RiskSignal] = []
            for cat, items in (payload or {}).items():
                if not isinstance(items, list):
                    continue
                for it in items[:5]:
                    eid = str(it.get("entity_id") or it.get("id") or "")
                    nm = it.get("name")
                    if not eid:
                        continue
                    out.append(
                        RiskSignal(
                            scenario="process_network_hubs",
                            title=f"Hub: {cat}",
                            score=float(it.get("score") or it.get("degree") or it.get("count") or 0.0),
                            entities=[RiskEntity(entity_id=eid, name=nm, entity_type=it.get("type"))],
                            supporting_docs=SupportingDocs(count=int(it.get("supporting_documents") or 0)),
                            explain="Nó central por conectividade/uso no grafo (exploração).",
                            focus=None,
                            raw=it,
                        )
                    )
            return out

        # =====================================================================
        # GDS-POWERED DETECTORS
        # =====================================================================

        async def d_connected_risk_clusters() -> List[RiskSignal]:
            """WCC: detecta clusters isolados (ilhas suspeitas no grafo)."""
            try:
                res = await self._graph_ask.ask(
                    operation=GraphOperation.WEAKLY_CONNECTED_COMPONENTS,
                    params={"entity_type": "Entity", "limit": limit},
                    tenant_id=tenant_id,
                    scope=scope,
                    case_id=case_id,
                    include_global=include_global,
                    timeout_ms=12000,
                )
                if not res.success:
                    return []
                out: List[RiskSignal] = []
                for row in (res.results or []):
                    size = int(row.get("size") or 0)
                    if size < 2 or size > 500:
                        continue
                    members = row.get("sample_members") or []
                    names = row.get("sample_names") or []
                    entities = [
                        RiskEntity(entity_id=str(m), name=str(n) if n else None)
                        for m, n in zip(members[:5], names[:5])
                    ]
                    out.append(
                        RiskSignal(
                            scenario="connected_risk_clusters",
                            title=f"Cluster isolado ({size} entidades)",
                            score=float(size),
                            entities=entities,
                            supporting_docs=SupportingDocs(count=0),
                            explain=f"Componente WCC com {size} entidades isoladas do grafo principal. Clusters pequenos e isolados podem indicar redes paralelas.",
                            focus=RiskFocus(source_id=str(members[0]), target_id=str(members[1])) if len(members) >= 2 else None,
                        )
                    )
                return out[:limit]
            except Exception as e:
                logger.warning("GDS detector connected_risk_clusters failed: %s", e)
                return []

        async def d_influence_propagation() -> List[RiskSignal]:
            """Eigenvector Centrality: detecta entidades com influência propagada alta."""
            try:
                res = await self._graph_ask.ask(
                    operation=GraphOperation.EIGENVECTOR_CENTRALITY,
                    params={"entity_type": "Entity", "limit": min(15, limit)},
                    tenant_id=tenant_id,
                    scope=scope,
                    case_id=case_id,
                    include_global=include_global,
                    timeout_ms=12000,
                )
                if not res.success:
                    return []
                out: List[RiskSignal] = []
                for row in (res.results or []):
                    eid = str(row.get("entity_id") or "")
                    score = float(row.get("score") or 0.0)
                    if not eid or score <= 0:
                        continue
                    out.append(
                        RiskSignal(
                            scenario="influence_propagation",
                            title="Alta influência propagada (Eigenvector)",
                            score=score,
                            entities=[RiskEntity(entity_id=eid, name=row.get("name"))],
                            supporting_docs=SupportingDocs(count=0),
                            explain=f"Eigenvector centrality={score:.4f}. Entidade conectada a outros nós altamente conectados — influência propagada de 2o/3o nível.",
                            focus=None,
                        )
                    )
                return out
            except Exception as e:
                logger.warning("GDS detector influence_propagation failed: %s", e)
                return []

        async def d_critical_intermediaries() -> List[RiskSignal]:
            """Betweenness: detecta intermediários críticos em cadeias."""
            try:
                res = await self._graph_ask.ask(
                    operation=GraphOperation.BETWEENNESS_CENTRALITY,
                    params={"entity_type": "Entity", "limit": min(15, limit)},
                    tenant_id=tenant_id,
                    scope=scope,
                    case_id=case_id,
                    include_global=include_global,
                    timeout_ms=12000,
                )
                if not res.success:
                    return []
                out: List[RiskSignal] = []
                for row in (res.results or []):
                    eid = str(row.get("entity_id") or "")
                    score = float(row.get("score") or 0.0)
                    if not eid or score <= 0:
                        continue
                    out.append(
                        RiskSignal(
                            scenario="critical_intermediaries",
                            title="Intermediário crítico (Betweenness)",
                            score=score,
                            entities=[RiskEntity(entity_id=eid, name=row.get("name"))],
                            supporting_docs=SupportingDocs(count=0),
                            explain=f"Betweenness centrality={score:.2f}. Entidade que serve de ponte entre grupos — remoção fragmentaria o grafo.",
                            focus=None,
                        )
                    )
                return out
            except Exception as e:
                logger.warning("GDS detector critical_intermediaries failed: %s", e)
                return []

        async def d_hidden_communities() -> List[RiskSignal]:
            """Leiden: detecta comunidades ocultas com alta modularidade."""
            try:
                res = await self._graph_ask.ask(
                    operation=GraphOperation.LEIDEN,
                    params={"entity_type": "Entity", "limit": 200},
                    tenant_id=tenant_id,
                    scope=scope,
                    case_id=case_id,
                    include_global=include_global,
                    timeout_ms=15000,
                )
                if not res.success:
                    return []
                # Agrupa por community_id e reporta comunidades pequenas/suspeitas
                from collections import defaultdict
                communities: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
                for row in (res.results or []):
                    cid = int(row.get("community_id") or 0)
                    communities[cid].append(row)
                out: List[RiskSignal] = []
                for cid, members in sorted(communities.items(), key=lambda x: len(x[1]), reverse=True):
                    size = len(members)
                    if size < 2:
                        continue
                    entities = [
                        RiskEntity(entity_id=str(m.get("entity_id")), name=m.get("name"))
                        for m in members[:5]
                    ]
                    first_id = str(members[0].get("entity_id") or "")
                    second_id = str(members[1].get("entity_id") or "") if len(members) >= 2 else ""
                    out.append(
                        RiskSignal(
                            scenario="hidden_communities",
                            title=f"Comunidade Leiden #{cid} ({size} membros)",
                            score=float(size),
                            entities=entities,
                            supporting_docs=SupportingDocs(count=0),
                            explain=f"Comunidade Leiden com {size} entidades que interagem mais entre si do que com o resto do grafo.",
                            focus=RiskFocus(source_id=first_id, target_id=second_id) if first_id and second_id else None,
                        )
                    )
                return out[:limit]
            except Exception as e:
                logger.warning("GDS detector hidden_communities failed: %s", e)
                return []

        async def d_behavioral_similarity() -> List[RiskSignal]:
            """Node Similarity: detecta pares de entidades com comportamento similar."""
            try:
                res = await self._graph_ask.ask(
                    operation=GraphOperation.NODE_SIMILARITY,
                    params={"entity_type": "Entity", "limit": min(20, limit), "top_k": 5},
                    tenant_id=tenant_id,
                    scope=scope,
                    case_id=case_id,
                    include_global=include_global,
                    timeout_ms=12000,
                )
                if not res.success:
                    return []
                out: List[RiskSignal] = []
                for row in (res.results or []):
                    e1_id = str(row.get("entity1_id") or "")
                    e2_id = str(row.get("entity2_id") or "")
                    sim = float(row.get("similarity") or 0.0)
                    if not e1_id or not e2_id or sim < 0.5:
                        continue
                    out.append(
                        RiskSignal(
                            scenario="behavioral_similarity",
                            title="Par com alta similaridade estrutural",
                            score=sim,
                            entities=[
                                RiskEntity(entity_id=e1_id, name=row.get("entity1_name")),
                                RiskEntity(entity_id=e2_id, name=row.get("entity2_name")),
                            ],
                            supporting_docs=SupportingDocs(count=0),
                            explain=f"Similaridade Jaccard={sim:.3f}. Entidades com vizinhos compartilhados — padrão de conexões quase idêntico.",
                            focus=RiskFocus(source_id=e1_id, target_id=e2_id),
                        )
                    )
                return out
            except Exception as e:
                logger.warning("GDS detector behavioral_similarity failed: %s", e)
                return []

        async def d_collusion_triangles() -> List[RiskSignal]:
            """Triangle Count: detecta entidades em muitos triângulos (conluio potencial)."""
            try:
                res = await self._graph_ask.ask(
                    operation=GraphOperation.TRIANGLE_COUNT,
                    params={"entity_type": "Entity", "limit": min(15, limit)},
                    tenant_id=tenant_id,
                    scope=scope,
                    case_id=case_id,
                    include_global=include_global,
                    timeout_ms=12000,
                )
                if not res.success:
                    return []
                out: List[RiskSignal] = []
                for row in (res.results or []):
                    eid = str(row.get("entity_id") or "")
                    tcount = int(row.get("triangleCount") or 0)
                    if not eid or tcount <= 0:
                        continue
                    out.append(
                        RiskSignal(
                            scenario="collusion_triangles",
                            title="Entidade em muitos triângulos",
                            score=float(tcount),
                            entities=[RiskEntity(entity_id=eid, name=row.get("name"))],
                            supporting_docs=SupportingDocs(count=0),
                            explain=f"Participa de {tcount} triângulos. Clusters densos de 3 entidades mutuamente conectadas podem indicar conluio.",
                            focus=None,
                        )
                    )
                return out
            except Exception as e:
                logger.warning("GDS detector collusion_triangles failed: %s", e)
                return []

        async def d_structural_vulnerabilities() -> List[RiskSignal]:
            """Bridges + Articulation Points: detecta pontos de fragilidade estrutural."""
            out: List[RiskSignal] = []
            # Bridges
            try:
                res_bridges = await self._graph_ask.ask(
                    operation=GraphOperation.BRIDGES,
                    params={"entity_type": "Entity", "limit": min(15, limit)},
                    tenant_id=tenant_id,
                    scope=scope,
                    case_id=case_id,
                    include_global=include_global,
                    timeout_ms=12000,
                )
                if res_bridges.success:
                    for row in (res_bridges.results or []):
                        f_id = str(row.get("from_entity_id") or "")
                        t_id = str(row.get("to_entity_id") or "")
                        if not f_id or not t_id:
                            continue
                        out.append(
                            RiskSignal(
                                scenario="structural_vulnerabilities",
                                title="Ponte estrutural (Bridge)",
                                score=1.0,
                                entities=[
                                    RiskEntity(entity_id=f_id, name=row.get("from_name")),
                                    RiskEntity(entity_id=t_id, name=row.get("to_name")),
                                ],
                                supporting_docs=SupportingDocs(count=0),
                                explain="Aresta bridge — remoção desconecta o grafo. Ponto único de falha na conectividade.",
                                focus=RiskFocus(source_id=f_id, target_id=t_id),
                            )
                        )
            except Exception as e:
                logger.warning("GDS bridges sub-detector failed: %s", e)

            # Articulation Points
            try:
                res_artic = await self._graph_ask.ask(
                    operation=GraphOperation.ARTICULATION_POINTS,
                    params={"entity_type": "Entity", "limit": min(10, limit)},
                    tenant_id=tenant_id,
                    scope=scope,
                    case_id=case_id,
                    include_global=include_global,
                    timeout_ms=12000,
                )
                if res_artic.success:
                    for row in (res_artic.results or []):
                        eid = str(row.get("entity_id") or "")
                        if not eid:
                            continue
                        out.append(
                            RiskSignal(
                                scenario="structural_vulnerabilities",
                                title="Ponto de articulação",
                                score=1.0,
                                entities=[RiskEntity(entity_id=eid, name=row.get("name"))],
                                supporting_docs=SupportingDocs(count=0),
                                explain="Nó de articulação — remoção fragmenta o grafo. Entidade crítica para conectividade.",
                                focus=None,
                            )
                        )
            except Exception as e:
                logger.warning("GDS articulation_points sub-detector failed: %s", e)

            return out[:limit]

        # =====================================================================
        # DETECTOR REGISTRY
        # =====================================================================

        detectors: List[Detector] = [
            # Cypher-based (original)
            Detector("orgao_empresa_comention", "orgao_empresa_comention", "Órgão ↔ Empresa (co-menções)", d_orgao_empresa),
            Detector("comenciona_hotspots", "comenciona_hotspots", "CO_MENCIONA hotspots", d_comenciona_hotspots),
            Detector("multi_process_actor", "multi_process_actor", "Entidade em muitos processos", d_multi_process_actor),
            Detector("representacao_massiva", "representacao_massiva", "Representação massiva", d_representacao_massiva),
            Detector("process_network_hubs", "process_network_hubs", "Hubs do grafo", d_process_network_hubs),
            # GDS-powered (new)
            Detector("connected_risk_clusters", "connected_risk_clusters", "Clusters isolados (WCC)", d_connected_risk_clusters),
            Detector("influence_propagation", "influence_propagation", "Influência propagada (Eigenvector)", d_influence_propagation),
            Detector("critical_intermediaries", "critical_intermediaries", "Intermediários críticos (Betweenness)", d_critical_intermediaries),
            Detector("hidden_communities", "hidden_communities", "Comunidades ocultas (Leiden)", d_hidden_communities),
            Detector("behavioral_similarity", "behavioral_similarity", "Similaridade comportamental", d_behavioral_similarity),
            Detector("collusion_triangles", "collusion_triangles", "Triângulos de conluio", d_collusion_triangles),
            Detector("structural_vulnerabilities", "structural_vulnerabilities", "Vulnerabilidades estruturais", d_structural_vulnerabilities),
        ]

        selected = filter_detectors(detectors, requested=request.scenarios)

        try:
            signals_nested = await asyncio.gather(*[d.run() for d in selected])
            signals: List[RiskSignal] = []
            for chunk in signals_nested:
                signals.extend(chunk)

            # Per-detector outputs can exceed limit; keep global cap while preserving ordering by score.
            signals.sort(key=lambda s: float(s.score or 0.0), reverse=True)
            signals = signals[: max(1, min(500, limit * max(1, len(selected))))][:200]

            report_id: Optional[str] = None
            if request.persist:
                report = GraphRiskReport(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    status="completed",
                    error=None,
                    params=request.model_dump(),
                    signals={"signals": [s.model_dump() for s in signals]},
                    created_at=utcnow(),
                    expires_at=utcnow() + timedelta(days=30),
                )
                db.add(report)
                await db.commit()
                await db.refresh(report)
                report_id = report.id

            execution_time = int((time.time() - start_time) * 1000)
            return RiskScanResponse(
                success=True,
                signals=signals,
                report_id=report_id,
                execution_time_ms=execution_time,
                error=None,
            )
        except Exception as e:
            logger.error("GraphRiskService.scan failed: %s", e)
            execution_time = int((time.time() - start_time) * 1000)
            return RiskScanResponse(success=False, signals=[], report_id=None, execution_time_ms=execution_time, error=str(e))

    async def list_reports(
        self,
        *,
        tenant_id: str,
        user_id: str,
        db: AsyncSession,
        limit: int = 50,
    ) -> List[GraphRiskReport]:
        limit = max(1, min(int(limit or 50), 200))
        q = (
            select(GraphRiskReport)
            .where(and_(GraphRiskReport.tenant_id == tenant_id, GraphRiskReport.user_id == user_id))
            .order_by(GraphRiskReport.created_at.desc())
            .limit(limit)
        )
        rows = await db.execute(q)
        return list(rows.scalars().all())

    async def get_report(
        self,
        *,
        tenant_id: str,
        user_id: str,
        db: AsyncSession,
        report_id: str,
    ) -> Optional[GraphRiskReport]:
        q = select(GraphRiskReport).where(
            and_(
                GraphRiskReport.id == report_id,
                GraphRiskReport.tenant_id == tenant_id,
                GraphRiskReport.user_id == user_id,
            )
        )
        rows = await db.execute(q)
        return rows.scalar_one_or_none()

    async def delete_report(
        self,
        *,
        tenant_id: str,
        user_id: str,
        db: AsyncSession,
        report_id: str,
    ) -> bool:
        report = await self.get_report(tenant_id=tenant_id, user_id=user_id, db=db, report_id=report_id)
        if not report:
            return False
        await db.delete(report)
        await db.commit()
        return True

    async def audit_edge(
        self,
        *,
        tenant_id: str,
        request: AuditEdgeRequest,
    ) -> AuditEdgeResponse:
        start_time = time.time()
        neo4j = await self._get_neo4j()
        scope = (request.scope or "").strip().lower() or None
        case_id = request.case_id
        include_global = bool(request.include_global)

        try:
            edge_q = (
                "MATCH (a:Entity {entity_id: $a_id})-[r]->(b:Entity {entity_id: $b_id}) "
                "WHERE ($include_candidates = true OR coalesce(r.layer, 'verified') <> 'candidate') "
                "  AND (type(r) =~ $rel_re) "
                "RETURN type(r) AS rel_type, properties(r) AS props "
                "LIMIT 50"
            )
            edge_rows = await self._read(
                neo4j,
                edge_q,
                {
                    "a_id": request.source_id,
                    "b_id": request.target_id,
                    "include_candidates": bool(request.include_candidates),
                    "rel_re": _REL_FILTER_AUDIT,
                },
                timeout_ms=6000,
            )

            com_q = (
                "MATCH (a:Entity {entity_id: $a_id}) "
                "MATCH (b:Entity {entity_id: $b_id}) "
                "MATCH (a)<-[:MENTIONS]-(c:Chunk)-[:MENTIONS]->(b) "
                "MATCH (d:Document)-[:HAS_CHUNK]->(c) "
                + _doc_visibility_where() +
                "RETURN d.id AS doc_id, left(coalesce(c.text_preview, ''), 220) AS preview "
                "ORDER BY d.id "
                "LIMIT $limit_docs"
            )
            com_rows = await self._read(
                neo4j,
                com_q,
                {
                    "a_id": request.source_id,
                    "b_id": request.target_id,
                    "tenant_id": tenant_id,
                    "include_global": include_global,
                    "scope": scope,
                    "case_id": case_id,
                    "limit_docs": int(request.limit_docs),
                },
                timeout_ms=8000,
            )

            notes = None
            if not edge_rows and com_rows:
                notes = "Sem aresta explícita entre as entidades; evidência disponível apenas por co-menções em chunks."

            execution_time = int((time.time() - start_time) * 1000)
            return AuditEdgeResponse(
                success=True,
                source_id=request.source_id,
                target_id=request.target_id,
                edge_matches=edge_rows,
                co_mentions=com_rows,
                notes=notes,
                execution_time_ms=execution_time,
            )
        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            return AuditEdgeResponse(
                success=False,
                source_id=request.source_id,
                target_id=request.target_id,
                edge_matches=[],
                co_mentions=[],
                notes=None,
                execution_time_ms=execution_time,
                error=str(e),
            )

    async def audit_chain(
        self,
        *,
        tenant_id: str,
        request: AuditChainRequest,
    ) -> AuditChainResponse:
        start_time = time.time()
        scope = (request.scope or "").strip().lower() or None
        case_id = request.case_id
        include_global = bool(request.include_global)

        try:
            res = await self._graph_ask.ask(
                operation=GraphOperation.PATH,
                params={
                    "source_id": request.source_id,
                    "target_id": request.target_id,
                    "max_hops": int(request.max_hops),
                    "limit": int(request.limit),
                    "include_candidates": bool(request.include_candidates),
                },
                tenant_id=tenant_id,
                scope=scope,
                case_id=case_id,
                include_global=include_global,
                timeout_ms=10000,
            )
            execution_time = int((time.time() - start_time) * 1000)
            return AuditChainResponse(
                success=res.success,
                source_id=request.source_id,
                target_id=request.target_id,
                paths=res.results or [],
                execution_time_ms=execution_time,
                error=res.error,
            )
        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            return AuditChainResponse(
                success=False,
                source_id=request.source_id,
                target_id=request.target_id,
                paths=[],
                execution_time_ms=execution_time,
                error=str(e),
            )


_graph_risk_service: Optional[GraphRiskService] = None


def get_graph_risk_service() -> GraphRiskService:
    global _graph_risk_service
    if _graph_risk_service is None:
        _graph_risk_service = GraphRiskService()
    return _graph_risk_service
