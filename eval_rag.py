#!/usr/bin/env python3
import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from typing import Any, Dict, List


def _load_jsonl(path: str) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            raw = line.strip()
            if not raw:
                continue
            items.append(json.loads(raw))
    return items


def _ensure_imports() -> None:
    try:
        import ragas  # noqa: F401
        import datasets  # noqa: F401
    except Exception as exc:
        raise RuntimeError(
            "RAGAS/datasets nao encontrados. Instale: pip install ragas datasets"
        ) from exc


def _prepare_dataset(rows: List[Dict[str, Any]]) -> "datasets.Dataset":
    from datasets import Dataset

    questions = []
    answers = []
    contexts = []
    ground_truths = []

    for item in rows:
        questions.append(item.get("question") or item.get("query") or "")
        answers.append(item.get("answer") or "")
        contexts.append(item.get("contexts") or [])
        ground_truths.append(item.get("ground_truth") or item.get("reference") or "")

    return Dataset.from_dict(
        {
            "question": questions,
            "answer": answers,
            "contexts": contexts,
            "ground_truth": ground_truths,
        }
    )


def _run_retrieval(rows: List[Dict[str, Any]], top_k: int) -> List[Dict[str, Any]]:
    sys.path.insert(0, os.path.join(os.getcwd(), "apps", "api"))
    from app.services.rag_module import create_rag_manager

    manager = create_rag_manager()
    enriched = []
    for item in rows:
        query = item.get("query") or item.get("question") or ""
        sources = item.get("sources") or None
        results = manager.hybrid_search(query=query, sources=sources, top_k=top_k)
        contexts = [r.get("text", "") for r in results]
        merged = dict(item)
        merged["contexts"] = contexts
        enriched.append(merged)
    return enriched


def _extract_summary(results: Any) -> Dict[str, Any]:
    summary: Dict[str, Any] = {}
    if hasattr(results, "to_dict"):
        try:
            summary = dict(results.to_dict())
        except Exception:
            summary = {}
    if not summary and hasattr(results, "scores"):
        try:
            summary = dict(results.scores)
        except Exception:
            summary = {}
    return summary


def _extract_samples(results: Any) -> List[Dict[str, Any]]:
    if hasattr(results, "to_pandas"):
        try:
            df = results.to_pandas()
            return df.to_dict(orient="records")
        except Exception:
            return []
    return []


async def _persist_results(payload: Dict[str, Any]) -> None:
    sys.path.insert(0, os.path.join(os.getcwd(), "apps", "api"))
    try:
        from app.core.database import AsyncSessionLocal, init_db
        from app.models.rag_eval import RAGEvalMetric
    except Exception as exc:
        raise RuntimeError(f"DB deps unavailable: {exc}") from exc

    await init_db()
    summary = payload.get("summary") or {}
    async with AsyncSessionLocal() as session:
        session.add(
            RAGEvalMetric(
                dataset=str(payload.get("dataset") or ""),
                context_precision=summary.get("context_precision"),
                context_recall=summary.get("context_recall"),
                faithfulness=summary.get("faithfulness"),
                answer_relevancy=summary.get("answer_relevancy"),
                metrics=payload,
            )
        )
        await session.commit()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="evals/sample_eval.jsonl")
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument("--out", default="evals/eval_results.json")
    parser.add_argument("--with-llm", action="store_true")
    parser.add_argument("--persist-db", action="store_true")
    parser.add_argument("--min-context-precision", type=float, default=None)
    parser.add_argument("--min-context-recall", type=float, default=None)
    parser.add_argument("--min-faithfulness", type=float, default=None)
    parser.add_argument("--min-answer-relevancy", type=float, default=None)
    args = parser.parse_args()

    rows = _load_jsonl(args.dataset)
    rows = _run_retrieval(rows, args.top_k)

    _ensure_imports()
    from ragas import evaluate
    from ragas.metrics import context_precision, context_recall, faithfulness, answer_relevancy

    dataset = _prepare_dataset(rows)
    metrics = [context_precision, context_recall]
    if args.with_llm or os.getenv("RAG_EVAL_WITH_LLM", "false").lower() in ("1", "true", "yes", "on"):
        metrics.extend([faithfulness, answer_relevancy])

    results = evaluate(dataset, metrics=metrics)
    summary = _extract_summary(results)
    samples = _extract_samples(results)
    payload = {
        "ts": datetime.utcnow().isoformat(),
        "dataset": args.dataset,
        "summary": summary,
        "samples": samples,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    if args.persist_db or os.getenv("RAG_EVAL_PERSIST_DB", "false").lower() in ("1", "true", "yes", "on"):
        asyncio.run(_persist_results(payload))

    thresholds = {
        "context_precision": args.min_context_precision or os.getenv("RAG_EVAL_MIN_CONTEXT_PRECISION"),
        "context_recall": args.min_context_recall or os.getenv("RAG_EVAL_MIN_CONTEXT_RECALL"),
        "faithfulness": args.min_faithfulness or os.getenv("RAG_EVAL_MIN_FAITHFULNESS"),
        "answer_relevancy": args.min_answer_relevancy or os.getenv("RAG_EVAL_MIN_ANSWER_RELEVANCY"),
    }
    for key, raw in thresholds.items():
        if raw is None or raw == "":
            continue
        try:
            min_val = float(raw)
        except (TypeError, ValueError):
            continue
        actual = summary.get(key)
        if actual is not None and actual < min_val:
            print(f"FAIL {key}: {actual:.4f} < {min_val:.4f}")
            return 2

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
