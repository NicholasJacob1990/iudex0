"""
Tests for factual QA operations in GraphAskService.

Tests the new operations exposed to agents:
- text2cypher (enum exposure)
- legal_chain (enum exposure)
- precedent_network (enum exposure)
- related_entities (new template + enum)
- entity_stats (new handler + enum)

Also tests parameter propagation in tool_handlers.

No external dependencies required (mocks Neo4j).
"""

import pytest
from unittest.mock import AsyncMock, MagicMock


# =============================================================================
# TOOL ENUM EXPOSURE
# =============================================================================


class TestToolEnumExposure:
    """Tests that all factual QA operations are in ASK_GRAPH_TOOL."""

    def test_text2cypher_in_tool_enum(self):
        from app.services.ai.shared.unified_tools import ASK_GRAPH_TOOL
        enum_values = ASK_GRAPH_TOOL.parameters["properties"]["operation"]["enum"]
        assert "text2cypher" in enum_values

    def test_legal_chain_in_tool_enum(self):
        from app.services.ai.shared.unified_tools import ASK_GRAPH_TOOL
        enum_values = ASK_GRAPH_TOOL.parameters["properties"]["operation"]["enum"]
        assert "legal_chain" in enum_values

    def test_precedent_network_in_tool_enum(self):
        from app.services.ai.shared.unified_tools import ASK_GRAPH_TOOL
        enum_values = ASK_GRAPH_TOOL.parameters["properties"]["operation"]["enum"]
        assert "precedent_network" in enum_values

    def test_related_entities_in_tool_enum(self):
        from app.services.ai.shared.unified_tools import ASK_GRAPH_TOOL
        enum_values = ASK_GRAPH_TOOL.parameters["properties"]["operation"]["enum"]
        assert "related_entities" in enum_values

    def test_entity_stats_in_tool_enum(self):
        from app.services.ai.shared.unified_tools import ASK_GRAPH_TOOL
        enum_values = ASK_GRAPH_TOOL.parameters["properties"]["operation"]["enum"]
        assert "entity_stats" in enum_values

    def test_question_param_exists(self):
        from app.services.ai.shared.unified_tools import ASK_GRAPH_TOOL
        params_props = ASK_GRAPH_TOOL.parameters["properties"]["params"]["properties"]
        assert "question" in params_props

    def test_decision_id_param_exists(self):
        from app.services.ai.shared.unified_tools import ASK_GRAPH_TOOL
        params_props = ASK_GRAPH_TOOL.parameters["properties"]["params"]["properties"]
        assert "decision_id" in params_props

    def test_relation_filter_param_exists(self):
        from app.services.ai.shared.unified_tools import ASK_GRAPH_TOOL
        params_props = ASK_GRAPH_TOOL.parameters["properties"]["params"]["properties"]
        assert "relation_filter" in params_props

    def test_description_mentions_text2cypher(self):
        from app.services.ai.shared.unified_tools import ASK_GRAPH_TOOL
        assert "text2cypher" in ASK_GRAPH_TOOL.description

    def test_description_mentions_related_entities(self):
        from app.services.ai.shared.unified_tools import ASK_GRAPH_TOOL
        assert "related_entities" in ASK_GRAPH_TOOL.description

    def test_description_mentions_entity_stats(self):
        from app.services.ai.shared.unified_tools import ASK_GRAPH_TOOL
        assert "entity_stats" in ASK_GRAPH_TOOL.description


# =============================================================================
# GRAPH OPERATION ENUM
# =============================================================================


class TestGraphOperationEnum:
    """Tests that new operations exist in GraphOperation enum."""

    def test_related_entities_in_enum(self):
        from app.services.graph_ask_service import GraphOperation
        assert GraphOperation.RELATED_ENTITIES == "related_entities"

    def test_entity_stats_in_enum(self):
        from app.services.graph_ask_service import GraphOperation
        assert GraphOperation.ENTITY_STATS == "entity_stats"


# =============================================================================
# VALIDATION
# =============================================================================


class TestValidation:
    """Tests parameter validation for new operations."""

    def test_related_entities_requires_entity_id(self):
        from app.services.graph_ask_service import GraphAskService, GraphOperation
        service = GraphAskService()
        error = service._validate_params(
            operation=GraphOperation.RELATED_ENTITIES,
            params={},
        )
        assert error is not None
        assert "entity_id" in error

    def test_related_entities_valid_with_entity_id(self):
        from app.services.graph_ask_service import GraphAskService, GraphOperation
        service = GraphAskService()
        error = service._validate_params(
            operation=GraphOperation.RELATED_ENTITIES,
            params={"entity_id": "art_5_cf"},
        )
        assert error is None

    def test_entity_stats_no_required_params(self):
        from app.services.graph_ask_service import GraphAskService, GraphOperation
        service = GraphAskService()
        error = service._validate_params(
            operation=GraphOperation.ENTITY_STATS,
            params={},
        )
        assert error is None


# =============================================================================
# RELATED_ENTITIES TEMPLATE
# =============================================================================


class TestRelatedEntitiesTemplate:
    """Tests that related_entities template is properly defined."""

    def test_template_exists(self):
        from app.services.graph_ask_service import CYPHER_TEMPLATES
        assert "related_entities" in CYPHER_TEMPLATES

    def test_template_has_entity_id_param(self):
        from app.services.graph_ask_service import CYPHER_TEMPLATES
        template = CYPHER_TEMPLATES["related_entities"]
        assert "$entity_id" in template

    def test_template_excludes_infra_rels(self):
        from app.services.graph_ask_service import CYPHER_TEMPLATES
        template = CYPHER_TEMPLATES["related_entities"]
        assert "FROM_CHUNK" in template
        assert "FROM_DOCUMENT" in template
        assert "NEXT_CHUNK" in template

    def test_template_has_relation_filter(self):
        from app.services.graph_ask_service import CYPHER_TEMPLATES
        template = CYPHER_TEMPLATES["related_entities"]
        assert "$relation_filter" in template

    def test_template_returns_direction(self):
        from app.services.graph_ask_service import CYPHER_TEMPLATES
        template = CYPHER_TEMPLATES["related_entities"]
        assert "direction" in template
        assert "outgoing" in template
        assert "incoming" in template

    def test_template_has_tenant_filter(self):
        from app.services.graph_ask_service import CYPHER_TEMPLATES
        template = CYPHER_TEMPLATES["related_entities"]
        assert "$tenant_id" in template


# =============================================================================
# ENTITY_STATS HANDLER
# =============================================================================


class TestEntityStatsHandler:
    """Tests for _handle_entity_stats method."""

    @pytest.mark.asyncio
    async def test_entity_stats_success(self):
        from app.services.graph_ask_service import GraphAskService

        service = GraphAskService()

        call_count = 0
        async def mock_read(query, params):
            nonlocal call_count
            call_count += 1
            if "count(e)" in query and "entity_type" not in query:
                return [{"c": 200}]
            elif "entity_type" in query:
                return [
                    {"type": "artigo", "c": 100},
                    {"type": "sumula", "c": 50},
                ]
            elif "count(r)" in query and "type(r) AS" not in query:
                return [{"c": 500}]
            else:
                return [
                    {"type": "REMETE_A", "c": 200},
                    {"type": "INTERPRETA", "c": 150},
                ]

        mock_neo4j = MagicMock()
        mock_neo4j._execute_read_async = mock_read
        service._neo4j = mock_neo4j

        result = await service._handle_entity_stats(
            params={},
            tenant_id="tenant_123",
        )

        assert result.success is True
        assert result.operation == "entity_stats"
        assert result.result_count == 4  # 4 categories
        categories = {r["category"] for r in result.results}
        assert categories == {"total_entities", "by_type", "total_relationships", "rel_types"}

    @pytest.mark.asyncio
    async def test_entity_stats_partial_failure(self):
        from app.services.graph_ask_service import GraphAskService

        service = GraphAskService()

        call_count = 0
        async def mock_read(query, params):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise Exception("Query timeout")
            return [{"c": 100}]

        mock_neo4j = MagicMock()
        mock_neo4j._execute_read_async = mock_read
        service._neo4j = mock_neo4j

        result = await service._handle_entity_stats(
            params={},
            tenant_id="tenant_123",
        )

        # Should still succeed with partial results
        assert result.success is True
        assert result.result_count == 4
        # One category should have error
        errors = [r for r in result.results if "error" in r]
        assert len(errors) == 1

    @pytest.mark.asyncio
    async def test_entity_stats_metadata(self):
        from app.services.graph_ask_service import GraphAskService

        service = GraphAskService()

        mock_neo4j = MagicMock()
        mock_neo4j._execute_read_async = AsyncMock(return_value=[{"c": 0}])
        service._neo4j = mock_neo4j

        result = await service._handle_entity_stats(
            params={},
            tenant_id="tenant_123",
        )

        assert result.success is True
        assert "categories" in result.metadata
        assert len(result.metadata["categories"]) == 4


# =============================================================================
# ENDPOINT LITERAL
# =============================================================================


class TestEndpointLiteral:
    """Tests that graph_ask endpoint accepts new operations."""

    def test_related_entities_in_literal(self):
        from app.api.endpoints.graph_ask import GraphAskRequest
        req = GraphAskRequest(
            operation="related_entities",
            params={"entity_id": "art_5_cf"},
        )
        assert req.operation == "related_entities"

    def test_entity_stats_in_literal(self):
        from app.api.endpoints.graph_ask import GraphAskRequest
        req = GraphAskRequest(
            operation="entity_stats",
            params={},
        )
        assert req.operation == "entity_stats"

    def test_text2cypher_already_in_literal(self):
        from app.api.endpoints.graph_ask import GraphAskRequest
        req = GraphAskRequest(
            operation="text2cypher",
            params={"question": "test"},
        )
        assert req.operation == "text2cypher"
