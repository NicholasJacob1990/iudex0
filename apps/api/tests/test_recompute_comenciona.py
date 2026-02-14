"""
Tests for recompute_co_menciona operation in GraphAskService.

This operation materializes deterministic, tenant-scoped candidate CO_MENCIONA
edges between Artigos (chunk co-occurrence) via Neo4jMVPService.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestRecomputeCoMencionaEnum:
    def test_enum_value(self):
        from app.services.graph_ask_service import GraphOperation

        assert GraphOperation.RECOMPUTE_CO_MENCIONA == "recompute_co_menciona"


class TestRecomputeCoMencionaEndpoint:
    def test_operation_literal_includes_recompute(self):
        from app.api.endpoints.graph_ask import GraphAskRequest
        from typing import get_args

        ops = set(get_args(GraphAskRequest.model_fields["operation"].annotation))
        assert "recompute_co_menciona" in ops


class TestRecomputeCoMencionaHandler:
    @pytest.mark.asyncio
    async def test_success_calls_neo4j(self):
        from app.services.graph_ask_service import GraphAskService

        service = GraphAskService()
        mock_neo4j = MagicMock()
        mock_neo4j.recompute_candidate_comentions = MagicMock(
            return_value={
                "ok": True,
                "tenant_id": "tenant_123",
                "include_global": True,
                "min_cooccurrences": 2,
                "max_pairs": 20000,
                "edges": 42,
            }
        )
        service._neo4j = mock_neo4j

        async def _to_thread(fn, *args, **kwargs):
            return fn(*args, **kwargs)

        with patch("app.services.graph_ask_service.asyncio.to_thread", new=AsyncMock(side_effect=_to_thread)):
            result = await service._handle_recompute_co_menciona(
                params={"min_cooccurrences": 2, "max_pairs": 20000},
                tenant_id="tenant_123",
                include_global=True,
            )

        assert result.success is True
        assert result.operation == "recompute_co_menciona"
        assert result.result_count == 1
        assert result.metadata == {"write_operation": True, "layer": "candidate"}
        assert result.results[0]["edges"] == 42

        mock_neo4j.recompute_candidate_comentions.assert_called_once()

    @pytest.mark.asyncio
    async def test_failure_returns_error(self):
        from app.services.graph_ask_service import GraphAskService

        service = GraphAskService()
        mock_neo4j = MagicMock()
        mock_neo4j.recompute_candidate_comentions = MagicMock(
            return_value={"ok": False, "error": "boom"}
        )
        service._neo4j = mock_neo4j

        async def _to_thread(fn, *args, **kwargs):
            return fn(*args, **kwargs)

        with patch("app.services.graph_ask_service.asyncio.to_thread", new=AsyncMock(side_effect=_to_thread)):
            result = await service._handle_recompute_co_menciona(
                params={},
                tenant_id="tenant_123",
                include_global=False,
            )

        assert result.success is False
        assert "boom" in (result.error or "")

