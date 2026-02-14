#!/usr/bin/env python3
"""
Offline RAGAS evaluation runner.

Usage:
  python apps/api/scripts/eval_rag_ragas.py --queries evals/queries.jsonl --out evals/ragas_report.json

Input JSONL format:
  {"question": "...", "ground_truth": "..."}  # ground_truth optional
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


def _read_jsonl(path: Path, limit: int = 0) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            raw = line.strip()
            if not raw:
                continue
            rows.append(json.loads(raw))
            if limit and len(rows) >= limit:
                break
    return rows


async def _answer_openai(question: str, contexts: List[str]) -> str:
    # Minimal answerer for eval purposes.
    try:
        from openai import AsyncOpenAI  # type: ignore
    except Exception as e:
        raise RuntimeError(f"openai not available: {e}") from e

    client = AsyncOpenAI()
    model = os.getenv("RAGAS_ANSWER_MODEL", "gpt-4o-mini")

    ctx = "\n\n".join([f"[Context {i+1}]\n{c}" for i, c in enumerate(contexts[:8])])
    prompt = (
        "Responda a pergunta usando APENAS os contextos fornecidos. "
        "Se faltar evidência, diga explicitamente que nao encontrou nos trechos.\n\n"
        f"Pergunta: {question}\n\n"
        f"Contextos:\n{ctx}\n\n"
        "Resposta:"
    )

    resp = await client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=400,
    )
    return (resp.choices[0].message.content or "").strip()


@dataclass(frozen=True)
class EvalItem:
    question: str
    ground_truth: Optional[str] = None


async def main_async(args: argparse.Namespace) -> int:
    # Ensure `app.*` imports work when executing from repo root.
    api_root = Path(__file__).resolve().parents[1]
    if str(api_root) not in sys.path:
        sys.path.insert(0, str(api_root))

    from app.services.rag.pipeline.rag_pipeline import get_rag_pipeline
    from app.services.rag.evals.ragas_eval import RagasSample, evaluate_ragas

    rows = _read_jsonl(Path(args.queries), limit=int(args.limit or 0))
    items: List[EvalItem] = []
    for r in rows:
        q = str(r.get("question") or r.get("query") or "").strip()
        if not q:
            continue
        items.append(EvalItem(question=q, ground_truth=(str(r.get("ground_truth") or "").strip() or None)))

    if not items:
        print("No questions found.")
        return 2

    pipeline = get_rag_pipeline()
    pipeline._ensure_components()

    samples: List[RagasSample] = []
    for it in items:
        out = await pipeline.search(
            it.question,
            indices=None,
            collections=None,
            filters={"tenant_id": args.tenant_id, "user_id": args.user_id, "include_global": True},
            top_k=int(args.top_k),
            include_graph=bool(args.include_graph),
            tenant_id=args.tenant_id,
            scope=args.scope,
        )
        contexts = [str(r.get("text") or "") for r in (out.results or []) if isinstance(r, dict)]
        contexts = [c for c in contexts if c.strip()]

        answer = await _answer_openai(it.question, contexts)
        samples.append(RagasSample(question=it.question, answer=answer, contexts=contexts, ground_truth=it.ground_truth))

    res = evaluate_ragas(samples)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")

    if bool(getattr(args, "store_db", False)):
        try:
            from app.core.database import SessionLocal
            from app.models.rag_eval import RAGEvalMetric

            scores = res.get("scores", {}) or {}
            row = RAGEvalMetric(
                dataset=str(args.dataset or "default"),
                context_precision=float(scores.get("context_precision", 0.0)) if scores.get("context_precision") is not None else None,
                context_recall=float(scores.get("context_recall", 0.0)) if scores.get("context_recall") is not None else None,
                faithfulness=float(scores.get("faithfulness", 0.0)) if scores.get("faithfulness") is not None else None,
                answer_relevancy=float(scores.get("answer_relevancy", 0.0)) if scores.get("answer_relevancy") is not None else None,
                metrics=scores,
            )
            db = SessionLocal()
            try:
                db.add(row)
                db.commit()
            finally:
                db.close()
        except Exception as e:
            print(f"DB store failed: {e}", file=sys.stderr)

    print(json.dumps(res.get("scores", {}), ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--queries", required=True, help="JSONL with {question, ground_truth?}")
    p.add_argument("--out", required=True, help="Output report JSON path")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--tenant-id", default="tenant-eval")
    p.add_argument("--user-id", default="user-eval")
    p.add_argument("--scope", default="global")
    p.add_argument("--top-k", type=int, default=8)
    p.add_argument("--include-graph", action="store_true")
    p.add_argument("--dataset", default="default", help="Dataset label stored in DB when --store-db is enabled")
    p.add_argument("--store-db", action="store_true", help="Store aggregate scores into rag_eval_metrics (best-effort)")
    args = p.parse_args()

    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
