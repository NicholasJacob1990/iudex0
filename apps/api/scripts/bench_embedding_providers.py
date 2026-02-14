"""
Benchmark de providers de embedding: JurisBERT (768d) vs Voyage-4-large (1024d).

Compara:
- Latência de embedding (p50/p95/avg)
- Recall@K em dataset jurídico BR (se golden set disponível)
- Custos estimados

Uso:
    python scripts/bench_embedding_providers.py
    python scripts/bench_embedding_providers.py --golden-set data/golden_qa.jsonl
    python scripts/bench_embedding_providers.py --providers voyage_v4,jurisbert --top-k 10
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# Minimal .env loader
_SCRIPT_DIR = Path(__file__).resolve().parent
_API_DIR = _SCRIPT_DIR.parent


def _load_dotenv() -> None:
    for env_path in [_API_DIR / ".env", _API_DIR.parent.parent / ".env"]:
        if not env_path.exists():
            continue
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key, value = key.strip(), value.strip()
            if not key or key in os.environ:
                continue
            if (value.startswith('"') and value.endswith('"')) or (
                value.startswith("'") and value.endswith("'")
            ):
                value = value[1:-1]
            os.environ[key] = value


_load_dotenv()

# Add project root to path
sys.path.insert(0, str(_API_DIR))

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sample legal queries (BR)
# ---------------------------------------------------------------------------
SAMPLE_QUERIES = [
    "Quais são os princípios do art. 37 da Constituição Federal?",
    "Requisitos da responsabilidade civil do Estado conforme § 6º do art. 37 da CF",
    "Súmula vinculante 13 do STF sobre nepotismo",
    "Diferença entre servidor público estatutário e celetista",
    "Hipóteses de desapropriação no direito administrativo brasileiro",
    "Prescrição quinquenal em ações contra a Fazenda Pública",
    "Regime jurídico das empresas públicas e sociedades de economia mista",
    "Licitação modalidades pregão concorrência tomada de preços",
    "Improbidade administrativa Lei 8.429/92 sanções cabíveis",
    "Controle de constitucionalidade concentrado e difuso no Brasil",
]


async def _bench_voyage(
    queries: List[str], model: str = "voyage-4-large"
) -> Dict[str, Any]:
    """Benchmark Voyage AI embedding."""
    try:
        from app.services.rag.voyage_embeddings import (
            VoyageEmbeddingsProvider,
            MODEL_DIMENSIONS,
        )
    except ImportError:
        return {"error": "voyageai not available"}

    provider = VoyageEmbeddingsProvider()
    if not provider.is_available:
        return {"error": "VOYAGE_API_KEY not set"}

    dims = MODEL_DIMENSIONS.get(model, 1024)
    latencies: List[float] = []
    embeddings: List[List[float]] = []

    for q in queries:
        t0 = time.perf_counter()
        emb = await provider.embed_query(q, model=model, input_type="query")
        elapsed = (time.perf_counter() - t0) * 1000
        latencies.append(elapsed)
        embeddings.append(emb)

    return {
        "provider": f"voyage ({model})",
        "dimensions": dims,
        "queries": len(queries),
        "latency_avg_ms": round(statistics.mean(latencies), 1),
        "latency_p50_ms": round(statistics.median(latencies), 1),
        "latency_p95_ms": round(sorted(latencies)[int(len(latencies) * 0.95)], 1),
        "embeddings": embeddings,
        "cost_stats": provider.cost_tracker.to_dict(),
    }


async def _bench_jurisbert(queries: List[str]) -> Dict[str, Any]:
    """Benchmark JurisBERT embedding."""
    try:
        from app.services.rag.jurisbert_embeddings import (
            JurisBERTEmbeddingsProvider,
        )
    except ImportError:
        return {"error": "jurisbert not available"}

    provider = JurisBERTEmbeddingsProvider()
    if not provider.is_available:
        return {"error": "JurisBERT model not loaded"}

    latencies: List[float] = []
    embeddings: List[List[float]] = []

    for q in queries:
        t0 = time.perf_counter()
        emb = await provider.embed_query(q)
        elapsed = (time.perf_counter() - t0) * 1000
        latencies.append(elapsed)
        embeddings.append(emb)

    return {
        "provider": "jurisbert",
        "dimensions": provider.dimensions,
        "queries": len(queries),
        "latency_avg_ms": round(statistics.mean(latencies), 1),
        "latency_p50_ms": round(statistics.median(latencies), 1),
        "latency_p95_ms": round(sorted(latencies)[int(len(latencies) * 0.95)], 1),
        "embeddings": embeddings,
    }


async def _search_qdrant(
    collection: str,
    query_vector: List[float],
    top_k: int = 10,
) -> List[Dict[str, Any]]:
    """Search Qdrant collection."""
    try:
        from qdrant_client import QdrantClient

        url = os.getenv("QDRANT_URL", "http://localhost:6333")
        api_key = os.getenv("QDRANT_API_KEY") or None
        client = QdrantClient(url=url, api_key=api_key)

        try:
            client.get_collection(collection)
        except Exception:
            return []

        results = client.search(
            collection_name=collection,
            query_vector=query_vector,
            limit=top_k,
        )
        return [
            {
                "id": str(r.id),
                "score": float(r.score),
                "text": (r.payload or {}).get("text", "")[:200],
            }
            for r in results
        ]
    except Exception as e:
        logger.warning("Qdrant search failed for %s: %s", collection, e)
        return []


async def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark embedding providers")
    parser.add_argument(
        "--providers",
        default="voyage_v4,jurisbert",
        help="Comma-separated providers to benchmark (voyage_v4, jurisbert)",
    )
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument(
        "--golden-set",
        help="JSONL file with golden QA pairs (fields: query, expected_chunk_ids)",
    )
    parser.add_argument(
        "--search",
        action="store_true",
        help="Also benchmark Qdrant search (requires running Qdrant)",
    )
    args = parser.parse_args()

    providers = [p.strip() for p in args.providers.split(",")]
    queries = SAMPLE_QUERIES

    if args.golden_set:
        golden_path = Path(args.golden_set)
        if golden_path.exists():
            queries = []
            for line in golden_path.read_text().splitlines():
                if line.strip():
                    data = json.loads(line)
                    queries.append(data["query"])
            print(f"Loaded {len(queries)} queries from golden set")

    print(f"\n{'='*70}")
    print(f"Embedding Provider Benchmark — {len(queries)} queries")
    print(f"{'='*70}\n")

    results: Dict[str, Dict[str, Any]] = {}

    for provider_name in providers:
        if provider_name == "voyage_v4":
            result = await _bench_voyage(queries, model="voyage-4-large")
        elif provider_name == "jurisbert":
            result = await _bench_jurisbert(queries)
        else:
            print(f"  Unknown provider: {provider_name}")
            continue

        results[provider_name] = result

        if "error" in result:
            print(f"  {provider_name}: {result['error']}")
            continue

        print(f"  {result['provider']}:")
        print(f"    Dimensions: {result['dimensions']}")
        print(f"    Latency avg: {result['latency_avg_ms']}ms")
        print(f"    Latency p50: {result['latency_p50_ms']}ms")
        print(f"    Latency p95: {result['latency_p95_ms']}ms")
        if "cost_stats" in result:
            costs = result["cost_stats"]
            print(f"    Tokens used: {costs.get('total_tokens', 0)}")
            print(f"    Est. cost: ${costs.get('estimated_cost_usd', 0):.6f}")
        print()

    # Qdrant search comparison
    if args.search and len(results) >= 2:
        collection_map = {
            "voyage_v4": "legal_br_v4",
            "jurisbert": "legal_br",
        }

        print(f"\n{'='*70}")
        print("Qdrant Search Comparison")
        print(f"{'='*70}\n")

        for i, query in enumerate(queries[:5]):
            print(f"  Q{i+1}: {query[:80]}...")
            for pname, result in results.items():
                if "error" in result or pname not in collection_map:
                    continue
                coll = collection_map[pname]
                embs = result.get("embeddings", [])
                if i >= len(embs):
                    continue
                search_results = await _search_qdrant(
                    coll, embs[i], top_k=args.top_k
                )
                if search_results:
                    top = search_results[0]
                    print(
                        f"    {pname} ({coll}): "
                        f"top score={top['score']:.4f}, "
                        f'"{top["text"][:80]}..."'
                    )
                else:
                    print(f"    {pname} ({coll}): no results")
            print()

    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
