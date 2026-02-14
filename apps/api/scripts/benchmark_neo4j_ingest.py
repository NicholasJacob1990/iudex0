#!/usr/bin/env python3
"""
Benchmark ingest round-trips: legacy per-row writes vs current batched UNWIND path.

This benchmark is synthetic and does not require a running Neo4j instance.
It estimates impact from reducing network round-trips using a configurable RTT.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
API_ROOT = os.path.dirname(SCRIPT_DIR)
if API_ROOT not in sys.path:
    sys.path.insert(0, API_ROOT)

from app.services.rag.core.neo4j_mvp import (
    FactExtractor,
    LegalEntityExtractor,
    Neo4jMVPConfig,
    Neo4jMVPService,
)


@dataclass
class Counter:
    writes: int = 0
    sleep_seconds: float = 0.0

    def write(self) -> None:
        self.writes += 1
        if self.sleep_seconds > 0:
            time.sleep(self.sleep_seconds)


def _build_chunks(num_chunks: int) -> List[Dict[str, Any]]:
    return [
        {
            "chunk_uid": f"chunk-{i}",
            "chunk_index": i,
            "text": f"texto-do-chunk-{i}",
        }
        for i in range(num_chunks)
    ]


def _make_fake_entity_extractor(entities_per_chunk: int):
    per_chunk = max(1, entities_per_chunk)

    def fake_extract(text: str) -> List[Dict[str, Any]]:
        idx = int(text.rsplit("-", 1)[-1])
        entities = [
            {
                "entity_id": "ent_common",
                "entity_type": "conceito",
                "name": "Entidade Comum",
                "normalized": "entidade comum",
                "metadata": {},
            }
        ]
        for j in range(1, per_chunk):
            ent_id = f"ent_{idx}_{j}"
            entities.append(
                {
                    "entity_id": ent_id,
                    "entity_type": "conceito",
                    "name": ent_id,
                    "normalized": ent_id,
                    "metadata": {},
                }
            )
        return entities

    return fake_extract


def _make_fake_fact_extractor(facts_per_chunk: int):
    per_chunk = max(0, facts_per_chunk)

    def fake_extract(text: str, max_facts: int = 1) -> List[str]:
        out = [f"Fato {text} #{i}" for i in range(per_chunk)]
        return out[: max(1, int(max_facts or 1))]

    return fake_extract


def _simulate_legacy_roundtrips(
    chunks: List[Dict[str, Any]],
    entities_per_chunk: int,
    facts_per_chunk: int,
    counter: Counter,
) -> int:
    # MERGE_DOCUMENT
    counter.write()

    # Per-chunk writes (legacy style, no UNWIND batching).
    for _ in chunks:
        counter.write()  # MERGE_CHUNK
        counter.write()  # LINK_DOC_CHUNK

    for _ in range(max(0, len(chunks) - 1)):
        counter.write()  # LINK_CHUNK_NEXT

    seen_entities = {"ent_common"} if entities_per_chunk > 0 else set()
    if entities_per_chunk > 0:
        counter.write()  # MERGE common entity once

    for i, _ in enumerate(chunks):
        for j in range(1, max(1, entities_per_chunk)):
            ent_id = f"ent_{i}_{j}"
            if ent_id not in seen_entities:
                seen_entities.add(ent_id)
                counter.write()  # MERGE entity
        for _ in range(max(1, entities_per_chunk)):
            counter.write()  # LINK_CHUNK_ENTITY

    for _ in chunks:
        for _ in range(max(0, facts_per_chunk)):
            counter.write()  # MERGE_FACT
            counter.write()  # LINK_CHUNK_FACT
            for _ in range(max(1, entities_per_chunk)):
                counter.write()  # LINK_FACT_ENTITY

    return counter.writes


def _run_batched_ingest(
    chunks: List[Dict[str, Any]],
    batch_size: int,
    facts_per_chunk: int,
    counter: Counter,
) -> int:
    cfg = Neo4jMVPConfig(
        uri="bolt://nonexistent:7687",
        create_indexes=False,
        batch_size=batch_size,
        max_facts_per_chunk=max(1, facts_per_chunk),
    )
    service = Neo4jMVPService(cfg)

    def fake_write(_query: str, _params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        counter.write()
        return []

    def fake_write_rows(
        query: str,
        rows: List[Dict[str, Any]],
        extra_params: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not rows:
            return
        for batch in service._iter_batches(rows, service.config.batch_size):
            params: Dict[str, Any] = {"rows": batch}
            if extra_params:
                params.update(extra_params)
            fake_write(query, params)

    service._execute_write = fake_write  # type: ignore[assignment]
    service._execute_write_rows = fake_write_rows  # type: ignore[assignment]

    service.ingest_document(
        doc_hash="bench-doc",
        chunks=chunks,
        metadata={"title": "Bench"},
        tenant_id="tenant-bench",
        scope="local",
        case_id="case-bench",
        extract_entities=True,
        semantic_extraction=False,
        extract_facts=facts_per_chunk > 0,
    )
    return counter.writes


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark Neo4j ingest round-trip reduction")
    parser.add_argument("--chunks", type=int, default=150, help="Number of chunks to ingest")
    parser.add_argument("--entities-per-chunk", type=int, default=3, help="Entities extracted per chunk")
    parser.add_argument("--facts-per-chunk", type=int, default=1, help="Facts extracted per chunk")
    parser.add_argument("--batch-size", type=int, default=100, help="Batch size for UNWIND writes")
    parser.add_argument("--rtt-ms", type=float, default=4.0, help="Simulated DB round-trip latency in milliseconds")
    args = parser.parse_args()

    chunks = _build_chunks(max(1, args.chunks))
    sleep_seconds = max(0.0, args.rtt_ms) / 1000.0

    original_entity_extract = LegalEntityExtractor.extract
    original_fact_extract = FactExtractor.extract
    LegalEntityExtractor.extract = staticmethod(_make_fake_entity_extractor(args.entities_per_chunk))  # type: ignore[assignment]
    FactExtractor.extract = staticmethod(_make_fake_fact_extractor(args.facts_per_chunk))  # type: ignore[assignment]

    try:
        legacy_counter = Counter(sleep_seconds=sleep_seconds)
        t0 = time.perf_counter()
        legacy_writes = _simulate_legacy_roundtrips(
            chunks=chunks,
            entities_per_chunk=max(1, args.entities_per_chunk),
            facts_per_chunk=max(0, args.facts_per_chunk),
            counter=legacy_counter,
        )
        legacy_secs = time.perf_counter() - t0

        batched_counter = Counter(sleep_seconds=sleep_seconds)
        t1 = time.perf_counter()
        batched_writes = _run_batched_ingest(
            chunks=chunks,
            batch_size=max(1, args.batch_size),
            facts_per_chunk=max(0, args.facts_per_chunk),
            counter=batched_counter,
        )
        batched_secs = time.perf_counter() - t1
    finally:
        LegalEntityExtractor.extract = original_entity_extract  # type: ignore[assignment]
        FactExtractor.extract = original_fact_extract  # type: ignore[assignment]

    if batched_writes == 0 or batched_secs <= 0:
        raise RuntimeError("Invalid benchmark result")

    write_reduction = legacy_writes / batched_writes
    time_reduction = legacy_secs / batched_secs

    print("Neo4j ingest benchmark (synthetic)")
    print(f"chunks={len(chunks)} entities_per_chunk={args.entities_per_chunk} facts_per_chunk={args.facts_per_chunk}")
    print(f"batch_size={args.batch_size} simulated_rtt_ms={args.rtt_ms:.2f}")
    print(f"legacy_round_trips={legacy_writes} batched_round_trips={batched_writes}")
    print(f"legacy_time_s={legacy_secs:.3f} batched_time_s={batched_secs:.3f}")
    print(f"round_trip_speedup={write_reduction:.2f}x")
    print(f"time_speedup={time_reduction:.2f}x")


if __name__ == "__main__":
    main()
