"""Focused tests for async Neo4j path and batched UNWIND ingest."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

import pytest

from app.services.rag.core.neo4j_mvp import (
    CypherQueries,
    FactExtractor,
    LegalEntityExtractor,
    Neo4jMVPConfig,
    Neo4jMVPService,
)


def _build_service(batch_size: int = 100) -> Neo4jMVPService:
    config = Neo4jMVPConfig(
        uri="bolt://nonexistent:7687",
        create_indexes=False,
        batch_size=batch_size,
    )
    return Neo4jMVPService(config)


def test_execute_write_rows_batches_by_config(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _build_service(batch_size=2)
    calls: List[Tuple[str, Dict[str, Any]]] = []

    def fake_execute_write(query: str, params: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
        calls.append((query, params or {}))
        return []

    monkeypatch.setattr(service, "_execute_write", fake_execute_write)

    rows = [{"id": i} for i in range(5)]
    service._execute_write_rows("UNWIND $rows AS row RETURN row", rows, {"tenant_id": "t1"})

    assert len(calls) == 3
    assert [len(call[1]["rows"]) for call in calls] == [2, 2, 1]
    assert all(call[1]["tenant_id"] == "t1" for call in calls)


@pytest.mark.asyncio
async def test_execute_write_rows_async_batches_by_config(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _build_service(batch_size=3)
    calls: List[Tuple[str, Dict[str, Any]]] = []

    async def fake_execute_write_async(
        query: str,
        params: Dict[str, Any] | None = None,
    ) -> List[Dict[str, Any]]:
        calls.append((query, params or {}))
        return []

    monkeypatch.setattr(service, "_execute_write_async", fake_execute_write_async)

    rows = [{"id": i} for i in range(8)]
    await service._execute_write_rows_async("UNWIND $rows AS row RETURN row", rows, {"tenant_id": "t1"})

    assert len(calls) == 3
    assert [len(call[1]["rows"]) for call in calls] == [3, 3, 2]
    assert all(call[1]["tenant_id"] == "t1" for call in calls)


def test_ingest_document_uses_batch_queries_with_expected_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_service(batch_size=100)
    write_calls: List[Tuple[str, Dict[str, Any]]] = []
    write_rows_calls: List[Tuple[str, List[Dict[str, Any]], Dict[str, Any]]] = []

    def fake_execute_write(query: str, params: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
        write_calls.append((query, params or {}))
        return []

    def fake_execute_write_rows(
        query: str,
        rows: List[Dict[str, Any]],
        extra_params: Dict[str, Any] | None = None,
    ) -> None:
        write_rows_calls.append((query, list(rows), dict(extra_params or {})))

    def fake_extract(text: str) -> List[Dict[str, Any]]:
        idx = text.rsplit("-", 1)[-1]
        return [
            {
                "entity_id": "ent_common",
                "entity_type": "conceito",
                "name": "Entidade Comum",
                "normalized": "entidade comum",
                "metadata": {},
            },
            {
                "entity_id": f"ent_{idx}",
                "entity_type": "conceito",
                "name": f"Entidade {idx}",
                "normalized": f"entidade {idx}",
                "metadata": {},
            },
        ]

    def fake_extract_facts(text: str, max_facts: int = 1) -> List[str]:
        return [f"Fato {text}"][:max_facts]

    monkeypatch.setattr(service, "_execute_write", fake_execute_write)
    monkeypatch.setattr(service, "_execute_write_rows", fake_execute_write_rows)
    monkeypatch.setattr(LegalEntityExtractor, "extract", staticmethod(fake_extract))
    monkeypatch.setattr(FactExtractor, "extract", staticmethod(fake_extract_facts))

    chunks = [
        {"chunk_uid": "chunk-0", "text": "texto-do-chunk-0", "chunk_index": 0},
        {"chunk_uid": "chunk-1", "text": "texto-do-chunk-1", "chunk_index": 1},
        {"chunk_uid": "chunk-2", "text": "texto-do-chunk-2", "chunk_index": 2},
    ]

    stats = service.ingest_document(
        doc_hash="doc-test-1",
        chunks=chunks,
        metadata={"title": "Documento de teste"},
        tenant_id="tenant-1",
        scope="local",
        case_id="case-1",
        extract_entities=True,
        semantic_extraction=False,
        extract_facts=True,
    )

    assert stats["document"] == 1
    assert stats["chunks"] == 3
    assert stats["next_rels"] == 2
    assert stats["entities"] == 4
    assert stats["mentions"] == 6
    assert stats["facts"] == 3
    assert stats["fact_refs"] == 6

    # MERGE_DOCUMENT + 4 unique entity merges.
    assert len(write_calls) == 5

    totals = {
        query: sum(len(rows) for q, rows, _ in write_rows_calls if q == query)
        for query in {
            CypherQueries.MERGE_CHUNKS_BATCH,
            CypherQueries.LINK_DOC_CHUNKS_BATCH,
            CypherQueries.LINK_CHUNK_NEXT_BATCH,
            CypherQueries.LINK_CHUNK_ENTITIES_BATCH,
            CypherQueries.MERGE_FACTS_BATCH,
            CypherQueries.LINK_CHUNK_FACTS_BATCH,
            CypherQueries.LINK_FACT_ENTITIES_BATCH,
        }
    }

    assert totals[CypherQueries.MERGE_CHUNKS_BATCH] == 3
    assert totals[CypherQueries.LINK_DOC_CHUNKS_BATCH] == 3
    assert totals[CypherQueries.LINK_CHUNK_NEXT_BATCH] == 2
    assert totals[CypherQueries.LINK_CHUNK_ENTITIES_BATCH] == 6
    assert totals[CypherQueries.MERGE_FACTS_BATCH] == 3
    assert totals[CypherQueries.LINK_CHUNK_FACTS_BATCH] == 3
    assert totals[CypherQueries.LINK_FACT_ENTITIES_BATCH] == 6


@pytest.mark.asyncio
async def test_ingest_document_async_uses_async_writes_only(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _build_service(batch_size=100)
    async_write_calls: List[Tuple[str, Dict[str, Any]]] = []
    async_write_rows_calls: List[Tuple[str, List[Dict[str, Any]], Dict[str, Any]]] = []
    merged_entities: List[str] = []

    def fail_sync(*_: Any, **__: Any) -> None:
        raise AssertionError("sync Neo4j write path should not be used in ingest_document_async")

    async def fake_execute_write_async(
        query: str,
        params: Dict[str, Any] | None = None,
    ) -> List[Dict[str, Any]]:
        async_write_calls.append((query, params or {}))
        return []

    async def fake_execute_write_rows_async(
        query: str,
        rows: List[Dict[str, Any]],
        extra_params: Dict[str, Any] | None = None,
    ) -> None:
        async_write_rows_calls.append((query, list(rows), dict(extra_params or {})))

    async def fake_merge_entity_async(ent: Dict[str, Any]) -> None:
        merged_entities.append(str(ent["entity_id"]))

    def fake_extract(text: str) -> List[Dict[str, Any]]:
        idx = text.rsplit("-", 1)[-1]
        return [
            {
                "entity_id": "ent_common",
                "entity_type": "conceito",
                "name": "Entidade Comum",
                "normalized": "entidade comum",
                "metadata": {},
            },
            {
                "entity_id": f"ent_{idx}",
                "entity_type": "conceito",
                "name": f"Entidade {idx}",
                "normalized": f"entidade {idx}",
                "metadata": {},
            },
        ]

    def fake_extract_facts(text: str, max_facts: int = 1) -> List[str]:
        return [f"Fato {text}"][:max_facts]

    monkeypatch.setattr(service, "_execute_write", fail_sync)
    monkeypatch.setattr(service, "_execute_write_rows", fail_sync)
    monkeypatch.setattr(service, "_execute_write_async", fake_execute_write_async)
    monkeypatch.setattr(service, "_execute_write_rows_async", fake_execute_write_rows_async)
    monkeypatch.setattr(service, "_merge_entity_async", fake_merge_entity_async)
    monkeypatch.setattr(LegalEntityExtractor, "extract", staticmethod(fake_extract))
    monkeypatch.setattr(FactExtractor, "extract", staticmethod(fake_extract_facts))

    chunks = [
        {"chunk_uid": "chunk-0", "text": "texto-do-chunk-0", "chunk_index": 0},
        {"chunk_uid": "chunk-1", "text": "texto-do-chunk-1", "chunk_index": 1},
    ]

    stats = await service.ingest_document_async(
        doc_hash="doc-test-async",
        chunks=chunks,
        metadata={"title": "Documento async"},
        tenant_id="tenant-1",
        scope="local",
        case_id="case-1",
        extract_entities=True,
        semantic_extraction=False,
        extract_facts=True,
    )

    assert stats["document"] == 1
    assert stats["chunks"] == 2
    assert stats["next_rels"] == 1
    assert stats["entities"] == 3
    assert stats["mentions"] == 4
    assert stats["facts"] == 2
    assert stats["fact_refs"] == 4
    assert len(async_write_calls) == 1  # MERGE_DOCUMENT
    assert len(merged_entities) == 3
    assert async_write_rows_calls, "batched async writes should be used"
