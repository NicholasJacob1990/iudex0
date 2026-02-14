"""
Testes para operações GDS Fase 1: Prioridade Máxima.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.graph_ask_service import GraphAskService, GraphOperation


# =============================================================================
# ENUM VERIFICATION
# =============================================================================


class TestGDSPhase1Enum:
    """Verifica que todas as 5 operações da Fase 1 estão no enum."""

    def test_closeness_centrality_in_enum(self):
        assert hasattr(GraphOperation, "CLOSENESS_CENTRALITY")
        assert GraphOperation.CLOSENESS_CENTRALITY.value == "closeness_centrality"

    def test_eigenvector_centrality_in_enum(self):
        assert hasattr(GraphOperation, "EIGENVECTOR_CENTRALITY")
        assert GraphOperation.EIGENVECTOR_CENTRALITY.value == "eigenvector_centrality"

    def test_leiden_in_enum(self):
        assert hasattr(GraphOperation, "LEIDEN")
        assert GraphOperation.LEIDEN.value == "leiden"

    def test_k_core_decomposition_in_enum(self):
        assert hasattr(GraphOperation, "K_CORE_DECOMPOSITION")
        assert GraphOperation.K_CORE_DECOMPOSITION.value == "k_core_decomposition"

    def test_knn_in_enum(self):
        assert hasattr(GraphOperation, "KNN")
        assert GraphOperation.KNN.value == "knn"


# =============================================================================
# HANDLER SMOKE TESTS
# =============================================================================


class TestClosenessCentralityHandler:
    """Testa handler de closeness_centrality."""

    @pytest.mark.asyncio
    async def test_handler_returns_results(self):
        """Handler retorna resultados formatados corretamente."""
        service = GraphAskService.__new__(GraphAskService)
        service._gds_available = True

        mock_neo4j = AsyncMock()
        mock_neo4j.execute_cypher = AsyncMock(
            return_value=[
                {
                    "entity_id": "art-5-cf",
                    "name": "Art. 5º CF",
                    "score": 0.75,
                }
            ]
        )

        with patch.object(service, "_get_neo4j", return_value=mock_neo4j):
            result = await service._handle_closeness_centrality(
                {"limit": 10}, "tenant-123"
            )

        assert result.success is True
        assert result.operation == "closeness_centrality"
        assert result.result_count == 1
        assert result.results[0]["entity_id"] == "art-5-cf"
        assert result.results[0]["score"] == 0.75
        assert result.metadata["algorithm"] == "closeness"


class TestEigenvectorCentralityHandler:
    """Testa handler de eigenvector_centrality."""

    @pytest.mark.asyncio
    async def test_handler_returns_results(self):
        """Handler retorna resultados formatados corretamente."""
        service = GraphAskService.__new__(GraphAskService)
        service._gds_available = True

        mock_neo4j = AsyncMock()
        mock_neo4j.execute_cypher = AsyncMock(
            return_value=[
                {
                    "entity_id": "art-37-cf",
                    "name": "Art. 37 CF",
                    "score": 0.92,
                }
            ]
        )

        with patch.object(service, "_get_neo4j", return_value=mock_neo4j):
            result = await service._handle_eigenvector_centrality(
                {"limit": 10, "max_iterations": 20}, "tenant-123"
            )

        assert result.success is True
        assert result.operation == "eigenvector_centrality"
        assert result.result_count == 1
        assert result.results[0]["score"] == 0.92
        assert result.metadata["algorithm"] == "eigenvector"
        assert result.metadata["max_iterations"] == 20


class TestLeidenHandler:
    """Testa handler de leiden."""

    @pytest.mark.asyncio
    async def test_handler_returns_communities(self):
        """Handler retorna comunidades com IDs."""
        service = GraphAskService.__new__(GraphAskService)
        service._gds_available = True

        mock_neo4j = AsyncMock()
        mock_neo4j.execute_cypher = AsyncMock(
            return_value=[
                {
                    "entity_id": "art-1-cf",
                    "name": "Art. 1º CF",
                    "community_id": 1,
                }
            ]
        )

        with patch.object(service, "_get_neo4j", return_value=mock_neo4j):
            result = await service._handle_leiden({"limit": 10}, "tenant-123")

        assert result.success is True
        assert result.operation == "leiden"
        assert result.result_count == 1
        assert result.results[0]["community_id"] == 1
        assert result.metadata["algorithm"] == "leiden"


class TestKCoreDecompositionHandler:
    """Testa handler de k_core_decomposition."""

    @pytest.mark.asyncio
    async def test_handler_returns_core_values(self):
        """Handler retorna nós com coreValue."""
        service = GraphAskService.__new__(GraphAskService)
        service._gds_available = True

        mock_neo4j = AsyncMock()
        mock_neo4j.execute_cypher = AsyncMock(
            return_value=[
                {
                    "entity_id": "art-100-cf",
                    "name": "Art. 100 CF",
                    "core_value": 5,
                }
            ]
        )

        with patch.object(service, "_get_neo4j", return_value=mock_neo4j):
            result = await service._handle_k_core_decomposition(
                {"limit": 10}, "tenant-123"
            )

        assert result.success is True
        assert result.operation == "k_core_decomposition"
        assert result.result_count == 1
        assert result.results[0]["core_value"] == 5
        assert result.metadata["algorithm"] == "k-core"


class TestKNNHandler:
    """Testa handler de knn."""

    @pytest.mark.asyncio
    async def test_handler_returns_similarity_pairs(self):
        """Handler retorna pares com similaridade."""
        service = GraphAskService.__new__(GraphAskService)
        service._gds_available = True

        mock_neo4j = AsyncMock()
        mock_neo4j.execute_cypher = AsyncMock(
            return_value=[
                {
                    "node1_id": "art-5-cf",
                    "node1_name": "Art. 5º CF",
                    "node2_id": "art-7-cf",
                    "node2_name": "Art. 7º CF",
                    "similarity": 0.88,
                }
            ]
        )

        with patch.object(service, "_get_neo4j", return_value=mock_neo4j):
            result = await service._handle_knn(
                {"top_k": 10, "limit": 20}, "tenant-123"
            )

        assert result.success is True
        assert result.operation == "knn"
        assert result.result_count == 1
        assert result.results[0]["similarity"] == 0.88
        assert result.metadata["algorithm"] == "knn"
        assert result.metadata["top_k"] == 10


# =============================================================================
# INTEGRATION: ASK() DISPATCHER
# =============================================================================


class TestGDSPhase1Dispatcher:
    """Testa que ask() dispatcher roteia corretamente para handlers Fase 1."""

    @pytest.mark.asyncio
    async def test_closeness_centrality_routes_correctly(self):
        """ask() roteia closeness_centrality para handler correto."""
        service = GraphAskService.__new__(GraphAskService)
        service._gds_available = True

        mock_handler = AsyncMock(
            return_value=MagicMock(
                success=True,
                operation="closeness_centrality",
                results=[],
                result_count=0,
            )
        )

        with patch.object(service, "_check_gds_available", return_value=True):
            with patch.object(
                service, "_handle_closeness_centrality", mock_handler
            ):
                result = await service.ask(
                    operation=GraphOperation.CLOSENESS_CENTRALITY.value,
                    params={"limit": 10},
                    tenant_id="tenant-123",
                )

        assert result.success is True
        mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_eigenvector_centrality_routes_correctly(self):
        """ask() roteia eigenvector_centrality para handler correto."""
        service = GraphAskService.__new__(GraphAskService)
        service._gds_available = True

        mock_handler = AsyncMock(
            return_value=MagicMock(
                success=True,
                operation="eigenvector_centrality",
                results=[],
                result_count=0,
            )
        )

        with patch.object(service, "_check_gds_available", return_value=True):
            with patch.object(
                service, "_handle_eigenvector_centrality", mock_handler
            ):
                result = await service.ask(
                    operation=GraphOperation.EIGENVECTOR_CENTRALITY.value,
                    params={"limit": 10},
                    tenant_id="tenant-123",
                )

        assert result.success is True
        mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_leiden_routes_correctly(self):
        """ask() roteia leiden para handler correto."""
        service = GraphAskService.__new__(GraphAskService)
        service._gds_available = True

        mock_handler = AsyncMock(
            return_value=MagicMock(
                success=True,
                operation="leiden",
                results=[],
                result_count=0,
            )
        )

        with patch.object(service, "_check_gds_available", return_value=True):
            with patch.object(service, "_handle_leiden", mock_handler):
                result = await service.ask(
                    operation=GraphOperation.LEIDEN.value,
                    params={"limit": 10},
                    tenant_id="tenant-123",
                )

        assert result.success is True
        mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_k_core_decomposition_routes_correctly(self):
        """ask() roteia k_core_decomposition para handler correto."""
        service = GraphAskService.__new__(GraphAskService)
        service._gds_available = True

        mock_handler = AsyncMock(
            return_value=MagicMock(
                success=True,
                operation="k_core_decomposition",
                results=[],
                result_count=0,
            )
        )

        with patch.object(service, "_check_gds_available", return_value=True):
            with patch.object(
                service, "_handle_k_core_decomposition", mock_handler
            ):
                result = await service.ask(
                    operation=GraphOperation.K_CORE_DECOMPOSITION.value,
                    params={"limit": 10},
                    tenant_id="tenant-123",
                )

        assert result.success is True
        mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_knn_routes_correctly(self):
        """ask() roteia knn para handler correto."""
        service = GraphAskService.__new__(GraphAskService)
        service._gds_available = True

        mock_handler = AsyncMock(
            return_value=MagicMock(
                success=True,
                operation="knn",
                results=[],
                result_count=0,
            )
        )

        with patch.object(service, "_check_gds_available", return_value=True):
            with patch.object(service, "_handle_knn", mock_handler):
                result = await service.ask(
                    operation=GraphOperation.KNN.value,
                    params={"top_k": 10, "limit": 20},
                    tenant_id="tenant-123",
                )

        assert result.success is True
        mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_gds_disabled_blocks_phase1_operations(self):
        """Se GDS não disponível, ask() retorna erro para operações Fase 1."""
        service = GraphAskService.__new__(GraphAskService)
        service._gds_available = False

        with patch.object(service, "_check_gds_available", return_value=False):
            result = await service.ask(
                operation=GraphOperation.CLOSENESS_CENTRALITY.value,
                params={"limit": 10},
                tenant_id="tenant-123",
            )

        assert result.success is False
        assert "GDS plugin não instalado" in result.error
