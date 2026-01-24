"""
Corrective RAG (CRAG) Gate Implementation

This module provides evidence quality assessment and corrective retrieval strategies
for the RAG pipeline. It evaluates search results against configurable thresholds
and recommends/executes fallback strategies when evidence is insufficient.

Key Features:
- Configurable score thresholds (MIN_BEST_SCORE, MIN_AVG_SCORE)
- Evidence levels: "strong", "moderate", "low", "insufficient"
- Multi-query and HyDE fallback strategies
- Comprehensive audit trail of corrective actions
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("CRAGGate")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def _env_float(name: str, default: float) -> float:
    """Read float from environment variable with fallback."""
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    """Read int from environment variable with fallback."""
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    """Read boolean from environment variable with fallback."""
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).lower() in ("1", "true", "yes", "on")


@dataclass
class CRAGConfig:
    """
    Configuration for CRAG gate thresholds and retry strategies.

    Attributes:
        min_best_score: Minimum acceptable score for the top result
        min_avg_score: Minimum acceptable average score for top-3 results
        strong_best_threshold: Score above which evidence is considered strong
        strong_avg_threshold: Average above which evidence is considered strong
        max_retry_rounds: Maximum number of corrective retry attempts
        enable_multi_query: Whether to use multi-query as fallback
        enable_hyde: Whether to use HyDE as fallback
        aggressive_top_k_multiplier: Factor to increase top_k in aggressive mode
        aggressive_bm25_weight: BM25 weight for aggressive hybrid search
        aggressive_semantic_weight: Semantic weight for aggressive hybrid search
    """

    min_best_score: float = field(
        default_factory=lambda: _env_float("CRAG_MIN_BEST_SCORE", 0.35)
    )
    min_avg_score: float = field(
        default_factory=lambda: _env_float("CRAG_MIN_AVG_SCORE", 0.25)
    )
    strong_best_threshold: float = field(
        default_factory=lambda: _env_float("CRAG_STRONG_BEST_THRESHOLD", 0.65)
    )
    strong_avg_threshold: float = field(
        default_factory=lambda: _env_float("CRAG_STRONG_AVG_THRESHOLD", 0.50)
    )
    max_retry_rounds: int = field(
        default_factory=lambda: _env_int("CRAG_MAX_RETRY_ROUNDS", 2)
    )
    enable_multi_query: bool = field(
        default_factory=lambda: _env_bool("CRAG_ENABLE_MULTI_QUERY", True)
    )
    enable_hyde: bool = field(
        default_factory=lambda: _env_bool("CRAG_ENABLE_HYDE", True)
    )
    multi_query_max: int = field(
        default_factory=lambda: _env_int("CRAG_MULTI_QUERY_MAX", 3)
    )
    aggressive_top_k_multiplier: float = field(
        default_factory=lambda: _env_float("CRAG_AGGRESSIVE_TOP_K_MULT", 2.0)
    )
    aggressive_bm25_weight: float = field(
        default_factory=lambda: _env_float("CRAG_AGGRESSIVE_BM25_WEIGHT", 0.45)
    )
    aggressive_semantic_weight: float = field(
        default_factory=lambda: _env_float("CRAG_AGGRESSIVE_SEMANTIC_WEIGHT", 0.55)
    )

    @classmethod
    def from_env(cls) -> "CRAGConfig":
        """Create configuration from environment variables."""
        return cls()

    def with_overrides(
        self,
        min_best_score: Optional[float] = None,
        min_avg_score: Optional[float] = None,
        **kwargs: Any,
    ) -> "CRAGConfig":
        """Create a copy with specified overrides."""
        return CRAGConfig(
            min_best_score=min_best_score if min_best_score is not None else self.min_best_score,
            min_avg_score=min_avg_score if min_avg_score is not None else self.min_avg_score,
            strong_best_threshold=kwargs.get("strong_best_threshold", self.strong_best_threshold),
            strong_avg_threshold=kwargs.get("strong_avg_threshold", self.strong_avg_threshold),
            max_retry_rounds=kwargs.get("max_retry_rounds", self.max_retry_rounds),
            enable_multi_query=kwargs.get("enable_multi_query", self.enable_multi_query),
            enable_hyde=kwargs.get("enable_hyde", self.enable_hyde),
            multi_query_max=kwargs.get("multi_query_max", self.multi_query_max),
            aggressive_top_k_multiplier=kwargs.get("aggressive_top_k_multiplier", self.aggressive_top_k_multiplier),
            aggressive_bm25_weight=kwargs.get("aggressive_bm25_weight", self.aggressive_bm25_weight),
            aggressive_semantic_weight=kwargs.get("aggressive_semantic_weight", self.aggressive_semantic_weight),
        )


# ---------------------------------------------------------------------------
# Evidence Levels
# ---------------------------------------------------------------------------


class EvidenceLevel(str, Enum):
    """Classification of evidence quality based on retrieval scores."""

    STRONG = "strong"
    MODERATE = "moderate"
    LOW = "low"
    INSUFFICIENT = "insufficient"

    @property
    def requires_correction(self) -> bool:
        """Check if this evidence level requires corrective action."""
        return self in (EvidenceLevel.LOW, EvidenceLevel.INSUFFICIENT)

    @property
    def is_acceptable(self) -> bool:
        """Check if this evidence level is acceptable for proceeding."""
        return self in (EvidenceLevel.STRONG, EvidenceLevel.MODERATE)


# ---------------------------------------------------------------------------
# Evaluation Result
# ---------------------------------------------------------------------------


@dataclass
class CRAGEvaluation:
    """
    Result of CRAG gate evaluation.

    Attributes:
        gate_passed: Whether the evidence passes the minimum thresholds
        evidence_level: Classification of evidence quality
        best_score: Score of the top result
        avg_top3: Average score of top 3 results
        result_count: Number of results evaluated
        reason: Human-readable explanation
        recommended_actions: List of recommended corrective actions
    """

    gate_passed: bool
    evidence_level: EvidenceLevel
    best_score: float
    avg_top3: float
    result_count: int
    reason: str
    recommended_actions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/serialization."""
        return {
            "gate_passed": self.gate_passed,
            "evidence_level": self.evidence_level.value,
            "best_score": round(self.best_score, 4),
            "avg_top3": round(self.avg_top3, 4),
            "result_count": self.result_count,
            "reason": self.reason,
            "recommended_actions": self.recommended_actions,
        }


# ---------------------------------------------------------------------------
# Corrective Action Tracking
# ---------------------------------------------------------------------------


@dataclass
class CorrectiveAction:
    """Record of a single corrective action attempted."""

    strategy: str
    success: bool
    duration_ms: int
    result_count: int
    best_score: float
    avg_top3: float
    parameters: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/serialization."""
        return {
            "strategy": self.strategy,
            "success": self.success,
            "duration_ms": self.duration_ms,
            "result_count": self.result_count,
            "best_score": round(self.best_score, 4),
            "avg_top3": round(self.avg_top3, 4),
            "parameters": self.parameters,
            "error": self.error,
        }


@dataclass
class CRAGAuditTrail:
    """
    Complete audit trail of CRAG evaluation and corrective actions.

    This provides full transparency into what was attempted and why.
    """

    query: str
    initial_evaluation: CRAGEvaluation
    actions: List[CorrectiveAction] = field(default_factory=list)
    final_evaluation: Optional[CRAGEvaluation] = None
    total_duration_ms: int = 0
    final_result_count: int = 0

    def add_action(self, action: CorrectiveAction) -> None:
        """Add a corrective action to the trail."""
        self.actions.append(action)

    def finalize(
        self,
        final_eval: CRAGEvaluation,
        total_duration_ms: int,
        final_result_count: int,
    ) -> None:
        """Finalize the audit trail with final results."""
        self.final_evaluation = final_eval
        self.total_duration_ms = total_duration_ms
        self.final_result_count = final_result_count

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/serialization."""
        return {
            "query": self.query[:200],
            "initial_evaluation": self.initial_evaluation.to_dict(),
            "actions": [a.to_dict() for a in self.actions],
            "final_evaluation": self.final_evaluation.to_dict() if self.final_evaluation else None,
            "total_duration_ms": self.total_duration_ms,
            "final_result_count": self.final_result_count,
            "correction_attempted": len(self.actions) > 0,
            "correction_successful": (
                self.final_evaluation is not None
                and self.final_evaluation.gate_passed
                and not self.initial_evaluation.gate_passed
            ),
        }

    def log_summary(self) -> None:
        """Log a summary of the audit trail."""
        summary = self.to_dict()
        if summary["correction_attempted"]:
            if summary["correction_successful"]:
                logger.info(
                    "CRAG correction successful: query=%s initial_level=%s final_level=%s actions=%s duration_ms=%s",
                    self.query[:80],
                    self.initial_evaluation.evidence_level.value,
                    self.final_evaluation.evidence_level.value if self.final_evaluation else "none",
                    [a.strategy for a in self.actions],
                    self.total_duration_ms,
                )
            else:
                logger.warning(
                    "CRAG correction unsuccessful: query=%s level=%s actions=%s duration_ms=%s",
                    self.query[:80],
                    self.final_evaluation.evidence_level.value if self.final_evaluation else "unknown",
                    [a.strategy for a in self.actions],
                    self.total_duration_ms,
                )
        else:
            logger.debug(
                "CRAG gate passed without correction: query=%s level=%s best=%.3f avg=%.3f",
                self.query[:80],
                self.initial_evaluation.evidence_level.value,
                self.initial_evaluation.best_score,
                self.initial_evaluation.avg_top3,
            )


# ---------------------------------------------------------------------------
# Core CRAG Gate Logic
# ---------------------------------------------------------------------------


class CRAGGate:
    """
    Corrective RAG Gate for evidence quality assessment and retry strategies.

    This class evaluates retrieval results against configurable thresholds
    and provides recommendations/execution of fallback strategies.
    """

    def __init__(self, config: Optional[CRAGConfig] = None):
        """
        Initialize CRAG gate with configuration.

        Args:
            config: CRAG configuration. If None, loads from environment.
        """
        self.config = config or CRAGConfig.from_env()

    def evaluate(self, results: List[Dict[str, Any]]) -> CRAGEvaluation:
        """
        Evaluate search results against CRAG thresholds.

        Args:
            results: List of search results with 'score' or 'final_score' field

        Returns:
            CRAGEvaluation with assessment and recommendations
        """
        if not results:
            return CRAGEvaluation(
                gate_passed=False,
                evidence_level=EvidenceLevel.INSUFFICIENT,
                best_score=0.0,
                avg_top3=0.0,
                result_count=0,
                reason="No results returned from search",
                recommended_actions=["multi_query", "hyde", "expand_sources"],
            )

        # Extract scores (support both 'score' and 'final_score' keys)
        scores = []
        for r in results:
            score = r.get("final_score") or r.get("score") or 0.0
            scores.append(float(score))

        best_score = max(scores) if scores else 0.0
        top3 = scores[:3]
        avg_top3 = sum(top3) / len(top3) if top3 else 0.0

        # Determine evidence level
        evidence_level = self._classify_evidence(best_score, avg_top3)

        # Check gate passage
        gate_passed = (
            best_score >= self.config.min_best_score
            and avg_top3 >= self.config.min_avg_score
        )

        # Build reason string
        reason = (
            f"best={best_score:.3f} (threshold={self.config.min_best_score:.2f}), "
            f"avg_top3={avg_top3:.3f} (threshold={self.config.min_avg_score:.2f})"
        )

        # Determine recommended actions
        recommended_actions = self._get_recommended_actions(evidence_level, best_score, avg_top3)

        return CRAGEvaluation(
            gate_passed=gate_passed,
            evidence_level=evidence_level,
            best_score=best_score,
            avg_top3=avg_top3,
            result_count=len(results),
            reason=reason,
            recommended_actions=recommended_actions,
        )

    def _classify_evidence(self, best_score: float, avg_top3: float) -> EvidenceLevel:
        """Classify evidence level based on scores."""
        if (
            best_score >= self.config.strong_best_threshold
            and avg_top3 >= self.config.strong_avg_threshold
        ):
            return EvidenceLevel.STRONG

        if (
            best_score >= self.config.min_best_score
            and avg_top3 >= self.config.min_avg_score
        ):
            return EvidenceLevel.MODERATE

        if best_score > 0 or avg_top3 > 0:
            return EvidenceLevel.LOW

        return EvidenceLevel.INSUFFICIENT

    def _get_recommended_actions(
        self,
        evidence_level: EvidenceLevel,
        best_score: float,
        avg_top3: float,
    ) -> List[str]:
        """Get recommended corrective actions based on evidence level."""
        if evidence_level == EvidenceLevel.STRONG:
            return []

        if evidence_level == EvidenceLevel.MODERATE:
            # Moderate evidence might benefit from slight improvements
            return ["expand_top_k"]

        actions = []

        # Low or insufficient evidence - recommend multiple strategies
        if self.config.enable_multi_query:
            actions.append("multi_query")

        # If semantic scores are particularly low, HyDE might help
        if best_score < self.config.min_best_score * 0.5 and self.config.enable_hyde:
            actions.append("hyde")

        # Always suggest aggressive search parameters for low evidence
        actions.append("aggressive_hybrid")

        if evidence_level == EvidenceLevel.INSUFFICIENT:
            actions.append("expand_sources")
            if self.config.enable_hyde and "hyde" not in actions:
                actions.append("hyde")

        return actions


# ---------------------------------------------------------------------------
# Retry Strategies
# ---------------------------------------------------------------------------


@dataclass
class RetryParameters:
    """Parameters for a retry attempt."""

    top_k: int
    bm25_weight: float
    semantic_weight: float
    use_multi_query: bool
    multi_query_count: int
    use_hyde: bool
    strategy_name: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "top_k": self.top_k,
            "bm25_weight": self.bm25_weight,
            "semantic_weight": self.semantic_weight,
            "use_multi_query": self.use_multi_query,
            "multi_query_count": self.multi_query_count,
            "use_hyde": self.use_hyde,
            "strategy_name": self.strategy_name,
        }


class RetryStrategyBuilder:
    """Builds retry strategies based on evidence level and available options."""

    def __init__(self, config: CRAGConfig, base_top_k: int = 10):
        """
        Initialize retry strategy builder.

        Args:
            config: CRAG configuration
            base_top_k: Base top_k value from original search
        """
        self.config = config
        self.base_top_k = base_top_k

    def get_strategies(
        self,
        evidence_level: EvidenceLevel,
        already_used_multi_query: bool = False,
        already_used_hyde: bool = False,
    ) -> List[RetryParameters]:
        """
        Get ordered list of retry strategies based on evidence level.

        Strategies are ordered by expected effectiveness and cost.
        """
        strategies = []

        if evidence_level == EvidenceLevel.STRONG:
            return []

        if evidence_level == EvidenceLevel.MODERATE:
            # Just expand top_k slightly
            strategies.append(
                RetryParameters(
                    top_k=min(int(self.base_top_k * 1.5), 50),
                    bm25_weight=0.5,
                    semantic_weight=0.5,
                    use_multi_query=False,
                    multi_query_count=0,
                    use_hyde=False,
                    strategy_name="expand_top_k",
                )
            )
            return strategies

        # For LOW/INSUFFICIENT evidence, build aggressive strategies

        # Strategy 1: Aggressive hybrid with increased top_k
        strategies.append(
            RetryParameters(
                top_k=min(int(self.base_top_k * self.config.aggressive_top_k_multiplier), 50),
                bm25_weight=self.config.aggressive_bm25_weight,
                semantic_weight=self.config.aggressive_semantic_weight,
                use_multi_query=False,
                multi_query_count=0,
                use_hyde=False,
                strategy_name="aggressive_hybrid",
            )
        )

        # Strategy 2: Multi-query (if not already used and enabled)
        if self.config.enable_multi_query and not already_used_multi_query:
            strategies.append(
                RetryParameters(
                    top_k=self.base_top_k,
                    bm25_weight=0.5,
                    semantic_weight=0.5,
                    use_multi_query=True,
                    multi_query_count=self.config.multi_query_max,
                    use_hyde=False,
                    strategy_name="multi_query",
                )
            )

        # Strategy 3: HyDE (if not already used and enabled)
        if self.config.enable_hyde and not already_used_hyde:
            strategies.append(
                RetryParameters(
                    top_k=self.base_top_k,
                    bm25_weight=0.4,
                    semantic_weight=0.6,
                    use_multi_query=False,
                    multi_query_count=0,
                    use_hyde=True,
                    strategy_name="hyde",
                )
            )

        # Strategy 4: Combined multi-query + aggressive (for INSUFFICIENT)
        if (
            evidence_level == EvidenceLevel.INSUFFICIENT
            and self.config.enable_multi_query
            and not already_used_multi_query
        ):
            strategies.append(
                RetryParameters(
                    top_k=min(int(self.base_top_k * self.config.aggressive_top_k_multiplier), 50),
                    bm25_weight=self.config.aggressive_bm25_weight,
                    semantic_weight=self.config.aggressive_semantic_weight,
                    use_multi_query=True,
                    multi_query_count=self.config.multi_query_max,
                    use_hyde=False,
                    strategy_name="aggressive_multi_query",
                )
            )

        return strategies[:self.config.max_retry_rounds]


# ---------------------------------------------------------------------------
# CRAG Orchestrator
# ---------------------------------------------------------------------------


class CRAGOrchestrator:
    """
    Orchestrates the complete CRAG workflow including evaluation and retries.

    This is the main entry point for using CRAG in the retrieval pipeline.
    """

    def __init__(self, config: Optional[CRAGConfig] = None):
        """
        Initialize CRAG orchestrator.

        Args:
            config: CRAG configuration. If None, loads from environment.
        """
        self.config = config or CRAGConfig.from_env()
        self.gate = CRAGGate(self.config)

    def evaluate_results(self, results: List[Dict[str, Any]]) -> CRAGEvaluation:
        """
        Evaluate search results against CRAG thresholds.

        Args:
            results: Search results to evaluate

        Returns:
            CRAGEvaluation with assessment
        """
        return self.gate.evaluate(results)

    def should_retry(
        self,
        evaluation: CRAGEvaluation,
        current_round: int = 0,
    ) -> bool:
        """
        Determine if a retry should be attempted.

        Args:
            evaluation: Current evaluation result
            current_round: Current retry round (0 = initial search)

        Returns:
            True if retry should be attempted
        """
        if evaluation.gate_passed:
            return False

        if current_round >= self.config.max_retry_rounds:
            return False

        # Don't retry if we have absolutely no results and have already tried
        if evaluation.result_count == 0 and current_round > 0:
            return False

        return evaluation.evidence_level.requires_correction

    def get_retry_parameters(
        self,
        evaluation: CRAGEvaluation,
        base_top_k: int,
        already_used_multi_query: bool = False,
        already_used_hyde: bool = False,
        current_round: int = 0,
    ) -> Optional[RetryParameters]:
        """
        Get parameters for next retry attempt.

        Args:
            evaluation: Current evaluation result
            base_top_k: Base top_k from original search
            already_used_multi_query: Whether multi-query was already tried
            already_used_hyde: Whether HyDE was already tried
            current_round: Current retry round

        Returns:
            RetryParameters for next attempt, or None if no more retries
        """
        if not self.should_retry(evaluation, current_round):
            return None

        builder = RetryStrategyBuilder(self.config, base_top_k)
        strategies = builder.get_strategies(
            evaluation.evidence_level,
            already_used_multi_query,
            already_used_hyde,
        )

        if current_round < len(strategies):
            return strategies[current_round]

        return None

    def create_audit_trail(
        self,
        query: str,
        initial_results: List[Dict[str, Any]],
    ) -> CRAGAuditTrail:
        """
        Create an audit trail for CRAG operations.

        Args:
            query: Original search query
            initial_results: Initial search results

        Returns:
            CRAGAuditTrail initialized with initial evaluation
        """
        initial_eval = self.gate.evaluate(initial_results)
        return CRAGAuditTrail(
            query=query,
            initial_evaluation=initial_eval,
        )

    def record_action(
        self,
        audit_trail: CRAGAuditTrail,
        strategy: str,
        results: List[Dict[str, Any]],
        duration_ms: int,
        parameters: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> CRAGEvaluation:
        """
        Record a corrective action and its results.

        Args:
            audit_trail: The audit trail to update
            strategy: Name of the strategy used
            results: Results from the retry attempt
            duration_ms: Duration of the retry in milliseconds
            parameters: Parameters used for the retry
            error: Error message if retry failed

        Returns:
            Evaluation of the new results
        """
        evaluation = self.gate.evaluate(results)

        action = CorrectiveAction(
            strategy=strategy,
            success=evaluation.gate_passed,
            duration_ms=duration_ms,
            result_count=len(results),
            best_score=evaluation.best_score,
            avg_top3=evaluation.avg_top3,
            parameters=parameters or {},
            error=error,
        )
        audit_trail.add_action(action)

        return evaluation


# ---------------------------------------------------------------------------
# Convenience Functions
# ---------------------------------------------------------------------------


def evaluate_crag_gate(
    results: List[Dict[str, Any]],
    min_best_score: Optional[float] = None,
    min_avg_score: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Convenience function to evaluate CRAG gate.

    This provides a simple interface compatible with existing code patterns.

    Args:
        results: Search results to evaluate
        min_best_score: Override for minimum best score threshold
        min_avg_score: Override for minimum average score threshold

    Returns:
        Dictionary with gate evaluation results
    """
    config = CRAGConfig.from_env()
    if min_best_score is not None or min_avg_score is not None:
        config = config.with_overrides(
            min_best_score=min_best_score,
            min_avg_score=min_avg_score,
        )

    gate = CRAGGate(config)
    evaluation = gate.evaluate(results)

    return {
        "gate_passed": evaluation.gate_passed,
        "safe_mode": not evaluation.gate_passed,
        "evidence_level": evaluation.evidence_level.value,
        "best_score": evaluation.best_score,
        "avg_top3": evaluation.avg_top3,
        "result_count": evaluation.result_count,
        "reason": evaluation.reason,
        "recommended_actions": evaluation.recommended_actions,
    }


def get_retry_strategy(
    results: List[Dict[str, Any]],
    base_top_k: int = 10,
    already_used_multi_query: bool = False,
    already_used_hyde: bool = False,
    min_best_score: Optional[float] = None,
    min_avg_score: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """
    Get recommended retry strategy based on current results.

    Args:
        results: Current search results
        base_top_k: Base top_k value
        already_used_multi_query: Whether multi-query was already used
        already_used_hyde: Whether HyDE was already used
        min_best_score: Override for minimum best score threshold
        min_avg_score: Override for minimum average score threshold

    Returns:
        Dictionary with retry parameters, or None if no retry recommended
    """
    config = CRAGConfig.from_env()
    if min_best_score is not None or min_avg_score is not None:
        config = config.with_overrides(
            min_best_score=min_best_score,
            min_avg_score=min_avg_score,
        )

    orchestrator = CRAGOrchestrator(config)
    evaluation = orchestrator.evaluate_results(results)

    retry_params = orchestrator.get_retry_parameters(
        evaluation,
        base_top_k,
        already_used_multi_query,
        already_used_hyde,
    )

    if retry_params is None:
        return None

    return retry_params.to_dict()


# ---------------------------------------------------------------------------
# Integration Helper
# ---------------------------------------------------------------------------


class CRAGIntegration:
    """
    Integration helper for incorporating CRAG into existing retrieval pipelines.

    This class provides a high-level interface for the complete CRAG workflow.
    """

    def __init__(
        self,
        config: Optional[CRAGConfig] = None,
        search_fn: Optional[Callable[..., List[Dict[str, Any]]]] = None,
        multi_query_fn: Optional[Callable[[str], List[str]]] = None,
        hyde_fn: Optional[Callable[[str], str]] = None,
    ):
        """
        Initialize CRAG integration.

        Args:
            config: CRAG configuration
            search_fn: Function to execute search (takes query, top_k, etc.)
            multi_query_fn: Function to generate multiple queries
            hyde_fn: Function to generate hypothetical document
        """
        self.config = config or CRAGConfig.from_env()
        self.orchestrator = CRAGOrchestrator(self.config)
        self.search_fn = search_fn
        self.multi_query_fn = multi_query_fn
        self.hyde_fn = hyde_fn

    async def search_with_correction(
        self,
        query: str,
        initial_results: List[Dict[str, Any]],
        base_top_k: int = 10,
        search_kwargs: Optional[Dict[str, Any]] = None,
    ) -> Tuple[List[Dict[str, Any]], CRAGAuditTrail]:
        """
        Execute search with CRAG correction if needed.

        Args:
            query: Search query
            initial_results: Results from initial search
            base_top_k: Base top_k value
            search_kwargs: Additional kwargs for search function

        Returns:
            Tuple of (final_results, audit_trail)
        """
        start_time = time.perf_counter()
        search_kwargs = search_kwargs or {}

        # Create audit trail
        audit_trail = self.orchestrator.create_audit_trail(query, initial_results)
        current_results = initial_results
        current_evaluation = audit_trail.initial_evaluation

        # Track what strategies have been used
        used_multi_query = False
        used_hyde = False
        current_round = 0

        # Execute correction loop
        while self.orchestrator.should_retry(current_evaluation, current_round):
            retry_params = self.orchestrator.get_retry_parameters(
                current_evaluation,
                base_top_k,
                used_multi_query,
                used_hyde,
                current_round,
            )

            if retry_params is None:
                break

            retry_start = time.perf_counter()
            retry_results: List[Dict[str, Any]] = []
            error: Optional[str] = None

            try:
                if retry_params.use_multi_query and self.multi_query_fn and self.search_fn:
                    # Generate multiple queries and search
                    queries = await self._run_multi_query(query)
                    for q in queries:
                        sub_results = await self._run_search(
                            q,
                            retry_params.top_k,
                            retry_params.bm25_weight,
                            retry_params.semantic_weight,
                            search_kwargs,
                        )
                        retry_results.extend(sub_results)
                    # Dedupe and re-rank
                    retry_results = self._dedupe_results(retry_results)[:retry_params.top_k]
                    used_multi_query = True

                elif retry_params.use_hyde and self.hyde_fn and self.search_fn:
                    # Generate hypothetical document and search
                    hyde_query = await self._run_hyde(query)
                    retry_results = await self._run_search(
                        hyde_query,
                        retry_params.top_k,
                        retry_params.bm25_weight,
                        retry_params.semantic_weight,
                        search_kwargs,
                    )
                    used_hyde = True

                elif self.search_fn:
                    # Standard aggressive search
                    retry_results = await self._run_search(
                        query,
                        retry_params.top_k,
                        retry_params.bm25_weight,
                        retry_params.semantic_weight,
                        search_kwargs,
                    )

            except Exception as e:
                error = str(e)
                logger.warning(f"CRAG retry failed: strategy={retry_params.strategy_name} error={error}")

            retry_duration = int((time.perf_counter() - retry_start) * 1000)

            # Record action and update evaluation
            current_evaluation = self.orchestrator.record_action(
                audit_trail,
                retry_params.strategy_name,
                retry_results,
                retry_duration,
                retry_params.to_dict(),
                error,
            )

            # Update current results if improvement
            if len(retry_results) > 0:
                if current_evaluation.best_score > audit_trail.initial_evaluation.best_score:
                    current_results = retry_results

            current_round += 1

        # Finalize audit trail
        total_duration = int((time.perf_counter() - start_time) * 1000)
        final_eval = self.orchestrator.evaluate_results(current_results)
        audit_trail.finalize(final_eval, total_duration, len(current_results))
        audit_trail.log_summary()

        return current_results, audit_trail

    async def _run_search(
        self,
        query: str,
        top_k: int,
        bm25_weight: float,
        semantic_weight: float,
        kwargs: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Execute search function."""
        if self.search_fn is None:
            return []

        import asyncio
        if asyncio.iscoroutinefunction(self.search_fn):
            return await self.search_fn(
                query=query,
                top_k=top_k,
                bm25_weight=bm25_weight,
                semantic_weight=semantic_weight,
                **kwargs,
            )
        else:
            return await asyncio.to_thread(
                self.search_fn,
                query=query,
                top_k=top_k,
                bm25_weight=bm25_weight,
                semantic_weight=semantic_weight,
                **kwargs,
            )

    async def _run_multi_query(self, query: str) -> List[str]:
        """Execute multi-query generation."""
        if self.multi_query_fn is None:
            return [query]

        import asyncio
        if asyncio.iscoroutinefunction(self.multi_query_fn):
            return await self.multi_query_fn(query)
        else:
            return await asyncio.to_thread(self.multi_query_fn, query)

    async def _run_hyde(self, query: str) -> str:
        """Execute HyDE generation."""
        if self.hyde_fn is None:
            return query

        import asyncio
        if asyncio.iscoroutinefunction(self.hyde_fn):
            return await self.hyde_fn(query)
        else:
            return await asyncio.to_thread(self.hyde_fn, query)

    def _dedupe_results(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Deduplicate results by chunk_uid, keeping highest score."""
        seen: Dict[str, Dict[str, Any]] = {}
        for r in results:
            uid = r.get("chunk_uid", "")
            if not uid:
                continue
            score = float(r.get("final_score") or r.get("score") or 0.0)
            if uid not in seen or score > float(seen[uid].get("final_score") or seen[uid].get("score") or 0.0):
                seen[uid] = r
        return sorted(seen.values(), key=lambda x: float(x.get("final_score") or x.get("score") or 0.0), reverse=True)
