"""
RAGAS evaluation helpers (offline).

This module provides a thin wrapper around the `ragas` library to evaluate
RAG outputs with metrics like faithfulness and answer relevancy.

It is intentionally best-effort:
- If `ragas` is not installed, we raise a clear ImportError.
- Callers should run this in a dedicated eval environment (CI job / cron).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class RagasSample:
    question: str
    answer: str
    contexts: List[str]
    ground_truth: Optional[str] = None

    def to_row(self) -> Dict[str, Any]:
        row: Dict[str, Any] = {
            "question": self.question,
            "answer": self.answer,
            "contexts": self.contexts,
        }
        if self.ground_truth:
            row["ground_truth"] = self.ground_truth
        return row


def evaluate_ragas(
    samples: List[RagasSample],
    *,
    metrics: Optional[List[Any]] = None,
) -> Dict[str, Any]:
    """
    Evaluate a list of samples with RAGAS.

    Returns:
        Dict with `scores` and `raw` result object (stringified).
    """
    if not samples:
        return {"scores": {}, "raw": None}

    try:
        from datasets import Dataset  # type: ignore
        from ragas import evaluate  # type: ignore
        from ragas.metrics import answer_relevancy, faithfulness  # type: ignore
        try:  # pragma: no cover - optional metrics depending on ragas version
            from ragas.metrics import context_precision, context_recall  # type: ignore
        except Exception:  # pragma: no cover
            context_precision = None  # type: ignore
            context_recall = None  # type: ignore
    except Exception as e:  # pragma: no cover
        raise ImportError(
            "RAGAS evaluation requires optional dependencies. "
            "Install: pip install ragas datasets"
        ) from e

    rows = [s.to_row() for s in samples]
    ds = Dataset.from_list(rows)

    use_metrics = metrics or [faithfulness, answer_relevancy]
    if metrics is None:
        has_gt = any(bool(s.ground_truth) for s in samples)
        if has_gt and context_precision is not None and context_recall is not None:
            use_metrics = [faithfulness, answer_relevancy, context_precision, context_recall]
    res = evaluate(ds, metrics=use_metrics)

    # `res` behaves like a dict with metric -> score; keep it JSON-friendly.
    scores: Dict[str, Any] = {}
    try:
        scores.update(dict(res))
    except Exception:  # pragma: no cover
        pass

    return {"scores": scores, "raw": str(res)}
