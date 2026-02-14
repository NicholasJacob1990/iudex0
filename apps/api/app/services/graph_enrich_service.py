"""
Graph Enrichment Service — Orquestrador do pipeline L1→L2→L3→L3b.

Executa as fases de enriquecimento sob demanda via endpoint /graph/enrich.
Todas as fases L2/L3/L3b criam :RELATED_TO com layer='candidate' (transparency-first).
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from app.schemas.graph_enrich import (
    EnrichLayer,
    EnrichRequest,
    EnrichResponse,
    LayerResult,
)

logger = logging.getLogger(__name__)


class GraphEnrichService:
    """Serviço de enriquecimento de grafo sob demanda."""

    def _get_session(self):
        """Obtém session sync do Neo4j."""
        from app.services.rag.core.neo4j_mvp import get_neo4j_mvp
        neo4j = get_neo4j_mvp()
        driver = neo4j.driver
        db_candidates = neo4j._database_candidates()
        db = db_candidates[0] if db_candidates else "neo4j"
        return driver.session(database=db)

    def _should_run(self, request: EnrichRequest, layer: EnrichLayer) -> bool:
        """Verifica se uma camada deve ser executada."""
        return EnrichLayer.all in request.layers or layer in request.layers

    def _run_l1_structural(self) -> LayerResult:
        """L1: Inferência estrutural determinística."""
        t0 = time.time()
        result = LayerResult(layer="structural")

        try:
            from app.services.rag.core.kg_builder.link_inference import run_structural_inference

            with self._get_session() as session:
                stats = run_structural_inference(session)

            result.candidates_created = stats.total_inferred
            result.details = {
                "transitive_remete_a": stats.transitive_remete_a,
                "transitive_cita": stats.transitive_cita,
                "co_citation": stats.co_citation_cita,
                "parent_inheritance": stats.parent_inheritance_remete_a,
                "symmetric_cita": stats.symmetric_cita,
                "jurisprudence_cluster": stats.jurisprudence_cluster,
            }
        except Exception as e:
            logger.error(f"L1 structural inference failed: {e}")
            result.warnings.append(f"L1 error: {str(e)[:200]}")

        result.duration_ms = int((time.time() - t0) * 1000)
        return result

    def _run_l2_embedding(
        self,
        request: EnrichRequest,
        pass_to_l3: bool = False,
    ) -> tuple[LayerResult, list]:
        """L2: Inferência por similaridade de embeddings."""
        t0 = time.time()
        result = LayerResult(layer="embedding")
        candidates_for_l3 = []

        try:
            from app.services.rag.core.kg_builder.link_predictor import run_embedding_based_inference

            with self._get_session() as session:
                stats = run_embedding_based_inference(
                    session,
                    use_adaptive_threshold=request.use_adaptive_threshold,
                    total_budget=request.total_budget,
                    enable_artigo=request.enable_artigo,
                    enable_cross_type=request.enable_cross_type,
                    pass_to_l3=pass_to_l3,
                )

            result.candidates_created = stats.total_inferred
            result.details = {
                "decisao_by_similarity": stats.decisao_cita_by_similarity,
                "sumula_by_similarity": stats.sumula_cita_by_similarity,
                "doutrina_by_similarity": stats.doutrina_cita_by_similarity,
                "artigo_by_similarity": stats.artigo_by_similarity,
                "cross_type_by_similarity": stats.cross_type_by_similarity,
            }
            candidates_for_l3 = stats.candidates_for_l3 or []

        except Exception as e:
            logger.error(f"L2 embedding inference failed: {e}")
            result.warnings.append(f"L2 error: {str(e)[:200]}")

        result.duration_ms = int((time.time() - t0) * 1000)
        return result, candidates_for_l3

    def _run_l3_llm(
        self,
        request: EnrichRequest,
        l2_candidates: list | None = None,
    ) -> LayerResult:
        """L3: Classificação e descoberta via LLM."""
        t0 = time.time()
        result = LayerResult(layer="llm")

        try:
            from app.services.rag.core.kg_builder.llm_link_suggester import run_llm_based_inference

            with self._get_session() as session:
                stats = run_llm_based_inference(
                    session,
                    model_provider=request.llm_provider,
                    model=request.llm_model,
                    max_decisao_pairs=request.max_llm_pairs,
                    max_doutrina_pairs=max(request.max_llm_pairs // 2, 10),
                    min_confidence=request.min_confidence,
                    l2_candidates=l2_candidates,
                )

            result.candidates_created = stats.links_created
            result.details = {
                "pairs_evaluated": stats.pairs_evaluated,
                "links_suggested": stats.links_suggested,
                "llm_api_calls": stats.llm_api_calls,
                "evidence_validated": stats.evidence_validated,
                "evidence_failed": stats.evidence_failed,
                "l2_candidates_validated": stats.l2_candidates_validated,
                "l2_candidates_rejected": stats.l2_candidates_rejected,
            }
        except Exception as e:
            logger.error(f"L3 LLM inference failed: {e}")
            result.warnings.append(f"L3 error: {str(e)[:200]}")

        result.duration_ms = int((time.time() - t0) * 1000)
        return result

    def _run_l3b_exploratory(self, request: EnrichRequest) -> LayerResult:
        """L3b: Modo exploratório para nós isolados."""
        t0 = time.time()
        result = LayerResult(layer="exploratory")

        try:
            from app.services.rag.core.kg_builder.llm_explorer import run_exploratory_enrichment

            with self._get_session() as session:
                stats = run_exploratory_enrichment(
                    session,
                    node_types=request.explore_node_types,
                    max_degree=request.max_degree_isolated,
                    max_nodes=request.max_isolated_nodes,
                    model_provider=request.llm_provider,
                    model=request.llm_model,
                    min_confidence=request.min_confidence_exploratory,
                )

            result.candidates_created = stats.suggestions_created
            result.details = {
                "isolated_nodes_found": stats.isolated_nodes_found,
                "nodes_explored": stats.nodes_explored,
                "llm_api_calls": stats.llm_api_calls,
                "evidence_validated": stats.evidence_validated,
                "evidence_failed": stats.evidence_failed,
                "shortlist_empty": stats.shortlist_empty,
            }
        except Exception as e:
            logger.error(f"L3b exploratory enrichment failed: {e}")
            result.warnings.append(f"L3b error: {str(e)[:200]}")

        result.duration_ms = int((time.time() - t0) * 1000)
        return result

    async def run_enrichment(self, request: EnrichRequest) -> EnrichResponse:
        """
        Executa o pipeline de enriquecimento completo.

        Pipeline: L1 (structural) → L2 (embedding) → L3 (llm) → L3b (exploratory)
        L2 pode passar candidatos para L3 validar (handoff).
        """
        t0 = time.time()
        layer_results = []
        warnings = []
        layers_executed = []
        total_candidates = 0
        total_structural = 0
        l2_candidates = []

        # L1 — Structural (creates typed rels, not candidates)
        if self._should_run(request, EnrichLayer.structural):
            l1_result = await asyncio.to_thread(self._run_l1_structural)
            layer_results.append(l1_result)
            layers_executed.append("structural")
            total_structural += l1_result.candidates_created
            warnings.extend(l1_result.warnings)

        # L2 — Embedding
        if self._should_run(request, EnrichLayer.embedding):
            pass_to_l3 = (
                request.pass_l2_to_l3
                and self._should_run(request, EnrichLayer.llm)
            )
            l2_result, l2_candidates = await asyncio.to_thread(
                self._run_l2_embedding, request, pass_to_l3
            )
            layer_results.append(l2_result)
            layers_executed.append("embedding")
            total_candidates += l2_result.candidates_created
            warnings.extend(l2_result.warnings)

        # L3 — LLM (with optional L2 handoff)
        if self._should_run(request, EnrichLayer.llm):
            l3_result = await asyncio.to_thread(
                self._run_l3_llm, request,
                l2_candidates if l2_candidates else None
            )
            layer_results.append(l3_result)
            layers_executed.append("llm")
            total_candidates += l3_result.candidates_created
            warnings.extend(l3_result.warnings)

        # L3b — Exploratory
        if self._should_run(request, EnrichLayer.exploratory):
            l3b_result = await asyncio.to_thread(
                self._run_l3b_exploratory, request
            )
            layer_results.append(l3b_result)
            layers_executed.append("exploratory")
            total_candidates += l3b_result.candidates_created
            warnings.extend(l3b_result.warnings)

        duration_ms = int((time.time() - t0) * 1000)

        return EnrichResponse(
            success=len(warnings) == 0 or total_candidates > 0 or total_structural > 0,
            layers_executed=layers_executed,
            total_candidates_created=total_candidates,
            total_structural_created=total_structural,
            layer_results=layer_results,
            warnings=warnings,
            duration_ms=duration_ms,
        )
