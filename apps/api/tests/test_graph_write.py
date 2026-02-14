"""
Tests for Graph Write via Chat — link_entities operation.

Tests the LINK_ENTITIES operation added to GraphAskService,
validating security layers, audit properties, and error handling.

No external dependencies required (mocks Neo4j).
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# =============================================================================
# ENUM & VALIDATION
# =============================================================================


class TestLinkEntitiesEnum:
    """Tests that LINK_ENTITIES is properly registered."""

    def test_link_entities_in_graph_operation(self):
        from app.services.graph_ask_service import GraphOperation
        assert GraphOperation.LINK_ENTITIES == "link_entities"

    def test_link_entities_in_validation(self):
        from app.services.graph_ask_service import GraphAskService, GraphOperation
        service = GraphAskService()
        error = service._validate_params(
            operation=GraphOperation.LINK_ENTITIES,
            params={},
        )
        # Should fail because source_id and target_id are missing
        assert error is not None
        assert "source_id" in error or "target_id" in error

    def test_link_entities_valid_params(self):
        from app.services.graph_ask_service import GraphAskService, GraphOperation
        service = GraphAskService()
        error = service._validate_params(
            operation=GraphOperation.LINK_ENTITIES,
            params={"source_id": "art_5_cf", "target_id": "sumula_stf_473"},
        )
        assert error is None


# =============================================================================
# HANDLER
# =============================================================================


class TestLinkEntitiesHandler:
    """Tests for _handle_link_entities method."""

    @pytest.mark.asyncio
    async def test_link_entities_preflight_requires_confirm(self):
        from app.services.graph_ask_service import GraphAskService

        service = GraphAskService()

        mock_neo4j = MagicMock()
        mock_neo4j.link_entities_async = AsyncMock(return_value=True)
        mock_neo4j._sanitize_relation_type = MagicMock(return_value="INTERPRETA")
        # _execute_query will call _execute_read_async; return entity info then docs count (twice per entity).
        mock_neo4j._execute_read_async = AsyncMock(side_effect=[
            [{"entity_id": "art_5_cf", "name": "Art. 5 CF", "entity_type": "artigo"}],
            [{"docs": 3}],
            [{"entity_id": "sumula_stf_473", "name": "Súmula 473 STF", "entity_type": "sumula"}],
            [{"docs": 2}],
        ])
        service._neo4j = mock_neo4j

        result = await service._handle_link_entities(
            params={
                "source_id": "art_5_cf",
                "target_id": "sumula_stf_473",
                "relation_type": "INTERPRETA",
                # confirm omitted => preflight
            },
            tenant_id="tenant_123",
            scope=None,
            case_id=None,
            include_global=True,
            timeout_ms=2000,
        )

        assert result.success is True
        assert result.metadata == {"requires_confirmation": True, "write_operation": False}
        assert result.results and "source" in result.results[0]
        assert result.results[0].get("preflight_token")
        mock_neo4j.link_entities_async.assert_not_called()

    @pytest.mark.asyncio
    async def test_link_entities_success(self):
        from app.services.graph_ask_service import GraphAskService

        service = GraphAskService()

        mock_neo4j = MagicMock()
        mock_neo4j.link_entities_async = AsyncMock(return_value=True)
        mock_neo4j._sanitize_relation_type = MagicMock(return_value="INTERPRETA")
        service._neo4j = mock_neo4j

        # For this unit test, disable the "require token" gate so we can test the write path directly.
        import app.services.graph_ask_service as gas
        gas._env_bool = lambda *_args, **_kwargs: False  # type: ignore

        result = await service._handle_link_entities(
            params={
                "source_id": "art_5_cf",
                "target_id": "sumula_stf_473",
                "relation_type": "INTERPRETA",
                "confirm": True,
                "preflight_token": "dummy.invalid",
            },
            tenant_id="tenant_123",
            scope=None,
            case_id=None,
            include_global=True,
            timeout_ms=2000,
        )

        assert result.success is True
        assert result.operation == "link_entities"
        assert result.result_count == 1
        assert result.results[0]["relation_type"] == "INTERPRETA"
        assert result.results[0]["source_id"] == "art_5_cf"
        assert result.results[0]["target_id"] == "sumula_stf_473"
        assert result.metadata == {"write_operation": True}

        # Verify link_entities_async was called with correct audit props
        call_args = mock_neo4j.link_entities_async.call_args
        props = call_args.kwargs["properties"]
        assert props["source"] == "user_chat"
        assert props["layer"] == "user_curated"
        assert props["verified"] is True
        assert props["created_by"] == "tenant_123"
        assert props["created_via"] == "chat"
        assert props["tenant_id"] == "tenant_123"

    @pytest.mark.asyncio
    async def test_link_entities_missing_params(self):
        from app.services.graph_ask_service import GraphAskService

        service = GraphAskService()

        import app.services.graph_ask_service as gas
        gas._env_bool = lambda *_args, **_kwargs: False  # type: ignore

        result = await service._handle_link_entities(
            params={"source_id": "art_5_cf"},  # missing target_id
            tenant_id="tenant_123",
            scope=None,
            case_id=None,
            include_global=True,
            timeout_ms=2000,
        )

        assert result.success is False
        assert "source_id" in result.error or "target_id" in result.error

    @pytest.mark.asyncio
    async def test_link_entities_entity_not_found(self):
        from app.services.graph_ask_service import GraphAskService

        service = GraphAskService()

        mock_neo4j = MagicMock()
        mock_neo4j.link_entities_async = AsyncMock(return_value=False)
        mock_neo4j._sanitize_relation_type = MagicMock(return_value="INTERPRETA")
        service._neo4j = mock_neo4j

        import app.services.graph_ask_service as gas
        gas._env_bool = lambda *_args, **_kwargs: False  # type: ignore

        result = await service._handle_link_entities(
            params={
                "source_id": "nonexistent_entity",
                "target_id": "another_nonexistent",
                "relation_type": "INTERPRETA",
                "confirm": True,
            },
            tenant_id="tenant_123",
            scope=None,
            case_id=None,
            include_global=True,
            timeout_ms=2000,
        )

        assert result.success is False
        assert "existem" in result.error.lower() or "falha" in result.error.lower()

    @pytest.mark.asyncio
    async def test_link_entities_invalid_relation_fallback(self):
        from app.services.graph_ask_service import GraphAskService

        service = GraphAskService()

        mock_neo4j = MagicMock()
        mock_neo4j.link_entities_async = AsyncMock(return_value=True)
        mock_neo4j._sanitize_relation_type = MagicMock(return_value="RELATED_TO")
        service._neo4j = mock_neo4j

        import app.services.graph_ask_service as gas
        gas._env_bool = lambda *_args, **_kwargs: False  # type: ignore

        result = await service._handle_link_entities(
            params={
                "source_id": "art_5_cf",
                "target_id": "sumula_stf_473",
                "relation_type": "INVALID_TYPE_123!",
                "confirm": True,
            },
            tenant_id="tenant_123",
            scope=None,
            case_id=None,
            include_global=True,
            timeout_ms=2000,
        )

        assert result.success is True
        assert result.results[0]["relation_type"] == "RELATED_TO"

    @pytest.mark.asyncio
    async def test_link_entities_audit_props_not_overridable(self):
        from app.services.graph_ask_service import GraphAskService

        service = GraphAskService()

        mock_neo4j = MagicMock()
        mock_neo4j.link_entities_async = AsyncMock(return_value=True)
        mock_neo4j._sanitize_relation_type = MagicMock(return_value="INTERPRETA")
        service._neo4j = mock_neo4j

        import app.services.graph_ask_service as gas
        gas._env_bool = lambda *_args, **_kwargs: False  # type: ignore

        result = await service._handle_link_entities(
            params={
                "source_id": "art_5_cf",
                "target_id": "sumula_stf_473",
                "relation_type": "INTERPRETA",
                "confirm": True,
                "properties": {
                    "source": "malicious_override",
                    "layer": "hacked",
                    "verified": False,
                    "created_by": "attacker",
                    "custom_field": "allowed",
                },
            },
            tenant_id="tenant_123",
            scope=None,
            case_id=None,
            include_global=True,
            timeout_ms=2000,
        )

        assert result.success is True

        call_args = mock_neo4j.link_entities_async.call_args
        props = call_args.kwargs["properties"]
        # Audit props must NOT be overridden
        assert props["source"] == "user_chat"
        assert props["layer"] == "user_curated"
        assert props["verified"] is True
        assert props["created_by"] == "tenant_123"
        assert props["tenant_id"] == "tenant_123"
        # Custom field should still be present
        assert props["custom_field"] == "allowed"


# =============================================================================
# TOOL DEFINITION
# =============================================================================


class TestAskGraphToolDefinition:
    """Tests that ASK_GRAPH_TOOL includes link_entities."""

    def test_link_entities_in_operation_enum(self):
        from app.services.ai.shared.unified_tools import ASK_GRAPH_TOOL
        enum_values = ASK_GRAPH_TOOL.parameters["properties"]["operation"]["enum"]
        assert "link_entities" in enum_values

    def test_relation_type_param_exists(self):
        from app.services.ai.shared.unified_tools import ASK_GRAPH_TOOL
        params_props = ASK_GRAPH_TOOL.parameters["properties"]["params"]["properties"]
        assert "relation_type" in params_props
        assert "confirm" in params_props
        assert "preflight_token" in params_props
        assert "properties" in params_props

    def test_description_mentions_link_entities(self):
        from app.services.ai.shared.unified_tools import ASK_GRAPH_TOOL
        assert "link_entities" in ASK_GRAPH_TOOL.description
        assert "Use **search**" in ASK_GRAPH_TOOL.description or "Use \"search\"" in ASK_GRAPH_TOOL.description
