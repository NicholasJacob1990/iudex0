"""
Neo4j Graph MCP Server — Exposes Neo4j graph queries as MCP tools.

Allows AI agents to query the legal knowledge graph via function calling.
Follows the same pattern as BNPMCPServer.

Tools exposed:
  - neo4j_entity_search: Search entities by name/type
  - neo4j_entity_neighbors: Find related entities
  - neo4j_path_find: Shortest path between entities
  - neo4j_graph_stats: Graph statistics
  - neo4j_ranking: Top entities by PageRank
  - neo4j_semantic_chain: Multi-hop semantic chain between legal devices
  - neo4j_precedent_network: Precedent network that influences a decision
  - neo4j_judge_decisions: Decisions linked to a judge/ministro
  - neo4j_fraud_signals: Suspicious org/empresa/process connections
  - neo4j_process_network: Process relationship network
  - neo4j_process_timeline: Process timeline/events
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class Neo4jMCPServer:
    """
    MCP Server that exposes Neo4j graph query tools via JSON-RPC.
    Used as a built-in MCP server within Iudex.
    """

    def __init__(self) -> None:
        self._graph_ask = None
        self.tools = self._define_tools()

    def _get_graph_ask(self):
        """Lazy-load GraphAskService."""
        if self._graph_ask is None:
            from app.services.graph_ask_service import GraphAskService
            self._graph_ask = GraphAskService()
        return self._graph_ask

    def _define_tools(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "neo4j_entity_search",
                "description": (
                    "Busca entidades jurídicas no grafo de conhecimento por nome ou tipo. "
                    "Entidades incluem: Lei, Artigo, Sumula, Tribunal, Processo, Tema, etc."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Texto de busca (nome ou parte do nome da entidade)",
                        },
                        "entity_type": {
                            "type": "string",
                            "description": "Filtrar por tipo (lei, artigo, sumula, tribunal, processo, tema)",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Máximo de resultados (default: 10)",
                        },
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "neo4j_entity_neighbors",
                "description": (
                    "Encontra entidades vizinhas/relacionadas a uma entidade específica. "
                    "Útil para descobrir co-ocorrências (quais leis/artigos aparecem juntos)."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "entity_id": {
                            "type": "string",
                            "description": "ID da entidade (retornado por neo4j_entity_search)",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Máximo de vizinhos (default: 10)",
                        },
                    },
                    "required": ["entity_id"],
                },
            },
            {
                "name": "neo4j_path_find",
                "description": (
                    "Encontra o caminho mais curto entre duas entidades no grafo. "
                    "Mostra como duas entidades se conectam via citações e co-ocorrências."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "source_id": {
                            "type": "string",
                            "description": "ID da entidade de origem",
                        },
                        "target_id": {
                            "type": "string",
                            "description": "ID da entidade de destino",
                        },
                    },
                    "required": ["source_id", "target_id"],
                },
            },
            {
                "name": "neo4j_graph_stats",
                "description": (
                    "Retorna estatísticas do grafo de conhecimento: "
                    "contagem de entidades, documentos, relacionamentos."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "entity_type": {
                            "type": "string",
                            "description": "Filtrar contagem por tipo (opcional)",
                        },
                    },
                },
            },
            {
                "name": "neo4j_ranking",
                "description": (
                    "Retorna as entidades mais importantes por PageRank. "
                    "Entidades mais citadas/referenciadas têm maior score."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "entity_type": {
                            "type": "string",
                            "description": "Filtrar por tipo (lei, artigo, sumula, etc.)",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Máximo de resultados (default: 10)",
                        },
                    },
                },
            },
            {
                "name": "neo4j_semantic_chain",
                "description": (
                    "Encontra cadeia semântica multi-hop entre dispositivos legais "
                    "(ex.: art. X -> súmula Y -> tese Z)."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "source_id": {"type": "string", "description": "Entity ID de origem"},
                        "target_id": {"type": "string", "description": "Entity ID de destino (opcional)"},
                        "relation_types": {
                            "description": "Lista ou string CSV de tipos de relação (opcional)",
                            "oneOf": [{"type": "array", "items": {"type": "string"}}, {"type": "string"}],
                        },
                        "max_hops": {"type": "integer", "description": "Máximo de hops (default: 4)"},
                        "limit": {"type": "integer", "description": "Máximo de caminhos (default: 20)"},
                    },
                    "required": ["source_id"],
                },
            },
            {
                "name": "neo4j_precedent_network",
                "description": (
                    "Retorna a rede de precedentes e citações que influencia uma decisão."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "decision_id": {"type": "string", "description": "Entity ID da decisão alvo"},
                        "max_hops": {"type": "integer", "description": "Profundidade máxima (default: 4)"},
                        "limit": {"type": "integer", "description": "Máximo de resultados (default: 20)"},
                    },
                    "required": ["decision_id"],
                },
            },
            {
                "name": "neo4j_judge_decisions",
                "description": (
                    "Busca decisões relacionadas a um mesmo juiz/ministro."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "judge_query": {"type": "string", "description": "Nome parcial do juiz/ministro"},
                        "decision_type": {"type": "string", "description": "Tipo de decisão (opcional)"},
                        "limit": {"type": "integer", "description": "Máximo de resultados (default: 20)"},
                    },
                    "required": ["judge_query"],
                },
            },
            {
                "name": "neo4j_fraud_signals",
                "description": (
                    "Detecta sinais de risco em conexões entre órgãos, empresas e processos."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "min_shared_docs": {
                            "type": "integer",
                            "description": "Mínimo de documentos compartilhados para sinalizar risco",
                        },
                        "limit": {"type": "integer", "description": "Máximo de sinais (default: 20)"},
                    },
                },
            },
            {
                "name": "neo4j_process_network",
                "description": (
                    "Retorna a rede de relacionamentos multi-hop conectada a um processo."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "process_id": {"type": "string", "description": "Entity ID do processo"},
                        "max_hops": {"type": "integer", "description": "Máximo de hops (default: 4)"},
                        "limit": {"type": "integer", "description": "Máximo de nós/resultados (default: 20)"},
                    },
                    "required": ["process_id"],
                },
            },
            {
                "name": "neo4j_process_timeline",
                "description": (
                    "Retorna timeline de documentos/eventos ligados a um processo."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "process_id": {"type": "string", "description": "Entity ID do processo"},
                        "limit": {"type": "integer", "description": "Máximo de eventos (default: 30)"},
                    },
                    "required": ["process_id"],
                },
            },
        ]

    async def handle_request(
        self, method: str, params: Optional[dict] = None
    ) -> dict:
        """Handle JSON-RPC request."""
        if method in ("initialize", "ping"):
            return {
                "serverInfo": {
                    "name": "neo4j-graph-mcp-server",
                    "version": "1.0.0",
                    "description": "Neo4j Legal Knowledge Graph MCP Server",
                },
                "capabilities": {"tools": {}},
            }

        if method in ("tools/list", "tools.list"):
            return {"tools": self.tools}

        if method in ("tools/call", "tools.call"):
            tool_name = (params or {}).get("name", "")
            arguments = (params or {}).get("arguments", {})
            return await self._call_tool(tool_name, arguments)

        return {"error": {"code": -32601, "message": f"Method not found: {method}"}}

    async def _call_tool(self, name: str, args: dict) -> dict:
        """Execute a tool and return results."""
        # Extract tenant_id from args or use default
        tenant_id = args.pop("tenant_id", args.pop("_tenant_id", "default"))
        scope = args.pop("scope", None)
        case_id = args.pop("case_id", None)

        try:
            graph_ask = self._get_graph_ask()

            operation_map = {
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

            operation = operation_map.get(name)
            if not operation:
                return {
                    "content": [{"type": "text", "text": f"Tool not found: {name}"}],
                    "isError": True,
                }

            result = await graph_ask.ask(
                operation=operation,
                params=args,
                tenant_id=tenant_id,
                scope=scope,
                case_id=case_id,
                include_global=True,
            )

            formatted = self._format_result(result)
            return {"content": [{"type": "text", "text": formatted}]}

        except Exception as e:
            logger.error("[Neo4j MCP] Tool %s error: %s", name, e)
            return {
                "content": [{"type": "text", "text": f"Error: {str(e)}"}],
                "isError": True,
            }

    def _format_result(self, result) -> str:
        """Format GraphAskResult into readable text."""
        if not result.success:
            return f"Erro: {result.error}"

        if not result.results:
            return "Nenhum resultado encontrado."

        lines = [f"### Resultados ({result.result_count} encontrados, {result.execution_time_ms}ms)\n"]

        for i, item in enumerate(result.results[:20]):
            if isinstance(item, dict):
                name = item.get("name", item.get("entity_id", f"#{i+1}"))
                entity_type = item.get("type", "")
                score = item.get("pagerank_score") or item.get("co_occurrences") or ""

                line = f"**{i+1}. {name}**"
                if entity_type:
                    line += f" ({entity_type})"
                if score:
                    line += f" — score: {score}"
                lines.append(line)

                # Add context if available
                contexts = item.get("sample_contexts", [])
                if contexts:
                    lines.append(f"   Contexto: {contexts[0][:150]}")
                lines.append("")
            else:
                lines.append(f"- {str(item)[:200]}")

        return "\n".join(lines)
