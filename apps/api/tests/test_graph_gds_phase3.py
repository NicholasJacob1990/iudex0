"""
Testes para algoritmos GDS Fase 3 (Avançado) no GraphAskService.

Fase 3 cobre:
- adamic_adar: Link prediction
- node2vec: Embeddings vetoriais
- all_pairs_shortest_path: Matriz de distâncias
- harmonic_centrality: Closeness para grafos desconectados
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.graph_ask_service import GraphAskService, GraphOperation


# =============================================================================
# ENUM VERIFICATION
# =============================================================================


class TestGDSPhase3OperationsEnum:
    """Verifica que todas as 4 operações GDS Fase 3 estão no enum."""

    def test_adamic_adar_in_enum(self):
        assert hasattr(GraphOperation, "ADAMIC_ADAR")
        assert GraphOperation.ADAMIC_ADAR.value == "adamic_adar"

    def test_node2vec_in_enum(self):
        assert hasattr(GraphOperation, "NODE2VEC")
        assert GraphOperation.NODE2VEC.value == "node2vec"

    def test_all_pairs_shortest_path_in_enum(self):
        assert hasattr(GraphOperation, "ALL_PAIRS_SHORTEST_PATH")
        assert GraphOperation.ALL_PAIRS_SHORTEST_PATH.value == "all_pairs_shortest_path"

    def test_harmonic_centrality_in_enum(self):
        assert hasattr(GraphOperation, "HARMONIC_CENTRALITY")
        assert GraphOperation.HARMONIC_CENTRALITY.value == "harmonic_centrality"


# =============================================================================
# HANDLER TESTS (SMOKE)
# =============================================================================


class TestAdamicAdarHandler:
    """Testa handler de adamic_adar."""

    @pytest.mark.asyncio
    async def test_adamic_adar_basic(self):
        """adamic_adar retorna score para par de nós."""
        service = GraphAskService.__new__(GraphAskService)
        service._gds_available = True

        mock_neo4j = AsyncMock()
        # adamic_adar é função, retorna score direto
        mock_neo4j.execute_cypher = AsyncMock(return_value=[
            {"node1": "art-1", "node2": "art-2", "score": 0.85}
        ])

        with patch.object(service, "_get_neo4j", return_value=mock_neo4j):
            result = await service._handle_adamic_adar(
                params={"node1_id": "art-1", "node2_id": "art-2"},
                tenant_id="test-tenant",
            )

        assert result.success is True
        assert result.operation == "adamic_adar"
        assert result.result_count == 1
        assert result.results[0]["score"] == 0.85
        assert result.metadata["algorithm"] == "adamicAdar"

    @pytest.mark.asyncio
    async def test_adamic_adar_missing_params(self):
        """adamic_adar sem node1_id ou node2_id retorna erro."""
        service = GraphAskService.__new__(GraphAskService)
        service._gds_available = True

        result = await service._handle_adamic_adar(
            params={},
            tenant_id="test-tenant",
        )

        assert result.success is False
        assert "node1_id" in result.error or "node2_id" in result.error


class TestNode2VecHandler:
    """Testa handler de node2vec."""

    @pytest.mark.asyncio
    async def test_node2vec_basic(self):
        """node2vec retorna embeddings vetoriais."""
        service = GraphAskService.__new__(GraphAskService)
        service._gds_available = True

        mock_neo4j = AsyncMock()
        # node2vec retorna array de floats
        mock_neo4j.execute_cypher = AsyncMock(return_value=[
            {"entity_id": "art-1", "embedding": [0.1, 0.2, 0.3, 0.4]},
            {"entity_id": "art-2", "embedding": [0.5, 0.6, 0.7, 0.8]},
        ])

        with patch.object(service, "_get_neo4j", return_value=mock_neo4j):
            result = await service._handle_node2vec(
                params={"entity_type": "Artigo", "embedding_dimension": 4, "limit": 10},
                tenant_id="test-tenant",
            )

        assert result.success is True
        assert result.operation == "node2vec"
        assert result.result_count == 2
        assert len(result.results[0]["embedding"]) == 4
        assert result.metadata["algorithm"] == "node2vec"
        assert result.metadata["embedding_dimension"] == 4


class TestAllPairsShortestPathHandler:
    """Testa handler de all_pairs_shortest_path."""

    @pytest.mark.asyncio
    async def test_all_pairs_shortest_path_basic(self):
        """all_pairs_shortest_path retorna matriz de distâncias."""
        service = GraphAskService.__new__(GraphAskService)
        service._gds_available = True

        mock_neo4j = AsyncMock()
        mock_neo4j.execute_cypher = AsyncMock(return_value=[
            {"source": "art-1", "target": "art-2", "distance": 1},
            {"source": "art-1", "target": "art-3", "distance": 2},
            {"source": "art-2", "target": "art-3", "distance": 1},
        ])

        with patch.object(service, "_get_neo4j", return_value=mock_neo4j):
            result = await service._handle_all_pairs_shortest_path(
                params={"entity_type": "Artigo", "limit": 100},
                tenant_id="test-tenant",
            )

        assert result.success is True
        assert result.operation == "all_pairs_shortest_path"
        assert result.result_count == 3
        assert result.metadata["algorithm"] == "allShortestPaths"


class TestHarmonicCentralityHandler:
    """Testa handler de harmonic_centrality."""

    @pytest.mark.asyncio
    async def test_harmonic_centrality_basic(self):
        """harmonic_centrality retorna centralidade robusta."""
        service = GraphAskService.__new__(GraphAskService)
        service._gds_available = True

        mock_neo4j = AsyncMock()
        mock_neo4j.execute_cypher = AsyncMock(return_value=[
            {"entity_id": "art-1", "name": "Art. 1", "score": 0.95},
            {"entity_id": "art-2", "name": "Art. 2", "score": 0.80},
        ])

        with patch.object(service, "_get_neo4j", return_value=mock_neo4j):
            result = await service._handle_harmonic_centrality(
                params={"entity_type": "Artigo", "limit": 20},
                tenant_id="test-tenant",
            )

        assert result.success is True
        assert result.operation == "harmonic_centrality"
        assert result.result_count == 2
        assert result.results[0]["score"] == 0.95
        assert result.metadata["algorithm"] == "harmonicCentrality"


# =============================================================================
# DISPATCHER INTEGRATION
# =============================================================================


class TestGDSPhase3Dispatcher:
    """Testa que as operações são despachadas corretamente."""

    @pytest.mark.asyncio
    async def test_dispatcher_calls_adamic_adar(self):
        """Dispatcher chama _handle_adamic_adar quando operation=adamic_adar."""
        service = GraphAskService.__new__(GraphAskService)
        service._gds_available = True

        mock_handler = AsyncMock(return_value=MagicMock(success=True))
        service._handle_adamic_adar = mock_handler

        with patch.object(service, "_get_neo4j", return_value=AsyncMock()):
            await service.ask(
                operation="adamic_adar",
                params={"node1_id": "art-1", "node2_id": "art-2"},
                tenant_id="test-tenant",
            )

        mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatcher_calls_node2vec(self):
        """Dispatcher chama _handle_node2vec quando operation=node2vec."""
        service = GraphAskService.__new__(GraphAskService)
        service._gds_available = True

        mock_handler = AsyncMock(return_value=MagicMock(success=True))
        service._handle_node2vec = mock_handler

        with patch.object(service, "_get_neo4j", return_value=AsyncMock()):
            await service.ask(
                operation="node2vec",
                params={"entity_type": "Artigo", "embedding_dimension": 8},
                tenant_id="test-tenant",
            )

        mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatcher_calls_all_pairs_shortest_path(self):
        """Dispatcher chama _handle_all_pairs_shortest_path."""
        service = GraphAskService.__new__(GraphAskService)
        service._gds_available = True

        mock_handler = AsyncMock(return_value=MagicMock(success=True))
        service._handle_all_pairs_shortest_path = mock_handler

        with patch.object(service, "_get_neo4j", return_value=AsyncMock()):
            await service.ask(
                operation="all_pairs_shortest_path",
                params={"entity_type": "Artigo"},
                tenant_id="test-tenant",
            )

        mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatcher_calls_harmonic_centrality(self):
        """Dispatcher chama _handle_harmonic_centrality."""
        service = GraphAskService.__new__(GraphAskService)
        service._gds_available = True

        mock_handler = AsyncMock(return_value=MagicMock(success=True))
        service._handle_harmonic_centrality = mock_handler

        with patch.object(service, "_get_neo4j", return_value=AsyncMock()):
            await service.ask(
                operation="harmonic_centrality",
                params={"entity_type": "Artigo", "limit": 20},
                tenant_id="test-tenant",
            )

        mock_handler.assert_called_once()
