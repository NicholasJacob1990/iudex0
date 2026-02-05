"""
Graph Ask Service — Consultas ao grafo via operações tipadas.

Este serviço implementa a abordagem segura de NL → Intent → Template Cypher,
evitando Cypher arbitrário e garantindo segurança multi-tenant.

Operações suportadas:
- path: Caminho mais curto entre duas entidades
- neighbors: Vizinhos semânticos de uma entidade
- cooccurrence: Co-ocorrência entre entidades em chunks
- search: Busca de entidades por nome/tipo
- count: Contagem de entidades/documentos

Todas as operações aplicam filtros de tenant_id/scope automaticamente.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from loguru import logger


class GraphOperation(str, Enum):
    """Operações suportadas pelo Graph Ask."""
    PATH = "path"
    NEIGHBORS = "neighbors"
    COOCCURRENCE = "cooccurrence"
    SEARCH = "search"
    COUNT = "count"


@dataclass
class GraphAskResult:
    """Resultado de uma consulta ao grafo."""
    success: bool
    operation: str
    results: List[Dict[str, Any]]
    result_count: int
    execution_time_ms: int
    cypher_template: Optional[str] = None  # Para debug (admin only)
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        d = {
            "success": self.success,
            "operation": self.operation,
            "results": self.results,
            "result_count": self.result_count,
            "execution_time_ms": self.execution_time_ms,
        }
        if self.error:
            d["error"] = self.error
        if self.cypher_template:
            d["cypher_template"] = self.cypher_template
        if self.metadata:
            d["metadata"] = self.metadata
        return d


# =============================================================================
# CYPHER TEMPLATES — Seguros e com placeholders para tenant_id
# =============================================================================

_MAX_HOPS_TOKEN = "__MAX_HOPS__"

_PATH_QUERY_TEMPLATE = f"""
    MATCH (source:Entity {{entity_id: $source_id}})
    MATCH (target:Entity {{entity_id: $target_id}})
    MATCH path = shortestPath((source)-[:MENTIONS|RELATED_TO|ASSERTS|REFERS_TO*1..{_MAX_HOPS_TOKEN}]-(target))
    WHERE all(n IN nodes(path) WHERE NOT n:Chunk OR exists {{
        MATCH (d:Document)-[:HAS_CHUNK]->(n)
        WHERE (d.tenant_id = $tenant_id OR ($include_global = true AND d.scope = 'global'))
          AND (d.sigilo IS NULL OR d.sigilo = false)
          AND ($case_id IS NOT NULL OR d.scope <> 'local')
          AND ($scope IS NULL OR d.scope = $scope)
          AND ($case_id IS NULL OR d.case_id = $case_id)
    }})
    RETURN
        [n IN nodes(path) | coalesce(n.name, n.entity_id, n.chunk_uid, n.doc_hash)] AS path,
        [n IN nodes(path) | coalesce(n.entity_id, n.chunk_uid, n.doc_hash)] AS path_ids,
        [r IN relationships(path) | type(r)] AS relationships,
        length(path) AS hops
    LIMIT $limit
"""

CYPHER_TEMPLATES = {
    # -------------------------------------------------------------------------
    # PATH: Caminho mais curto entre duas entidades
    # -------------------------------------------------------------------------
    # NOTE: relationship length can't be parameterized in Cypher; we sanitize and inject it.
    "path": _PATH_QUERY_TEMPLATE,

    # -------------------------------------------------------------------------
    # NEIGHBORS: Vizinhos semânticos (via co-ocorrência em chunks)
    # -------------------------------------------------------------------------
    "neighbors": """
        MATCH (e:Entity {entity_id: $entity_id})<-[:MENTIONS]-(c:Chunk)-[:MENTIONS]->(neighbor:Entity)
        MATCH (d:Document)-[:HAS_CHUNK]->(c)
        WHERE neighbor.entity_id <> $entity_id
          AND (d.tenant_id = $tenant_id OR ($include_global = true AND d.scope = 'global'))
          AND (d.sigilo IS NULL OR d.sigilo = false)
          AND ($case_id IS NOT NULL OR d.scope <> 'local')
          AND ($scope IS NULL OR d.scope = $scope)
          AND ($case_id IS NULL OR d.case_id = $case_id)
        WITH neighbor, count(DISTINCT c) AS co_occurrences,
             collect(DISTINCT left(c.text_preview, 150))[0..3] AS sample_contexts
        RETURN
            neighbor.entity_id AS entity_id,
            neighbor.name AS name,
            neighbor.entity_type AS type,
            co_occurrences,
            sample_contexts
        ORDER BY co_occurrences DESC
        LIMIT $limit
    """,

    # -------------------------------------------------------------------------
    # COOCCURRENCE: Co-ocorrência entre duas entidades específicas
    # -------------------------------------------------------------------------
    "cooccurrence": """
        MATCH (e1:Entity {entity_id: $entity1_id})<-[:MENTIONS]-(c:Chunk)-[:MENTIONS]->(e2:Entity {entity_id: $entity2_id})
        MATCH (d:Document)-[:HAS_CHUNK]->(c)
        WHERE (d.tenant_id = $tenant_id OR ($include_global = true AND d.scope = 'global'))
          AND (d.sigilo IS NULL OR d.sigilo = false)
          AND ($case_id IS NOT NULL OR d.scope <> 'local')
          AND ($scope IS NULL OR d.scope = $scope)
          AND ($case_id IS NULL OR d.case_id = $case_id)
        WITH c, d, e1, e2
        RETURN
            e1.name AS entity1_name,
            e2.name AS entity2_name,
            count(DISTINCT c) AS co_occurrence_count,
            collect(DISTINCT d.title)[0..5] AS documents,
            collect(DISTINCT left(c.text_preview, 200))[0..3] AS sample_contexts
        LIMIT 1
    """,

    # -------------------------------------------------------------------------
    # SEARCH: Busca entidades por nome (com filtro de tipo opcional)
    # -------------------------------------------------------------------------
    "search": """
        MATCH (e:Entity)
        WHERE (toLower(e.name) CONTAINS toLower($query) OR toLower(e.normalized) CONTAINS toLower($query))
          AND ($entity_type IS NULL OR e.entity_type = $entity_type)
        OPTIONAL MATCH (e)<-[:MENTIONS]-(c:Chunk)<-[:HAS_CHUNK]-(d:Document)
        WHERE (d.tenant_id = $tenant_id OR ($include_global = true AND d.scope = 'global'))
          AND (d.sigilo IS NULL OR d.sigilo = false)
          AND ($case_id IS NOT NULL OR d.scope <> 'local')
          AND ($scope IS NULL OR d.scope = $scope)
          AND ($case_id IS NULL OR d.case_id = $case_id)
        WITH e, count(DISTINCT c) AS mention_count
        WHERE mention_count > 0
        RETURN
            e.entity_id AS entity_id,
            e.name AS name,
            e.entity_type AS type,
            e.normalized AS normalized,
            mention_count
        ORDER BY mention_count DESC
        LIMIT $limit
    """,

    # -------------------------------------------------------------------------
    # COUNT: Contagem de entidades/documentos com filtros
    # -------------------------------------------------------------------------
    "count": """
        MATCH (e:Entity)
        WHERE ($entity_type IS NULL OR e.entity_type = $entity_type)
          AND ($query IS NULL OR toLower(e.name) CONTAINS toLower($query))
        OPTIONAL MATCH (e)<-[:MENTIONS]-(c:Chunk)<-[:HAS_CHUNK]-(d:Document)
        WHERE (d.tenant_id = $tenant_id OR ($include_global = true AND d.scope = 'global'))
          AND (d.sigilo IS NULL OR d.sigilo = false)
          AND ($case_id IS NOT NULL OR d.scope <> 'local')
          AND ($scope IS NULL OR d.scope = $scope)
          AND ($case_id IS NULL OR d.case_id = $case_id)
        WITH e, count(DISTINCT d) AS doc_count
        WHERE doc_count > 0
        RETURN
            count(DISTINCT e) AS entity_count,
            sum(doc_count) AS total_document_references
    """,
}


class GraphAskService:
    """
    Serviço para consultas seguras ao grafo Neo4j.

    Usa templates Cypher pré-definidos com parâmetros tipados,
    garantindo segurança multi-tenant e evitando injection.
    """

    def __init__(self):
        """Inicializa o serviço."""
        self._neo4j = None

    async def _get_neo4j(self):
        """Obtém instância do Neo4j service (lazy loading)."""
        if self._neo4j is None:
            try:
                from app.services.rag.core.neo4j_mvp import get_neo4j_mvp
                self._neo4j = get_neo4j_mvp()
            except Exception as e:
                logger.error(f"Failed to get Neo4j service: {e}")
                raise RuntimeError("Neo4j service not available")
        return self._neo4j

    async def ask(
        self,
        operation: Union[str, GraphOperation],
        params: Dict[str, Any],
        tenant_id: str,
        scope: Optional[str] = None,
        case_id: Optional[str] = None,
        include_global: bool = True,
        show_template: bool = False,
        timeout_ms: int = 5000,
    ) -> GraphAskResult:
        """
        Executa uma consulta tipada ao grafo.

        Args:
            operation: Operação a executar (path, neighbors, cooccurrence, search, count)
            params: Parâmetros específicos da operação
            tenant_id: ID do tenant para filtro de segurança
            scope: Escopo opcional (global, private, group, local)
            case_id: ID do caso opcional
            show_template: Se True, inclui template Cypher no resultado (admin only)
            timeout_ms: Timeout em milissegundos

        Returns:
            GraphAskResult com resultados ou erro
        """
        start_time = time.time()

        normalized_scope = (scope or "").strip().lower() or None
        if normalized_scope == "group":
            return GraphAskResult(
                success=False,
                operation=str(operation),
                results=[],
                result_count=0,
                execution_time_ms=0,
                error="Escopo 'group' não suportado nesta versão do GraphAsk (evita bypass de RBAC).",
            )
        if normalized_scope == "local" and not case_id:
            return GraphAskResult(
                success=False,
                operation=str(operation),
                results=[],
                result_count=0,
                execution_time_ms=0,
                error="Escopo 'local' requer case_id.",
            )

        # Normalizar operação
        if isinstance(operation, str):
            try:
                operation = GraphOperation(operation.lower())
            except ValueError:
                return GraphAskResult(
                    success=False,
                    operation=operation,
                    results=[],
                    result_count=0,
                    execution_time_ms=0,
                    error=f"Operação inválida: {operation}. Válidas: {[o.value for o in GraphOperation]}"
                )

        # Obter template
        template = CYPHER_TEMPLATES.get(operation.value)
        if not template:
            return GraphAskResult(
                success=False,
                operation=operation.value,
                results=[],
                result_count=0,
                execution_time_ms=0,
                error=f"Template não encontrado para operação: {operation.value}"
            )

        # Validar parâmetros obrigatórios por operação
        validation_error = self._validate_params(operation, params)
        if validation_error:
            return GraphAskResult(
                success=False,
                operation=operation.value,
                results=[],
                result_count=0,
                execution_time_ms=0,
                error=validation_error
            )

        # Preparar parâmetros com defaults e segurança
        cypher_params = self._prepare_params(
            operation=operation,
            params=params,
            tenant_id=tenant_id,
            scope=normalized_scope,
            case_id=case_id,
            include_global=include_global,
        )
        query_text = self._build_query_text(operation, template, cypher_params)

        try:
            # Executar query
            neo4j = await self._get_neo4j()

            # Usar método de execução do Neo4j MVP
            results = await self._execute_query(neo4j, query_text, cypher_params, timeout_ms)

            execution_time = int((time.time() - start_time) * 1000)

            return GraphAskResult(
                success=True,
                operation=operation.value,
                results=results,
                result_count=len(results),
                execution_time_ms=execution_time,
                cypher_template=template.strip() if show_template else None,
                metadata={"params_used": list(cypher_params.keys())}
            )

        except Exception as e:
            logger.error(f"GraphAskService.ask failed: {e}")
            execution_time = int((time.time() - start_time) * 1000)
            return GraphAskResult(
                success=False,
                operation=operation.value,
                results=[],
                result_count=0,
                execution_time_ms=execution_time,
                error=str(e)
            )

    def _validate_params(self, operation: GraphOperation, params: Dict[str, Any]) -> Optional[str]:
        """Valida parâmetros obrigatórios por operação."""
        required = {
            GraphOperation.PATH: ["source_id", "target_id"],
            GraphOperation.NEIGHBORS: ["entity_id"],
            GraphOperation.COOCCURRENCE: ["entity1_id", "entity2_id"],
            GraphOperation.SEARCH: ["query"],
            GraphOperation.COUNT: [],  # Todos opcionais
        }

        missing = [p for p in required.get(operation, []) if p not in params or not params[p]]
        if missing:
            return f"Parâmetros obrigatórios faltando: {missing}"

        return None

    def _prepare_params(
        self,
        operation: GraphOperation,
        params: Dict[str, Any],
        tenant_id: str,
        scope: Optional[str],
        case_id: Optional[str],
        include_global: bool,
    ) -> Dict[str, Any]:
        """Prepara parâmetros com defaults e filtros de segurança."""

        # Base: sempre inclui tenant_id e scope
        cypher_params = {
            "tenant_id": tenant_id,
            "scope": scope,
            "case_id": case_id,
            "include_global": bool(include_global),
        }

        # Defaults por operação
        defaults = {
            GraphOperation.PATH: {"max_hops": 4, "limit": 5},
            GraphOperation.NEIGHBORS: {"limit": 20},
            GraphOperation.COOCCURRENCE: {},
            GraphOperation.SEARCH: {"limit": 30, "entity_type": None},
            GraphOperation.COUNT: {"entity_type": None, "query": None},
        }

        # Aplicar defaults
        for key, value in defaults.get(operation, {}).items():
            if key not in params:
                cypher_params[key] = value

        # Copiar parâmetros do usuário (com sanitização básica)
        for key, value in params.items():
            if isinstance(value, str):
                # Limitar tamanho de strings para evitar abuse
                cypher_params[key] = value[:500]
            elif isinstance(value, (int, float)):
                # Limitar valores numéricos
                if key == "limit":
                    cypher_params[key] = min(int(value), 100)
                elif key == "max_hops":
                    cypher_params[key] = min(int(value), 6)
                else:
                    cypher_params[key] = value
            else:
                cypher_params[key] = value

        return cypher_params

    def _build_query_text(
        self,
        operation: GraphOperation,
        template: str,
        params: Dict[str, Any],
    ) -> str:
        """
        Build final query text for a given operation.

        Some Cypher fragments can't be parameterized (e.g., relationship-length ranges),
        so we inject sanitized integers.
        """
        if operation == GraphOperation.PATH:
            hops_raw = params.get("max_hops", 4)
            try:
                hops = int(hops_raw)
            except (TypeError, ValueError):
                hops = 4
            hops = max(1, min(hops, 6))
            return template.replace(_MAX_HOPS_TOKEN, str(hops))
        return template

    async def _execute_query(
        self,
        neo4j,
        query_text: str,
        params: Dict[str, Any],
        timeout_ms: int,
    ) -> List[Dict[str, Any]]:
        """Executa query no Neo4j com timeout."""
        import asyncio

        def run_sync():
            # Prefer the service's own read helper (handles DB fallback and driver resets).
            return neo4j._execute_read(query_text, params)

        # Executar com timeout
        try:
            loop = asyncio.get_running_loop()
            results = await asyncio.wait_for(
                loop.run_in_executor(None, run_sync),
                timeout=timeout_ms / 1000.0
            )
            return results
        except asyncio.TimeoutError:
            raise TimeoutError(f"Query excedeu timeout de {timeout_ms}ms")

    # =========================================================================
    # CONVENIENCE METHODS - Atalhos para operações comuns
    # =========================================================================

    async def find_path(
        self,
        source_id: str,
        target_id: str,
        tenant_id: str,
        max_hops: int = 4,
        scope: Optional[str] = None,
        case_id: Optional[str] = None,
        include_global: bool = True,
    ) -> GraphAskResult:
        """Encontra caminho entre duas entidades."""
        return await self.ask(
            operation=GraphOperation.PATH,
            params={"source_id": source_id, "target_id": target_id, "max_hops": max_hops},
            tenant_id=tenant_id,
            scope=scope,
            case_id=case_id,
            include_global=include_global,
        )

    async def get_neighbors(
        self,
        entity_id: str,
        tenant_id: str,
        limit: int = 20,
        scope: Optional[str] = None,
        case_id: Optional[str] = None,
        include_global: bool = True,
    ) -> GraphAskResult:
        """Obtém vizinhos semânticos de uma entidade."""
        return await self.ask(
            operation=GraphOperation.NEIGHBORS,
            params={"entity_id": entity_id, "limit": limit},
            tenant_id=tenant_id,
            scope=scope,
            case_id=case_id,
            include_global=include_global,
        )

    async def find_cooccurrence(
        self,
        entity1_id: str,
        entity2_id: str,
        tenant_id: str,
        scope: Optional[str] = None,
        case_id: Optional[str] = None,
        include_global: bool = True,
    ) -> GraphAskResult:
        """Encontra co-ocorrências entre duas entidades."""
        return await self.ask(
            operation=GraphOperation.COOCCURRENCE,
            params={"entity1_id": entity1_id, "entity2_id": entity2_id},
            tenant_id=tenant_id,
            scope=scope,
            case_id=case_id,
            include_global=include_global,
        )

    async def search_entities(
        self,
        query: str,
        tenant_id: str,
        entity_type: Optional[str] = None,
        limit: int = 30,
        scope: Optional[str] = None,
        case_id: Optional[str] = None,
        include_global: bool = True,
    ) -> GraphAskResult:
        """Busca entidades por nome."""
        return await self.ask(
            operation=GraphOperation.SEARCH,
            params={"query": query, "entity_type": entity_type, "limit": limit},
            tenant_id=tenant_id,
            scope=scope,
            case_id=case_id,
            include_global=include_global,
        )

    async def count_entities(
        self,
        tenant_id: str,
        entity_type: Optional[str] = None,
        query: Optional[str] = None,
        scope: Optional[str] = None,
        case_id: Optional[str] = None,
        include_global: bool = True,
    ) -> GraphAskResult:
        """Conta entidades com filtros."""
        return await self.ask(
            operation=GraphOperation.COUNT,
            params={"entity_type": entity_type, "query": query},
            tenant_id=tenant_id,
            scope=scope,
            case_id=case_id,
            include_global=include_global,
        )


# =============================================================================
# SINGLETON
# =============================================================================

_graph_ask_service: Optional[GraphAskService] = None


def get_graph_ask_service() -> GraphAskService:
    """Obtém instância singleton do GraphAskService."""
    global _graph_ask_service
    if _graph_ask_service is None:
        _graph_ask_service = GraphAskService()
    return _graph_ask_service
