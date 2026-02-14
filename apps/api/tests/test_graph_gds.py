"""
Testes básicos para operações GDS (Graph Data Science) no GraphAskService.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.graph_ask_service import GraphAskService, GraphOperation


# =============================================================================
# ENUM VERIFICATION
# =============================================================================


class TestGDSOperationsEnum:
    """Verifica que todas as 8 operações GDS estão no enum."""

    def test_betweenness_centrality_in_enum(self):
        assert hasattr(GraphOperation, "BETWEENNESS_CENTRALITY")
        assert GraphOperation.BETWEENNESS_CENTRALITY.value == "betweenness_centrality"

    def test_community_detection_in_enum(self):
        assert hasattr(GraphOperation, "COMMUNITY_DETECTION")
        assert GraphOperation.COMMUNITY_DETECTION.value == "community_detection"

    def test_node_similarity_in_enum(self):
        assert hasattr(GraphOperation, "NODE_SIMILARITY")
        assert GraphOperation.NODE_SIMILARITY.value == "node_similarity"

    def test_pagerank_personalized_in_enum(self):
        assert hasattr(GraphOperation, "PAGERANK_PERSONALIZED")
        assert GraphOperation.PAGERANK_PERSONALIZED.value == "pagerank_personalized"

    def test_weakly_connected_components_in_enum(self):
        assert hasattr(GraphOperation, "WEAKLY_CONNECTED_COMPONENTS")
        assert (
            GraphOperation.WEAKLY_CONNECTED_COMPONENTS.value
            == "weakly_connected_components"
        )

    def test_shortest_path_weighted_in_enum(self):
        assert hasattr(GraphOperation, "SHORTEST_PATH_WEIGHTED")
        assert (
            GraphOperation.SHORTEST_PATH_WEIGHTED.value == "shortest_path_weighted"
        )

    def test_triangle_count_in_enum(self):
        assert hasattr(GraphOperation, "TRIANGLE_COUNT")
        assert GraphOperation.TRIANGLE_COUNT.value == "triangle_count"

    def test_degree_centrality_in_enum(self):
        assert hasattr(GraphOperation, "DEGREE_CENTRALITY")
        assert GraphOperation.DEGREE_CENTRALITY.value == "degree_centrality"


# =============================================================================
# GDS AVAILABILITY CHECK
# =============================================================================


class TestGDSAvailability:
    """Testa verificação de disponibilidade do plugin GDS."""

    @pytest.mark.asyncio
    async def test_gds_disabled_env_var(self):
        """Se NEO4J_GDS_ENABLED=false, operações GDS retornam erro."""
        service = GraphAskService.__new__(GraphAskService)
        service._gds_available = None

        with patch("app.services.graph_ask_service._env_bool", return_value=False):
            result = await service._check_gds_available()
            assert result is False

    @pytest.mark.asyncio
    async def test_gds_enabled_but_not_installed(self):
        """Se GDS habilitado mas gds.version() falha, retorna False."""
        service = GraphAskService.__new__(GraphAskService)
        service._gds_available = None

        mock_neo4j = AsyncMock()
        mock_neo4j.execute_cypher = AsyncMock(side_effect=Exception("GDS not found"))

        with patch("app.services.graph_ask_service._env_bool", return_value=True):
            with patch.object(service, "_get_neo4j", return_value=mock_neo4j):
                result = await service._check_gds_available()
                assert result is False

    @pytest.mark.asyncio
    async def test_gds_enabled_and_installed(self):
        """Se GDS habilitado e gds.version() retorna versão, retorna True."""
        service = GraphAskService.__new__(GraphAskService)
        service._gds_available = None

        mock_neo4j = AsyncMock()
        mock_neo4j.execute_cypher = AsyncMock(return_value=[{"version": "2.5.0"}])

        with patch("app.services.graph_ask_service._env_bool", return_value=True):
            with patch.object(service, "_get_neo4j", return_value=mock_neo4j):
                result = await service._check_gds_available()
                assert result is True

    @pytest.mark.asyncio
    async def test_gds_check_cached(self):
        """GDS check é cacheado após primeira chamada."""
        service = GraphAskService.__new__(GraphAskService)
        service._gds_available = True  # Pré-definido

        # Não deve chamar Neo4j novamente
        result = await service._check_gds_available()
        assert result is True


# =============================================================================
# HANDLER SMOKE TESTS (com mocks)
# =============================================================================


class TestBetweennessCentralityHandler:
    """Testa handler de betweenness_centrality."""

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
                    "entity_type": "artigo",
                    "score": 0.85,
                }
            ]
        )

        with patch.object(service, "_get_neo4j", return_value=mock_neo4j):
            result = await service._handle_betweenness_centrality(
                {"limit": 10}, "tenant-123"
            )

        assert result.success is True
        assert result.operation == "betweenness_centrality"
        assert result.result_count == 1
        assert result.results[0]["entity_id"] == "art-5-cf"
        assert result.results[0]["score"] == 0.85


class TestCommunityDetectionHandler:
    """Testa handler de community_detection."""

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
                    "entity_type": "artigo",
                    "community_id": 1,
                }
            ]
        )

        with patch.object(service, "_get_neo4j", return_value=mock_neo4j):
            result = await service._handle_community_detection(
                {"limit": 10}, "tenant-123"
            )

        assert result.success is True
        assert result.operation == "community_detection"
        assert result.result_count == 1
        assert result.results[0]["community_id"] == 1


class TestNodeSimilarityHandler:
    """Testa handler de node_similarity."""

    @pytest.mark.asyncio
    async def test_handler_returns_similarity_scores(self):
        """Handler retorna pares com similaridade."""
        service = GraphAskService.__new__(GraphAskService)
        service._gds_available = True

        mock_neo4j = AsyncMock()
        mock_neo4j.execute_cypher = AsyncMock(
            return_value=[
                {
                    "node1_id": "art-5-cf",
                    "node2_id": "art-7-cf",
                    "similarity": 0.75,
                }
            ]
        )

        with patch.object(service, "_get_neo4j", return_value=mock_neo4j):
            result = await service._handle_node_similarity(
                {"top_k": 10, "limit": 20}, "tenant-123"
            )

        assert result.success is True
        assert result.operation == "node_similarity"
        assert result.result_count == 1
        assert result.results[0]["similarity"] == 0.75


class TestPagerankPersonalizedHandler:
    """Testa handler de pagerank_personalized."""

    @pytest.mark.asyncio
    async def test_handler_accepts_empty_source_ids(self):
        """Handler aceita source_ids vazio (retorna resultados vazios).

        Nota: Validação mais rigorosa poderia ser adicionada no futuro para
        retornar erro quando source_ids está vazio, já que PageRank personalizado
        sem sementes não faz sentido semântico.
        """
        service = GraphAskService.__new__(GraphAskService)
        service._gds_available = True

        mock_neo4j = AsyncMock()
        mock_neo4j.execute_cypher = AsyncMock(return_value=[])

        with patch.object(service, "_get_neo4j", return_value=mock_neo4j):
            # Sem source_ids → sucesso, mas sem resultados
            result = await service._handle_pagerank_personalized({}, "tenant-123")

        assert result.success is True
        assert result.result_count == 0

    @pytest.mark.asyncio
    async def test_handler_returns_pagerank_scores(self):
        """Handler retorna scores personalizados."""
        service = GraphAskService.__new__(GraphAskService)
        service._gds_available = True

        mock_neo4j = AsyncMock()
        mock_neo4j.execute_cypher = AsyncMock(
            return_value=[
                {
                    "entity_id": "art-37-cf",
                    "name": "Art. 37 CF",
                    "entity_type": "artigo",
                    "score": 0.92,
                }
            ]
        )

        with patch.object(service, "_get_neo4j", return_value=mock_neo4j):
            result = await service._handle_pagerank_personalized(
                {"source_ids": ["art-5-cf", "art-7-cf"], "limit": 10}, "tenant-123"
            )

        assert result.success is True
        assert result.operation == "pagerank_personalized"
        assert result.result_count == 1
        assert result.results[0]["score"] == 0.92


class TestWeaklyConnectedComponentsHandler:
    """Testa handler de weakly_connected_components."""

    @pytest.mark.asyncio
    async def test_handler_returns_components(self):
        """Handler retorna nós com component_id."""
        service = GraphAskService.__new__(GraphAskService)
        service._gds_available = True

        mock_neo4j = AsyncMock()
        mock_neo4j.execute_cypher = AsyncMock(
            return_value=[
                {
                    "entity_id": "art-100-cf",
                    "name": "Art. 100 CF",
                    "entity_type": "artigo",
                    "component_id": 5,
                }
            ]
        )

        with patch.object(service, "_get_neo4j", return_value=mock_neo4j):
            result = await service._handle_weakly_connected_components(
                {"limit": 10}, "tenant-123"
            )

        assert result.success is True
        assert result.operation == "weakly_connected_components"
        assert result.result_count == 1
        assert result.results[0]["component_id"] == 5


class TestShortestPathWeightedHandler:
    """Testa handler de shortest_path_weighted."""

    @pytest.mark.asyncio
    async def test_handler_requires_source_and_target(self):
        """Handler valida source_id e target_id."""
        service = GraphAskService.__new__(GraphAskService)
        service._gds_available = True

        # Sem source_id
        result = await service._handle_shortest_path_weighted(
            {"target_id": "art-2-cf"}, "tenant-123"
        )
        assert result.success is False
        assert "source_id e target_id são obrigatórios" in result.error

    @pytest.mark.asyncio
    async def test_handler_returns_weighted_path(self):
        """Handler retorna caminho com custo total."""
        service = GraphAskService.__new__(GraphAskService)
        service._gds_available = True

        mock_neo4j = AsyncMock()
        mock_neo4j.execute_cypher = AsyncMock(
            return_value=[
                {
                    "path": ["art-5-cf", "art-37-cf", "lei-14133"],
                    "total_cost": 2.5,
                }
            ]
        )

        with patch.object(service, "_get_neo4j", return_value=mock_neo4j):
            result = await service._handle_shortest_path_weighted(
                {
                    "source_id": "art-5-cf",
                    "target_id": "lei-14133",
                    "weight_property": "cooccurrence_count",
                },
                "tenant-123",
            )

        assert result.success is True
        assert result.operation == "shortest_path_weighted"
        assert result.result_count == 1
        assert result.results[0]["total_cost"] == 2.5


class TestTriangleCountHandler:
    """Testa handler de triangle_count."""

    @pytest.mark.asyncio
    async def test_handler_returns_triangle_counts(self):
        """Handler retorna nós com contagem de triângulos."""
        service = GraphAskService.__new__(GraphAskService)
        service._gds_available = True

        mock_neo4j = AsyncMock()
        mock_neo4j.execute_cypher = AsyncMock(
            return_value=[
                {
                    "entity_id": "art-5-cf",
                    "name": "Art. 5º CF",
                    "entity_type": "artigo",
                    "triangle_count": 12,
                }
            ]
        )

        with patch.object(service, "_get_neo4j", return_value=mock_neo4j):
            result = await service._handle_triangle_count({"limit": 10}, "tenant-123")

        assert result.success is True
        assert result.operation == "triangle_count"
        assert result.result_count == 1
        assert result.results[0]["triangle_count"] == 12


class TestDegreeCentralityHandler:
    """Testa handler de degree_centrality."""

    @pytest.mark.asyncio
    async def test_handler_returns_degree_counts(self):
        """Handler retorna nós com contagem de grau."""
        service = GraphAskService.__new__(GraphAskService)
        service._gds_available = True

        mock_neo4j = AsyncMock()
        mock_neo4j.execute_cypher = AsyncMock(
            return_value=[
                {
                    "entity_id": "sumula-vinculante-1",
                    "name": "Súmula Vinculante 1",
                    "entity_type": "sumula",
                    "degree": 48,
                }
            ]
        )

        with patch.object(service, "_get_neo4j", return_value=mock_neo4j):
            result = await service._handle_degree_centrality(
                {"direction": "INCOMING", "limit": 10}, "tenant-123"
            )

        assert result.success is True
        assert result.operation == "degree_centrality"
        assert result.result_count == 1
        assert result.results[0]["degree"] == 48


# =============================================================================
# INTEGRATION: ASK() DISPATCHER
# =============================================================================


class TestGDSDispatcher:
    """Testa que ask() dispatcher roteia corretamente para GDS handlers."""

    @pytest.mark.asyncio
    async def test_gds_disabled_blocks_operation(self):
        """Se GDS não disponível, ask() retorna erro antes de chamar handler."""
        service = GraphAskService.__new__(GraphAskService)
        service._gds_available = False

        with patch.object(service, "_check_gds_available", return_value=False):
            result = await service.ask(
                operation=GraphOperation.BETWEENNESS_CENTRALITY.value,
                params={"limit": 10},
                tenant_id="tenant-123",
            )

        assert result.success is False
        assert "GDS plugin não instalado" in result.error

    @pytest.mark.asyncio
    async def test_gds_enabled_routes_to_handler(self):
        """Se GDS disponível, ask() roteia para handler correto."""
        service = GraphAskService.__new__(GraphAskService)
        service._gds_available = True

        mock_handler = AsyncMock(
            return_value=MagicMock(
                success=True,
                operation="betweenness_centrality",
                results=[],
                result_count=0,
            )
        )

        with patch.object(service, "_check_gds_available", return_value=True):
            with patch.object(
                service, "_handle_betweenness_centrality", mock_handler
            ):
                result = await service.ask(
                    operation=GraphOperation.BETWEENNESS_CENTRALITY.value,
                    params={"limit": 10},
                    tenant_id="tenant-123",
                )

        assert result.success is True
        mock_handler.assert_called_once()
