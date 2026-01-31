"""
Benchmark de latência do RAG em "condições reais" (infra local via Docker).

Mede:
- Latência total por query (p50/p95/p99) para o pipeline novo (RAGPipeline.search)
- Breakdown por estágio (média/p95 por stage quando disponível no trace)

Observações:
- Por padrão força embeddings locais (SentenceTransformers) para evitar depender de chaves externas.
- Opcionalmente ativa HyDE/MultiQuery/CRAG (LLM) via `--use-llm`.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import random
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _load_dotenv(path: Path) -> None:
    """
    Minimal .env loader (no dependency on python-dotenv).
    - Ignores comments/blank lines
    - Supports KEY=VALUE
    - Strips surrounding single/double quotes
    """
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or key in os.environ:
            continue
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        os.environ[key] = value


def _configure_logging() -> None:
    # Keep benchmark output readable (avoid request/transport spam).
    logging.getLogger().setLevel(logging.WARNING)
    for name in ("opensearch", "httpx", "neo4j", "urllib3", "RAGPipeline"):
        logging.getLogger(name).setLevel(logging.WARNING)
    logging.getLogger("neo4j.notifications").setLevel(logging.ERROR)


def _percentile(sorted_data: List[float], p: float) -> float:
    if not sorted_data:
        return 0.0
    k = (len(sorted_data) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_data) - 1)
    if f == c:
        return float(sorted_data[f])
    return float(sorted_data[f] * (c - k) + sorted_data[c] * (k - f))


def _load_queries(path: Path) -> List[Tuple[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"Query file not found: {path}")
    queries: List[Tuple[str, str]] = []
    if path.suffix.lower() == ".jsonl":
        with path.open("r", encoding="utf-8") as f:
            for idx, line in enumerate(f):
                raw = line.strip()
                if not raw:
                    continue
                obj = json.loads(raw)
                query = str(obj.get("query") or obj.get("question") or "").strip()
                if not query:
                    continue
                label = str(obj.get("id") or obj.get("domain") or f"q{idx+1}")
                queries.append((label, query))
    else:
        with path.open("r", encoding="utf-8") as f:
            for idx, line in enumerate(f):
                query = line.strip()
                if not query:
                    continue
                queries.append((f"q{idx+1}", query))
    return queries


@dataclass(frozen=True)
class BenchResult:
    label: str
    query: str
    samples_ms: List[float]
    stage_samples_ms: Dict[str, List[float]]

    def summary(self) -> Dict[str, Any]:
        samples = sorted(self.samples_ms)
        return {
            "label": self.label,
            "query": self.query,
            "n": len(samples),
            "p50_ms": round(_percentile(samples, 50), 2),
            "p95_ms": round(_percentile(samples, 95), 2),
            "p99_ms": round(_percentile(samples, 99), 2),
            "mean_ms": round(statistics.mean(samples), 2) if samples else 0.0,
        }


async def _bench_pipeline(
    *,
    queries: List[Tuple[str, str]],
    iterations: int,
    warmup: int,
    tenant_id: str,
    user_id: str,
    include_graph: bool,
    argument_graph_enabled: bool,
) -> List[BenchResult]:
    # Ensure `app.*` imports work when executing from repo root.
    api_root = Path(__file__).resolve().parents[1]
    if str(api_root) not in sys.path:
        sys.path.insert(0, str(api_root))

    from app.services.rag.config import reset_rag_config, get_rag_config
    from app.services.rag.pipeline.rag_pipeline import get_rag_pipeline

    reset_rag_config()
    cfg = get_rag_config()

    pipeline = get_rag_pipeline()
    pipeline._ensure_components()

    indices = cfg.get_opensearch_indices()
    collections = cfg.get_qdrant_collections()

    results: List[BenchResult] = []
    for label, query in queries:
        samples: List[float] = []
        stage_samples: Dict[str, List[float]] = {}

        for i in range(warmup + iterations):
            t0 = time.perf_counter()
            out = await pipeline.search(
                query,
                indices=list(indices),
                collections=list(collections),
                filters={"tenant_id": tenant_id, "user_id": user_id, "include_global": True},
                top_k=8,
                include_graph=include_graph,
                argument_graph_enabled=argument_graph_enabled,
                tenant_id=tenant_id,
                scope="",
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000.0

            # Discard warmup samples (first run tends to include model loads / connection pools).
            if i < warmup:
                continue

            samples.append(elapsed_ms)
            try:
                metrics = out.trace.to_metrics() if out.trace else {}
                stage_latencies = metrics.get("stage_latencies") or {}
                if isinstance(stage_latencies, dict):
                    for stage_name, ms in stage_latencies.items():
                        if isinstance(ms, (int, float)) and ms >= 0:
                            stage_samples.setdefault(str(stage_name), []).append(float(ms))
            except Exception:
                pass

        results.append(BenchResult(label=label, query=query, samples_ms=samples, stage_samples_ms=stage_samples))

    return results


def _print_summary(results: List[BenchResult]) -> None:
    # Query totals
    print("\n== Totais por query ==")
    for r in results:
        s = r.summary()
        print(
            f"- [{s['label']}] n={s['n']} p50={s['p50_ms']}ms p95={s['p95_ms']}ms "
            f"p99={s['p99_ms']}ms mean={s['mean_ms']}ms"
        )

    # Stage aggregates
    print("\n== Breakdown por estágio (média / p95) ==")
    stage_all: Dict[str, List[float]] = {}
    for r in results:
        for st, vals in r.stage_samples_ms.items():
            stage_all.setdefault(st, []).extend(vals)
    for st, vals in sorted(stage_all.items(), key=lambda kv: (statistics.mean(kv[1]) if kv[1] else 0.0), reverse=True):
        sv = sorted(vals)
        print(f"- {st}: mean={round(statistics.mean(sv), 2)}ms p95={round(_percentile(sv, 95), 2)}ms n={len(sv)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--warmup", type=int, default=2)
    parser.add_argument("--tenant-id", default="tenant-bench")
    parser.add_argument("--user-id", default="user-bench")
    parser.add_argument("--no-graph", action="store_true", help="Disable graph enrichment.")
    parser.add_argument("--argument-graph", action="store_true", help="Enable legacy ArgumentRAG enrichment.")
    parser.add_argument("--use-llm", action="store_true", help="Enable HyDE/MultiQuery/CRAG (uses configured LLM keys).")
    parser.add_argument("--query-file", default=None, help="Optional query file (jsonl with 'query' or plain text).")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of queries loaded.")
    parser.add_argument("--shuffle", action="store_true", help="Shuffle loaded queries before limiting.")
    parser.add_argument(
        "--embeddings-provider",
        choices=("auto", "openai", "local"),
        default=None,
        help="Override RAG_EMBEDDINGS_PROVIDER (default: keep env/.env).",
    )
    parser.add_argument(
        "--embedding-model",
        default=None,
        help="Override embedding model (e.g. text-embedding-3-large).",
    )
    parser.add_argument(
        "--embedding-dimensions",
        type=int,
        default=None,
        help="Override EMBEDDING_DIMENSIONS (must match Qdrant collections).",
    )
    parser.add_argument(
        "--openai-embeddings-large",
        action="store_true",
        help="Shortcut: use OpenAI text-embedding-3-large (3072 dims).",
    )
    parser.add_argument("--dotenv", default="apps/api/.env", help="Path to .env (only sets vars not already set).")
    args = parser.parse_args()

    _configure_logging()

    repo_root = Path(__file__).resolve().parents[3]
    _load_dotenv(repo_root / args.dotenv)

    # Defaults aligned with local Docker compose from this repo.
    os.environ.setdefault("OPENSEARCH_URL", "https://localhost:9200")
    os.environ.setdefault("OPENSEARCH_USER", "admin")
    os.environ.setdefault("OPENSEARCH_PASS", "admin")
    os.environ.setdefault("OPENSEARCH_VERIFY_CERTS", "false")
    os.environ.setdefault("QDRANT_URL", "http://localhost:6333")
    # Prefer IPv4 to avoid intermittent localhost/IPv6 resolution issues with Bolt.
    os.environ["NEO4J_URI"] = os.environ.get("NEO4J_URI", "bolt://127.0.0.1:7687").replace("bolt://localhost", "bolt://127.0.0.1")
    os.environ.setdefault("NEO4J_USER", os.environ.get("NEO4J_USERNAME", "neo4j"))
    os.environ.setdefault("NEO4J_DATABASE", "iudex")
    # Avoid schema/index creation noise during latency benchmark.
    os.environ.setdefault("NEO4J_CREATE_INDEXES", "false")
    os.environ.setdefault("NEO4J_MAX_POOL_SIZE", "10")
    os.environ.setdefault("NEO4J_CONNECTION_TIMEOUT", "5")

    # Disable result-level cache for realistic latency numbers.
    os.environ.setdefault("RAG_ENABLE_RESULT_CACHE", "false")

    # Embeddings settings: default to OpenAI-dimension-compatible local setup if nothing specified.
    if args.openai_embeddings_large:
        os.environ["RAG_EMBEDDINGS_PROVIDER"] = "openai"
        os.environ["EMBEDDING_MODEL"] = "text-embedding-3-large"
        os.environ["EMBEDDING_DIMENSIONS"] = "3072"
    else:
        if args.embeddings_provider:
            os.environ["RAG_EMBEDDINGS_PROVIDER"] = args.embeddings_provider
        if args.embedding_model:
            os.environ["EMBEDDING_MODEL"] = args.embedding_model
        if args.embedding_dimensions:
            os.environ["EMBEDDING_DIMENSIONS"] = str(int(args.embedding_dimensions))

    # Safe local default when nothing was specified.
    os.environ.setdefault("RAG_EMBEDDINGS_PROVIDER", "local")
    os.environ.setdefault(
        "RAG_LOCAL_EMBEDDING_MODEL",
        "sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
    )
    os.environ.setdefault("EMBEDDING_DIMENSIONS", "3072")

    if not args.use_llm:
        os.environ.setdefault("RAG_ENABLE_HYDE", "false")
        os.environ.setdefault("RAG_ENABLE_MULTIQUERY", "false")
        os.environ.setdefault("RAG_ENABLE_CRAG", "false")
        os.environ.setdefault("RAG_MULTI_QUERY_LLM", "false")
    else:
        # Keep `.env` defaults (usually true), but ensure they're on if the environment is sparse.
        os.environ.setdefault("RAG_ENABLE_HYDE", "true")
        os.environ.setdefault("RAG_ENABLE_MULTIQUERY", "true")
        os.environ.setdefault("RAG_ENABLE_CRAG", "true")
        # Prefer API-key Gemini for benchmarking (Vertex quotas are often tighter).
        os.environ["IUDEX_GEMINI_AUTH"] = "apikey"
        # Use OpenAI for HyDE/MultiQuery by default (avoids Gemini quota issues).
        os.environ.setdefault("RAG_QUERY_EXPANSION_PROVIDER", "openai")

    if os.environ.get("RAG_EMBEDDINGS_PROVIDER") == "openai" and not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY não está definido (necessário para embeddings OpenAI).")

    # Remote embeddings need longer timeouts than the dev defaults.
    if os.environ.get("RAG_EMBEDDINGS_PROVIDER") == "openai":
        os.environ.setdefault("RAG_VECTOR_TIMEOUT", "8.0")

    include_graph = not bool(args.no_graph)

    if args.query_file:
        queries = _load_queries(Path(args.query_file))
        if args.shuffle:
            random.shuffle(queries)
        if args.limit:
            queries = queries[: max(1, int(args.limit))]
    else:
        queries: List[Tuple[str, str]] = [
            ("lexical", "Lei 8.666/1993 art. 37"),
            ("semantic", "responsabilidade civil do Estado por omissão"),
            ("juris", "dano moral STJ REsp 1234567"),
        ]

    results = asyncio.run(
        _bench_pipeline(
            queries=queries,
            iterations=max(1, args.iterations),
            warmup=max(0, args.warmup),
            tenant_id=str(args.tenant_id),
            user_id=str(args.user_id),
            include_graph=include_graph,
            argument_graph_enabled=bool(args.argument_graph),
        )
    )
    _print_summary(results)


if __name__ == "__main__":
    main()
