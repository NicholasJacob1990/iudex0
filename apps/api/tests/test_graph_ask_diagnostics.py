"""
Tests for GraphAskService legal_diagnostics operation.

This is intentionally database-free: we mock Neo4j MVP async read calls and
assert the resulting payload shape is stable.
"""

import pytest
from unittest.mock import AsyncMock


@pytest.mark.asyncio
async def test_legal_diagnostics_returns_payload(monkeypatch):
    from app.services.graph_ask_service import GraphAskService

    svc = GraphAskService()

    # Mock Neo4j service and executor.
    neo4j = AsyncMock()

    async def _fake_read(query_text, params):
        # Minimal routing based on query fragments.
        q = " ".join(query_text.split()).upper()

        if "MATCH (D:DOCUMENT" in q and "RETURN COUNT(D) AS C" in q:
            return [{"c": 0}]  # force unscoped mode

        if "RETURN COUNT(N) AS C" in q and "MATCH (N:ARTIGO)" in q:
            return [{"c": 10}]
        if "RETURN COUNT(N) AS C" in q and "MATCH (N:LEI)" in q:
            return [{"c": 3}]
        if "RETURN COUNT(N) AS C" in q and "MATCH (N:SUMULA)" in q:
            return [{"c": 2}]
        if "RETURN COUNT(N) AS C" in q and "MATCH (N:DECISAO)" in q:
            return [{"c": 4}]
        if "RETURN COUNT(N) AS C" in q and "MATCH (N:TESE)" in q:
            return [{"c": 1}]

        if "REMETE_A" in q and "RETURN COUNT(DISTINCT R) AS C" in q:
            return [{"c": 5}]

        if "RETURN COUNT(DISTINCT [A1,A2]) AS C" in q:
            return [{"c": 2}]

        if "RETURN A1.NAME AS ORIGEM" in q:
            return [{"origem": "Art. 135 do CTN", "destino": "Art. 50 do CC", "evidence": "nos termos do art. 50", "c": 3}]

        if "RETURN COUNT(*) AS C" in q and "REMETE_A" in q and "A3:ARTIGO" in q:
            return [{"c": 1}]

        if "RETURN A1.NAME AS A1" in q and "A3.NAME AS A3" in q:
            return [{"a1": "Art. 1 do X", "a2": "Art. 2 do X", "a3": "Art. 3 do X", "evidence1": "conforme art. 2", "evidence2": "nos termos do art. 3"}]

        # chain analyzer queries (all return 0 by default here)
        if "RETURN COUNT(*) AS C" in q:
            return [{"c": 0}]

        if "MATCH (A:ARTIGO)<-[:INTERPRETA]-(D:DECISAO)" in q:
            return [{"artigo": "Art. 135 do CTN", "decisoes_count": 2, "decisoes": ["REsp 1.134.186"]}]

        if "MATCH (S:SUMULA)" in q and "FUNDAMENTA|INTERPRETA" in q and "REMETE_A" in q and "A2:ARTIGO" in q:
            if "RETURN COUNT(*) AS C" in q:
                return [{"c": 1}]
            return [{
                "sumula": "Sumula 392 do STJ",
                "a1": "Art. 135 do CTN",
                "a2": "Art. 124 do CTN",
                "rel0": "FUNDAMENTA",
                "evidence0": "sumula fundamenta-se no art. 135",
                "evidence1": "nos termos do art. 124",
            }]

        return [{"c": 0}]

    neo4j._execute_read_async.side_effect = _fake_read

    async def _get_neo4j():
        return neo4j

    monkeypatch.setattr(svc, "_get_neo4j", _get_neo4j)

    result = await svc.ask(
        operation="legal_diagnostics",
        params={},
        tenant_id="t1",
        include_global=True,
    )

    assert result.success is True
    assert result.operation == "legal_diagnostics"
    assert result.result_count == 1
    payload = result.results[0]

    assert "components" in payload
    assert payload["remissoes_art_art_total"] == 5
    assert payload["remissoes_cross_law_total"] == 2
    assert isinstance(payload["remissoes_top"], list)
    if payload["remissoes_top"]:
        assert "evidence" in payload["remissoes_top"][0]
    assert "cadeias_3_hops_total" in payload
    if payload.get("cadeias_3_hops_samples"):
        assert "evidence1" in payload["cadeias_3_hops_samples"][0]
        assert "evidence2" in payload["cadeias_3_hops_samples"][0]
    assert "chain_counts_4_5_hops" in payload
    assert "artigos_mais_interpretados" in payload
    assert "sumula_art_art_total" in payload
    if payload.get("sumula_art_art_samples"):
        assert "evidence0" in payload["sumula_art_art_samples"][0]
        assert "evidence1" in payload["sumula_art_art_samples"][0]
