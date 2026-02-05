"""
Graph Ask API Endpoints — Consultas ao grafo via operações tipadas.

Endpoint seguro para consultas ao knowledge graph usando operações pré-definidas
em vez de Cypher arbitrário. Todas as operações aplicam filtros de tenant
automaticamente.

Operações:
- path: Caminho entre entidades
- neighbors: Vizinhos semânticos
- cooccurrence: Co-ocorrência em documentos
- search: Busca de entidades
- count: Contagem com filtros
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Literal, Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.security import get_org_context, OrgContext
from app.models.user import UserRole
from app.services.graph_ask_service import (
    get_graph_ask_service,
    GraphAskService,
    GraphOperation,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# SCHEMAS
# =============================================================================


class PathRequest(BaseModel):
    """Request para operação PATH."""
    source_id: str = Field(..., description="Entity ID de origem")
    target_id: str = Field(..., description="Entity ID de destino")
    max_hops: int = Field(4, ge=1, le=6, description="Máximo de hops no caminho")


class NeighborsRequest(BaseModel):
    """Request para operação NEIGHBORS."""
    entity_id: str = Field(..., description="Entity ID para buscar vizinhos")
    limit: int = Field(20, ge=1, le=100, description="Número máximo de vizinhos")


class CooccurrenceRequest(BaseModel):
    """Request para operação COOCCURRENCE."""
    entity1_id: str = Field(..., description="Primeiro entity ID")
    entity2_id: str = Field(..., description="Segundo entity ID")


class SearchRequest(BaseModel):
    """Request para operação SEARCH."""
    query: str = Field(..., min_length=1, max_length=200, description="Termo de busca")
    entity_type: Optional[str] = Field(
        None,
        description="Filtrar por tipo: lei, artigo, sumula, tema, tribunal, tese, conceito"
    )
    limit: int = Field(30, ge=1, le=100, description="Número máximo de resultados")


class CountRequest(BaseModel):
    """Request para operação COUNT."""
    entity_type: Optional[str] = Field(None, description="Filtrar por tipo de entidade")
    query: Optional[str] = Field(None, max_length=200, description="Filtrar por nome")


class GraphAskRequest(BaseModel):
    """
    Request unificado para qualquer operação.

    Use este schema quando quiser especificar a operação dinamicamente.
    """
    operation: Literal["path", "neighbors", "cooccurrence", "search", "count"] = Field(
        ..., description="Operação a executar"
    )
    params: Dict[str, Any] = Field(..., description="Parâmetros da operação")
    scope: Optional[str] = Field(None, description="Escopo: global, private, group, local")
    include_global: bool = Field(True, description="Se true, inclui corpus global além do tenant")
    case_id: Optional[str] = Field(None, description="ID do caso para filtro")
    show_template: bool = Field(False, description="Mostrar template Cypher (admin only)")


class GraphAskResponse(BaseModel):
    """Resposta padrão do Graph Ask."""
    success: bool
    operation: str
    results: List[Dict[str, Any]]
    result_count: int
    execution_time_ms: int
    cypher_template: Optional[str] = None
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


# =============================================================================
# ENDPOINTS
# =============================================================================


@router.post("/ask", response_model=GraphAskResponse)
async def ask_graph(
    request: GraphAskRequest,
    ctx: OrgContext = Depends(get_org_context),
    service: GraphAskService = Depends(get_graph_ask_service),
):
    """
    Executa uma consulta tipada ao grafo de conhecimento.

    Endpoint unificado que aceita qualquer operação suportada.
    Os filtros de tenant são aplicados automaticamente.

    **Operações disponíveis:**

    - `path`: Encontra caminho entre duas entidades
      - params: {source_id, target_id, max_hops?}

    - `neighbors`: Retorna vizinhos semânticos de uma entidade
      - params: {entity_id, limit?}

    - `cooccurrence`: Encontra co-ocorrências entre entidades
      - params: {entity1_id, entity2_id}

    - `search`: Busca entidades por nome
      - params: {query, entity_type?, limit?}

    - `count`: Conta entidades com filtros
      - params: {entity_type?, query?}
    """
    # Verificar se show_template é permitido (apenas admin)
    show_template = request.show_template and (ctx.user.role == UserRole.ADMIN)

    result = await service.ask(
        operation=request.operation,
        params=request.params,
        tenant_id=ctx.tenant_id,
        scope=request.scope,
        case_id=request.case_id,
        include_global=bool(request.include_global),
        show_template=show_template,
    )

    return GraphAskResponse(**result.to_dict())


@router.post("/ask/path", response_model=GraphAskResponse)
async def ask_path(
    request: PathRequest,
    scope: Optional[str] = Query(None, description="Escopo de acesso"),
    case_id: Optional[str] = Query(None, description="ID do caso"),
    ctx: OrgContext = Depends(get_org_context),
    include_global: bool = Query(True, description="Include global scope content"),
    service: GraphAskService = Depends(get_graph_ask_service),
):
    """
    Encontra o caminho mais curto entre duas entidades no grafo.

    **Exemplo de uso:**
    ```json
    {
      "source_id": "art_5_CF",
      "target_id": "sumula_473_STF",
      "max_hops": 4
    }
    ```

    **Retorna:**
    - Lista de nós no caminho (entidades e chunks)
    - Tipos de relacionamentos
    - Número de hops
    """
    result = await service.find_path(
        source_id=request.source_id,
        target_id=request.target_id,
        tenant_id=ctx.tenant_id,
        max_hops=request.max_hops,
        scope=scope,
        case_id=case_id,
        include_global=bool(include_global),
    )

    return GraphAskResponse(**result.to_dict())


@router.post("/ask/neighbors", response_model=GraphAskResponse)
async def ask_neighbors(
    request: NeighborsRequest,
    scope: Optional[str] = Query(None, description="Escopo de acesso"),
    case_id: Optional[str] = Query(None, description="ID do caso"),
    ctx: OrgContext = Depends(get_org_context),
    include_global: bool = Query(True, description="Include global scope content"),
    service: GraphAskService = Depends(get_graph_ask_service),
):
    """
    Retorna vizinhos semânticos de uma entidade.

    Vizinhos são entidades que co-ocorrem nos mesmos chunks,
    indicando relação semântica.

    **Exemplo de uso:**
    ```json
    {
      "entity_id": "lei_8666_1993",
      "limit": 20
    }
    ```

    **Retorna:**
    - Lista de entidades vizinhas
    - Contagem de co-ocorrências
    - Amostras de contexto
    """
    result = await service.get_neighbors(
        entity_id=request.entity_id,
        tenant_id=ctx.tenant_id,
        limit=request.limit,
        scope=scope,
        case_id=case_id,
        include_global=bool(include_global),
    )

    return GraphAskResponse(**result.to_dict())


@router.post("/ask/cooccurrence", response_model=GraphAskResponse)
async def ask_cooccurrence(
    request: CooccurrenceRequest,
    scope: Optional[str] = Query(None, description="Escopo de acesso"),
    case_id: Optional[str] = Query(None, description="ID do caso"),
    ctx: OrgContext = Depends(get_org_context),
    include_global: bool = Query(True, description="Include global scope content"),
    service: GraphAskService = Depends(get_graph_ask_service),
):
    """
    Encontra co-ocorrências entre duas entidades específicas.

    Retorna quantas vezes as entidades aparecem juntas
    e em quais documentos/contextos.

    **Exemplo de uso:**
    ```json
    {
      "entity1_id": "lei_8666_1993",
      "entity2_id": "sumula_331_TST"
    }
    ```

    **Retorna:**
    - Contagem de co-ocorrências
    - Documentos onde aparecem juntas
    - Amostras de contexto
    """
    result = await service.find_cooccurrence(
        entity1_id=request.entity1_id,
        entity2_id=request.entity2_id,
        tenant_id=ctx.tenant_id,
        scope=scope,
        case_id=case_id,
        include_global=bool(include_global),
    )

    return GraphAskResponse(**result.to_dict())


@router.post("/ask/search", response_model=GraphAskResponse)
async def ask_search(
    request: SearchRequest,
    scope: Optional[str] = Query(None, description="Escopo de acesso"),
    case_id: Optional[str] = Query(None, description="ID do caso"),
    ctx: OrgContext = Depends(get_org_context),
    include_global: bool = Query(True, description="Include global scope content"),
    service: GraphAskService = Depends(get_graph_ask_service),
):
    """
    Busca entidades no grafo por nome.

    **Exemplo de uso:**
    ```json
    {
      "query": "8.666",
      "entity_type": "lei",
      "limit": 20
    }
    ```

    **Tipos de entidade válidos:**
    - lei, artigo, sumula, tema, tribunal
    - tese, conceito, principio, instituto

    **Retorna:**
    - Lista de entidades matching
    - Contagem de menções em documentos
    """
    result = await service.search_entities(
        query=request.query,
        tenant_id=ctx.tenant_id,
        entity_type=request.entity_type,
        limit=request.limit,
        scope=scope,
        case_id=case_id,
        include_global=bool(include_global),
    )

    return GraphAskResponse(**result.to_dict())


@router.post("/ask/count", response_model=GraphAskResponse)
async def ask_count(
    request: CountRequest,
    scope: Optional[str] = Query(None, description="Escopo de acesso"),
    case_id: Optional[str] = Query(None, description="ID do caso"),
    ctx: OrgContext = Depends(get_org_context),
    include_global: bool = Query(True, description="Include global scope content"),
    service: GraphAskService = Depends(get_graph_ask_service),
):
    """
    Conta entidades no grafo com filtros opcionais.

    **Exemplo de uso:**
    ```json
    {
      "entity_type": "sumula",
      "query": "STF"
    }
    ```

    **Retorna:**
    - Contagem total de entidades
    - Total de referências em documentos
    """
    result = await service.count_entities(
        tenant_id=ctx.tenant_id,
        entity_type=request.entity_type,
        query=request.query,
        scope=scope,
        case_id=case_id,
        include_global=bool(include_global),
    )

    return GraphAskResponse(**result.to_dict())


# =============================================================================
# HEALTH CHECK
# =============================================================================


@router.get("/ask/health")
async def graph_ask_health():
    """Verifica se o serviço está disponível."""
    try:
        service = get_graph_ask_service()
        neo4j = await service._get_neo4j()
        return {
            "status": "healthy",
            "neo4j_connected": neo4j is not None,
            "operations_available": [op.value for op in GraphOperation],
        }
    except Exception as e:
        logger.error(f"Graph Ask health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
        }
