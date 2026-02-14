"""
Tests for discover_hubs operation in GraphAskService (Gap 8).

Tests the DISCOVER_HUBS operation, validating enum registration,
parameter validation, tool definition, and handler behavior.

No external dependencies required (mocks Neo4j).
"""

import pytest
from unittest.mock import AsyncMock, MagicMock


# =============================================================================
# ENUM & VALIDATION
# =============================================================================


class TestDiscoverHubsEnum:
    """Tests that DISCOVER_HUBS is properly registered."""

    def test_discover_hubs_in_graph_operation(self):
        from app.services.graph_ask_service import GraphOperation
        assert GraphOperation.DISCOVER_HUBS == "discover_hubs"

    def test_discover_hubs_validation_no_required_params(self):
        from app.services.graph_ask_service import GraphAskService, GraphOperation
        service = GraphAskService()
        error = service._validate_params(
            operation=GraphOperation.DISCOVER_HUBS,
            params={},
        )
        # discover_hubs has no required params
        assert error is None

    def test_discover_hubs_with_top_n(self):
        from app.services.graph_ask_service import GraphAskService, GraphOperation
        service = GraphAskService()
        error = service._validate_params(
            operation=GraphOperation.DISCOVER_HUBS,
            params={"top_n": 5},
        )
        assert error is None


# =============================================================================
# HANDLER
# =============================================================================


class TestDiscoverHubsHandler:
    """Tests for _handle_discover_hubs method."""

    @pytest.mark.asyncio
    async def test_discover_hubs_success(self):
        from app.services.graph_ask_service import GraphAskService

        service = GraphAskService()

        mock_neo4j = MagicMock()
        mock_neo4j._execute_read_async = AsyncMock(return_value=[
            {"artigo": "Art. 5 do CF", "referencias": 15},
            {"artigo": "Art. 37 do CF", "referencias": 10},
        ])
        service._neo4j = mock_neo4j

        result = await service._handle_discover_hubs(
            params={"top_n": 5},
            tenant_id="tenant_123",
        )

        assert result.success is True
        assert result.operation == "discover_hubs"
        assert result.result_count > 0
        assert result.metadata == {"top_n": 5}

    @pytest.mark.asyncio
    async def test_discover_hubs_default_top_n(self):
        from app.services.graph_ask_service import GraphAskService

        service = GraphAskService()

        mock_neo4j = MagicMock()
        mock_neo4j._execute_read_async = AsyncMock(return_value=[])
        service._neo4j = mock_neo4j

        result = await service._handle_discover_hubs(
            params={},
            tenant_id="tenant_123",
        )

        assert result.success is True
        assert result.metadata["top_n"] == 10

    @pytest.mark.asyncio
    async def test_discover_hubs_top_n_capped_at_50(self):
        from app.services.graph_ask_service import GraphAskService

        service = GraphAskService()

        mock_neo4j = MagicMock()
        mock_neo4j._execute_read_async = AsyncMock(return_value=[])
        service._neo4j = mock_neo4j

        result = await service._handle_discover_hubs(
            params={"top_n": 100},
            tenant_id="tenant_123",
        )

        assert result.success is True
        assert result.metadata["top_n"] == 50

    @pytest.mark.asyncio
    async def test_discover_hubs_categories(self):
        from app.services.graph_ask_service import GraphAskService

        service = GraphAskService()

        call_count = 0
        async def mock_read(query, params):
            nonlocal call_count
            call_count += 1
            return [{"name": f"item_{call_count}", "count": call_count}]

        mock_neo4j = MagicMock()
        mock_neo4j._execute_read_async = mock_read
        service._neo4j = mock_neo4j

        result = await service._handle_discover_hubs(
            params={},
            tenant_id="tenant_123",
        )

        assert result.success is True
        # 5 categories should be queried
        assert call_count == 5
        categories = {r["category"] for r in result.results}
        expected = {
            "artigos_mais_referenciados",
            "artigos_que_mais_referenciam",
            "artigos_mais_conectados",
            "decisoes_com_mais_teses",
            "leis_com_mais_artigos",
        }
        assert categories == expected

    @pytest.mark.asyncio
    async def test_discover_hubs_partial_failure(self):
        from app.services.graph_ask_service import GraphAskService

        service = GraphAskService()

        call_count = 0
        async def mock_read(query, params):
            nonlocal call_count
            call_count += 1
            if call_count == 3:
                raise Exception("Query timeout")
            return [{"name": f"item_{call_count}", "count": call_count}]

        mock_neo4j = MagicMock()
        mock_neo4j._execute_read_async = mock_read
        service._neo4j = mock_neo4j

        result = await service._handle_discover_hubs(
            params={},
            tenant_id="tenant_123",
        )

        # Should still succeed with partial results
        assert result.success is True
        assert result.result_count == 4  # 5 queries, 1 failed


# =============================================================================
# TOOL DEFINITION
# =============================================================================


class TestDiscoverHubsToolDefinition:
    """Tests that ASK_GRAPH_TOOL includes discover_hubs."""

    def test_discover_hubs_in_operation_enum(self):
        from app.services.ai.shared.unified_tools import ASK_GRAPH_TOOL
        enum_values = ASK_GRAPH_TOOL.parameters["properties"]["operation"]["enum"]
        assert "discover_hubs" in enum_values

    def test_top_n_param_exists(self):
        from app.services.ai.shared.unified_tools import ASK_GRAPH_TOOL
        params_props = ASK_GRAPH_TOOL.parameters["properties"]["params"]["properties"]
        assert "top_n" in params_props

    def test_description_mentions_discover_hubs(self):
        from app.services.ai.shared.unified_tools import ASK_GRAPH_TOOL
        assert "discover_hubs" in ASK_GRAPH_TOOL.description
