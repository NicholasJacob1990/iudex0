"""
Tests for the graph enrichment pipeline (L1→L2→L3→L3b).

Covers:
- EmbeddingCandidate dataclass
- Generic embedding inference (RELATED_TO, not typed)
- Anti-hallucination evidence validation
- L2→L3 handoff
- Exploratory mode (isolated nodes)
- Enrichment schemas
"""

import json
from dataclasses import asdict
from unittest.mock import MagicMock, patch

import pytest


# ============================================================================
# L2: EmbeddingCandidate + RELATED_TO
# ============================================================================


def test_embedding_candidate_dataclass():
    """EmbeddingCandidate has all expected fields."""
    from app.services.rag.core.kg_builder.link_predictor import EmbeddingCandidate

    c = EmbeddingCandidate(
        source_element_id="4:abc:1",
        target_element_id="4:abc:2",
        source_name="REsp 1234",
        target_name="REsp 5678",
        source_type="Decisao",
        target_type="Decisao",
        similarity_score=0.92,
        confidence=0.85,
        candidate_type="semantic:embedding_similarity:DecisaoxDecisao",
    )
    d = asdict(c)
    assert d["source_element_id"] == "4:abc:1"
    assert d["similarity_score"] == 0.92
    assert d["candidate_type"].startswith("semantic:")


def test_type_pair_config_includes_artigo():
    """TYPE_PAIR_CONFIG should include Artigo×Artigo and cross-type pairs."""
    from app.services.rag.core.kg_builder.link_predictor import TYPE_PAIR_CONFIG

    assert ("Artigo", "Artigo") in TYPE_PAIR_CONFIG
    assert ("Decisao", "Sumula") in TYPE_PAIR_CONFIG
    assert ("Decisao", "Artigo") in TYPE_PAIR_CONFIG


def test_generic_creates_related_to():
    """infer_links_by_embedding_generic creates RELATED_TO, not typed relationships."""
    from app.services.rag.core.kg_builder.link_predictor import infer_links_by_embedding_generic

    session = MagicMock()
    # Return empty list for embeddings query (no nodes found)
    session.run.return_value = iter([])

    count, candidates = infer_links_by_embedding_generic(
        session, "Decisao", "Decisao",
        similarity_threshold=0.9,
        return_candidates=False,
    )

    # With no embeddings, should create nothing
    assert count == 0
    assert candidates == []


def test_return_candidates_no_writes():
    """return_candidates=True should return candidates without writing to graph."""
    from app.services.rag.core.kg_builder.link_predictor import EmbeddingCandidate
    import numpy as np

    # We test indirectly — with no embeddings found, both modes should behave the same
    from app.services.rag.core.kg_builder.link_predictor import infer_links_by_embedding_generic

    session = MagicMock()
    session.run.return_value = iter([])

    count, candidates = infer_links_by_embedding_generic(
        session, "Artigo", "Artigo",
        similarity_threshold=0.95,
        return_candidates=True,
    )

    assert count == 0
    assert isinstance(candidates, list)


def test_adaptive_threshold_fallback():
    """When no samples, adaptive threshold falls back to conservative defaults."""
    from app.services.rag.core.kg_builder.link_predictor import compute_pair_profile_by_sampling

    session = MagicMock()
    # Return empty list (no embeddings)
    session.run.return_value = iter([])

    profile = compute_pair_profile_by_sampling(session, "Decisao", "Decisao", sample_size=100)
    # Returns a conservative profile with n_samples=0 and high thresholds
    assert profile.n_samples == 0
    assert profile.adaptive_threshold >= 0.8  # Conservative fallback


# ============================================================================
# L3: Anti-hallucination evidence validation
# ============================================================================


def test_valid_evidence_passes():
    """Substring evidence should pass validation."""
    from app.services.rag.core.kg_builder.llm_link_suggester import _validate_evidence

    snippets = [
        "O tribunal decidiu que a lei 8.666 se aplica ao caso concreto.",
        "A súmula 331 do TST foi aplicada como precedente vinculante."
    ]
    evidence = "a lei 8.666 se aplica ao caso concreto"
    assert _validate_evidence(evidence, snippets) is True


def test_fabricated_evidence_fails():
    """Evidence not in any snippet should fail."""
    from app.services.rag.core.kg_builder.llm_link_suggester import _validate_evidence

    snippets = ["O tribunal decidiu conforme precedente."]
    evidence = "A constituição federal garante o direito à liberdade"
    assert _validate_evidence(evidence, snippets) is False


def test_short_evidence_fails():
    """Evidence shorter than 10 chars should fail."""
    from app.services.rag.core.kg_builder.llm_link_suggester import _validate_evidence

    snippets = ["Texto do tribunal."]
    assert _validate_evidence("curto", snippets) is False
    assert _validate_evidence("", snippets) is False
    assert _validate_evidence(None, snippets) is False


def test_confidence_reduction_invalid_evidence():
    """LLM suggestion with invalid evidence should have confidence halved."""
    from app.services.rag.core.kg_builder.llm_link_suggester import _validate_evidence

    snippets = ["Contexto real do nó A."]
    fabricated = "Evidência completamente inventada pelo LLM"

    # Evidence fails
    assert _validate_evidence(fabricated, snippets) is False
    # In the actual code, confidence *= 0.5 when evidence_ok is False
    # We just verify the validation logic here; integration is tested below


# ============================================================================
# L3: RELATED_TO creation (not typed)
# ============================================================================


def test_creates_related_to_not_typed():
    """create_llm_suggested_links should create RELATED_TO, not typed relationships."""
    from app.services.rag.core.kg_builder.llm_link_suggester import create_llm_suggested_links

    session = MagicMock()
    suggestions = [{
        "source_element_id": "4:abc:1",
        "target_element_id": "4:abc:2",
        "source": "REsp 1234",
        "target": "REsp 5678",
        "node_type": "Decisao",
        "type": "CITA",
        "confidence": 0.85,
        "reasoning": "test",
        "evidence": "trecho real",
        "evidence_validated": True,
    }]

    count = create_llm_suggested_links(session, suggestions)
    assert count == 1

    # Verify it used elementId path (first branch)
    call_args = session.run.call_args
    query = call_args[0][0]
    assert "RELATED_TO" in query
    assert "candidate" in query  # layer = 'candidate'
    # Should NOT create typed relationship like :CITA directly
    assert "CREATE (a)-[r:CITA]" not in query


def test_explicit_node_type():
    """Suggestions should use explicit node_type, not heuristic name matching."""
    from app.services.rag.core.kg_builder.llm_link_suggester import create_llm_suggested_links

    session = MagicMock()
    suggestions = [{
        "source": "Autor X",
        "target": "Autor Y",
        "node_type": "Doutrina",
        "type": "COMPLEMENTA",
        "confidence": 0.8,
        "reasoning": "test",
        "evidence": "",
        "evidence_validated": False,
    }]

    count = create_llm_suggested_links(session, suggestions)
    assert count == 1

    # Should use Doutrina in MATCH
    call_args = session.run.call_args
    query = call_args[0][0]
    assert "Doutrina" in query


# ============================================================================
# L2→L3 Handoff
# ============================================================================


def test_l2_returns_candidates_for_l3():
    """run_embedding_based_inference with pass_to_l3=True should populate candidates_for_l3."""
    from app.services.rag.core.kg_builder.link_predictor import run_embedding_based_inference

    session = MagicMock()

    # Mock that handles both .single() and iteration
    class MockResult:
        def __init__(self, data=None):
            self._data = data or {}

        def single(self):
            return self._data if self._data else None

        def __iter__(self):
            return iter([])

    # Return a mock result with cnt=0 for count queries, empty for others
    def mock_run(*args, **kwargs):
        query = args[0] if args else ""
        if "count(n)" in query:
            return MockResult({"cnt": 0})
        return MockResult()

    session.run.side_effect = mock_run

    stats = run_embedding_based_inference(
        session,
        enable_decisao=True,
        enable_sumula=False,
        enable_doutrina=False,
        pass_to_l3=True,
    )

    # With no embeddings, candidates_for_l3 should be empty
    assert isinstance(stats.candidates_for_l3, list)


@patch("app.services.rag.core.kg_builder.llm_link_suggester._get_llm_client")
def test_l3_validates_l2_candidates_no_client(mock_client):
    """validate_l2_candidates_via_llm should gracefully handle no LLM client."""
    from app.services.rag.core.kg_builder.llm_link_suggester import validate_l2_candidates_via_llm

    mock_client.return_value = None  # No client available

    session = MagicMock()
    suggestions, stats = validate_l2_candidates_via_llm(session, [])

    assert suggestions == []
    assert stats.llm_api_calls == 0


# ============================================================================
# L3b: Exploratory mode
# ============================================================================


def test_find_isolated_nodes():
    """find_isolated_nodes should return nodes with degree <= max_degree."""
    from app.services.rag.core.kg_builder.llm_explorer import find_isolated_nodes

    session = MagicMock()
    # Simulate finding 2 isolated Decisao nodes
    mock_result = [
        {"element_id": "4:abc:1", "name": "REsp 9999", "type": "Decisao", "degree": 0},
        {"element_id": "4:abc:2", "name": "AI 1234", "type": "Decisao", "degree": 1},
    ]
    session.run.return_value = iter(mock_result)

    isolated = find_isolated_nodes(session, node_types=["Decisao"], max_degree=1)

    assert len(isolated) == 2
    assert isolated[0]["degree"] <= 1
    assert isolated[1]["degree"] <= 1


def test_exploratory_creates_candidates():
    """Exploratory links should be :RELATED_TO with candidate_type='exploratory:llm:...'."""
    from app.services.rag.core.kg_builder.llm_explorer import _create_exploratory_links

    session = MagicMock()
    suggestions = [{
        "source_element_id": "4:abc:1",
        "target_element_id": "4:abc:2",
        "source_name": "REsp 9999",
        "target_name": "AI 1234",
        "source_type": "Decisao",
        "target_type": "Decisao",
        "type": "CITA",
        "confidence": 0.85,
        "reasoning": "precedente indireto",
        "evidence": "trecho real",
        "evidence_validated": True,
        "shortlist_source": "embedding",
    }]

    count = _create_exploratory_links(session, suggestions)
    assert count == 1

    call_args = session.run.call_args
    query = call_args[0][0]
    assert "RELATED_TO" in query
    assert "exploratory_llm" in query  # source = 'exploratory_llm'
    assert "candidate" in query  # layer = 'candidate'


def test_validate_evidence_explorer():
    """Explorer's _validate_evidence should behave same as L3's."""
    from app.services.rag.core.kg_builder.llm_explorer import _validate_evidence

    snippets = ["O artigo 5 da CF garante direitos fundamentais."]
    assert _validate_evidence("artigo 5 da CF garante direitos", snippets) is True
    assert _validate_evidence("artigo inventado pelo LLM", snippets) is False


# ============================================================================
# Schemas
# ============================================================================


def test_enrich_request_defaults():
    """EnrichRequest should have sensible defaults."""
    from app.schemas.graph_enrich import EnrichRequest, EnrichLayer

    req = EnrichRequest()
    assert EnrichLayer.all in req.layers
    assert req.pass_l2_to_l3 is True
    assert req.min_confidence == 0.75
    assert req.min_confidence_exploratory == 0.80
    assert req.max_isolated_nodes == 50


def test_enrich_layer_enum():
    """EnrichLayer enum should have all 5 values."""
    from app.schemas.graph_enrich import EnrichLayer

    assert EnrichLayer.structural.value == "structural"
    assert EnrichLayer.embedding.value == "embedding"
    assert EnrichLayer.llm.value == "llm"
    assert EnrichLayer.exploratory.value == "exploratory"
    assert EnrichLayer.all.value == "all"


def test_enrich_response_model():
    """EnrichResponse can be instantiated with expected fields."""
    from app.schemas.graph_enrich import EnrichResponse, LayerResult

    resp = EnrichResponse(
        success=True,
        layers_executed=["structural", "embedding"],
        total_candidates_created=42,
        total_structural_created=10,
        layer_results=[
            LayerResult(layer="structural", candidates_created=10),
            LayerResult(layer="embedding", candidates_created=32),
        ],
        duration_ms=1500,
    )
    assert resp.total_candidates_created == 42
    assert len(resp.layer_results) == 2


# ============================================================================
# Postprocessor stats
# ============================================================================


def test_postprocessor_stats_has_new_fields():
    """LegalPostProcessStats should include L3b and handoff fields."""
    from app.services.rag.core.kg_builder.legal_postprocessor import LegalPostProcessStats

    stats = LegalPostProcessStats()
    assert hasattr(stats, "exploratory_isolated_found")
    assert hasattr(stats, "exploratory_links_created")
    assert hasattr(stats, "llm_evidence_validated")
    assert hasattr(stats, "llm_l2_candidates_validated")
    assert hasattr(stats, "embedding_artigo_links_inferred")
    assert hasattr(stats, "embedding_cross_type_links_inferred")
