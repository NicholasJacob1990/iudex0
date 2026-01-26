"""
Graph Visualization API Endpoints

Endpoints for exploring and visualizing the legal knowledge graph.
Supports:
- Entity search by type (legislacao, jurisprudencia, doutrina)
- Entity details with neighbors
- Graph export for D3.js/force-graph visualization
- Path finding between entities

All endpoints require authentication and use the user's ID as tenant_id.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.security import get_current_user
from app.models.user import User
from app.services.rag.core.neo4j_mvp import (
    EntityType,
    LegalEntityExtractor,
    get_neo4j_mvp,
)

logger = logging.getLogger(__name__)

router = APIRouter()


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
}

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


# =============================================================================
# ENDPOINTS
# =============================================================================


@router.get("/entities", response_model=List[Dict[str, Any]])
async def search_entities(
    current_user: User = Depends(get_current_user),
    query: Optional[str] = Query(None, description="Search query"),
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
    tenant_id = str(current_user.id)

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
             AND (d.tenant_id = $tenant_id OR d.scope = 'global')
             AND (d.sigilo IS NULL OR d.sigilo = false)
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
        results = neo4j._execute_read(cypher, params)

        # Add group to results
        for r in results:
            r["group"] = get_entity_group(r.get("type", ""))

        return results
    except Exception as e:
        logger.error(f"Error searching entities: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/entity/{entity_id}", response_model=EntityDetail)
async def get_entity_detail(
    entity_id: str,
    current_user: User = Depends(get_current_user),
    include_chunks: bool = Query(True),
    max_neighbors: int = Query(20, ge=1, le=100),
):
    """
    Get detailed information about an entity including neighbors and chunks.
    """
    neo4j = get_neo4j_mvp()
    tenant_id = str(current_user.id)

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
        entity_results = neo4j._execute_read(entity_query, {"entity_id": entity_id})

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
          AND (d.tenant_id = $tenant_id OR d.scope = 'global')
          AND (d.sigilo IS NULL OR d.sigilo = false)
        WITH e, neighbor, 'co_occurrence' AS rel_type, count(DISTINCT c) AS weight

        // Also get RELATED_TO relationships
        UNION

        MATCH (e:Entity {entity_id: $entity_id})-[:RELATED_TO]-(neighbor:Entity)
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

        neighbors = neo4j._execute_read(
            neighbors_query,
            {"entity_id": entity_id, "tenant_id": tenant_id, "limit": max_neighbors}
        )

        # Get chunks mentioning this entity
        chunks = []
        if include_chunks:
            chunks_query = """
            MATCH (e:Entity {entity_id: $entity_id})<-[:MENTIONS]-(c:Chunk)
            MATCH (d:Document)-[:HAS_CHUNK]->(c)
            WHERE (d.tenant_id = $tenant_id OR d.scope = 'global')
              AND (d.sigilo IS NULL OR d.sigilo = false)
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

            chunks = neo4j._execute_read(chunks_query, {"entity_id": entity_id, "tenant_id": tenant_id})

        return EntityDetail(
            id=entity["id"],
            name=entity["name"],
            type=entity["type"],
            normalized=entity.get("normalized", ""),
            metadata=entity.get("metadata") or {},
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
    current_user: User = Depends(get_current_user),
    entity_ids: Optional[str] = Query(
        None,
        description="Comma-separated entity IDs to start from"
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
    tenant_id = str(current_user.id)

    type_list = [t.strip().lower() for t in types.split(",") if t.strip()]
    group_list = [g.strip().lower() for g in groups.split(",") if g.strip()]

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
                  AND (d.tenant_id = $tenant_id OR d.scope = 'global')
                  AND (d.sigilo IS NULL OR d.sigilo = false)
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

            results = neo4j._execute_read(seed_query, {
                "seed_ids": seed_ids,
                "types": type_list,
                "tenant_id": tenant_id,
                "max_neighbors": max_nodes // 2
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
                        metadata=r.get("metadata") or {},
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
                     AND (d.tenant_id = $tenant_id OR d.scope = 'global')
                     AND (d.sigilo IS NULL OR d.sigilo = false)
                    THEN 1
                    ELSE 0
                END
            ) AS mention_count
            ORDER BY mention_count DESC
            LIMIT $limit
            RETURN
                e.entity_id AS id,
                e.name AS name,
                e.entity_type AS type,
                e.metadata AS metadata,
                mention_count
            """

            results = neo4j._execute_read(top_query, {
                "types": type_list,
                "tenant_id": tenant_id,
                "limit": max_nodes
            })

            for r in results:
                entity_type = r.get("type", "")
                group = get_entity_group(entity_type)

                if group in group_list:
                    nodes.append(GraphNode(
                        id=r["id"],
                        label=r["name"],
                        type=entity_type,
                        group=group,
                        metadata=r.get("metadata") or {},
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
                  AND (d.tenant_id = $tenant_id OR d.scope = 'global')
                  AND (d.sigilo IS NULL OR d.sigilo = false)
                WITH e1, e2, count(DISTINCT c) AS weight
                RETURN
                    e1.entity_id AS source,
                    e2.entity_id AS target,
                    weight
                ORDER BY weight DESC
                LIMIT 200
                """

                rel_results = neo4j._execute_read(rel_query, {"node_ids": list(node_ids), "tenant_id": tenant_id})

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
                RETURN
                    e1.entity_id AS source,
                    e2.entity_id AS target,
                    coalesce(r.weight, 1) AS weight
                LIMIT 200
                """
                rel_related_results = neo4j._execute_read(
                    rel_related_query, {"node_ids": list(node_ids)}
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

        return GraphData(nodes=nodes, links=links)

    except Exception as e:
        logger.error(f"Error exporting graph: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/path")
async def find_path(
    source_id: str = Query(..., description="Source entity ID"),
    target_id: str = Query(..., description="Target entity ID"),
    current_user: User = Depends(get_current_user),
    max_length: int = Query(4, ge=1, le=6),
):
    """
    Find paths between two entities.

    Useful for understanding how legal concepts are connected.
    """
    neo4j = get_neo4j_mvp()
    tenant_id = str(current_user.id)

    path_query = f"""
    MATCH (e1:Entity {{entity_id: $source_id}})
    MATCH (e2:Entity {{entity_id: $target_id}})
    MATCH path = shortestPath((e1)-[:MENTIONS|RELATED_TO*1..{max_length}]-(e2))
    WHERE all(n IN nodes(path) WHERE NOT n:Chunk OR exists {{
        MATCH (d:Document)-[:HAS_CHUNK]->(n)
        WHERE (d.tenant_id = $tenant_id OR d.scope = 'global')
          AND (d.sigilo IS NULL OR d.sigilo = false)
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
        results = neo4j._execute_read(path_query, {
            "source_id": source_id,
            "target_id": target_id,
            "tenant_id": tenant_id,
        })

        if not results:
            return {
                "found": False,
                "message": f"No path found between {source_id} and {target_id} within {max_length} hops"
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
            "paths": paths
        }

    except Exception as e:
        logger.error(f"Error finding path: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats", response_model=GraphStats)
async def get_graph_stats(current_user: User = Depends(get_current_user)):
    """
    Get statistics about the knowledge graph.
    """
    neo4j = get_neo4j_mvp()
    tenant_id = str(current_user.id)

    stats_query = """
    MATCH (d:Document)
    WHERE (d.tenant_id = $tenant_id OR d.scope = 'global')
      AND (d.sigilo IS NULL OR d.sigilo = false)
    WITH count(DISTINCT d) AS total_documents

    MATCH (d:Document)-[:HAS_CHUNK]->(c:Chunk)
    WHERE (d.tenant_id = $tenant_id OR d.scope = 'global')
      AND (d.sigilo IS NULL OR d.sigilo = false)
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
    WHERE (d.tenant_id = $tenant_id OR d.scope = 'global')
      AND (d.sigilo IS NULL OR d.sigilo = false)
    MATCH (d)-[:HAS_CHUNK]->(c:Chunk)-[:MENTIONS]->(e:Entity)
    RETURN e.entity_type AS type, count(DISTINCT e) AS count
    ORDER BY count DESC
    """

    try:
        stats_result = neo4j._execute_read(stats_query, {"tenant_id": tenant_id})
        type_counts = neo4j._execute_read(type_count_query, {"tenant_id": tenant_id})

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
    current_user: User = Depends(get_current_user),
    limit: int = Query(30, ge=1, le=100),
):
    """
    Get semantically related entities based on co-occurrence and context.

    This is the main endpoint for discovering relationships between legal concepts.
    Returns entities that frequently appear together in the same document contexts.
    """
    neo4j = get_neo4j_mvp()
    tenant_id = str(current_user.id)

    # Query for entities that co-occur in the same chunks
    semantic_query = """
    MATCH (e:Entity {entity_id: $entity_id})

    // Find chunks mentioning this entity
    MATCH (e)<-[:MENTIONS]-(c:Chunk)
    MATCH (d0:Document)-[:HAS_CHUNK]->(c)
    WHERE (d0.tenant_id = $tenant_id OR d0.scope = 'global')
      AND (d0.sigilo IS NULL OR d0.sigilo = false)

    // Find other entities in the same chunks (semantic co-occurrence)
    MATCH (c)-[:MENTIONS]->(other:Entity)
    WHERE other.entity_id <> e.entity_id

    // Count co-occurrences and gather context
    WITH other, count(DISTINCT c) AS co_occurrences,
         collect(DISTINCT c.text_preview)[0..3] AS sample_contexts

    // Get document info for context
    OPTIONAL MATCH (other)<-[:MENTIONS]-(oc:Chunk)<-[:HAS_CHUNK]-(d:Document)
    WHERE (d.tenant_id = $tenant_id OR d.scope = 'global')
      AND (d.sigilo IS NULL OR d.sigilo = false)

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
        results = neo4j._execute_read(semantic_query, {
            "entity_id": entity_id,
            "tenant_id": tenant_id,
            "limit": limit
        })

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
    current_user: User = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=200),
):
    """
    Get remissões (cross-references) for a legal entity.

    Shows all other legal provisions that reference or are referenced by this entity.
    Particularly useful for articles of law.
    """
    neo4j = get_neo4j_mvp()
    tenant_id = str(current_user.id)

    remissoes_query = """
    // Find entity
    MATCH (e:Entity {entity_id: $entity_id})

    // Find chunks that mention this entity
    MATCH (e)<-[:MENTIONS]-(c:Chunk)
    MATCH (d0:Document)-[:HAS_CHUNK]->(c)
    WHERE (d0.tenant_id = $tenant_id OR d0.scope = 'global')
      AND (d0.sigilo IS NULL OR d0.sigilo = false)

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
                 AND (d1.tenant_id = $tenant_id OR d1.scope = 'global')
                 AND (d1.sigilo IS NULL OR d1.sigilo = false)
                THEN sample.text_preview
                ELSE NULL
            END
         )[0] AS sample_text

    RETURN
        other.entity_id AS id,
        other.name AS name,
        other.entity_type AS type,
        other.normalized AS normalized,
        co_occurrences,
        sample_text
    ORDER BY co_occurrences DESC
    LIMIT $limit
    """

    try:
        results = neo4j._execute_read(remissoes_query, {
            "entity_id": entity_id,
            "tenant_id": tenant_id,
            "limit": limit
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
