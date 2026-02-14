"""
Graph Visualization API Endpoints

Endpoints for exploring and visualizing the legal knowledge graph.
Supports:
- Entity search by type (legislacao, jurisprudencia, doutrina)
- Entity details with neighbors
- Graph export for D3.js/force-graph visualization
- Path finding between entities

All endpoints require authentication and use OrgContext.tenant_id for multi-tenancy.
"""

from __future__ import annotations
import hashlib
import json

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.security import get_org_context, OrgContext
from app.services.rag.core.neo4j_mvp import (
    EntityType,
    FactExtractor,
    LegalEntityExtractor,
    get_neo4j_mvp,
)

logger = logging.getLogger(__name__)

router = APIRouter()

def _parse_csv(value: Optional[str]) -> Optional[List[str]]:
    if not value:
        return None
    out = [v.strip() for v in value.split(",") if v and v.strip()]
    return out or None


async def _neo4j_read(neo4j: Any, query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Execute non-blocking Neo4j read from async endpoints."""
    return await neo4j._execute_read_async(query, params)


async def _neo4j_write(neo4j: Any, query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Execute non-blocking Neo4j write from async endpoints."""
    return await neo4j._execute_write_async(query, params)


def _normalize_path_hops(max_length: int, *, is_admin: bool) -> tuple[int, list[str]]:
    """Clamp path hops and enforce deep-traversal policy for interactive usage."""
    warnings: list[str] = []
    hops = max(1, min(int(max_length or 4), 6))
    if hops == 6 and not is_admin:
        warnings.append("6 hops requer perfil admin; profundidade ajustada para 5.")
        hops = 5
    if hops >= 5:
        warnings.append(
            "Profundidade alta pode aumentar latência e ruído; prefira 2-4 para consultas comuns."
        )
    return hops, warnings


# =============================================================================
# SCHEMAS
# =============================================================================


class EntityFilter(BaseModel):
    """Filter for entity search."""
    entity_types: List[str] = Field(
        default=["lei", "artigo", "sumula", "jurisprudencia", "tema", "tribunal"],
        description="Entity types to include"
    )
    query: Optional[str] = Field(None, description="Search query for entity names")
    limit: int = Field(50, ge=1, le=200)


class GraphNode(BaseModel):
    """Node in the graph visualization."""
    id: str
    label: str
    type: str
    group: str  # For coloring: legislacao, jurisprudencia, doutrina
    metadata: Dict[str, Any] = {}
    size: int = 1  # Based on connections


class GraphLink(BaseModel):
    """Link/edge in the graph visualization."""
    source: str
    target: str
    type: str
    label: str = ""  # Human-readable label
    description: str = ""  # Explanation of the relationship
    weight: float = 1.0
    semantic: bool = True  # Is this a semantic/inferred relation?


class GraphData(BaseModel):
    """Graph data for D3.js/force-graph visualization."""
    nodes: List[GraphNode]
    links: List[GraphLink]


class EntityDetail(BaseModel):
    """Detailed entity information with neighbors."""
    id: str
    name: str
    type: str
    normalized: str
    metadata: Dict[str, Any]
    neighbors: List[Dict[str, Any]]
    chunks: List[Dict[str, Any]]


class PathResult(BaseModel):
    """Path between two entities."""
    source: str
    target: str
    path: List[str]
    relationships: List[str]
    length: int


class LexicalSearchRequest(BaseModel):
    """Request for lexical search in graph entities."""
    terms: List[str] = Field(default=[], description="Search terms/phrases")
    devices: List[str] = Field(default=[], description="Legal devices (Art. 5º, Lei 8.666)")
    authors: List[str] = Field(default=[], description="Authors/tribunals (STF, Min. Barroso)")
    match_mode: str = Field(default="any", description="Match mode: 'any' (OR) or 'all' (AND)")
    include_global: bool = Field(default=True, description="Include global scope documents for mention_count")
    types: List[str] = Field(
        default=["lei", "artigo", "sumula", "jurisprudencia", "tema", "tribunal"],
        description="Entity types to search"
    )
    limit: int = Field(default=100, ge=1, le=500)


class ContentSearchRequest(BaseModel):
    """Request for content-based search (OpenSearch BM25) to seed the graph."""
    query: str = Field(..., min_length=2, description="Free-text query to search in chunks (BM25)")
    types: List[str] = Field(
        default=["lei", "artigo", "sumula", "jurisprudencia", "tema", "tribunal", "tese", "conceito"],
        description="Entity types to extract/return"
    )
    groups: List[str] = Field(
        default=["legislacao", "jurisprudencia", "doutrina"],
        description="Which content groups to search (maps to OpenSearch indices)"
    )
    max_chunks: int = Field(default=15, ge=1, le=50, description="Max chunks to fetch from OpenSearch")
    max_entities: int = Field(default=30, ge=1, le=200, description="Max entity IDs to return")
    include_global: bool = Field(default=True, description="Include global scope content in OpenSearch search")
    document_ids: List[str] = Field(default=[], description="Restrict search to these doc_ids (UUIDs) if provided")
    case_ids: List[str] = Field(default=[], description="Restrict search to these case_ids if provided")


class ContentSearchResponse(BaseModel):
    """Response for content-based search used to seed the graph visualization."""
    query: str
    chunks_count: int
    entities_count: int
    entity_ids: List[str]
    entities: List[Dict[str, Any]]


class AddFromRAGRequest(BaseModel):
    """Request to add entities from RAG local documents to graph."""
    document_ids: List[str] = Field(default=[], description="Document IDs to extract from")
    case_ids: List[str] = Field(default=[], description="Case IDs to extract from")
    extract_semantic: bool = Field(default=True, description="Use semantic extraction (LLM)")


class AddFromRAGResponse(BaseModel):
    """Response from adding entities from RAG."""
    documents_processed: int
    chunks_processed: int
    entities_extracted: int
    entities_added: int
    entities_existing: int
    relationships_created: int
    entities: List[Dict[str, Any]]


class AddFactsFromRAGRequest(BaseModel):
    """Request to backfill Fact nodes from already-ingested local RAG chunks."""
    document_ids: List[str] = Field(default=[], description="Document IDs to extract from")
    case_ids: List[str] = Field(default=[], description="Case IDs to extract from")
    max_chunks: int = Field(default=2000, ge=1, le=20000, description="Max chunks to scan")
    max_facts_per_chunk: int = Field(default=2, ge=1, le=10, description="Max facts extracted per chunk")


class AddFactsFromRAGResponse(BaseModel):
    """Response from backfilling facts."""
    documents_processed: int
    chunks_processed: int
    facts_upserted: int
    fact_refs_upserted: int


class CandidateStatsResponse(BaseModel):
    """Aggregated statistics for candidate edges."""
    candidate_type: str
    rel_type: str
    edges: int
    avg_confidence: float
    with_evidence: int
    distinct_docs: int


class PromoteCandidatesRequest(BaseModel):
    """Request to promote candidate edges to verified."""
    candidate_type: str = Field(..., min_length=1, description="candidate_type to promote")
    min_confidence: float = Field(0.0, ge=0.0, le=1.0)
    require_evidence: bool = Field(False)
    max_edges: int = Field(5000, ge=1, le=50000)
    promote_to_typed: bool = Field(
        False,
        description="If true, migrate RELATED_TO-><typed> when candidate_type suffix matches an allowed relationship type.",
    )


class GraphStats(BaseModel):
    """Graph statistics."""
    total_entities: int
    total_chunks: int
    total_documents: int
    entities_by_type: Dict[str, int]
    relationships_count: int


# =============================================================================
# ENTITY TYPE MAPPING
# =============================================================================


ENTITY_GROUPS = {
    # Legislação
    "lei": "legislacao",
    "artigo": "legislacao",
    # Jurisprudência
    "sumula": "jurisprudencia",
    "jurisprudencia": "jurisprudencia",
    "tema": "jurisprudencia",
    "acordao": "jurisprudencia",
    "tribunal": "jurisprudencia",
    "ministro": "jurisprudencia",
    "ratio_decidendi": "jurisprudencia",
    # Doutrina / Conceitos Semânticos
    "tese": "doutrina",
    "conceito": "doutrina",
    "principio": "doutrina",
    "instituto": "doutrina",
    "fundamento": "doutrina",
    # Outros
    "parte": "outros",
    "oab": "outros",
    "processo": "outros",
    # Fatos (extraidos de documentos locais)
    "fato": "fatos",
}


def parse_metadata(metadata_value: Any) -> Dict[str, Any]:
    """
    Parse metadata from Neo4j property.

    Neo4j only supports primitive types and homogeneous lists as properties.
    Metadata is stored as JSON string and needs to be deserialized on read.
    """
    if metadata_value is None:
        return {}
    if isinstance(metadata_value, dict):
        return metadata_value
    if isinstance(metadata_value, str):
        try:
            return json.loads(metadata_value)
        except (json.JSONDecodeError, ValueError):
            return {"raw": metadata_value}
    return {"raw": str(metadata_value)}


# Tipos de relações semânticas no grafo
SEMANTIC_RELATIONS = {
    # Relações estruturais
    "co_occurrence": {
        "label": "Aparece junto com",
        "description": "Entidades mencionadas no mesmo trecho de documento",
        "semantic": True,
    },
    "related": {
        "label": "Relacionado semanticamente",
        "description": "Conexão semântica inferida pelo contexto",
        "semantic": True,
    },
    "mentions": {
        "label": "Menciona",
        "description": "Documento ou trecho que referencia a entidade",
        "semantic": False,
    },
    # Relações legais explícitas
    "cita": {
        "label": "Cita",
        "description": "Citação explícita de dispositivo legal",
        "semantic": False,
    },
    # Relações semânticas extraídas por LLM
    "fundamenta": {
        "label": "Fundamenta",
        "description": "Serve como fundamento jurídico",
        "semantic": True,
    },
    "interpreta": {
        "label": "Interpreta",
        "description": "Oferece interpretação do dispositivo",
        "semantic": True,
    },
    "aplica": {
        "label": "Aplica",
        "description": "Aplicação prática do dispositivo",
        "semantic": True,
    },
    "complementa": {
        "label": "Complementa",
        "description": "Complementa ou detalha outro dispositivo",
        "semantic": True,
    },
    "contrapoe": {
        "label": "Contrapõe",
        "description": "Contradiz ou se opõe a outro entendimento",
        "semantic": True,
    },
    "deriva": {
        "label": "Deriva de",
        "description": "Deriva ou decorre de outro conceito",
        "semantic": True,
    },
    "vincula": {
        "label": "Vincula",
        "description": "Vincula ou obriga observância",
        "semantic": True,
    },
    "excepciona": {
        "label": "Excepciona",
        "description": "É exceção ou ressalva de outra regra",
        "semantic": True,
    },
    "fact_refers_to": {
        "label": "Relacionado ao fato",
        "description": "Fato extraído do documento que referencia/conecta esta entidade",
        "semantic": False,
    },
}


def get_entity_group(entity_type: str) -> str:
    """Get the group (legislacao/jurisprudencia/doutrina) for an entity type."""
    return ENTITY_GROUPS.get(entity_type.lower(), "outros")


def get_relation_info(relation_type: str) -> Dict[str, Any]:
    """Get human-readable information about a relation type."""
    return SEMANTIC_RELATIONS.get(relation_type.lower(), {
        "label": relation_type,
        "description": "Relação semântica",
        "semantic": True,
    })


def _opensearch_indices_for_groups(groups: List[str]) -> List[str]:
    """
    Map graph groups (legislacao/jurisprudencia/doutrina) to OpenSearch indices.
    """
    try:
        from app.services.rag.config import get_rag_config
        cfg = get_rag_config()
    except Exception:
        cfg = None  # type: ignore

    if cfg is None:
        return []

    group_set = {g.strip().lower() for g in (groups or []) if g}
    indices: List[str] = []

    # Always keep local index available; scope filter decides visibility.
    indices.append(cfg.opensearch_index_local)

    if "legislacao" in group_set:
        indices.append(cfg.opensearch_index_lei)
    if "jurisprudencia" in group_set:
        indices.append(cfg.opensearch_index_juris)
    if "doutrina" in group_set:
        indices.append(cfg.opensearch_index_doutrina)

    # De-dup preserving order
    seen = set()
    out: List[str] = []
    for idx in indices:
        if idx and idx not in seen:
            seen.add(idx)
            out.append(idx)
    return out


# =============================================================================
# ENDPOINTS
# =============================================================================


@router.get("/entities", response_model=List[Dict[str, Any]])
async def search_entities(
    ctx: OrgContext = Depends(get_org_context),
    query: Optional[str] = Query(None, description="Search query"),
    include_global: bool = Query(True, description="Include global scope content"),
    types: str = Query(
        "lei,artigo,sumula,jurisprudencia,tema,tribunal",
        description="Comma-separated entity types"
    ),
    group: Optional[str] = Query(
        None,
        description="Filter by group: legislacao, jurisprudencia, doutrina"
    ),
    limit: int = Query(50, ge=1, le=200),
):
    """
    Search entities in the knowledge graph.

    Supports filtering by:
    - Query text (searches in entity names)
    - Entity types (lei, artigo, sumula, etc.)
    - Group (legislacao, jurisprudencia, doutrina)
    """
    neo4j = get_neo4j_mvp()
    tenant_id = ctx.tenant_id

    # Parse types
    type_list = [t.strip().lower() for t in types.split(",") if t.strip()]

    # Filter by group if specified
    if group:
        group = group.lower()
        type_list = [t for t in type_list if get_entity_group(t) == group]

    # Build Cypher query
    cypher = """
    MATCH (e:Entity)
    WHERE e.entity_type IN $types
    """

    params: Dict[str, Any] = {
        "types": type_list,
        "tenant_id": tenant_id,
        "limit": limit,
        "include_global": bool(include_global),
    }

    if query:
        cypher += " AND toLower(e.name) CONTAINS toLower($query)"
        params["query"] = query

    cypher += """
    OPTIONAL MATCH (e)<-[:MENTIONS]-(c:Chunk)
    OPTIONAL MATCH (d:Document)-[:HAS_CHUNK]->(c)
    WITH e, sum(
        CASE
            WHEN d IS NOT NULL
             AND (d.tenant_id = $tenant_id OR ($include_global = true AND d.scope = 'global'))
             AND (d.sigilo IS NULL OR d.sigilo = false)
             AND (d.scope <> 'local')
            THEN 1
            ELSE 0
        END
    ) AS mention_count
    RETURN
        e.entity_id AS id,
        e.name AS name,
        e.entity_type AS type,
        e.normalized AS normalized,
        e.metadata AS metadata,
        mention_count
    ORDER BY mention_count DESC, e.name
    LIMIT $limit
    """

    try:
        results = await _neo4j_read(neo4j, cypher, params)

        # Add group and parse metadata
        for r in results:
            r["group"] = get_entity_group(r.get("type", ""))
            r["metadata"] = parse_metadata(r.get("metadata"))

        return results
    except Exception as e:
        logger.error(f"Error searching entities: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/entity/{entity_id}", response_model=EntityDetail)
async def get_entity_detail(
    entity_id: str,
    ctx: OrgContext = Depends(get_org_context),
    include_global: bool = Query(True, description="Include global scope content"),
    document_ids: Optional[str] = Query(
        None,
        description="Comma-separated document IDs to filter by (matches Document.doc_id or Document.doc_hash)",
    ),
    case_ids: Optional[str] = Query(
        None,
        description="Comma-separated case IDs to filter by (matches Document.case_id). Required to include local scope.",
    ),
    include_chunks: bool = Query(True),
    max_neighbors: int = Query(20, ge=1, le=100),
):
    """
    Get detailed information about an entity including neighbors and chunks.
    """
    neo4j = get_neo4j_mvp()
    tenant_id = ctx.tenant_id
    doc_id_list = _parse_csv(document_ids)
    case_id_list = _parse_csv(case_ids)

    # Get entity
    entity_query = """
    MATCH (e:Entity {entity_id: $entity_id})
    RETURN
        e.entity_id AS id,
        e.name AS name,
        e.entity_type AS type,
        e.normalized AS normalized,
        e.metadata AS metadata
    """

    try:
        entity_results = await _neo4j_read(neo4j, entity_query, {"entity_id": entity_id})

        if not entity_results:
            raise HTTPException(status_code=404, detail=f"Entity {entity_id} not found")

        entity = entity_results[0]

        # Get neighbors (entities connected via chunks or RELATED_TO)
        neighbors_query = """
        MATCH (e:Entity {entity_id: $entity_id})

        // Get entities that co-occur in same chunks
        OPTIONAL MATCH (e)<-[:MENTIONS]-(c:Chunk)-[:MENTIONS]->(neighbor:Entity)
        OPTIONAL MATCH (d:Document)-[:HAS_CHUNK]->(c)
        WHERE neighbor.entity_id <> e.entity_id
          AND d IS NOT NULL
          AND (d.tenant_id = $tenant_id OR ($include_global = true AND d.scope = 'global'))
          AND (d.sigilo IS NULL OR d.sigilo = false)
          AND ($case_ids IS NOT NULL OR $document_ids IS NOT NULL OR d.scope <> 'local')
          AND ($case_ids IS NULL OR d.case_id IN $case_ids)
          AND (
                $document_ids IS NULL
                OR d.doc_id IN $document_ids
                OR d.doc_hash IN $document_ids
          )
        WITH e, neighbor, 'co_occurrence' AS rel_type, count(DISTINCT c) AS weight

        // Also get RELATED_TO relationships
        UNION

        MATCH (e:Entity {entity_id: $entity_id})-[:RELATED_TO]-(neighbor:Entity)
        WHERE exists {
            MATCH (e)<-[:MENTIONS]-(:Chunk)<-[:HAS_CHUNK]-(d:Document)
            WHERE (d.tenant_id = $tenant_id OR ($include_global = true AND d.scope = 'global'))
              AND (d.sigilo IS NULL OR d.sigilo = false)
              AND ($case_ids IS NOT NULL OR $document_ids IS NOT NULL OR d.scope <> 'local')
              AND ($case_ids IS NULL OR d.case_id IN $case_ids)
              AND (
                    $document_ids IS NULL
                    OR d.doc_id IN $document_ids
                    OR d.doc_hash IN $document_ids
              )
        }
        AND exists {
            MATCH (neighbor)<-[:MENTIONS]-(:Chunk)<-[:HAS_CHUNK]-(d:Document)
            WHERE (d.tenant_id = $tenant_id OR ($include_global = true AND d.scope = 'global'))
              AND (d.sigilo IS NULL OR d.sigilo = false)
              AND ($case_ids IS NOT NULL OR $document_ids IS NOT NULL OR d.scope <> 'local')
              AND ($case_ids IS NULL OR d.case_id IN $case_ids)
              AND (
                    $document_ids IS NULL
                    OR d.doc_id IN $document_ids
                    OR d.doc_hash IN $document_ids
              )
        }
        WITH e, neighbor, 'related' AS rel_type, 1 AS weight

        RETURN DISTINCT
            neighbor.entity_id AS id,
            neighbor.name AS name,
            neighbor.entity_type AS type,
            rel_type AS relationship,
            weight
        ORDER BY weight DESC
        LIMIT $limit
        """

        neighbors = await _neo4j_read(neo4j, 
            neighbors_query,
            {
                "entity_id": entity_id,
                "tenant_id": tenant_id,
                "include_global": bool(include_global),
                "limit": max_neighbors,
                "case_ids": case_id_list,
                "document_ids": doc_id_list,
            }
        )

        # Get chunks mentioning this entity
        chunks = []
        if include_chunks:
            chunks_query = """
            MATCH (e:Entity {entity_id: $entity_id})<-[:MENTIONS]-(c:Chunk)
            MATCH (d:Document)-[:HAS_CHUNK]->(c)
            WHERE (d.tenant_id = $tenant_id OR ($include_global = true AND d.scope = 'global'))
              AND (d.sigilo IS NULL OR d.sigilo = false)
              AND ($case_ids IS NOT NULL OR $document_ids IS NOT NULL OR d.scope <> 'local')
              AND ($case_ids IS NULL OR d.case_id IN $case_ids)
              AND (
                    $document_ids IS NULL
                    OR d.doc_id IN $document_ids
                    OR d.doc_hash IN $document_ids
              )
            RETURN
                c.chunk_uid AS chunk_uid,
                c.text_preview AS text,
                c.chunk_index AS chunk_index,
                d.doc_hash AS doc_hash,
                d.title AS doc_title,
                d.source_type AS source_type
            ORDER BY c.chunk_index
            LIMIT 20
            """

            chunks = await _neo4j_read(neo4j, 
                chunks_query,
                {
                    "entity_id": entity_id,
                    "tenant_id": tenant_id,
                    "include_global": bool(include_global),
                    "case_ids": case_id_list,
                    "document_ids": doc_id_list,
                },
            )

        return EntityDetail(
            id=entity["id"],
            name=entity["name"],
            type=entity["type"],
            normalized=entity.get("normalized", ""),
            metadata=parse_metadata(entity.get("metadata")),
            neighbors=neighbors,
            chunks=chunks,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting entity detail: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/export", response_model=GraphData)
async def export_graph(
    ctx: OrgContext = Depends(get_org_context),
    entity_ids: Optional[str] = Query(
        None,
        description="Comma-separated entity IDs to start from"
    ),
    include_global: bool = Query(True, description="Include global scope content"),
    document_ids: Optional[str] = Query(
        None,
        description="Comma-separated document IDs to filter by (matches Document.doc_id or Document.doc_hash)"
    ),
    case_ids: Optional[str] = Query(
        None,
        description="Comma-separated case IDs to filter by (matches Document.case_id). Required to include local scope.",
    ),
    types: str = Query(
        "lei,artigo,sumula,jurisprudencia,tema",
        description="Entity types to include"
    ),
    groups: str = Query(
        "legislacao,jurisprudencia,doutrina",
        description="Groups to include: legislacao, jurisprudencia, doutrina"
    ),
    max_nodes: int = Query(100, ge=1, le=500),
    include_relationships: bool = Query(True),
):
    """
    Export subgraph for visualization.

    Returns nodes and links in D3.js/force-graph format.
    """
    neo4j = get_neo4j_mvp()
    tenant_id = ctx.tenant_id

    type_list = [t.strip().lower() for t in types.split(",") if t.strip()]
    group_list = [g.strip().lower() for g in groups.split(",") if g.strip()]
    doc_id_list = _parse_csv(document_ids)
    case_id_list = _parse_csv(case_ids)
    include_facts = "fatos" in group_list

    try:
        logger.info(
            "[graph.export] tenant_id=%s user_id=%s include_global=%s doc_ids=%d case_ids=%d seed_entities=%s",
            tenant_id,
            getattr(ctx.user, "id", "unknown"),
            bool(include_global),
            len(doc_id_list or []),
            len(case_id_list or []),
            "yes" if bool(entity_ids) else "no",
        )
    except Exception:
        pass

    # Filter types by groups
    type_list = [t for t in type_list if get_entity_group(t) in group_list]

    nodes: List[GraphNode] = []
    links: List[GraphLink] = []
    node_ids: set = set()

    try:
        # If specific entity_ids provided, start from those
        if entity_ids:
            seed_ids = [e.strip() for e in entity_ids.split(",") if e.strip()]

            # Get seed entities and their neighbors
            seed_query = """
            MATCH (e:Entity)
            WHERE e.entity_id IN $seed_ids

            CALL {
                WITH e
                MATCH (e)<-[:MENTIONS]-(c:Chunk)-[:MENTIONS]->(neighbor:Entity)
                MATCH (d:Document)-[:HAS_CHUNK]->(c)
                WHERE neighbor.entity_type IN $types
                  AND (d.tenant_id = $tenant_id OR ($include_global = true AND d.scope = 'global'))
                  AND (d.sigilo IS NULL OR d.sigilo = false)
                  AND ($case_ids IS NOT NULL OR $document_ids IS NOT NULL OR d.scope <> 'local')
                  AND ($case_ids IS NULL OR d.case_id IN $case_ids)
                  AND (
                        $document_ids IS NULL
                        OR d.doc_id IN $document_ids
                        OR d.doc_hash IN $document_ids
                  )
                RETURN collect(DISTINCT neighbor)[0..$max_neighbors] AS neighbors
            }

            RETURN
                e.entity_id AS id,
                e.name AS name,
                e.entity_type AS type,
                e.metadata AS metadata,
                [n IN neighbors | {
                    id: n.entity_id,
                    name: n.name,
                    type: n.entity_type
                }] AS neighbors
            """

            results = await _neo4j_read(neo4j, seed_query, {
                "seed_ids": seed_ids,
                "types": type_list,
                "tenant_id": tenant_id,
                "include_global": bool(include_global),
                "max_neighbors": max_nodes // 2,
                "case_ids": case_id_list,
                "document_ids": doc_id_list,
            })

            for r in results:
                entity_type = r.get("type", "")
                group = get_entity_group(entity_type)

                if r["id"] not in node_ids:
                    nodes.append(GraphNode(
                        id=r["id"],
                        label=r["name"],
                        type=entity_type,
                        group=group,
                        metadata=parse_metadata(r.get("metadata")),
                        size=len(r.get("neighbors", [])) + 1
                    ))
                    node_ids.add(r["id"])

                for neighbor in r.get("neighbors", []):
                    n_type = neighbor.get("type", "")
                    n_group = get_entity_group(n_type)

                    if neighbor["id"] not in node_ids and n_group in group_list:
                        nodes.append(GraphNode(
                            id=neighbor["id"],
                            label=neighbor["name"],
                            type=n_type,
                            group=n_group,
                            size=1
                        ))
                        node_ids.add(neighbor["id"])

                    if neighbor["id"] in node_ids and include_relationships:
                        rel_info = get_relation_info("co_occurrence")
                        links.append(GraphLink(
                            source=r["id"],
                            target=neighbor["id"],
                            type="co_occurrence",
                            label=rel_info["label"],
                            description=rel_info["description"],
                            weight=1.0,
                            semantic=True
                        ))

        else:
            # Get top entities by mention count
            top_query = """
            MATCH (e:Entity)
            WHERE e.entity_type IN $types
            OPTIONAL MATCH (e)<-[:MENTIONS]-(c:Chunk)
            OPTIONAL MATCH (d:Document)-[:HAS_CHUNK]->(c)
            WITH e, sum(
                CASE
                    WHEN d IS NOT NULL
                     AND (d.tenant_id = $tenant_id OR ($include_global = true AND d.scope = 'global'))
                     AND (d.sigilo IS NULL OR d.sigilo = false)
                     AND ($case_ids IS NOT NULL OR $document_ids IS NOT NULL OR d.scope <> 'local')
                     AND ($case_ids IS NULL OR d.case_id IN $case_ids)
                     AND (
                           $document_ids IS NULL
                           OR d.doc_id IN $document_ids
                           OR d.doc_hash IN $document_ids
                     )
                    THEN 1
                    ELSE 0
                END
            ) AS mention_count
            WHERE mention_count > 0
            ORDER BY mention_count DESC
            LIMIT $limit
            RETURN
                e.entity_id AS id,
                e.name AS name,
                e.entity_type AS type,
                e.metadata AS metadata,
                mention_count
            """

            results = await _neo4j_read(neo4j, 
                top_query,
                {
                    "types": type_list,
                    "tenant_id": tenant_id,
                    "include_global": bool(include_global),
                    "limit": max_nodes,
                    "case_ids": case_id_list,
                    "document_ids": doc_id_list,
                },
            )

            for r in results:
                entity_type = r.get("type", "")
                group = get_entity_group(entity_type)

                if group in group_list:
                    nodes.append(GraphNode(
                        id=r["id"],
                        label=r["name"],
                        type=entity_type,
                        group=group,
                        metadata=parse_metadata(r.get("metadata")),
                        size=r.get("mention_count", 1)
                    ))
                    node_ids.add(r["id"])

            # Get relationships between these nodes
            if include_relationships and len(node_ids) > 1:
                rel_query = """
                MATCH (e1:Entity)<-[:MENTIONS]-(c:Chunk)-[:MENTIONS]->(e2:Entity)
                MATCH (d:Document)-[:HAS_CHUNK]->(c)
	                WHERE e1.entity_id IN $node_ids
	                  AND e2.entity_id IN $node_ids
	                  AND e1.entity_id < e2.entity_id
	                  AND (d.tenant_id = $tenant_id OR ($include_global = true AND d.scope = 'global'))
	                  AND (d.sigilo IS NULL OR d.sigilo = false)
	                  AND ($case_ids IS NOT NULL OR $document_ids IS NOT NULL OR d.scope <> 'local')
	                  AND ($case_ids IS NULL OR d.case_id IN $case_ids)
	                  AND (
	                        $document_ids IS NULL
	                        OR d.doc_id IN $document_ids
                        OR d.doc_hash IN $document_ids
                  )
                WITH e1, e2, count(DISTINCT c) AS weight
                RETURN
                    e1.entity_id AS source,
                    e2.entity_id AS target,
                    weight
                ORDER BY weight DESC
                LIMIT 200
                """

                rel_results = await _neo4j_read(neo4j, 
                    rel_query,
                    {
                        "node_ids": list(node_ids),
                        "tenant_id": tenant_id,
                        "include_global": bool(include_global),
                        "case_ids": case_id_list,
                        "document_ids": doc_id_list,
                    },
                )

                for r in rel_results:
                    rel_info = get_relation_info("co_occurrence")
                    links.append(GraphLink(
                        source=r["source"],
                        target=r["target"],
                        type="co_occurrence",
                        label=rel_info["label"],
                        description=rel_info["description"],
                        weight=r.get("weight", 1),
                        semantic=True
                    ))

                # Also include explicit RELATED_TO edges between entities
                rel_related_query = """
                MATCH (e1:Entity)-[r:RELATED_TO]-(e2:Entity)
                WHERE e1.entity_id IN $node_ids
                  AND e2.entity_id IN $node_ids
                  AND e1.entity_id < e2.entity_id
                  AND exists {
                    MATCH (e1)<-[:MENTIONS]-(:Chunk)<-[:HAS_CHUNK]-(d:Document)
                    WHERE (d.tenant_id = $tenant_id OR ($include_global = true AND d.scope = 'global'))
                      AND (d.sigilo IS NULL OR d.sigilo = false)
                      AND ($case_ids IS NOT NULL OR $document_ids IS NOT NULL OR d.scope <> 'local')
                      AND ($case_ids IS NULL OR d.case_id IN $case_ids)
                      AND (
                            $document_ids IS NULL
                            OR d.doc_id IN $document_ids
                            OR d.doc_hash IN $document_ids
                      )
                  }
                  AND exists {
                    MATCH (e2)<-[:MENTIONS]-(:Chunk)<-[:HAS_CHUNK]-(d:Document)
                    WHERE (d.tenant_id = $tenant_id OR ($include_global = true AND d.scope = 'global'))
                      AND (d.sigilo IS NULL OR d.sigilo = false)
                      AND ($case_ids IS NOT NULL OR $document_ids IS NOT NULL OR d.scope <> 'local')
                      AND ($case_ids IS NULL OR d.case_id IN $case_ids)
                      AND (
                            $document_ids IS NULL
                            OR d.doc_id IN $document_ids
                            OR d.doc_hash IN $document_ids
                      )
                  }
                RETURN
                    e1.entity_id AS source,
                    e2.entity_id AS target,
                    coalesce(r.weight, 1) AS weight
                LIMIT 200
                """
                rel_related_results = await _neo4j_read(neo4j, 
                    rel_related_query,
                    {
                        "node_ids": list(node_ids),
                        "tenant_id": tenant_id,
                        "include_global": bool(include_global),
                        "case_ids": case_id_list,
                        "document_ids": doc_id_list,
                    },
                )
                for r in rel_related_results:
                    rel_info = get_relation_info("related")
                    links.append(
                        GraphLink(
                            source=r["source"],
                            target=r["target"],
                            type="related",
                            label=rel_info["label"],
                            description=rel_info["description"],
                            weight=r.get("weight", 1),
                            semantic=True,
                        )
                    )

        # Optional: include Fact nodes extracted from local documents to connect narrative -> entities.
        if include_facts and node_ids:
            fact_query = """
            MATCH (c:Chunk)-[:ASSERTS]->(f:Fact)-[:REFERS_TO]->(e:Entity)
            MATCH (d:Document)-[:HAS_CHUNK]->(c)
            WHERE e.entity_id IN $node_ids
              AND (d.tenant_id = $tenant_id OR ($include_global = true AND d.scope = 'global'))
              AND (d.sigilo IS NULL OR d.sigilo = false)
              AND ($case_ids IS NOT NULL OR $document_ids IS NOT NULL OR d.scope <> 'local')
              AND ($case_ids IS NULL OR d.case_id IN $case_ids)
              AND (
                    $document_ids IS NULL
                    OR d.doc_id IN $document_ids
                    OR d.doc_hash IN $document_ids
              )
            RETURN DISTINCT
                f.fact_id AS fact_id,
                coalesce(f.text_preview, f.text) AS fact_text,
                f.metadata AS metadata,
                e.entity_id AS entity_id
            LIMIT $limit
            """

            limit = min(500, max_nodes * 2)
            fact_rows = await _neo4j_read(neo4j, 
                fact_query,
                {
                    "node_ids": list(node_ids),
                    "tenant_id": tenant_id,
                    "include_global": bool(include_global),
                    "case_ids": case_id_list,
                    "document_ids": doc_id_list,
                    "limit": limit,
                },
            )

            rel_info = get_relation_info("fact_refers_to")
            for r in fact_rows:
                fid = str(r.get("fact_id") or "").strip()
                eid = str(r.get("entity_id") or "").strip()
                if not fid or not eid:
                    continue

                if fid not in node_ids:
                    text = str(r.get("fact_text") or "").strip()
                    label = text[:120] + ("..." if len(text) > 120 else "")
                    nodes.append(
                        GraphNode(
                            id=fid,
                            label=label or fid,
                            type="fato",
                            group="fatos",
                            metadata={
                                "text": text,
                                **parse_metadata(r.get("metadata")),
                            },
                            size=1,
                        )
                    )
                    node_ids.add(fid)

                if include_relationships:
                    links.append(
                        GraphLink(
                            source=fid,
                            target=eid,
                            type="fact_refers_to",
                            label=rel_info["label"],
                            description=rel_info["description"],
                            weight=1.0,
                            semantic=bool(rel_info.get("semantic", False)),
                        )
                    )

        return GraphData(nodes=nodes, links=links)

    except Exception as e:
        logger.error(f"Error exporting graph: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/path")
async def find_path(
    source_id: str = Query(..., description="Source entity ID"),
    target_id: str = Query(..., description="Target entity ID"),
    ctx: OrgContext = Depends(get_org_context),
    include_global: bool = Query(True, description="Include global scope content"),
    document_ids: Optional[str] = Query(
        None,
        description="Comma-separated document IDs to filter by (matches Document.doc_id or Document.doc_hash)",
    ),
    case_ids: Optional[str] = Query(
        None,
        description="Comma-separated case IDs to filter by (matches Document.case_id). Required to include local scope.",
    ),
    max_length: int = Query(4, ge=1, le=6),
):
    """
    Find paths between two entities.

    Useful for understanding how legal concepts are connected.
    """
    neo4j = get_neo4j_mvp()
    tenant_id = ctx.tenant_id
    doc_id_list = _parse_csv(document_ids)
    case_id_list = _parse_csv(case_ids)
    requested_hops = max_length
    effective_hops, warnings = _normalize_path_hops(
        max_length,
        is_admin=bool(getattr(ctx, "is_org_admin", False)),
    )

    # Additional protective downgrade for highly connected anchors on deep traversals.
    if effective_hops >= 5:
        degree_query = """
        MATCH (e:Entity {entity_id: $entity_id})-[r]-()
        RETURN count(r) AS degree
        """
        source_degree_rows = await _neo4j_read(neo4j, degree_query, {"entity_id": source_id})
        target_degree_rows = await _neo4j_read(neo4j, degree_query, {"entity_id": target_id})
        source_degree = int(source_degree_rows[0]["degree"]) if source_degree_rows else 0
        target_degree = int(target_degree_rows[0]["degree"]) if target_degree_rows else 0
        max_degree = max(source_degree, target_degree)

        if max_degree >= 100 and not getattr(ctx, "is_org_admin", False):
            warnings.append(
                f"Nós com alto grau ({max_degree}) detectados; profundidade ajustada para 4 para evitar explosão."
            )
            effective_hops = 4

    path_query = f"""
    MATCH (e1:Entity {{entity_id: $source_id}})
    MATCH (e2:Entity {{entity_id: $target_id}})
    MATCH path = shortestPath((e1)-[:MENTIONS|RELATED_TO|ASSERTS|REFERS_TO*1..{effective_hops}]-(e2))
    WHERE all(n IN nodes(path) WHERE NOT n:Chunk OR exists {{
        MATCH (d:Document)-[:HAS_CHUNK]->(n)
        WHERE (d.tenant_id = $tenant_id OR ($include_global = true AND d.scope = 'global'))
          AND (d.sigilo IS NULL OR d.sigilo = false)
          AND ($case_ids IS NOT NULL OR $document_ids IS NOT NULL OR d.scope <> 'local')
          AND ($case_ids IS NULL OR d.case_id IN $case_ids)
          AND (
                $document_ids IS NULL
                OR d.doc_id IN $document_ids
                OR d.doc_hash IN $document_ids
          )
    }})
    RETURN
        [n IN nodes(path) | coalesce(n.name, n.entity_id, n.chunk_uid)] AS path_names,
        [n IN nodes(path) | coalesce(n.entity_id, n.chunk_uid, n.doc_hash)] AS path_ids,
        [r IN relationships(path) | type(r)] AS relationships,
        length(path) AS path_length,
        [n IN nodes(path) | {{
            labels: labels(n),
            entity_id: n.entity_id,
            chunk_uid: n.chunk_uid,
            doc_hash: n.doc_hash,
            name: n.name,
            entity_type: n.entity_type,
            normalized: n.normalized,
            chunk_index: n.chunk_index,
            text_preview: n.text_preview
        }}] AS path_nodes,
        [r IN relationships(path) | {{
            type: type(r),
            from_id: coalesce(startNode(r).entity_id, startNode(r).chunk_uid, startNode(r).doc_hash),
            to_id: coalesce(endNode(r).entity_id, endNode(r).chunk_uid, endNode(r).doc_hash),
            properties: properties(r)
        }}] AS path_edges
    LIMIT 5
    """

    try:
        results = await _neo4j_read(neo4j, path_query, {
            "source_id": source_id,
            "target_id": target_id,
            "tenant_id": tenant_id,
            "include_global": bool(include_global),
            "case_ids": case_id_list,
            "document_ids": doc_id_list,
        })

        if not results:
            return {
                "found": False,
                "message": f"No path found between {source_id} and {target_id} within {effective_hops} hops",
                "requested_hops": requested_hops,
                "effective_hops": effective_hops,
                "warnings": warnings or None,
            }

        paths = []
        for r in results:
            paths.append({
                "path": r["path_names"],
                "path_ids": r["path_ids"],
                "relationships": r["relationships"],
                "length": r["path_length"],
                "nodes": r.get("path_nodes", []),
                "edges": r.get("path_edges", []),
            })

        return {
            "found": True,
            "source": source_id,
            "target": target_id,
            "paths": paths,
            "requested_hops": requested_hops,
            "effective_hops": effective_hops,
            "warnings": warnings or None,
        }

    except Exception as e:
        logger.error(f"Error finding path: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats", response_model=GraphStats)
async def get_graph_stats(
    ctx: OrgContext = Depends(get_org_context),
    include_global: bool = Query(True, description="Include global scope content"),
    document_ids: Optional[str] = Query(
        None,
        description="Comma-separated document IDs to filter by (matches Document.doc_id or Document.doc_hash)",
    ),
    case_ids: Optional[str] = Query(
        None,
        description="Comma-separated case IDs to filter by (matches Document.case_id). Required to include local scope.",
    ),
):
    """
    Get statistics about the knowledge graph.
    """
    neo4j = get_neo4j_mvp()
    tenant_id = ctx.tenant_id
    doc_id_list = _parse_csv(document_ids)
    case_id_list = _parse_csv(case_ids)

    stats_query = """
    MATCH (d:Document)
    WHERE (d.tenant_id = $tenant_id OR ($include_global = true AND d.scope = 'global'))
      AND (d.sigilo IS NULL OR d.sigilo = false)
      AND ($case_ids IS NOT NULL OR $document_ids IS NOT NULL OR d.scope <> 'local')
      AND ($case_ids IS NULL OR d.case_id IN $case_ids)
      AND (
            $document_ids IS NULL
            OR d.doc_id IN $document_ids
            OR d.doc_hash IN $document_ids
      )
    WITH count(DISTINCT d) AS total_documents

    MATCH (d:Document)-[:HAS_CHUNK]->(c:Chunk)
    WHERE (d.tenant_id = $tenant_id OR ($include_global = true AND d.scope = 'global'))
      AND (d.sigilo IS NULL OR d.sigilo = false)
      AND ($case_ids IS NOT NULL OR $document_ids IS NOT NULL OR d.scope <> 'local')
      AND ($case_ids IS NULL OR d.case_id IN $case_ids)
      AND (
            $document_ids IS NULL
            OR d.doc_id IN $document_ids
            OR d.doc_hash IN $document_ids
      )
    WITH total_documents, collect(DISTINCT c) AS chunks, count(DISTINCT c) AS total_chunks

    UNWIND chunks AS c
    OPTIONAL MATCH (c)-[m:MENTIONS]->(e:Entity)
    WITH total_documents, total_chunks, count(DISTINCT e) AS total_entities, count(m) AS rel_count

    RETURN
        total_entities,
        total_chunks,
        total_documents,
        rel_count
    """

    type_count_query = """
    MATCH (d:Document)
    WHERE (d.tenant_id = $tenant_id OR ($include_global = true AND d.scope = 'global'))
      AND (d.sigilo IS NULL OR d.sigilo = false)
      AND ($case_ids IS NOT NULL OR $document_ids IS NOT NULL OR d.scope <> 'local')
      AND ($case_ids IS NULL OR d.case_id IN $case_ids)
      AND (
            $document_ids IS NULL
            OR d.doc_id IN $document_ids
            OR d.doc_hash IN $document_ids
      )
    MATCH (d)-[:HAS_CHUNK]->(c:Chunk)-[:MENTIONS]->(e:Entity)
    RETURN e.entity_type AS type, count(DISTINCT e) AS count
    ORDER BY count DESC
    """

    try:
        params = {
            "tenant_id": tenant_id,
            "include_global": bool(include_global),
            "case_ids": case_id_list,
            "document_ids": doc_id_list,
        }
        stats_result = await _neo4j_read(neo4j, stats_query, params)
        type_counts = await _neo4j_read(neo4j, type_count_query, params)

        stats = stats_result[0] if stats_result else {}

        entities_by_type = {r["type"]: r["count"] for r in type_counts}

        return GraphStats(
            total_entities=stats.get("total_entities", 0),
            total_chunks=stats.get("total_chunks", 0),
            total_documents=stats.get("total_documents", 0),
            entities_by_type=entities_by_type,
            relationships_count=stats.get("rel_count", 0)
        )

    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/extract-entities")
async def extract_entities_from_text(
    text: str = Query(..., description="Text to extract entities from"),
):
    """
    Extract legal entities from text.

    Useful for testing entity extraction or preparing search queries.
    """
    entities = LegalEntityExtractor.extract(text)

    # Add groups
    for e in entities:
        e["group"] = get_entity_group(e.get("entity_type", ""))

    return {
        "text": text[:200] + "..." if len(text) > 200 else text,
        "entities": entities,
        "count": len(entities)
    }


@router.get("/relation-types")
async def get_relation_types():
    """
    Get available semantic relation types.

    Returns all relation types with their labels and descriptions.
    """
    return {
        "relations": [
            {
                "type": rel_type,
                **rel_info
            }
            for rel_type, rel_info in SEMANTIC_RELATIONS.items()
        ],
        "entity_groups": ENTITY_GROUPS,
    }


@router.get("/semantic-neighbors/{entity_id}")
async def get_semantic_neighbors(
    entity_id: str,
    ctx: OrgContext = Depends(get_org_context),
    include_global: bool = Query(True, description="Include global scope content"),
    document_ids: Optional[str] = Query(
        None,
        description="Comma-separated document IDs to filter by (matches Document.doc_id or Document.doc_hash)",
    ),
    case_ids: Optional[str] = Query(
        None,
        description="Comma-separated case IDs to filter by (matches Document.case_id). Required to include local scope.",
    ),
    limit: int = Query(30, ge=1, le=100),
):
    """
    Get semantically related entities based on co-occurrence and context.

    This is the main endpoint for discovering relationships between legal concepts.
    Returns entities that frequently appear together in the same document contexts.
    """
    neo4j = get_neo4j_mvp()
    tenant_id = ctx.tenant_id
    doc_id_list = _parse_csv(document_ids)
    case_id_list = _parse_csv(case_ids)

    # Query for entities that co-occur in the same chunks
    semantic_query = """
    MATCH (e:Entity {entity_id: $entity_id})

    // Find chunks mentioning this entity
    MATCH (e)<-[:MENTIONS]-(c:Chunk)
    MATCH (d0:Document)-[:HAS_CHUNK]->(c)
    WHERE (d0.tenant_id = $tenant_id OR ($include_global = true AND d0.scope = 'global'))
      AND (d0.sigilo IS NULL OR d0.sigilo = false)
      AND ($case_ids IS NOT NULL OR $document_ids IS NOT NULL OR d0.scope <> 'local')
      AND ($case_ids IS NULL OR d0.case_id IN $case_ids)
      AND (
            $document_ids IS NULL
            OR d0.doc_id IN $document_ids
            OR d0.doc_hash IN $document_ids
      )

    // Find other entities in the same chunks (semantic co-occurrence)
    MATCH (c)-[:MENTIONS]->(other:Entity)
    WHERE other.entity_id <> e.entity_id

    // Count co-occurrences and gather context
    WITH other, count(DISTINCT c) AS co_occurrences,
         collect(DISTINCT c.text_preview)[0..3] AS sample_contexts

    // Get document info for context
    OPTIONAL MATCH (other)<-[:MENTIONS]-(oc:Chunk)<-[:HAS_CHUNK]-(d:Document)
    WHERE (d.tenant_id = $tenant_id OR ($include_global = true AND d.scope = 'global'))
      AND (d.sigilo IS NULL OR d.sigilo = false)
      AND ($case_ids IS NOT NULL OR $document_ids IS NOT NULL OR d.scope <> 'local')
      AND ($case_ids IS NULL OR d.case_id IN $case_ids)
      AND (
            $document_ids IS NULL
            OR d.doc_id IN $document_ids
            OR d.doc_hash IN $document_ids
      )

    WITH other, co_occurrences, sample_contexts,
         collect(DISTINCT d.title)[0..2] AS source_docs

    RETURN
        other.entity_id AS id,
        other.name AS name,
        other.entity_type AS type,
        other.normalized AS normalized,
        co_occurrences,
        sample_contexts,
        source_docs
    ORDER BY co_occurrences DESC
    LIMIT $limit
    """

    try:
        results = await _neo4j_read(neo4j, 
            semantic_query,
            {
                "entity_id": entity_id,
                "tenant_id": tenant_id,
                "include_global": bool(include_global),
                "limit": limit,
                "case_ids": case_id_list,
                "document_ids": doc_id_list,
            },
        )

        # Enrich with semantic information
        enriched = []
        for r in results:
            entity_type = r.get("type", "")
            group = get_entity_group(entity_type)

            # Determine relationship type based on entity types
            relation_type = "co_occurrence"
            if entity_type in ["lei", "artigo"] and group == "legislacao":
                relation_type = "complementa"
            elif entity_type in ["sumula", "jurisprudencia"]:
                relation_type = "interpreta"

            rel_info = get_relation_info(relation_type)

            enriched.append({
                "id": r["id"],
                "name": r["name"],
                "type": entity_type,
                "group": group,
                "normalized": r.get("normalized"),
                "strength": r["co_occurrences"],
                "relation": {
                    "type": relation_type,
                    "label": rel_info["label"],
                    "description": rel_info["description"],
                },
                "sample_contexts": r.get("sample_contexts", []),
                "source_docs": r.get("source_docs", []),
            })

        return {
            "entity_id": entity_id,
            "total": len(enriched),
            "neighbors": enriched,
        }

    except Exception as e:
        logger.error(f"Error getting semantic neighbors: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/remissoes/{entity_id}")
async def get_remissoes(
    entity_id: str,
    ctx: OrgContext = Depends(get_org_context),
    include_global: bool = Query(True, description="Include global scope content"),
    document_ids: Optional[str] = Query(
        None,
        description="Comma-separated document IDs to filter by (matches Document.doc_id or Document.doc_hash)",
    ),
    case_ids: Optional[str] = Query(
        None,
        description="Comma-separated case IDs to filter by (matches Document.case_id). Required to include local scope.",
    ),
    limit: int = Query(50, ge=1, le=200),
):
    """
    Get remissões (cross-references) for a legal entity.

    Shows all other legal provisions that reference or are referenced by this entity.
    Particularly useful for articles of law.
    """
    neo4j = get_neo4j_mvp()
    tenant_id = ctx.tenant_id
    user_id = str(ctx.user.id)
    group_ids = list(getattr(ctx, "team_ids", []) or [])
    try:
        from app.models.user import UserRole
        show_sample_text = bool(getattr(ctx, "is_org_admin", False)) or getattr(ctx.user, "role", None) == UserRole.ADMIN
    except Exception:
        show_sample_text = bool(getattr(ctx, "is_org_admin", False))
    doc_id_list = _parse_csv(document_ids)
    case_id_list = _parse_csv(case_ids)

    remissoes_query = """
    // Find entity
    MATCH (e:Entity {entity_id: $entity_id})

    // Find chunks that mention this entity
    MATCH (e)<-[:MENTIONS]-(c:Chunk)
    MATCH (d0:Document)-[:HAS_CHUNK]->(c)
    WHERE (d0.tenant_id = $tenant_id OR ($include_global = true AND d0.scope = 'global'))
      AND (
            d0.sigilo IS NULL
            OR d0.sigilo = false
            OR $user_id IS NULL
            OR $user_id IN coalesce(d0.allowed_users, [])
      )
      AND (
            d0.scope <> 'group'
            OR (
                coalesce(size($group_ids), 0) > 0
                AND any(g IN $group_ids WHERE g IN coalesce(d0.group_ids, []))
            )
      )
      AND ($case_ids IS NOT NULL OR $document_ids IS NOT NULL OR d0.scope <> 'local')
      AND ($case_ids IS NULL OR d0.case_id IN $case_ids)
      AND (
            $document_ids IS NULL
            OR d0.doc_id IN $document_ids
            OR d0.doc_hash IN $document_ids
      )

    // Find other entities mentioned in same chunks (remissões)
    MATCH (c)-[:MENTIONS]->(other:Entity)
    WHERE other.entity_id <> e.entity_id
      AND other.entity_type IN ['lei', 'artigo', 'sumula', 'tema']

    // Group by entity and count co-occurrences
    WITH e, other, count(DISTINCT c) AS co_occurrences

    // Get sample chunk for context
		    OPTIONAL MATCH (e)<-[:MENTIONS]-(sample:Chunk)-[:MENTIONS]->(other)
		    OPTIONAL MATCH (d1:Document)-[:HAS_CHUNK]->(sample)
		    WITH e, other, co_occurrences,
		         collect(
            CASE
                WHEN d1 IS NOT NULL
                 AND $show_sample_text = true
	                 AND (d1.tenant_id = $tenant_id OR ($include_global = true AND d1.scope = 'global'))
	                 AND (
	                        d1.sigilo IS NULL
	                        OR d1.sigilo = false
	                        OR $user_id IS NULL
	                        OR $user_id IN coalesce(d1.allowed_users, [])
	                 )
                     AND (
                           d1.scope <> 'group'
                           OR (
                               coalesce(size($group_ids), 0) > 0
                               AND any(g IN $group_ids WHERE g IN coalesce(d1.group_ids, []))
                           )
                     )
	                 AND ($case_ids IS NOT NULL OR $document_ids IS NOT NULL OR d1.scope <> 'local')
	                 AND ($case_ids IS NULL OR d1.case_id IN $case_ids)
	                 AND (
	                       $document_ids IS NULL
	                       OR d1.doc_id IN $document_ids
	                       OR d1.doc_hash IN $document_ids
	                 )
                THEN sample.text_preview
                ELSE NULL
		            END
		         )[0] AS sample_text

	    // Annotate with stored graph edges when available (verified vs candidate)
	    OPTIONAL MATCH (e)-[rv:REMETE_A]->(other)
	    OPTIONAL MATCH (other)-[rv2:REMETE_A]->(e)
	    OPTIONAL MATCH (e)-[rc:CO_MENCIONA]->(other)
	    OPTIONAL MATCH (other)-[rc2:CO_MENCIONA]->(e)
	    WITH e, other, co_occurrences, sample_text,
	         coalesce(rv, rv2) AS rem_edge,
	         coalesce(rc, rc2) AS cand_edge
	
	    RETURN
	        other.entity_id AS id,
	        other.name AS name,
	        other.entity_type AS type,
	        other.normalized AS normalized,
	        co_occurrences,
	        sample_text,
	        CASE WHEN rem_edge IS NOT NULL THEN true ELSE false END AS verified,
	        CASE
	            WHEN rem_edge IS NOT NULL THEN 'REMETE_A'
	            WHEN cand_edge IS NOT NULL THEN 'CO_MENCIONA'
	            ELSE 'co_occurrence'
	        END AS relationship_type,
	        coalesce(rem_edge.dimension, cand_edge.dimension, NULL) AS dimension,
	        coalesce(rem_edge.evidence, cand_edge.evidence, NULL) AS evidence,
	        coalesce(rem_edge.layer, cand_edge.layer, CASE WHEN rem_edge IS NOT NULL THEN 'verified' ELSE 'candidate' END) AS layer
	    ORDER BY co_occurrences DESC
	    LIMIT $limit
	    """

    try:
        results = await _neo4j_read(neo4j, remissoes_query, {
            "entity_id": entity_id,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "group_ids": group_ids,
            "show_sample_text": bool(show_sample_text),
            "include_global": bool(include_global),
            "limit": limit,
            "case_ids": case_id_list,
            "document_ids": doc_id_list,
        })

        # Group by type
        legislacao = []
        jurisprudencia = []

        for r in results:
            r["group"] = get_entity_group(r.get("type", ""))

            if r["group"] == "legislacao":
                legislacao.append(r)
            elif r["group"] == "jurisprudencia":
                jurisprudencia.append(r)

        return {
            "entity_id": entity_id,
            "total_remissoes": len(results),
            "legislacao": legislacao,
            "jurisprudencia": jurisprudencia,
            "all": results
        }

    except Exception as e:
        logger.error(f"Error getting remissoes: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# ENRICHMENT PIPELINE (L1→L2→L3→L3b)
# ============================================================================


@router.post("/enrich")
async def enrich_graph(
    ctx: OrgContext = Depends(get_org_context),
    request: Optional[Dict[str, Any]] = None,
):
    """
    Executa o pipeline de enriquecimento do grafo.

    Layers:
    - structural (L1): Inferência determinística (transitividade, co-citação, etc.)
    - embedding (L2): Similaridade de embeddings → :RELATED_TO candidates
    - llm (L3): Classificação/descoberta via LLM → :RELATED_TO candidates
    - exploratory (L3b): Descoberta para nós isolados → :RELATED_TO candidates

    Requer perfil admin.
    """
    if not getattr(ctx, "is_admin", False):
        raise HTTPException(status_code=403, detail="Enrichment requires admin privileges")

    from app.schemas.graph_enrich import EnrichRequest as EnrichReq
    from app.services.graph_enrich_service import GraphEnrichService

    enrich_request = EnrichReq(**(request or {}))
    service = GraphEnrichService()
    result = await service.run_enrichment(enrich_request)
    return result


@router.post("/candidates/recompute")
async def recompute_candidate_graph(
    ctx: OrgContext = Depends(get_org_context),
    include_global: bool = Query(True, description="Include global scope content"),
    min_cooccurrences: int = Query(2, ge=1, le=20, description="Min chunk co-occurrences to create a candidate edge"),
    max_pairs: int = Query(20000, ge=1, le=200000, description="Maximum candidate edges to create/update"),
):
    """
    Recompute candidate (inferred) edges for exploration.

    Creates/updates (:Artigo)-[:CO_MENCIONA {layer:'candidate', verified:false, ...}]->(:Artigo)
    based on chunk co-occurrence, skipping any pair that already has an official REMETE_A.

    Admin only.
    """
    if not bool(getattr(ctx, "is_org_admin", False)):
        raise HTTPException(status_code=403, detail="Admin only")

    neo4j = get_neo4j_mvp()
    result = neo4j.recompute_candidate_comentions(
        tenant_id=ctx.tenant_id,
        include_global=bool(include_global),
        min_cooccurrences=int(min_cooccurrences),
        max_pairs=int(max_pairs),
    )
    if not result.get("ok"):
        raise HTTPException(status_code=500, detail=result.get("error", "failed"))
    return result


@router.get("/candidates/stats", response_model=List[CandidateStatsResponse])
async def get_candidate_stats(
    ctx: OrgContext = Depends(get_org_context),
    limit: int = Query(50, ge=1, le=500),
    candidate_type_prefix: Optional[str] = Query(None, description="Filter candidate_type by prefix"),
):
    """List aggregated candidate edge stats (admin only)."""
    if not bool(getattr(ctx, "is_org_admin", False)):
        raise HTTPException(status_code=403, detail="Admin only")

    neo4j = get_neo4j_mvp()
    rows = neo4j.get_candidate_edge_stats(
        tenant_id=ctx.tenant_id,
        limit=int(limit),
        candidate_type_prefix=candidate_type_prefix,
    )
    # Ensure types match response model
    out: List[CandidateStatsResponse] = []
    for r in rows or []:
        out.append(
            CandidateStatsResponse(
                candidate_type=str(r.get("candidate_type", "")),
                rel_type=str(r.get("rel_type", "")),
                edges=int(r.get("edges", 0) or 0),
                avg_confidence=float(r.get("avg_confidence", 0.0) or 0.0),
                with_evidence=int(r.get("with_evidence", 0) or 0),
                distinct_docs=int(r.get("distinct_docs", 0) or 0),
            )
        )
    return out


@router.post("/candidates/promote")
async def promote_candidate_edges(
    request: PromoteCandidatesRequest,
    ctx: OrgContext = Depends(get_org_context),
):
    """Promote candidate edges to verified (admin only)."""
    if not bool(getattr(ctx, "is_org_admin", False)):
        raise HTTPException(status_code=403, detail="Admin only")

    neo4j = get_neo4j_mvp()
    result = neo4j.promote_candidate_edges(
        tenant_id=ctx.tenant_id,
        candidate_type=request.candidate_type,
        min_confidence=float(request.min_confidence),
        require_evidence=bool(request.require_evidence),
        max_edges=int(request.max_edges),
        promote_to_typed=bool(request.promote_to_typed),
    )
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "failed"))
    return result


# =============================================================================
# LEXICAL SEARCH IN GRAPH
# =============================================================================


@router.post("/lexical-search", response_model=List[Dict[str, Any]])
async def lexical_search_entities(
    request: LexicalSearchRequest,
    ctx: OrgContext = Depends(get_org_context),
):
    """
    Search entities in the graph using Neo4j fulltext index.

    Uses the `rag_entity_fulltext` index with Lucene query syntax for efficient search.

    Supports:
    - Terms: general search terms
    - Devices: legal devices (Art. 5º, Lei 8.666, Súmula 331)
    - Authors: authors/tribunals (STF, Min. Barroso)
    - Match mode: 'any' (OR) or 'all' (AND)

    Returns entities that match the search criteria, ranked by relevance score.
    """
    neo4j = get_neo4j_mvp()
    tenant_id = ctx.tenant_id

    # Combine all search terms
    all_terms = request.terms + request.devices + request.authors

    if not all_terms:
        raise HTTPException(status_code=400, detail="At least one search term required")

    # Build Lucene query string
    # Escape special Lucene characters: + - && || ! ( ) { } [ ] ^ " ~ * ? : \ /
    def escape_lucene(term: str) -> str:
        special_chars = r'+-&|!(){}[]^"~*?:\/'
        escaped = ""
        for c in term:
            if c in special_chars:
                escaped += f"\\{c}"
            else:
                escaped += c
        return escaped

    # Build query based on match mode
    escaped_terms = [escape_lucene(t) for t in all_terms]

    if request.match_mode == "all":
        # AND: all terms must match (use Lucene AND operator)
        lucene_query = " AND ".join(escaped_terms)
    else:
        # OR: any term matches (default Lucene behavior, but explicit OR for clarity)
        lucene_query = " OR ".join(escaped_terms)

    # Use Neo4j fulltext index for efficient search
    # The rag_entity_fulltext index is on: [e.name, e.entity_id, e.normalized]
    cypher = """
    CALL db.index.fulltext.queryNodes('rag_entity_fulltext', $lucene_query) YIELD node AS e, score
    WHERE e.entity_type IN $types

    // Get mention count for additional ranking
    OPTIONAL MATCH (e)<-[:MENTIONS]-(c:Chunk)
    OPTIONAL MATCH (d:Document)-[:HAS_CHUNK]->(c)
	    WITH e, score, sum(
	        CASE
	            WHEN d IS NOT NULL
	             AND (d.tenant_id = $tenant_id OR ($include_global = true AND d.scope = 'global'))
	             AND (d.sigilo IS NULL OR d.sigilo = false)
	             AND (d.scope <> 'local')
	            THEN 1
	            ELSE 0
	        END
	    ) AS mention_count

    RETURN
        e.entity_id AS id,
        e.name AS name,
        e.entity_type AS type,
        e.normalized AS normalized,
        e.metadata AS metadata,
        score AS relevance_score,
        mention_count
    ORDER BY score DESC, mention_count DESC, e.name
    LIMIT $limit
    """

    params: Dict[str, Any] = {
        "lucene_query": lucene_query,
        "types": [t.lower() for t in request.types],
        "tenant_id": tenant_id,
        "include_global": bool(request.include_global),
        "limit": request.limit,
    }

    try:
        results = await _neo4j_read(neo4j, cypher, params)

        # Add group and parse metadata
        for r in results:
            r["group"] = get_entity_group(r.get("type", ""))
            r["metadata"] = parse_metadata(r.get("metadata"))

        return results
    except Exception as e:
        # Fallback to CONTAINS-based search if fulltext index not available
        logger.warning(f"Fulltext search failed, falling back to CONTAINS: {e}")

        # Build CONTAINS-based fallback query
        if request.match_mode == "all":
            conditions = [f"toLower(e.name) CONTAINS toLower($term{i})" for i, _ in enumerate(all_terms)]
            where_clause = " AND ".join(conditions)
        else:
            conditions = [f"toLower(e.name) CONTAINS toLower($term{i})" for i, _ in enumerate(all_terms)]
            where_clause = " OR ".join(conditions)

        fallback_cypher = f"""
        MATCH (e:Entity)
        WHERE e.entity_type IN $types
          AND ({where_clause})

	        OPTIONAL MATCH (e)<-[:MENTIONS]-(c:Chunk)
	        OPTIONAL MATCH (d:Document)-[:HAS_CHUNK]->(c)
	        WITH e, sum(
	            CASE
	                WHEN d IS NOT NULL
	                 AND (d.tenant_id = $tenant_id OR ($include_global = true AND d.scope = 'global'))
	                 AND (d.sigilo IS NULL OR d.sigilo = false)
	                 AND (d.scope <> 'local')
	                THEN 1
	                ELSE 0
	            END
	        ) AS mention_count

        RETURN
            e.entity_id AS id,
            e.name AS name,
            e.entity_type AS type,
            e.normalized AS normalized,
            e.metadata AS metadata,
            1.0 AS relevance_score,
            mention_count
        ORDER BY mention_count DESC, e.name
        LIMIT $limit
        """

        fallback_params: Dict[str, Any] = {
            "types": [t.lower() for t in request.types],
            "tenant_id": tenant_id,
            "include_global": bool(request.include_global),
            "limit": request.limit,
        }
        for i, term in enumerate(all_terms):
            fallback_params[f"term{i}"] = term

        try:
            results = await _neo4j_read(neo4j, fallback_cypher, fallback_params)
            for r in results:
                r["group"] = get_entity_group(r.get("type", ""))
                r["metadata"] = parse_metadata(r.get("metadata"))
            return results
        except Exception as fallback_error:
            logger.error(f"Error in lexical search fallback: {fallback_error}")
            raise HTTPException(status_code=500, detail=str(fallback_error))


# =============================================================================
# CONTENT SEARCH (OPENSEARCH) -> ENTITY IDS (SEED GRAPH)
# =============================================================================


@router.post("/content-search", response_model=ContentSearchResponse)
async def content_search_seed_graph(
    request: ContentSearchRequest,
    ctx: OrgContext = Depends(get_org_context),
):
    """
    Search chunk content via OpenSearch BM25 and return entity_ids to seed /graph/export.

    This is the "Modo Conteudo" for the graph UI:
    1) OpenSearch BM25 finds relevant chunks ("onde no texto")
    2) Regex extractor derives legal entities from those chunks
    3) The UI calls /graph/export with the returned entity_ids ("como se conecta")
    """
    try:
        from app.services.rag.storage.opensearch_service import get_opensearch_service
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OpenSearch service not available: {e}")

    service = get_opensearch_service()
    tenant_id = ctx.tenant_id
    user_id = str(ctx.user.id)
    group_ids = list(getattr(ctx, "team_ids", []) or [])

    indices = _opensearch_indices_for_groups(request.groups)
    if not indices:
        raise HTTPException(status_code=400, detail="No indices available for requested groups")

    doc_ids = [d for d in request.document_ids if d]
    case_ids = [c for c in request.case_ids if c]

    source_filter: Optional[Dict[str, Any]] = None
    if doc_ids or case_ids:
        must_filters: List[Dict[str, Any]] = []
        if doc_ids:
            must_filters.append({"terms": {"doc_id": doc_ids}})
        if case_ids:
            must_filters.append({"terms": {"case_id": case_ids}})
        source_filter = {"bool": {"must": must_filters}}

    try:
        logger.info(
            "[graph.content_search] tenant_id=%s user_id=%s include_global=%s doc_ids=%d case_ids=%d query_len=%d",
            tenant_id,
            user_id,
            bool(request.include_global),
            len(doc_ids),
            len(case_ids),
            len(request.query or ""),
        )
    except Exception:
        pass

    # Two-pass search:
    # - Pass 1: normal visibility (global/private/group); local only when case_id is provided (handled in OpenSearch filter).
    # - Pass 2: local-only, but ONLY when the user scopes by document_id and/or case_id (to avoid mixing locals from all cases).
    results: List[Dict[str, Any]] = []
    try:
        results.extend(
            service.search_lexical(
                query=request.query,
                indices=indices,
                top_k=request.max_chunks,
                scope=None,
                tenant_id=tenant_id,
                case_id=None,
                user_id=user_id,
                group_ids=group_ids or None,
                sigilo=None,
                include_global=bool(request.include_global),
                source_filter=source_filter,
            )
            or []
        )
    except Exception as e:
        logger.warning(f"OpenSearch content search failed (default scopes): {e}")

    if source_filter is not None:
        try:
            local_results = service.search_lexical(
                query=request.query,
                indices=[indices[0]],  # local index is always first
                top_k=request.max_chunks,
                scope="local",
                tenant_id=tenant_id,
                case_id=case_ids[0] if len(case_ids) == 1 else None,
                user_id=user_id,
                group_ids=group_ids or None,
                sigilo=None,
                include_global=False,
                source_filter=source_filter,
            )
            results.extend(local_results or [])
        except Exception as e:
            logger.warning(f"OpenSearch content search failed (local scope): {e}")

    # Deduplicate by chunk_uid
    seen_uids = set()
    unique_chunks: List[Dict[str, Any]] = []
    for r in results:
        uid = str(r.get("chunk_uid") or "")
        if not uid or uid in seen_uids:
            continue
        seen_uids.add(uid)
        unique_chunks.append(r)
        if len(unique_chunks) >= request.max_chunks:
            break

    allowed_types = {t.strip().lower() for t in (request.types or []) if t}
    counts: Dict[str, int] = {}
    sample: Dict[str, Dict[str, Any]] = {}

    for ch in unique_chunks:
        text = ch.get("text") or ""
        if not text:
            continue
        for ent in LegalEntityExtractor.extract(text):
            etype = str(ent.get("entity_type") or "").lower()
            eid = str(ent.get("entity_id") or "")
            if not eid:
                continue
            if allowed_types and etype not in allowed_types:
                continue
            counts[eid] = counts.get(eid, 0) + 1
            if eid not in sample:
                sample[eid] = ent

    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    entity_ids = [eid for eid, _ in ranked[: request.max_entities]]

    entities_out: List[Dict[str, Any]] = []
    for eid in entity_ids:
        ent = dict(sample.get(eid) or {})
        ent["mentions_in_results"] = counts.get(eid, 0)
        ent["group"] = get_entity_group(ent.get("entity_type", ""))
        entities_out.append(ent)

    return ContentSearchResponse(
        query=request.query,
        chunks_count=len(unique_chunks),
        entities_count=len(entity_ids),
        entity_ids=entity_ids,
        entities=entities_out,
    )


# =============================================================================
# ADD ENTITIES FROM RAG LOCAL
# =============================================================================


@router.post("/add-from-rag", response_model=AddFromRAGResponse)
async def add_entities_from_rag(
    request: AddFromRAGRequest,
    ctx: OrgContext = Depends(get_org_context),
):
    """
    Extract entities from RAG local documents and add them to the knowledge graph.

    This endpoint:
    1. Retrieves chunks from specified documents/cases
    2. Extracts legal entities using regex patterns
    3. Optionally uses semantic extraction (LLM) for concepts
    4. Adds new entities to Neo4j graph
    5. Creates MENTIONS relationships between chunks and entities

    Use this to populate the graph from your local document collection.
    """
    neo4j = get_neo4j_mvp()
    tenant_id = ctx.tenant_id

    if not request.document_ids and not request.case_ids:
        raise HTTPException(
            status_code=400,
            detail="At least one document_id or case_id required"
        )

    # Build query to get chunks from specified documents
    cypher_get_chunks = """
    MATCH (d:Document)-[:HAS_CHUNK]->(c:Chunk)
    WHERE d.tenant_id = $tenant_id
    """

    params: Dict[str, Any] = {"tenant_id": tenant_id}

    conditions = []
    if request.document_ids:
        # Support both canonical doc_hash and the original app-level document UUID (d.doc_id).
        conditions.append("(d.doc_id IN $doc_ids OR d.doc_hash IN $doc_ids)")
        params["doc_ids"] = request.document_ids
    if request.case_ids:
        conditions.append("d.case_id IN $case_ids")
        params["case_ids"] = request.case_ids

    if conditions:
        cypher_get_chunks += " AND (" + " OR ".join(conditions) + ")"

    cypher_get_chunks += """
    RETURN
        coalesce(d.doc_id, d.doc_hash) AS doc_id,
        d.title AS doc_title,
        c.chunk_uid AS chunk_id,
        c.text_preview AS text,
        c.chunk_index AS chunk_index
    ORDER BY d.doc_hash, c.chunk_index
    """

    try:
        chunks = await _neo4j_read(neo4j, cypher_get_chunks, params)

        if not chunks:
            return AddFromRAGResponse(
                documents_processed=0,
                chunks_processed=0,
                entities_extracted=0,
                entities_added=0,
                entities_existing=0,
                relationships_created=0,
                entities=[]
            )

        # Track results
        doc_ids_processed = set()
        all_extracted_entities = []
        entities_added = []
        entities_existing = []
        relationships_created = 0

        # Process each chunk
        for chunk in chunks:
            doc_ids_processed.add(chunk["doc_id"])
            text = chunk.get("text", "")
            chunk_id = chunk.get("chunk_id")

            if not text or not chunk_id:
                continue

            # Extract entities using regex patterns
            extracted = LegalEntityExtractor.extract(text)

            for entity in extracted:
                entity_id = entity.get("entity_id")
                if not entity_id:
                    continue

                all_extracted_entities.append(entity)

                # Check if entity exists
                exists_query = """
                MATCH (e:Entity {entity_id: $entity_id})
                RETURN e.entity_id AS id
                """
                existing = await _neo4j_read(neo4j, exists_query, {"entity_id": entity_id})

                if existing:
                    entities_existing.append(entity)
                else:
                    entities_added.append(entity)

                # Use MERGE for entity (Neo4j best practice: avoids duplicates)
                # MERGE will create if not exists, or match if exists
                merge_entity = """
                MERGE (e:Entity {entity_id: $entity_id})
                ON CREATE SET
                    e.entity_type = $entity_type,
                    e.name = $name,
                    e.normalized = $normalized,
                    e.metadata = $metadata,
                    e.created_at = datetime()
                ON MATCH SET
                    e.updated_at = datetime()
                RETURN e.entity_id AS id
                """
                # Neo4j only supports primitive types and homogeneous lists as properties
                # Maps/dicts must be serialized as JSON string
                raw_metadata = entity.get("metadata", {})
                metadata_str = json.dumps(raw_metadata) if isinstance(raw_metadata, dict) else str(raw_metadata)

                await _neo4j_write(neo4j, merge_entity, {
                    "entity_id": entity_id,
                    "entity_type": entity.get("entity_type", "unknown"),
                    "name": entity.get("name", entity_id),
                    "normalized": entity.get("normalized", entity_id),
                    "metadata": metadata_str
                })

                # MERGE relationship: MATCH nodes first, then MERGE relationship
                # This is the Neo4j best practice pattern
                merge_rel = """
                MATCH (c:Chunk {chunk_uid: $chunk_id})
                MATCH (e:Entity {entity_id: $entity_id})
                MERGE (c)-[r:MENTIONS]->(e)
                ON CREATE SET r.created_at = datetime()
                RETURN type(r) AS rel_type
                """
                result = await _neo4j_write(neo4j, merge_rel, {
                    "chunk_id": chunk_id,
                    "entity_id": entity_id
                })
                if result:
                    relationships_created += 1

        return AddFromRAGResponse(
            documents_processed=len(doc_ids_processed),
            chunks_processed=len(chunks),
            entities_extracted=len(all_extracted_entities),
            entities_added=len(entities_added),
            entities_existing=len(entities_existing),
            relationships_created=relationships_created,
            entities=entities_added[:50]  # Return first 50 new entities
        )

    except Exception as e:
        logger.error(f"Error adding entities from RAG: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# ARGUMENT GRAPH VISUALIZATION
# =============================================================================


class ArgumentGraphNode(BaseModel):
    """Node in the argument graph."""
    id: str
    type: str  # claim, evidence, actor, issue
    label: str
    claim_type: Optional[str] = None  # tese, contratese
    polarity: Optional[int] = None
    role: Optional[str] = None


class ArgumentGraphEdge(BaseModel):
    """Edge in the argument graph."""
    source: str
    target: str
    type: str  # SUPPORTS, OPPOSES, EVIDENCES, ARGUES, RAISES
    stance: Optional[str] = None
    weight: Optional[float] = None


class ArgumentGraphData(BaseModel):
    """Full argument graph for visualization."""
    nodes: List[ArgumentGraphNode]
    edges: List[ArgumentGraphEdge]
    stats: Dict[str, int]


@router.get("/argument-graph/{case_id}", response_model=ArgumentGraphData)
async def get_argument_graph(
    case_id: str,
    ctx: OrgContext = Depends(get_org_context),
):
    """
    Get the argument graph for a case.

    Returns the full debate structure (Claims, Evidence, Actors, Issues)
    with relationships (SUPPORTS, OPPOSES, EVIDENCES, ARGUES, RAISES)
    suitable for frontend visualization.

    Nodes are colored by type:
    - Claims (tese=green, contratese=red)
    - Evidence (blue)
    - Actor (orange)
    - Issue (purple)
    """
    try:
        from app.services.rag.core.argument_neo4j import get_argument_neo4j

        svc = get_argument_neo4j()
        tenant_id = ctx.tenant_id

        graph = svc.get_argument_graph(tenant_id=tenant_id, case_id=case_id)
        stats = svc.get_stats(tenant_id=tenant_id)

        nodes = [
            ArgumentGraphNode(**n) for n in graph.get("nodes", [])
        ]
        edges = [
            ArgumentGraphEdge(**e) for e in graph.get("edges", [])
        ]

        return ArgumentGraphData(
            nodes=nodes,
            edges=edges,
            stats=stats,
        )

    except Exception as e:
        logger.error("Error getting argument graph for case %s: %s", case_id, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/argument-stats", response_model=Dict[str, int])
async def get_argument_stats(
    ctx: OrgContext = Depends(get_org_context),
):
    """
    Get argument graph statistics for the current tenant.

    Returns counts of Claims, Evidence, Actors, and Issues.
    """
    try:
        from app.services.rag.core.argument_neo4j import get_argument_neo4j

        svc = get_argument_neo4j()
        tenant_id = ctx.tenant_id
        return svc.get_stats(tenant_id=tenant_id)

    except Exception as e:
        logger.error("Error getting argument stats: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# FACT NODES FROM RAG
# =============================================================================


@router.post("/add-facts-from-rag", response_model=AddFactsFromRAGResponse)
async def add_facts_from_rag(
    request: AddFactsFromRAGRequest,
    ctx: OrgContext = Depends(get_org_context),
):
    """
    Backfill Fact nodes from already-ingested local documents (Document/Chunk already in Neo4j).

    This is useful if you ingested documents before enabling `extract_facts` on ingestion.
    It uses `Chunk.text_preview` (not full text), so it's best-effort and intentionally conservative.
    """
    neo4j = get_neo4j_mvp()
    tenant_id = ctx.tenant_id

    if not request.document_ids and not request.case_ids:
        raise HTTPException(
            status_code=400,
            detail="At least one document_id or case_id required",
        )

    cypher = """
    MATCH (d:Document)-[:HAS_CHUNK]->(c:Chunk)
    WHERE d.tenant_id = $tenant_id
      AND d.scope = 'local'
    """

    params: Dict[str, Any] = {
        "tenant_id": tenant_id,
        "max_chunks": int(request.max_chunks or 2000),
    }

    conditions = []
    if request.document_ids:
        conditions.append("(d.doc_id IN $doc_ids OR d.doc_hash IN $doc_ids)")
        params["doc_ids"] = request.document_ids
    if request.case_ids:
        conditions.append("d.case_id IN $case_ids")
        params["case_ids"] = request.case_ids

    if conditions:
        cypher += " AND (" + " OR ".join(conditions) + ")"

    cypher += """
    OPTIONAL MATCH (c)-[:MENTIONS]->(e:Entity)
    RETURN
        d.doc_hash AS doc_hash,
        coalesce(d.doc_id, d.doc_hash) AS doc_id,
        d.scope AS scope,
        d.case_id AS case_id,
        c.chunk_uid AS chunk_uid,
        c.text_preview AS text,
        c.chunk_index AS chunk_index,
        collect(DISTINCT e.entity_id) AS entity_ids
    ORDER BY d.doc_hash, c.chunk_index
    LIMIT $max_chunks
    """

    try:
        rows = await _neo4j_read(neo4j, cypher, params)
        if not rows:
            return AddFactsFromRAGResponse(
                documents_processed=0,
                chunks_processed=0,
                facts_upserted=0,
                fact_refs_upserted=0,
            )

        fact_rows: List[Dict[str, Any]] = []
        docs_processed: set = set()
        max_facts = int(request.max_facts_per_chunk or 2)

        for r in rows:
            doc_hash = str(r.get("doc_hash") or "")
            doc_id = str(r.get("doc_id") or "")
            chunk_uid = str(r.get("chunk_uid") or "")
            chunk_index = int(r.get("chunk_index") or 0)
            text = str(r.get("text") or "")
            entity_ids = [str(e) for e in (r.get("entity_ids") or []) if e]

            if not doc_hash or not chunk_uid or not text.strip():
                continue

            docs_processed.add(doc_id or doc_hash)

            for fact_text in FactExtractor.extract(text, max_facts=max_facts):
                fact_norm = " ".join(fact_text.strip().lower().split())
                fact_hash = hashlib.sha256(f"{doc_hash}:{chunk_uid}:{fact_norm}".encode()).hexdigest()[:24]
                fact_id = f"fact_{fact_hash}"

                fact_rows.append(
                    {
                        "fact_id": fact_id,
                        "text": fact_text[:2000],
                        "text_preview": fact_text[:320],
                        "doc_hash": doc_hash,
                        "doc_id": doc_id or None,
                        "tenant_id": tenant_id,
                        "scope": "local",
                        "case_id": r.get("case_id"),
                        "metadata": json.dumps(
                            {"chunk_uid": chunk_uid, "chunk_index": chunk_index},
                            ensure_ascii=True,
                        ),
                        "chunk_uid": chunk_uid,
                        "entity_ids": entity_ids,
                    }
                )

        if not fact_rows:
            return AddFactsFromRAGResponse(
                documents_processed=len(docs_processed),
                chunks_processed=len(rows),
                facts_upserted=0,
                fact_refs_upserted=0,
            )

        # Batch write (UNWIND) to reduce round-trips.
        upsert_query = """
        UNWIND $rows AS row
        MERGE (f:Fact {fact_id: row.fact_id})
        ON CREATE SET
            f.text = row.text,
            f.text_preview = row.text_preview,
            f.doc_hash = row.doc_hash,
            f.doc_id = row.doc_id,
            f.tenant_id = row.tenant_id,
            f.scope = row.scope,
            f.case_id = row.case_id,
            f.metadata = row.metadata,
            f.created_at = datetime()
        ON MATCH SET
            f.updated_at = datetime()
        WITH row, f
        MATCH (c:Chunk {chunk_uid: row.chunk_uid})
        MERGE (c)-[:ASSERTS]->(f)
        WITH row, f
        UNWIND coalesce(row.entity_ids, []) AS eid
        MATCH (e:Entity {entity_id: eid})
        MERGE (f)-[:REFERS_TO]->(e)
        RETURN count(*) AS refs
        """

        batch_size = 200
        for i in range(0, len(fact_rows), batch_size):
            await _neo4j_write(neo4j, upsert_query, {"rows": fact_rows[i:i + batch_size]})

        fact_refs = sum(len(r.get("entity_ids") or []) for r in fact_rows)
        return AddFactsFromRAGResponse(
            documents_processed=len(docs_processed),
            chunks_processed=len(rows),
            facts_upserted=len(fact_rows),
            fact_refs_upserted=fact_refs,
        )

    except Exception as e:
        logger.error(f"Error adding facts from RAG: {e}")
        raise HTTPException(status_code=500, detail=str(e))
