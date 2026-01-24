"""
Unit tests for CRAG (Corrective RAG) Gate module.

Tests cover:
- Evidence level classification (STRONG, MODERATE, LOW, INSUFFICIENT)
- Gate decisions (pass/fail based on thresholds)
- Retry strategies (multi-query, HyDE, aggressive hybrid)
- Audit trail generation
- Configuration overrides

Location: apps/api/app/services/rag/core/crag_gate.py
"""

from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from app.services.rag.core.crag_gate import (
    CRAGConfig,
    CRAGGate,
    CRAGEvaluation,
    CRAGOrchestrator,
    CRAGAuditTrail,
    CRAGIntegration,
    CorrectiveAction,
    EvidenceLevel,
    RetryParameters,
    RetryStrategyBuilder,
    evaluate_crag_gate,
    get_retry_strategy,
    create_crag_orchestrator,
)

from .fixtures import (
    high_score_results,
    low_score_results,
    mixed_score_results,
    empty_results,
    create_results_with_scores,
    create_results_with_final_scores,
    assert_valid_evaluation,
)


# =============================================================================
# CRAGConfig Tests
# =============================================================================

class TestCRAGConfig:
    """Tests for CRAGConfig dataclass."""

    def test_default_values(self):
        """Test CRAGConfig has sensible defaults."""
        config = CRAGConfig()

        assert config.min_best_score == 0.5
        assert config.min_avg_score == 0.35
        assert config.strong_best_threshold == 0.70
        assert config.strong_avg_threshold == 0.55
        assert config.max_retry_rounds == 2
        assert config.enable_multi_query is True
        assert config.enable_hyde is True
        assert config.multi_query_max == 3
        assert config.aggressive_top_k_multiplier == 2.0
        assert config.aggressive_bm25_weight == 0.45
        assert config.aggressive_semantic_weight == 0.55

    def test_with_overrides_min_scores(self):
        """Test with_overrides for min_best_score and min_avg_score."""
        config = CRAGConfig()
        new_config = config.with_overrides(min_best_score=0.6, min_avg_score=0.4)

        assert new_config.min_best_score == 0.6
        assert new_config.min_avg_score == 0.4
        # Original should be unchanged
        assert config.min_best_score == 0.5
        assert config.min_avg_score == 0.35

    def test_with_overrides_kwargs(self):
        """Test with_overrides with additional kwargs."""
        config = CRAGConfig()
        new_config = config.with_overrides(
            max_retry_rounds=5,
            enable_hyde=False,
            aggressive_top_k_multiplier=3.0,
        )

        assert new_config.max_retry_rounds == 5
        assert new_config.enable_hyde is False
        assert new_config.aggressive_top_k_multiplier == 3.0
        # Unchanged values should persist
        assert new_config.min_best_score == 0.5
        assert new_config.enable_multi_query is True

    def test_with_overrides_none_values_keep_original(self):
        """Test that None values in overrides keep original values."""
        config = CRAGConfig(min_best_score=0.6)
        new_config = config.with_overrides(min_best_score=None)

        assert new_config.min_best_score == 0.6

    def test_from_rag_config(self):
        """Test CRAGConfig.from_rag_config loads from RAGConfig."""
        mock_rag_config = MagicMock()
        mock_rag_config.crag_min_best_score = 0.55
        mock_rag_config.crag_min_avg_score = 0.40
        mock_rag_config.crag_max_retries = 3
        mock_rag_config.enable_multiquery = True
        mock_rag_config.enable_hyde = False
        mock_rag_config.multiquery_max = 4

        config = CRAGConfig.from_rag_config(mock_rag_config)

        assert config.min_best_score == 0.55
        assert config.min_avg_score == 0.40
        assert config.max_retry_rounds == 3
        assert config.enable_multi_query is True
        assert config.enable_hyde is False
        assert config.multi_query_max == 4


# =============================================================================
# EvidenceLevel Tests
# =============================================================================

class TestEvidenceLevel:
    """Tests for EvidenceLevel enum."""

    def test_requires_correction(self):
        """Test requires_correction property."""
        assert EvidenceLevel.STRONG.requires_correction is False
        assert EvidenceLevel.MODERATE.requires_correction is False
        assert EvidenceLevel.LOW.requires_correction is True
        assert EvidenceLevel.INSUFFICIENT.requires_correction is True

    def test_is_acceptable(self):
        """Test is_acceptable property."""
        assert EvidenceLevel.STRONG.is_acceptable is True
        assert EvidenceLevel.MODERATE.is_acceptable is True
        assert EvidenceLevel.LOW.is_acceptable is False
        assert EvidenceLevel.INSUFFICIENT.is_acceptable is False

    def test_confidence_score(self):
        """Test confidence_score property."""
        assert EvidenceLevel.STRONG.confidence_score == 1.0
        assert EvidenceLevel.MODERATE.confidence_score == 0.7
        assert EvidenceLevel.LOW.confidence_score == 0.4
        assert EvidenceLevel.INSUFFICIENT.confidence_score == 0.1

    def test_enum_values(self):
        """Test enum string values."""
        assert EvidenceLevel.STRONG.value == "strong"
        assert EvidenceLevel.MODERATE.value == "moderate"
        assert EvidenceLevel.LOW.value == "low"
        assert EvidenceLevel.INSUFFICIENT.value == "insufficient"


# =============================================================================
# CRAGEvaluation Tests
# =============================================================================

class TestCRAGEvaluation:
    """Tests for CRAGEvaluation dataclass."""

    def test_to_dict(self):
        """Test to_dict serialization."""
        evaluation = CRAGEvaluation(
            gate_passed=True,
            evidence_level=EvidenceLevel.STRONG,
            best_score=0.85,
            avg_top3=0.75,
            result_count=10,
            reasons=["Reason 1", "Reason 2"],
            recommended_actions=["action1"],
        )

        result = evaluation.to_dict()

        assert result["gate_passed"] is True
        assert result["evidence_level"] == "strong"
        assert result["best_score"] == 0.85
        assert result["avg_top3"] == 0.75
        assert result["result_count"] == 10
        assert result["reasons"] == ["Reason 1", "Reason 2"]
        assert result["recommended_actions"] == ["action1"]
        assert result["confidence"] == 1.0

    def test_reason_property(self):
        """Test reason property concatenates reasons."""
        evaluation = CRAGEvaluation(
            gate_passed=True,
            evidence_level=EvidenceLevel.STRONG,
            best_score=0.85,
            avg_top3=0.75,
            reasons=["First reason", "Second reason"],
            recommended_actions=[],
        )

        assert evaluation.reason == "First reason; Second reason"

    def test_reason_property_empty(self):
        """Test reason property with empty reasons."""
        evaluation = CRAGEvaluation(
            gate_passed=True,
            evidence_level=EvidenceLevel.STRONG,
            best_score=0.85,
            avg_top3=0.75,
            reasons=[],
            recommended_actions=[],
        )

        assert evaluation.reason == ""

    def test_str_representation(self):
        """Test __str__ method."""
        evaluation = CRAGEvaluation(
            gate_passed=True,
            evidence_level=EvidenceLevel.STRONG,
            best_score=0.85,
            avg_top3=0.75,
            result_count=10,
            reasons=[],
            recommended_actions=[],
        )

        result = str(evaluation)

        assert "PASSED" in result
        assert "strong" in result
        assert "0.850" in result
        assert "0.750" in result
        assert "n=10" in result


# =============================================================================
# CRAGGate Tests - Evidence Level Classification
# =============================================================================

class TestCRAGGateClassification:
    """Tests for CRAGGate evidence level classification."""

    @pytest.fixture
    def gate(self):
        """Create a CRAGGate with default config."""
        return CRAGGate(CRAGConfig())

    def test_classify_strong_evidence(self, gate):
        """Test STRONG evidence classification."""
        results = create_results_with_scores([0.85, 0.80, 0.75, 0.60])
        evaluation = gate.evaluate(results)

        assert evaluation.evidence_level == EvidenceLevel.STRONG
        assert evaluation.gate_passed is True
        assert evaluation.best_score == 0.85

    def test_classify_moderate_evidence(self, gate):
        """Test MODERATE evidence classification."""
        # Best score >= 0.5, avg >= 0.35, but not strong thresholds
        results = create_results_with_scores([0.60, 0.50, 0.40])
        evaluation = gate.evaluate(results)

        assert evaluation.evidence_level == EvidenceLevel.MODERATE
        assert evaluation.gate_passed is True

    def test_classify_low_evidence(self, gate):
        """Test LOW evidence classification."""
        # Below thresholds but non-zero
        results = create_results_with_scores([0.40, 0.30, 0.25])
        evaluation = gate.evaluate(results)

        assert evaluation.evidence_level == EvidenceLevel.LOW
        assert evaluation.gate_passed is False

    def test_classify_insufficient_evidence_empty(self, gate):
        """Test INSUFFICIENT evidence for empty results."""
        results = []
        evaluation = gate.evaluate(results)

        assert evaluation.evidence_level == EvidenceLevel.INSUFFICIENT
        assert evaluation.gate_passed is False
        assert evaluation.best_score == 0.0
        assert evaluation.avg_top3 == 0.0
        assert "No results" in evaluation.reasons[0]

    def test_classify_insufficient_evidence_zero_scores(self, gate):
        """Test INSUFFICIENT evidence for zero scores."""
        results = create_results_with_scores([0.0, 0.0, 0.0])
        evaluation = gate.evaluate(results)

        assert evaluation.evidence_level == EvidenceLevel.INSUFFICIENT
        assert evaluation.gate_passed is False


# =============================================================================
# CRAGGate Tests - Gate Decisions
# =============================================================================

class TestCRAGGateDecisions:
    """Tests for CRAGGate pass/fail decisions."""

    def test_gate_passes_with_high_scores(self, high_score_results):
        """Test gate passes with high quality results."""
        gate = CRAGGate(CRAGConfig())
        evaluation = gate.evaluate(high_score_results)

        assert evaluation.gate_passed is True
        assert "Gate passed" in evaluation.reason

    def test_gate_fails_with_low_scores(self, low_score_results):
        """Test gate fails with low quality results."""
        gate = CRAGGate(CRAGConfig())
        evaluation = gate.evaluate(low_score_results)

        assert evaluation.gate_passed is False
        assert "below minimum threshold" in evaluation.reason.lower()

    def test_gate_passes_at_threshold(self):
        """Test gate passes at exact threshold."""
        config = CRAGConfig(min_best_score=0.5, min_avg_score=0.35)
        gate = CRAGGate(config)

        # Scores exactly at threshold
        results = create_results_with_scores([0.5, 0.35, 0.35])
        evaluation = gate.evaluate(results)

        assert evaluation.gate_passed is True

    def test_gate_fails_just_below_threshold(self):
        """Test gate fails just below threshold."""
        config = CRAGConfig(min_best_score=0.5, min_avg_score=0.35)
        gate = CRAGGate(config)

        results = create_results_with_scores([0.49, 0.35, 0.35])
        evaluation = gate.evaluate(results)

        assert evaluation.gate_passed is False

    def test_gate_uses_final_score_field(self):
        """Test gate correctly uses final_score field."""
        gate = CRAGGate(CRAGConfig())
        results = create_results_with_final_scores([0.85, 0.75, 0.65])
        evaluation = gate.evaluate(results)

        assert evaluation.best_score == 0.85
        assert evaluation.gate_passed is True

    def test_gate_handles_mixed_score_fields(self):
        """Test gate handles results with different score field names."""
        gate = CRAGGate(CRAGConfig())
        results = [
            {"chunk_uid": "a", "score": 0.80, "text": "Doc A"},
            {"chunk_uid": "b", "final_score": 0.75, "text": "Doc B"},
            {"chunk_uid": "c", "rerank_score": 0.70, "text": "Doc C"},
        ]
        evaluation = gate.evaluate(results)

        assert evaluation.best_score == 0.80
        assert evaluation.result_count == 3

    def test_gate_handles_invalid_scores(self):
        """Test gate handles invalid/non-numeric scores gracefully."""
        gate = CRAGGate(CRAGConfig())
        results = [
            {"chunk_uid": "a", "score": "invalid", "text": "Doc A"},
            {"chunk_uid": "b", "score": None, "text": "Doc B"},
            {"chunk_uid": "c", "score": 0.7, "text": "Doc C"},
        ]
        evaluation = gate.evaluate(results)

        # Should handle gracefully, using 0.0 for invalid scores
        assert evaluation.result_count == 3
        assert evaluation.best_score == 0.7


# =============================================================================
# CRAGGate Tests - Recommended Actions
# =============================================================================

class TestCRAGGateRecommendedActions:
    """Tests for CRAGGate recommended actions."""

    def test_strong_evidence_no_actions(self):
        """Test STRONG evidence recommends no actions."""
        gate = CRAGGate(CRAGConfig())
        results = create_results_with_scores([0.85, 0.80, 0.75])
        evaluation = gate.evaluate(results)

        assert evaluation.recommended_actions == []

    def test_moderate_evidence_expand_top_k(self):
        """Test MODERATE evidence recommends expand_top_k."""
        gate = CRAGGate(CRAGConfig())
        results = create_results_with_scores([0.55, 0.45, 0.40])
        evaluation = gate.evaluate(results)

        assert "expand_top_k" in evaluation.recommended_actions

    def test_low_evidence_recommends_multi_query(self):
        """Test LOW evidence recommends multi_query."""
        gate = CRAGGate(CRAGConfig(enable_multi_query=True))
        results = create_results_with_scores([0.40, 0.30, 0.25])
        evaluation = gate.evaluate(results)

        assert "multi_query" in evaluation.recommended_actions
        assert "aggressive_hybrid" in evaluation.recommended_actions

    def test_low_evidence_recommends_hyde_when_very_low(self):
        """Test LOW evidence recommends HyDE when scores very low."""
        gate = CRAGGate(CRAGConfig(enable_hyde=True))
        results = create_results_with_scores([0.20, 0.15, 0.10])
        evaluation = gate.evaluate(results)

        assert "hyde" in evaluation.recommended_actions

    def test_insufficient_evidence_recommends_all_strategies(self):
        """Test INSUFFICIENT evidence recommends multiple strategies."""
        gate = CRAGGate(CRAGConfig(enable_multi_query=True, enable_hyde=True))
        results = []
        evaluation = gate.evaluate(results)

        assert "multi_query" in evaluation.recommended_actions
        assert "hyde" in evaluation.recommended_actions
        assert "expand_sources" in evaluation.recommended_actions

    def test_disabled_strategies_not_recommended(self):
        """Test disabled strategies are not recommended."""
        gate = CRAGGate(CRAGConfig(enable_multi_query=False, enable_hyde=False))
        results = create_results_with_scores([0.20, 0.15, 0.10])
        evaluation = gate.evaluate(results)

        assert "multi_query" not in evaluation.recommended_actions
        assert "hyde" not in evaluation.recommended_actions


# =============================================================================
# RetryStrategyBuilder Tests
# =============================================================================

class TestRetryStrategyBuilder:
    """Tests for RetryStrategyBuilder."""

    def test_no_strategies_for_strong_evidence(self):
        """Test no retry strategies for STRONG evidence."""
        config = CRAGConfig()
        builder = RetryStrategyBuilder(config, base_top_k=10)

        strategies = builder.get_strategies(EvidenceLevel.STRONG)

        assert strategies == []

    def test_expand_top_k_for_moderate_evidence(self):
        """Test expand_top_k strategy for MODERATE evidence."""
        config = CRAGConfig()
        builder = RetryStrategyBuilder(config, base_top_k=10)

        strategies = builder.get_strategies(EvidenceLevel.MODERATE)

        assert len(strategies) == 1
        assert strategies[0].strategy_name == "expand_top_k"
        assert strategies[0].top_k == 15  # 10 * 1.5

    def test_aggressive_strategies_for_low_evidence(self):
        """Test aggressive strategies for LOW evidence."""
        config = CRAGConfig(enable_multi_query=True, enable_hyde=True, max_retry_rounds=5)
        builder = RetryStrategyBuilder(config, base_top_k=10)

        strategies = builder.get_strategies(EvidenceLevel.LOW)

        strategy_names = [s.strategy_name for s in strategies]
        assert "aggressive_hybrid" in strategy_names
        assert "multi_query" in strategy_names
        # HyDE is included for LOW evidence
        assert "hyde" in strategy_names

    def test_combined_strategy_for_insufficient(self):
        """Test combined strategies for INSUFFICIENT evidence."""
        config = CRAGConfig(enable_multi_query=True, max_retry_rounds=5)
        builder = RetryStrategyBuilder(config, base_top_k=10)

        strategies = builder.get_strategies(EvidenceLevel.INSUFFICIENT)

        strategy_names = [s.strategy_name for s in strategies]
        assert "aggressive_multi_query" in strategy_names

    def test_max_retry_rounds_limits_strategies(self):
        """Test max_retry_rounds limits number of strategies."""
        config = CRAGConfig(max_retry_rounds=1, enable_multi_query=True, enable_hyde=True)
        builder = RetryStrategyBuilder(config, base_top_k=10)

        strategies = builder.get_strategies(EvidenceLevel.LOW)

        assert len(strategies) <= 1

    def test_already_used_strategies_excluded(self):
        """Test already used strategies are excluded."""
        config = CRAGConfig(enable_multi_query=True, enable_hyde=True)
        builder = RetryStrategyBuilder(config, base_top_k=10)

        strategies = builder.get_strategies(
            EvidenceLevel.LOW,
            already_used_multi_query=True,
            already_used_hyde=True,
        )

        strategy_names = [s.strategy_name for s in strategies]
        assert "multi_query" not in strategy_names
        assert "hyde" not in strategy_names

    def test_retry_parameters_to_dict(self):
        """Test RetryParameters.to_dict serialization."""
        params = RetryParameters(
            top_k=20,
            bm25_weight=0.45,
            semantic_weight=0.55,
            use_multi_query=True,
            multi_query_count=3,
            use_hyde=False,
            strategy_name="test_strategy",
        )

        result = params.to_dict()

        assert result["top_k"] == 20
        assert result["bm25_weight"] == 0.45
        assert result["semantic_weight"] == 0.55
        assert result["use_multi_query"] is True
        assert result["multi_query_count"] == 3
        assert result["use_hyde"] is False
        assert result["strategy_name"] == "test_strategy"

    def test_suggest_adjustments(self):
        """Test suggest_adjustments method."""
        config = CRAGConfig()
        builder = RetryStrategyBuilder(config, base_top_k=10)

        # Round 0 - aggressive hybrid
        adj0 = builder.suggest_adjustments(EvidenceLevel.LOW, current_round=0)
        assert adj0["top_k_multiplier"] == 2.0
        assert adj0["bm25_weight"] == 0.45

        # Round 1 - multi-query
        adj1 = builder.suggest_adjustments(EvidenceLevel.LOW, current_round=1)
        assert adj1["use_multi_query"] is True

        # Round 2+ - HyDE
        adj2 = builder.suggest_adjustments(EvidenceLevel.LOW, current_round=2)
        assert adj2["use_hyde"] is True


# =============================================================================
# CRAGOrchestrator Tests
# =============================================================================

class TestCRAGOrchestrator:
    """Tests for CRAGOrchestrator."""

    @pytest.fixture
    def orchestrator(self):
        """Create orchestrator with default config."""
        return CRAGOrchestrator(CRAGConfig())

    def test_evaluate_results(self, orchestrator, high_score_results):
        """Test evaluate_results delegates to gate."""
        evaluation = orchestrator.evaluate_results(high_score_results)

        assert_valid_evaluation(evaluation)
        assert evaluation.gate_passed is True

    def test_should_retry_gate_passed(self, orchestrator, high_score_results):
        """Test should_retry returns False when gate passed."""
        evaluation = orchestrator.evaluate_results(high_score_results)

        assert orchestrator.should_retry(evaluation, current_round=0) is False

    def test_should_retry_gate_failed(self, orchestrator, low_score_results):
        """Test should_retry returns True when gate failed."""
        evaluation = orchestrator.evaluate_results(low_score_results)

        assert orchestrator.should_retry(evaluation, current_round=0) is True

    def test_should_retry_max_rounds_exceeded(self, orchestrator, low_score_results):
        """Test should_retry returns False when max rounds exceeded."""
        evaluation = orchestrator.evaluate_results(low_score_results)

        # Default max is 2
        assert orchestrator.should_retry(evaluation, current_round=0) is True
        assert orchestrator.should_retry(evaluation, current_round=1) is True
        assert orchestrator.should_retry(evaluation, current_round=2) is False

    def test_should_retry_empty_results_after_first(self, orchestrator, empty_results):
        """Test should_retry returns False for empty results after first try."""
        evaluation = orchestrator.evaluate_results(empty_results)

        assert orchestrator.should_retry(evaluation, current_round=0) is True
        assert orchestrator.should_retry(evaluation, current_round=1) is False

    def test_get_retry_parameters(self, orchestrator, low_score_results):
        """Test get_retry_parameters returns valid parameters."""
        evaluation = orchestrator.evaluate_results(low_score_results)

        params = orchestrator.get_retry_parameters(
            evaluation, base_top_k=10, current_round=0
        )

        assert params is not None
        assert params.top_k > 0
        assert params.strategy_name == "aggressive_hybrid"

    def test_get_retry_parameters_none_when_no_retry(self, orchestrator, high_score_results):
        """Test get_retry_parameters returns None when no retry needed."""
        evaluation = orchestrator.evaluate_results(high_score_results)

        params = orchestrator.get_retry_parameters(
            evaluation, base_top_k=10, current_round=0
        )

        assert params is None


# =============================================================================
# CRAGAuditTrail Tests
# =============================================================================

class TestCRAGAuditTrail:
    """Tests for CRAGAuditTrail."""

    def test_create_audit_trail(self):
        """Test creating an audit trail."""
        evaluation = CRAGEvaluation(
            gate_passed=False,
            evidence_level=EvidenceLevel.LOW,
            best_score=0.4,
            avg_top3=0.3,
            reasons=["Low scores"],
            recommended_actions=["multi_query"],
        )

        trail = CRAGAuditTrail(
            query="test query",
            initial_evaluation=evaluation,
        )

        assert trail.query == "test query"
        assert trail.initial_evaluation == evaluation
        assert len(trail.actions) == 0
        assert trail.correction_attempted is False

    def test_add_action(self):
        """Test adding corrective actions."""
        trail = CRAGAuditTrail(
            query="test query",
            initial_evaluation=CRAGEvaluation(
                gate_passed=False,
                evidence_level=EvidenceLevel.LOW,
                best_score=0.4,
                avg_top3=0.3,
                reasons=[],
                recommended_actions=[],
            ),
        )

        action = CorrectiveAction(
            strategy="multi_query",
            success=True,
            duration_ms=150,
            result_count=5,
            best_score=0.7,
            avg_top3=0.6,
        )

        trail.add_action(action)

        assert len(trail.actions) == 1
        assert trail.correction_attempted is True

    def test_finalize(self):
        """Test finalizing audit trail."""
        trail = CRAGAuditTrail(
            query="test query",
            initial_evaluation=CRAGEvaluation(
                gate_passed=False,
                evidence_level=EvidenceLevel.LOW,
                best_score=0.4,
                avg_top3=0.3,
                reasons=[],
                recommended_actions=[],
            ),
        )

        final_eval = CRAGEvaluation(
            gate_passed=True,
            evidence_level=EvidenceLevel.MODERATE,
            best_score=0.6,
            avg_top3=0.5,
            reasons=[],
            recommended_actions=[],
        )

        trail.finalize(final_eval, total_duration_ms=200, final_result_count=10)

        assert trail.final_evaluation == final_eval
        assert trail.total_duration_ms == 200
        assert trail.final_result_count == 10

    def test_correction_successful(self):
        """Test correction_successful property."""
        trail = CRAGAuditTrail(
            query="test query",
            initial_evaluation=CRAGEvaluation(
                gate_passed=False,
                evidence_level=EvidenceLevel.LOW,
                best_score=0.4,
                avg_top3=0.3,
                reasons=[],
                recommended_actions=[],
            ),
        )

        trail.add_action(
            CorrectiveAction(
                strategy="multi_query",
                success=True,
                duration_ms=150,
                result_count=5,
                best_score=0.7,
                avg_top3=0.6,
            )
        )

        trail.finalize(
            CRAGEvaluation(
                gate_passed=True,
                evidence_level=EvidenceLevel.MODERATE,
                best_score=0.6,
                avg_top3=0.5,
                reasons=[],
                recommended_actions=[],
            ),
            total_duration_ms=200,
            final_result_count=10,
        )

        assert trail.correction_successful is True

    def test_to_dict_serialization(self):
        """Test to_dict serialization."""
        trail = CRAGAuditTrail(
            query="test query",
            initial_evaluation=CRAGEvaluation(
                gate_passed=False,
                evidence_level=EvidenceLevel.LOW,
                best_score=0.4,
                avg_top3=0.3,
                reasons=["Low scores"],
                recommended_actions=["multi_query"],
            ),
        )

        result = trail.to_dict()

        assert "query" in result
        assert "initial_evaluation" in result
        assert "actions" in result
        assert result["correction_attempted"] is False


# =============================================================================
# CRAGIntegration Tests
# =============================================================================

class TestCRAGIntegration:
    """Tests for CRAGIntegration high-level interface."""

    @pytest.fixture
    def mock_search_fn(self):
        """Create mock search function."""
        async def search_fn(query: str, top_k: int, **kwargs):
            return [
                {"chunk_uid": "doc1", "text": "Result 1", "score": 0.75},
                {"chunk_uid": "doc2", "text": "Result 2", "score": 0.65},
            ]
        return search_fn

    @pytest.fixture
    def mock_multi_query_fn(self):
        """Create mock multi-query function."""
        async def multi_query_fn(query: str):
            return [query, f"{query} variant 1", f"{query} variant 2"]
        return multi_query_fn

    @pytest.fixture
    def mock_hyde_fn(self):
        """Create mock HyDE function."""
        async def hyde_fn(query: str):
            return f"Hypothetical document for: {query}"
        return hyde_fn

    @pytest.mark.asyncio
    async def test_search_with_correction_no_retry_needed(
        self, mock_search_fn, mock_multi_query_fn, mock_hyde_fn
    ):
        """Test search_with_correction when no retry needed."""
        integration = CRAGIntegration(
            config=CRAGConfig(min_best_score=0.5, min_avg_score=0.3),
            search_fn=mock_search_fn,
            multi_query_fn=mock_multi_query_fn,
            hyde_fn=mock_hyde_fn,
        )

        initial_results = [
            {"chunk_uid": "doc1", "text": "Good result", "score": 0.80},
            {"chunk_uid": "doc2", "text": "Another good result", "score": 0.70},
            {"chunk_uid": "doc3", "text": "Third result", "score": 0.60},
        ]

        results, trail = await integration.search_with_correction(
            query="test query",
            initial_results=initial_results,
            base_top_k=10,
        )

        assert len(results) == 3
        assert trail.correction_attempted is False
        assert trail.initial_evaluation.gate_passed is True

    @pytest.mark.asyncio
    async def test_search_with_correction_retry_success(
        self, mock_search_fn, mock_multi_query_fn, mock_hyde_fn
    ):
        """Test search_with_correction with successful retry."""
        integration = CRAGIntegration(
            config=CRAGConfig(min_best_score=0.6, min_avg_score=0.5),
            search_fn=mock_search_fn,
            multi_query_fn=mock_multi_query_fn,
            hyde_fn=mock_hyde_fn,
        )

        initial_results = [
            {"chunk_uid": "doc1", "text": "Low result", "score": 0.40},
            {"chunk_uid": "doc2", "text": "Another low result", "score": 0.30},
        ]

        results, trail = await integration.search_with_correction(
            query="test query",
            initial_results=initial_results,
            base_top_k=10,
        )

        assert trail.correction_attempted is True
        assert len(trail.actions) > 0

    def test_dedupe_results(self):
        """Test _dedupe_results removes duplicates and keeps highest score."""
        integration = CRAGIntegration(config=CRAGConfig())

        results = [
            {"chunk_uid": "doc1", "text": "Doc 1", "score": 0.5},
            {"chunk_uid": "doc1", "text": "Doc 1", "score": 0.8},  # Duplicate, higher score
            {"chunk_uid": "doc2", "text": "Doc 2", "score": 0.6},
        ]

        deduped = integration._dedupe_results(results)

        assert len(deduped) == 2
        # doc1 should have the higher score
        doc1 = next(r for r in deduped if r["chunk_uid"] == "doc1")
        assert doc1["score"] == 0.8


# =============================================================================
# Convenience Function Tests
# =============================================================================

class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""

    @patch("app.services.rag.core.crag_gate.CRAGConfig.from_env")
    def test_evaluate_crag_gate(self, mock_from_env, high_score_results):
        """Test evaluate_crag_gate convenience function."""
        mock_from_env.return_value = CRAGConfig()

        result = evaluate_crag_gate(high_score_results)

        assert "gate_passed" in result
        assert "evidence_level" in result
        assert "best_score" in result
        assert "avg_top3" in result
        assert "safe_mode" in result
        assert result["gate_passed"] is True
        assert result["safe_mode"] is False

    @patch("app.services.rag.core.crag_gate.CRAGConfig.from_env")
    def test_evaluate_crag_gate_with_overrides(self, mock_from_env, high_score_results):
        """Test evaluate_crag_gate with custom thresholds."""
        mock_from_env.return_value = CRAGConfig()

        result = evaluate_crag_gate(
            high_score_results,
            min_best_score=0.95,  # Higher threshold
            min_avg_score=0.90,
        )

        # Should fail with higher thresholds
        assert result["gate_passed"] is False

    @patch("app.services.rag.core.crag_gate.CRAGConfig.from_env")
    def test_get_retry_strategy(self, mock_from_env, low_score_results):
        """Test get_retry_strategy convenience function."""
        mock_from_env.return_value = CRAGConfig()

        result = get_retry_strategy(
            low_score_results,
            base_top_k=10,
        )

        assert result is not None
        assert "top_k" in result
        assert "strategy_name" in result

    @patch("app.services.rag.core.crag_gate.CRAGConfig.from_env")
    def test_get_retry_strategy_none_when_good(self, mock_from_env, high_score_results):
        """Test get_retry_strategy returns None for good results."""
        mock_from_env.return_value = CRAGConfig()

        result = get_retry_strategy(high_score_results, base_top_k=10)

        assert result is None

    @patch("app.services.rag.core.crag_gate.CRAGConfig.from_env")
    def test_create_crag_orchestrator(self, mock_from_env):
        """Test create_crag_orchestrator factory function."""
        mock_from_env.return_value = CRAGConfig()

        orchestrator = create_crag_orchestrator(
            min_best_score=0.6,
            max_retry_rounds=3,
        )

        assert isinstance(orchestrator, CRAGOrchestrator)
        assert orchestrator.config.min_best_score == 0.6
        assert orchestrator.config.max_retry_rounds == 3


# =============================================================================
# Edge Cases and Error Handling
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_single_result(self):
        """Test evaluation with single result."""
        gate = CRAGGate(CRAGConfig())
        results = [{"chunk_uid": "doc1", "text": "Only doc", "score": 0.75}]

        evaluation = gate.evaluate(results)

        assert evaluation.result_count == 1
        assert evaluation.best_score == 0.75
        # avg_top3 should handle less than 3 results
        assert evaluation.avg_top3 == 0.75

    def test_two_results(self):
        """Test evaluation with two results."""
        gate = CRAGGate(CRAGConfig())
        results = [
            {"chunk_uid": "doc1", "text": "Doc 1", "score": 0.80},
            {"chunk_uid": "doc2", "text": "Doc 2", "score": 0.60},
        ]

        evaluation = gate.evaluate(results)

        assert evaluation.result_count == 2
        assert evaluation.avg_top3 == 0.70  # (0.8 + 0.6) / 2

    def test_very_high_scores(self):
        """Test evaluation with scores near 1.0."""
        gate = CRAGGate(CRAGConfig())
        results = create_results_with_scores([0.99, 0.98, 0.97])

        evaluation = gate.evaluate(results)

        assert evaluation.evidence_level == EvidenceLevel.STRONG
        assert evaluation.gate_passed is True
        assert evaluation.best_score == 0.99

    def test_negative_scores_handled(self):
        """Test evaluation handles negative scores gracefully."""
        gate = CRAGGate(CRAGConfig())
        results = [
            {"chunk_uid": "doc1", "text": "Doc 1", "score": -0.5},
            {"chunk_uid": "doc2", "text": "Doc 2", "score": 0.3},
        ]

        evaluation = gate.evaluate(results)

        # Should not crash, LOW or INSUFFICIENT based on best positive
        assert evaluation.result_count == 2

    def test_results_without_text_field(self):
        """Test evaluation with results missing text field."""
        gate = CRAGGate(CRAGConfig())
        results = [
            {"chunk_uid": "doc1", "score": 0.8},
            {"chunk_uid": "doc2", "score": 0.7},
        ]

        evaluation = gate.evaluate(results)

        assert evaluation.result_count == 2
        assert evaluation.best_score == 0.8

    def test_corrective_action_to_dict(self):
        """Test CorrectiveAction serialization."""
        action = CorrectiveAction(
            strategy="multi_query",
            success=True,
            duration_ms=100,
            result_count=5,
            best_score=0.7,
            avg_top3=0.6,
            parameters={"top_k": 20},
            error=None,
        )

        result = action.to_dict()

        assert result["strategy"] == "multi_query"
        assert result["success"] is True
        assert result["duration_ms"] == 100
        assert result["parameters"] == {"top_k": 20}
        assert result["error"] is None

    def test_corrective_action_with_error(self):
        """Test CorrectiveAction with error."""
        action = CorrectiveAction(
            strategy="hyde",
            success=False,
            duration_ms=50,
            result_count=0,
            best_score=0.0,
            avg_top3=0.0,
            error="LLM timeout",
        )

        result = action.to_dict()

        assert result["success"] is False
        assert result["error"] == "LLM timeout"
