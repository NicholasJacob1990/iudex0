"""
Unit tests for Neo4j-backed CogRAG CognitiveMemory.

These tests do not require a real Neo4j instance; we mock the Neo4j service
interface used by CognitiveMemory (._execute_read / ._execute_write).
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import pytest

from app.services.rag.core.cograg.memory import CognitiveMemory


class _FakeNeo4j:
    def __init__(self):
        self.writes: List[Dict[str, Any]] = []
        self.reads: List[Dict[str, Any]] = []
        self._read_queue: List[List[Dict[str, Any]]] = []

    def queue_read(self, rows: List[Dict[str, Any]]) -> None:
        self._read_queue.append(rows)

    def _execute_write(self, query: str, params: Optional[Dict[str, Any]] = None):
        self.writes.append({"query": query, "params": params or {}})
        # mimic neo4j_mvp: returns list[dict]
        return [{"ok": True}]

    def _execute_read(self, query: str, params: Optional[Dict[str, Any]] = None):
        self.reads.append({"query": query, "params": params or {}})
        if self._read_queue:
            return self._read_queue.pop(0)
        return []


def test_store_consultation_writes_expected_shape():
    neo4j = _FakeNeo4j()
    mem = CognitiveMemory(neo4j)

    consulta_id = mem.store_consultation(
        query="Qual o prazo prescricional trabalhista?",
        tenant_id="t1",
        scope="global",
        case_id=None,
        mind_map={"root": "q"},
        sub_questions=[{"node_id": "n1", "question": "sub?"}],
        evidence_map={"n1": {"chunk_results": []}},
        sub_answers=[{"node_id": "n1", "answer": "A", "confidence": 0.7, "citations": [], "evidence_refs": []}],
        integrated_response="Final",
        citations_used=["ref:x"],
        verification_status="approved",
        verification_issues=[],
    )

    assert consulta_id
    assert neo4j.writes, "expected a Neo4j write"
    write = neo4j.writes[0]
    assert "MERGE (c:Consulta" in write["query"]
    assert write["params"]["tenant_id"] == "t1"
    assert write["params"]["consulta_id"] == consulta_id
    assert isinstance(write["params"]["sub_rows"], list)
    assert write["params"]["sub_rows"][0]["node_id"] == "n1"
    # json fields stored as strings
    assert isinstance(write["params"]["mind_map_json"], str)
    json.loads(write["params"]["mind_map_json"])


def test_find_similar_consultation_picks_best_and_loads_penalties():
    neo4j = _FakeNeo4j()
    mem = CognitiveMemory(neo4j)

    # 1) recent consultations
    neo4j.queue_read(
        [
            {
                "consulta_id": "c1",
                "query": "prazo prescricional trabalhista",
                "keywords": ["prazo", "prescricional", "trabalhista"],
                "created_at": "2026-01-01T00:00:00Z",
                "mind_map_json": "{}",
                "answer_summary": "x",
            },
            {
                "consulta_id": "c2",
                "query": "recurso penal",
                "keywords": ["recurso", "penal"],
                "created_at": "2026-01-01T00:00:00Z",
                "mind_map_json": "{}",
                "answer_summary": "y",
            },
        ]
    )
    # 2) load subperguntas for best
    neo4j.queue_read(
        [
            {
                "node_id": "n1",
                "question": "sub",
                "answer": "ans",
                "confidence": 0.8,
                "citations": ["Art. 7"],
                "evidence_refs": ["abc"],
            }
        ]
    )
    # 3) penalties from corrections
    neo4j.queue_read([{"bad_refs": ["abc", "def"]}])

    hit = mem.find_similar_consultation(
        query="Qual é o prazo prescricional trabalhista?",
        tenant_id="t1",
        threshold=0.2,
    )
    assert hit is not None
    assert hit.consulta_id == "c1"
    assert hit.penalized_refs == ["abc", "def"]
    assert hit.sub_answers and hit.sub_answers[0]["evidence_refs"] == ["abc"]


def test_apply_correction_writes():
    neo4j = _FakeNeo4j()
    mem = CognitiveMemory(neo4j)

    correcao_id = mem.apply_correction(
        consulta_id="c1",
        tenant_id="t1",
        texto="Correção",
        usuario_id="u1",
        tipo="juridico",
        bad_refs=["abc"],
    )

    assert correcao_id
    assert neo4j.writes
    assert "CREATE (co:Correcao" in neo4j.writes[0]["query"]
    assert neo4j.writes[0]["params"]["bad_refs"] == ["abc"]

