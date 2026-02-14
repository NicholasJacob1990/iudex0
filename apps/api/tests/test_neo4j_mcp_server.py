"""
Tests for Neo4j MCP Server — exposes graph queries as MCP tools.

Mocks GraphAskService to test without Neo4j.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass
from typing import List, Dict, Any, Optional


@dataclass
class MockGraphAskResult:
    """Mock GraphAskResult for testing."""
    success: bool = True
    results: Optional[List[Dict[str, Any]]] = None
    result_count: int = 0
    execution_time_ms: float = 10.0
    error: Optional[str] = None


class TestNeo4jMCPServer:
    """Tests for Neo4jMCPServer."""

    @pytest.fixture
    def server(self):
        from app.services.mcp_servers.neo4j_server import Neo4jMCPServer
        return Neo4jMCPServer()

    def test_tools_defined(self, server):
        """Test that all tools are defined."""
        assert len(server.tools) == 11
        names = {t["name"] for t in server.tools}
        assert names == {
            "neo4j_entity_search",
            "neo4j_entity_neighbors",
            "neo4j_path_find",
            "neo4j_graph_stats",
            "neo4j_ranking",
            "neo4j_semantic_chain",
            "neo4j_precedent_network",
            "neo4j_judge_decisions",
            "neo4j_fraud_signals",
            "neo4j_process_network",
            "neo4j_process_timeline",
        }

    def test_tools_have_input_schema(self, server):
        """Test that each tool has a valid inputSchema."""
        for tool in server.tools:
            assert "inputSchema" in tool
            assert tool["inputSchema"]["type"] == "object"
            assert "properties" in tool["inputSchema"]

    @pytest.mark.asyncio
    async def test_initialize_method(self, server):
        """Test initialize returns server info."""
        result = await server.handle_request("initialize")
        assert "serverInfo" in result
        assert result["serverInfo"]["name"] == "neo4j-graph-mcp-server"

    @pytest.mark.asyncio
    async def test_ping_method(self, server):
        """Test ping returns server info."""
        result = await server.handle_request("ping")
        assert "serverInfo" in result

    @pytest.mark.asyncio
    async def test_tools_list(self, server):
        """Test tools/list returns all tools."""
        result = await server.handle_request("tools/list")
        assert "tools" in result
        assert len(result["tools"]) == 11

    @pytest.mark.asyncio
    async def test_tools_list_dot_notation(self, server):
        """Test tools.list (dot notation) also works."""
        result = await server.handle_request("tools.list")
        assert "tools" in result

    @pytest.mark.asyncio
    async def test_unknown_method(self, server):
        """Test unknown method returns error."""
        result = await server.handle_request("unknown/method")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_call_entity_search(self, server):
        """Test tools/call routes to entity search."""
        mock_ask = MockGraphAskResult(
            success=True,
            results=[
                {"name": "Lei 8.666", "type": "lei", "entity_id": "lei_8666"},
            ],
            result_count=1,
        )
        mock_service = AsyncMock()
        mock_service.ask.return_value = mock_ask

        server._graph_ask = mock_service

        result = await server.handle_request("tools/call", {
            "name": "neo4j_entity_search",
            "arguments": {"query": "Lei 8.666"},
        })

        assert "content" in result
        assert not result.get("isError")
        mock_service.ask.assert_called_once()
        call_kwargs = mock_service.ask.call_args
        assert call_kwargs.kwargs["operation"] == "search"

    @pytest.mark.asyncio
    async def test_call_unknown_tool(self, server):
        """Test calling unknown tool returns error."""
        mock_service = AsyncMock()
        server._graph_ask = mock_service

        result = await server.handle_request("tools/call", {
            "name": "nonexistent_tool",
            "arguments": {},
        })

        assert result.get("isError") is True
        assert "not found" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_call_tool_error_handling(self, server):
        """Test that tool errors are caught and returned."""
        mock_service = AsyncMock()
        mock_service.ask.side_effect = Exception("Connection refused")
        server._graph_ask = mock_service

        result = await server.handle_request("tools/call", {
            "name": "neo4j_graph_stats",
            "arguments": {},
        })

        assert result.get("isError") is True
        assert "Connection refused" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_operation_mapping(self, server):
        """Test that all tool names map to correct operations."""
        expected = {
            "neo4j_entity_search": "search",
            "neo4j_entity_neighbors": "neighbors",
            "neo4j_path_find": "path",
            "neo4j_graph_stats": "count",
            "neo4j_ranking": "ranking",
            "neo4j_semantic_chain": "legal_chain",
            "neo4j_precedent_network": "precedent_network",
            "neo4j_judge_decisions": "judge_decisions",
            "neo4j_fraud_signals": "fraud_signals",
            "neo4j_process_network": "process_network",
            "neo4j_process_timeline": "process_timeline",
        }
        mock_service = AsyncMock()
        mock_service.ask.return_value = MockGraphAskResult(
            success=True, results=[], result_count=0,
        )
        server._graph_ask = mock_service

        for tool_name, expected_op in expected.items():
            await server.handle_request("tools/call", {
                "name": tool_name,
                "arguments": {"query": "test"},
            })
            actual_op = mock_service.ask.call_args.kwargs["operation"]
            assert actual_op == expected_op, f"{tool_name} → expected {expected_op}, got {actual_op}"


class TestFormatResult:
    """Tests for result formatting."""

    @pytest.fixture
    def server(self):
        from app.services.mcp_servers.neo4j_server import Neo4jMCPServer
        return Neo4jMCPServer()

    def test_format_success(self, server):
        result = MockGraphAskResult(
            success=True,
            results=[
                {"name": "Lei 8.666", "type": "lei", "pagerank_score": 0.85},
            ],
            result_count=1,
        )
        text = server._format_result(result)
        assert "Lei 8.666" in text
        assert "(lei)" in text

    def test_format_empty(self, server):
        result = MockGraphAskResult(success=True, results=[], result_count=0)
        text = server._format_result(result)
        assert "Nenhum resultado" in text

    def test_format_error(self, server):
        result = MockGraphAskResult(success=False, error="Query failed")
        text = server._format_result(result)
        assert "Erro" in text
        assert "Query failed" in text

    def test_format_with_contexts(self, server):
        result = MockGraphAskResult(
            success=True,
            results=[
                {
                    "name": "Art. 5",
                    "type": "artigo",
                    "sample_contexts": ["O artigo 5 da CF garante direitos fundamentais..."],
                },
            ],
            result_count=1,
        )
        text = server._format_result(result)
        assert "Contexto" in text


class TestMCPConfig:
    """Test that Neo4j MCP server is registered in config."""

    def test_registered_in_builtin_servers(self):
        from app.services.mcp_config import BUILTIN_MCP_SERVERS
        labels = [s["label"] for s in BUILTIN_MCP_SERVERS]
        assert "neo4j-graph" in labels

    def test_handler_class_path(self):
        from app.services.mcp_config import BUILTIN_MCP_SERVERS
        neo4j_entry = next(s for s in BUILTIN_MCP_SERVERS if s["label"] == "neo4j-graph")
        assert neo4j_entry["handler_class"] == "app.services.mcp_servers.neo4j_server.Neo4jMCPServer"
        assert neo4j_entry["builtin"] is True

    def test_load_builtin_includes_neo4j(self):
        from app.services.mcp_config import load_builtin_mcp_servers
        servers = load_builtin_mcp_servers()
        labels = [s.label for s in servers]
        assert "neo4j-graph" in labels
