"""
Budget Tracker for RAG Requests

Track and enforce token/cost budgets per RAG request to control costs
from HyDE + multi-query expansion operations.

Features:
- Track embedding token usage
- Track LLM calls (HyDE, multi-query, rewrite)
- Warn when approaching budget limits
- Raise errors when limits exceeded
- Generate usage reports for observability

Usage:
    tracker = BudgetTracker(max_tokens=50000, max_llm_calls=5)

    # Check before expensive operations
    if tracker.can_make_llm_call():
        result = await generate_hyde(query)
        tracker.track_llm_call(input_tokens=100, output_tokens=200, model="gemini-2.0-flash")

    # Get final report
    report = tracker.get_usage_report()
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.services.rag.config import get_rag_config

logger = logging.getLogger("rag.budget_tracker")


# Token estimates for common models (per 1K chars, approximate)
TOKEN_ESTIMATES: Dict[str, float] = {
    # Embedding models
    "text-embedding-3-large": 0.25,  # ~4 chars per token
    "text-embedding-3-small": 0.25,
    "text-embedding-ada-002": 0.25,
    # LLM models (Portuguese tends to be slightly higher)
    "gemini-2.0-flash": 0.30,
    "gemini-1.5-flash": 0.30,
    "gemini-1.5-pro": 0.30,
    "gpt-4o": 0.28,
    "gpt-4o-mini": 0.28,
    "gpt-4-turbo": 0.28,
    "claude-3-5-sonnet": 0.27,
    "claude-3-haiku": 0.27,
}


def estimate_tokens(text: str, model: str = "gemini-2.0-flash") -> int:
    """
    Estimate token count for text based on model.

    Uses character-based estimation since we don't want to import
    heavy tokenizers. Portuguese legal text tends to have slightly
    higher token/char ratios than English.

    Args:
        text: Text to estimate tokens for
        model: Model name for rate lookup

    Returns:
        Estimated token count
    """
    if not text:
        return 0

    # Get model-specific rate or use default
    rate = TOKEN_ESTIMATES.get(model, 0.28)

    # Estimate based on character count
    char_count = len(text)
    estimated = int(char_count * rate)

    # Minimum 1 token for non-empty text
    return max(1, estimated)


class BudgetExceededError(Exception):
    """Raised when request budget is exceeded."""

    def __init__(
        self,
        message: str,
        tokens_used: int,
        max_tokens: int,
        llm_calls_made: int,
        max_llm_calls: int,
    ):
        super().__init__(message)
        self.tokens_used = tokens_used
        self.max_tokens = max_tokens
        self.llm_calls_made = llm_calls_made
        self.max_llm_calls = max_llm_calls


@dataclass
class LLMCallRecord:
    """Record of a single LLM call for tracking."""

    operation: str  # "hyde", "multiquery", "rewrite", etc.
    model: str
    input_tokens: int
    output_tokens: int
    timestamp: float = field(default_factory=time.time)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def to_dict(self) -> Dict[str, Any]:
        return {
            "operation": self.operation,
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "timestamp": self.timestamp,
        }


@dataclass
class EmbeddingRecord:
    """Record of embedding operations for tracking."""

    text_length: int
    estimated_tokens: int
    model: str
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text_length": self.text_length,
            "estimated_tokens": self.estimated_tokens,
            "model": self.model,
            "timestamp": self.timestamp,
        }


@dataclass
class BudgetTracker:
    """
    Track and enforce token/cost budgets per RAG request.

    This class provides cost control for RAG operations by tracking:
    - Total token usage across embeddings and LLM calls
    - Number of LLM calls (HyDE, multi-query, rewrite)
    - Warning thresholds for proactive budget management

    Example:
        tracker = BudgetTracker(max_tokens=50000, max_llm_calls=5)

        # Before HyDE generation
        if tracker.can_make_llm_call():
            result = await hyde_service.generate(query)
            tracker.track_llm_call(
                input_tokens=estimate_tokens(query),
                output_tokens=estimate_tokens(result),
                model="gemini-2.0-flash",
                operation="hyde"
            )

        # Before multi-query expansion
        if tracker.can_make_llm_call() and tracker.can_use_tokens(500):
            variants = await expand_queries(query)
            tracker.track_llm_call(...)
    """

    max_tokens: int = 50000
    max_llm_calls: int = 5
    warn_at_percent: float = 0.8

    # Internal tracking (not init params)
    tokens_used: int = field(default=0, init=False)
    llm_calls_made: int = field(default=0, init=False)

    # Detailed records
    llm_call_records: List[LLMCallRecord] = field(default_factory=list, init=False)
    embedding_records: List[EmbeddingRecord] = field(default_factory=list, init=False)

    # Warning state
    _token_warning_issued: bool = field(default=False, init=False)
    _llm_warning_issued: bool = field(default=False, init=False)

    # Timing
    _created_at: float = field(default_factory=time.time, init=False)

    @classmethod
    def from_config(cls) -> "BudgetTracker":
        """Create tracker from RAG configuration."""
        config = get_rag_config()
        return cls(
            max_tokens=config.max_tokens_per_request,
            max_llm_calls=config.max_llm_calls_per_request,
            warn_at_percent=config.warn_at_budget_percent,
        )

    def track_embedding(
        self,
        text: str,
        model: str = "text-embedding-3-large",
    ) -> int:
        """
        Track embedding token usage.

        Args:
            text: Text being embedded
            model: Embedding model name

        Returns:
            Estimated tokens used
        """
        estimated = estimate_tokens(text, model)
        self.tokens_used += estimated

        self.embedding_records.append(EmbeddingRecord(
            text_length=len(text),
            estimated_tokens=estimated,
            model=model,
        ))

        self._check_token_warning()

        logger.debug(
            f"Embedding tracked: {estimated} tokens (total: {self.tokens_used}/{self.max_tokens})"
        )

        return estimated

    def track_llm_call(
        self,
        input_tokens: int,
        output_tokens: int,
        model: str,
        operation: str = "unknown",
    ) -> int:
        """
        Track LLM call (HyDE, multi-query, rewrite).

        Args:
            input_tokens: Input token count
            output_tokens: Output token count
            model: Model name
            operation: Operation type ("hyde", "multiquery", "rewrite")

        Returns:
            Total tokens used for this call
        """
        total = input_tokens + output_tokens
        self.tokens_used += total
        self.llm_calls_made += 1

        self.llm_call_records.append(LLMCallRecord(
            operation=operation,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        ))

        self._check_token_warning()
        self._check_llm_warning()

        logger.debug(
            f"LLM call tracked ({operation}): {total} tokens "
            f"(total: {self.tokens_used}/{self.max_tokens}, "
            f"calls: {self.llm_calls_made}/{self.max_llm_calls})"
        )

        return total

    def track_llm_call_from_text(
        self,
        input_text: str,
        output_text: str,
        model: str,
        operation: str = "unknown",
    ) -> int:
        """
        Track LLM call by estimating tokens from text.

        Convenience method when actual token counts aren't available.

        Args:
            input_text: Input text
            output_text: Output text
            model: Model name
            operation: Operation type

        Returns:
            Total estimated tokens used
        """
        input_tokens = estimate_tokens(input_text, model)
        output_tokens = estimate_tokens(output_text, model)
        return self.track_llm_call(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=model,
            operation=operation,
        )

    def can_make_llm_call(self) -> bool:
        """
        Check if we can make another LLM call.

        Returns:
            True if under LLM call limit
        """
        return self.llm_calls_made < self.max_llm_calls

    def can_use_tokens(self, estimated_tokens: int) -> bool:
        """
        Check if we have budget for more tokens.

        Args:
            estimated_tokens: Tokens we want to use

        Returns:
            True if within budget
        """
        return (self.tokens_used + estimated_tokens) <= self.max_tokens

    def get_remaining_tokens(self) -> int:
        """Get remaining token budget."""
        return max(0, self.max_tokens - self.tokens_used)

    def get_remaining_llm_calls(self) -> int:
        """Get remaining LLM call budget."""
        return max(0, self.max_llm_calls - self.llm_calls_made)

    def get_token_usage_percent(self) -> float:
        """Get token usage as percentage (0.0-1.0)."""
        if self.max_tokens <= 0:
            return 1.0
        return self.tokens_used / self.max_tokens

    def get_llm_usage_percent(self) -> float:
        """Get LLM call usage as percentage (0.0-1.0)."""
        if self.max_llm_calls <= 0:
            return 1.0
        return self.llm_calls_made / self.max_llm_calls

    def is_budget_exceeded(self) -> bool:
        """Check if any budget limit is exceeded."""
        return (
            self.tokens_used > self.max_tokens or
            self.llm_calls_made > self.max_llm_calls
        )

    def raise_if_exceeded(self) -> None:
        """
        Raise BudgetExceededError if limits exceeded.

        Raises:
            BudgetExceededError: If token or LLM call limits exceeded
        """
        if self.tokens_used > self.max_tokens:
            raise BudgetExceededError(
                f"Token budget exceeded: {self.tokens_used}/{self.max_tokens}",
                tokens_used=self.tokens_used,
                max_tokens=self.max_tokens,
                llm_calls_made=self.llm_calls_made,
                max_llm_calls=self.max_llm_calls,
            )

        if self.llm_calls_made > self.max_llm_calls:
            raise BudgetExceededError(
                f"LLM call limit exceeded: {self.llm_calls_made}/{self.max_llm_calls}",
                tokens_used=self.tokens_used,
                max_tokens=self.max_tokens,
                llm_calls_made=self.llm_calls_made,
                max_llm_calls=self.max_llm_calls,
            )

    def get_usage_report(self) -> Dict[str, Any]:
        """
        Get current usage statistics.

        Returns:
            Dictionary with usage metrics and details
        """
        elapsed = time.time() - self._created_at

        return {
            # Limits
            "max_tokens": self.max_tokens,
            "max_llm_calls": self.max_llm_calls,
            "warn_at_percent": self.warn_at_percent,

            # Current usage
            "tokens_used": self.tokens_used,
            "tokens_remaining": self.get_remaining_tokens(),
            "token_usage_percent": round(self.get_token_usage_percent() * 100, 2),

            "llm_calls_made": self.llm_calls_made,
            "llm_calls_remaining": self.get_remaining_llm_calls(),
            "llm_usage_percent": round(self.get_llm_usage_percent() * 100, 2),

            # Status
            "is_exceeded": self.is_budget_exceeded(),
            "token_warning_issued": self._token_warning_issued,
            "llm_warning_issued": self._llm_warning_issued,

            # Timing
            "elapsed_seconds": round(elapsed, 3),

            # Breakdown by operation
            "llm_calls_by_operation": self._get_calls_by_operation(),
            "tokens_by_operation": self._get_tokens_by_operation(),

            # Detailed records (optional, can be large)
            "llm_call_count": len(self.llm_call_records),
            "embedding_count": len(self.embedding_records),
        }

    def get_detailed_report(self) -> Dict[str, Any]:
        """
        Get detailed usage report including all records.

        Returns:
            Full report with individual call/embedding records
        """
        report = self.get_usage_report()
        report["llm_call_records"] = [r.to_dict() for r in self.llm_call_records]
        report["embedding_records"] = [r.to_dict() for r in self.embedding_records]
        return report

    def _get_calls_by_operation(self) -> Dict[str, int]:
        """Group LLM call count by operation type."""
        counts: Dict[str, int] = {}
        for record in self.llm_call_records:
            counts[record.operation] = counts.get(record.operation, 0) + 1
        return counts

    def _get_tokens_by_operation(self) -> Dict[str, int]:
        """Group token usage by operation type."""
        totals: Dict[str, int] = {}
        for record in self.llm_call_records:
            totals[record.operation] = totals.get(record.operation, 0) + record.total_tokens
        return totals

    def _check_token_warning(self) -> None:
        """Check and log token warning if threshold crossed."""
        if self._token_warning_issued:
            return

        usage_percent = self.get_token_usage_percent()
        if usage_percent >= self.warn_at_percent:
            logger.warning(
                f"Token budget warning: {usage_percent*100:.1f}% used "
                f"({self.tokens_used}/{self.max_tokens} tokens)"
            )
            self._token_warning_issued = True

    def _check_llm_warning(self) -> None:
        """Check and log LLM call warning if threshold crossed."""
        if self._llm_warning_issued:
            return

        usage_percent = self.get_llm_usage_percent()
        if usage_percent >= self.warn_at_percent:
            logger.warning(
                f"LLM call budget warning: {usage_percent*100:.1f}% used "
                f"({self.llm_calls_made}/{self.max_llm_calls} calls)"
            )
            self._llm_warning_issued = True

    def reset(self) -> None:
        """Reset all tracking (useful for testing)."""
        self.tokens_used = 0
        self.llm_calls_made = 0
        self.llm_call_records.clear()
        self.embedding_records.clear()
        self._token_warning_issued = False
        self._llm_warning_issued = False
        self._created_at = time.time()


__all__ = [
    "BudgetTracker",
    "BudgetExceededError",
    "LLMCallRecord",
    "EmbeddingRecord",
    "estimate_tokens",
    "TOKEN_ESTIMATES",
]
