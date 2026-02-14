"""
Testes para operações GDS Fase 2 (Casos Específicos) no GraphAskService.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.graph_ask_service import GraphAskService, GraphOperation


# =============================================================================
# ENUM VERIFICATION
# =============================================================================


class TestGDSPhase2OperationsEnum:
    """Verifica que todas as 4 operações GDS Fase 2 estão no enum."""

    def test_bridges_in_enum(self):
        assert hasattr(GraphOperation, "BRIDGES")
        assert GraphOperation.BRIDGES.value == "bridges"

    def test_articulation_points_in_enum(self):
        assert hasattr(GraphOperation, "ARTICULATION_POINTS")
        assert GraphOperation.ARTICULATION_POINTS.value == "articulation_points"

    def test_strongly_connected_components_in_enum(self):
        assert hasattr(GraphOperation, "STRONGLY_CONNECTED_COMPONENTS")
        assert (
            GraphOperation.STRONGLY_CONNECTED_COMPONENTS.value
            == "strongly_connected_components"
        )

    def test_yens_k_shortest_paths_in_enum(self):
        assert hasattr(GraphOperation, "YENS_K_SHORTEST_PATHS")
        assert GraphOperation.YENS_K_SHORTEST_PATHS.value == "yens_k_shortest_paths"


# =============================================================================
# HANDLER SMOKE TESTS (com mocks)
# =============================================================================


class TestBridgesHandler:
    """Testa handler de bridges."""

    @pytest.mark.asyncio
    async def test_handler_returns_bridge_edges(self):
        """Handler retorna arestas críticas (pontes)."""
        service = GraphAskService.__new__(GraphAskService)
        service._gds_available = True

        mock_neo4j = AsyncMock()
        mock_neo4j.execute_cypher = AsyncMock(
            return_value=[
                {
                    "from_entity_id": "art-5-cf",
                    "from_name": "Art. 5º CF",
                    "to_entity_id": "art-37-cf",
                    "to_name": "Art. 37 CF",
                }
            ]
        )

        with patch.object(service, "_get_neo4j", return_value=mock_neo4j):
            result = await service._handle_bridges({"limit": 50}, "tenant-123")

        assert result.success is True
        assert result.operation == "bridges"
        assert result.result_count == 1
        assert result.results[0]["from_entity_id"] == "art-5-cf"
        assert result.results[0]["to_entity_id"] == "art-37-cf"


class TestArticulationPointsHandler:
    """Testa handler de articulation_points."""

    @pytest.mark.asyncio
    async def test_handler_returns_critical_nodes(self):
        """Handler retorna nós críticos (pontos de articulação)."""
        service = GraphAskService.__new__(GraphAskService)
        service._gds_available = True

        mock_neo4j = AsyncMock()
        mock_neo4j.execute_cypher = AsyncMock(
            return_value=[
                {
                    "entity_id": "art-100-cf",
                    "name": "Art. 100 CF",
                }
            ]
        )

        with patch.object(service, "_get_neo4j", return_value=mock_neo4j):
            result = await service._handle_articulation_points(
                {"limit": 50}, "tenant-123"
            )

        assert result.success is True
        assert result.operation == "articulation_points"
        assert result.result_count == 1
        assert result.results[0]["entity_id"] == "art-100-cf"


class TestStronglyConnectedComponentsHandler:
    """Testa handler de strongly_connected_components."""

    @pytest.mark.asyncio
    async def test_handler_returns_sccs(self):
        """Handler retorna componentes fortemente conectados (SCCs)."""
        service = GraphAskService.__new__(GraphAskService)
        service._gds_available = True

        mock_neo4j = AsyncMock()
        mock_neo4j.execute_cypher = AsyncMock(
            return_value=[
                {
                    "entity_id": "art-1-cf",
                    "name": "Art. 1º CF",
                    "component_id": 1,
                },
                {
                    "entity_id": "art-2-cf",
                    "name": "Art. 2º CF",
                    "component_id": 1,
                },
            ]
        )

        with patch.object(service, "_get_neo4j", return_value=mock_neo4j):
            result = await service._handle_strongly_connected_components(
                {"limit": 100}, "tenant-123"
            )

        assert result.success is True
        assert result.operation == "strongly_connected_components"
        assert result.result_count == 2
        assert result.results[0]["component_id"] == 1
        assert result.results[1]["component_id"] == 1


class TestYensKShortestPathsHandler:
    """Testa handler de yens_k_shortest_paths."""

    @pytest.mark.asyncio
    async def test_handler_requires_source_and_target(self):
        """Handler valida source_id e target_id obrigatórios."""
        service = GraphAskService.__new__(GraphAskService)
        service._gds_available = True

        # Sem source_id
        result = await service._handle_yens_k_shortest_paths(
            {"target_id": "art-2-cf", "k": 3}, "tenant-123"
        )
        assert result.success is False
        assert "source_id e target_id são obrigatórios" in result.error

        # Sem target_id
        result = await service._handle_yens_k_shortest_paths(
            {"source_id": "art-1-cf", "k": 3}, "tenant-123"
        )
        assert result.success is False
        assert "source_id e target_id são obrigatórios" in result.error

    @pytest.mark.asyncio
    async def test_handler_returns_k_paths(self):
        """Handler retorna K caminhos alternativos."""
        service = GraphAskService.__new__(GraphAskService)
        service._gds_available = True

        mock_neo4j = AsyncMock()
        mock_neo4j.execute_cypher = AsyncMock(
            return_value=[
                {
                    "path_index": 0,
                    "path": ["art-5-cf", "art-37-cf", "lei-14133"],
                    "total_cost": 2.0,
                },
                {
                    "path_index": 1,
                    "path": ["art-5-cf", "art-6-cf", "art-37-cf", "lei-14133"],
                    "total_cost": 3.0,
                },
            ]
        )

        with patch.object(service, "_get_neo4j", return_value=mock_neo4j):
            result = await service._handle_yens_k_shortest_paths(
                {
                    "source_id": "art-5-cf",
                    "target_id": "lei-14133",
                    "k": 3,
                },
                "tenant-123",
            )

        assert result.success is True
        assert result.operation == "yens_k_shortest_paths"
        assert result.result_count == 2
        assert result.results[0]["path_index"] == 0
        assert len(result.results[0]["path"]) == 3
        assert result.results[1]["path_index"] == 1
        assert len(result.results[1]["path"]) == 4


# =============================================================================
# INTEGRATION: ASK() DISPATCHER
# =============================================================================


class TestGDSPhase2Dispatcher:
    """Testa que ask() dispatcher roteia corretamente para GDS Fase 2 handlers."""

    @pytest.mark.asyncio
    async def test_gds_disabled_blocks_bridges(self):
        """Se GDS não disponível, ask() retorna erro para bridges."""
        service = GraphAskService.__new__(GraphAskService)
        service._gds_available = False

        with patch.object(service, "_check_gds_available", return_value=False):
            result = await service.ask(
                operation=GraphOperation.BRIDGES.value,
                params={"limit": 50},
                tenant_id="tenant-123",
            )

        assert result.success is False
        assert "GDS plugin não instalado" in result.error

    @pytest.mark.asyncio
    async def test_gds_enabled_routes_to_bridges(self):
        """Se GDS disponível, ask() roteia para handler bridges."""
        service = GraphAskService.__new__(GraphAskService)
        service._gds_available = True

        mock_handler = AsyncMock(
            return_value=MagicMock(
                success=True,
                operation="bridges",
                results=[],
                result_count=0,
            )
        )

        with patch.object(service, "_check_gds_available", return_value=True):
            with patch.object(service, "_handle_bridges", mock_handler):
                result = await service.ask(
                    operation=GraphOperation.BRIDGES.value,
                    params={"limit": 50},
                    tenant_id="tenant-123",
                )

        assert result.success is True
        mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_gds_enabled_routes_to_articulation_points(self):
        """Se GDS disponível, ask() roteia para handler articulation_points."""
        service = GraphAskService.__new__(GraphAskService)
        service._gds_available = True

        mock_handler = AsyncMock(
            return_value=MagicMock(
                success=True,
                operation="articulation_points",
                results=[],
                result_count=0,
            )
        )

        with patch.object(service, "_check_gds_available", return_value=True):
            with patch.object(service, "_handle_articulation_points", mock_handler):
                result = await service.ask(
                    operation=GraphOperation.ARTICULATION_POINTS.value,
                    params={"limit": 50},
                    tenant_id="tenant-123",
                )

        assert result.success is True
        mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_gds_enabled_routes_to_strongly_connected_components(self):
        """Se GDS disponível, ask() roteia para handler strongly_connected_components."""
        service = GraphAskService.__new__(GraphAskService)
        service._gds_available = True

        mock_handler = AsyncMock(
            return_value=MagicMock(
                success=True,
                operation="strongly_connected_components",
                results=[],
                result_count=0,
            )
        )

        with patch.object(service, "_check_gds_available", return_value=True):
            with patch.object(
                service, "_handle_strongly_connected_components", mock_handler
            ):
                result = await service.ask(
                    operation=GraphOperation.STRONGLY_CONNECTED_COMPONENTS.value,
                    params={"limit": 100},
                    tenant_id="tenant-123",
                )

        assert result.success is True
        mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_gds_enabled_routes_to_yens_k_shortest_paths(self):
        """Se GDS disponível, ask() roteia para handler yens_k_shortest_paths."""
        service = GraphAskService.__new__(GraphAskService)
        service._gds_available = True

        mock_handler = AsyncMock(
            return_value=MagicMock(
                success=True,
                operation="yens_k_shortest_paths",
                results=[],
                result_count=0,
            )
        )

        with patch.object(service, "_check_gds_available", return_value=True):
            with patch.object(service, "_handle_yens_k_shortest_paths", mock_handler):
                result = await service.ask(
                    operation=GraphOperation.YENS_K_SHORTEST_PATHS.value,
                    params={
                        "source_id": "art-5-cf",
                        "target_id": "lei-14133",
                        "k": 3,
                    },
                    tenant_id="tenant-123",
                )

        assert result.success is True
        mock_handler.assert_called_once()
