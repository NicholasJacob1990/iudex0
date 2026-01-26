"""
Graph Backend Factory

Provides a unified interface to switch between:
- NetworkX (default): Local graph with JSON persistence
- Neo4j: Scalable graph database with Cypher queries

Usage:
    from app.services.rag.core.graph_factory import get_knowledge_graph, GraphBackend

    # Get graph based on config (RAG_GRAPH_BACKEND env var)
    graph = get_knowledge_graph()

    # Or explicitly specify backend
    graph = get_knowledge_graph(backend=GraphBackend.NEO4J)

Configuration:
    RAG_GRAPH_BACKEND=networkx  # Default, uses JSON files
    RAG_GRAPH_BACKEND=neo4j     # Uses Neo4j database

    # Neo4j specific (only needed if backend=neo4j)
    NEO4J_URI=bolt://localhost:7687
    NEO4J_USER=neo4j
    NEO4J_PASSWORD=password
    NEO4J_DATABASE=iudex
"""

from __future__ import annotations

import logging
import os
import threading
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, Tuple, TYPE_CHECKING

from app.services.rag.config import get_rag_config

if TYPE_CHECKING:
    from app.services.rag.core.graph_rag import LegalKnowledgeGraph
    from app.services.rag.core.graph_neo4j import Neo4jGraphRAG

logger = logging.getLogger(__name__)


# =============================================================================
# ENUMS
# =============================================================================


class GraphBackend(str, Enum):
    """Available graph backend implementations."""
    NETWORKX = "networkx"
    NEO4J = "neo4j"


# =============================================================================
# PROTOCOL (Interface)
# =============================================================================


class KnowledgeGraphProtocol(Protocol):
    """
    Protocol defining the interface for knowledge graph implementations.

    Both NetworkX and Neo4j implementations must satisfy this protocol.
    """

    def add_entity(
        self,
        entity_id: str,
        entity_type: str,
        name: str,
        properties: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Add an entity (node) to the graph."""
        ...

    def add_relationship(
        self,
        from_entity: str,
        to_entity: str,
        relationship_type: str,
        properties: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Add a relationship (edge) between entities."""
        ...

    def get_entity(self, entity_id: str) -> Optional[Dict[str, Any]]:
        """Get entity by ID."""
        ...

    def get_neighbors(
        self,
        entity_id: str,
        relationship_types: Optional[List[str]] = None,
        max_hops: int = 1,
    ) -> List[Dict[str, Any]]:
        """Get neighboring entities."""
        ...

    def search_entities(
        self,
        query: str,
        entity_types: Optional[List[str]] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Search entities by text."""
        ...

    def get_context_for_query(
        self,
        query: str,
        max_tokens: int = 2000,
    ) -> str:
        """Get relevant graph context for a query."""
        ...

    def persist(self) -> bool:
        """Persist graph state."""
        ...

    def close(self) -> None:
        """Close connections and cleanup."""
        ...


# =============================================================================
# ADAPTER FOR NETWORKX
# =============================================================================


class NetworkXAdapter:
    """
    Adapter wrapping LegalKnowledgeGraph to satisfy KnowledgeGraphProtocol.
    """

    def __init__(
        self,
        persist_path: Optional[str] = None,
        scope: str = "global",
        scope_id: Optional[str] = None,
    ):
        from app.services.rag.core.graph_rag import LegalKnowledgeGraph

        self._scope = scope
        self._scope_id = scope_id

        # Determine persist path
        if persist_path is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            scope_key = f"{scope}_{scope_id}" if scope_id else scope
            persist_path = os.path.join(
                base_dir, "data", "graph_db", "scopes", f"knowledge_graph_{scope_key}.json"
            )

        self._graph = LegalKnowledgeGraph(persist_path=persist_path)
        self._persist_path = persist_path
        logger.info(f"NetworkX graph initialized: {persist_path}")

    @property
    def backend(self) -> GraphBackend:
        return GraphBackend.NETWORKX

    @property
    def inner_graph(self) -> "LegalKnowledgeGraph":
        """Access the underlying LegalKnowledgeGraph."""
        return self._graph

    def add_entity(
        self,
        entity_id: str,
        entity_type: str,
        name: str,
        properties: Optional[Dict[str, Any]] = None,
    ) -> bool:
        try:
            from app.services.rag.core.graph_rag import EntityType, Scope

            # Map string to EntityType enum
            try:
                etype = EntityType(entity_type.lower())
            except ValueError:
                etype = EntityType.OUTRO

            # Map scope string to Scope enum
            try:
                scope = Scope(self._scope.lower())
            except ValueError:
                scope = Scope.PRIVATE

            self._graph.add_entity(
                entity_id=entity_id,
                entity_type=etype,
                name=name,
                scope=scope,
                scope_id=self._scope_id,
                properties=properties or {},
            )
            return True
        except Exception as e:
            logger.error(f"Error adding entity: {e}")
            return False

    def add_relationship(
        self,
        from_entity: str,
        to_entity: str,
        relationship_type: str,
        properties: Optional[Dict[str, Any]] = None,
    ) -> bool:
        try:
            from app.services.rag.core.graph_rag import RelationType

            # Map string to RelationType enum
            try:
                rtype = RelationType(relationship_type.lower())
            except ValueError:
                rtype = RelationType.MENCIONA

            self._graph.add_relationship(
                from_id=from_entity,
                to_id=to_entity,
                rel_type=rtype,
                properties=properties or {},
            )
            return True
        except Exception as e:
            logger.error(f"Error adding relationship: {e}")
            return False

    def get_entity(self, entity_id: str) -> Optional[Dict[str, Any]]:
        try:
            return self._graph.get_entity(entity_id)
        except Exception:
            return None

    def get_neighbors(
        self,
        entity_id: str,
        relationship_types: Optional[List[str]] = None,
        max_hops: int = 1,
    ) -> List[Dict[str, Any]]:
        try:
            neighbors = self._graph.get_neighbors(
                entity_id=entity_id,
                max_hops=max_hops,
            )
            return neighbors
        except Exception as e:
            logger.error(f"Error getting neighbors: {e}")
            return []

    def search_entities(
        self,
        query: str,
        entity_types: Optional[List[str]] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        try:
            results = self._graph.search(query=query, limit=limit)
            if entity_types:
                results = [r for r in results if r.get("entity_type") in entity_types]
            return results[:limit]
        except Exception as e:
            logger.error(f"Error searching entities: {e}")
            return []

    def get_context_for_query(
        self,
        query: str,
        max_tokens: int = 2000,
    ) -> str:
        try:
            return self._graph.get_context_for_query(query=query, max_tokens=max_tokens)
        except Exception as e:
            logger.error(f"Error getting context: {e}")
            return ""

    def persist(self) -> bool:
        try:
            self._graph.persist()
            return True
        except Exception as e:
            logger.error(f"Error persisting graph: {e}")
            return False

    def close(self) -> None:
        try:
            self._graph.persist()
        except Exception:
            pass


# =============================================================================
# ADAPTER FOR NEO4J
# =============================================================================


class Neo4jAdapter:
    """
    Adapter wrapping Neo4jGraphRAG to satisfy KnowledgeGraphProtocol.
    """

    def __init__(
        self,
        uri: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        database: Optional[str] = None,
    ):
        config = get_rag_config()

        self._uri = uri or config.neo4j_uri
        self._user = user or config.neo4j_user
        self._password = password or config.neo4j_password
        self._database = database or config.neo4j_database
        self._hybrid_enabled = bool(getattr(config, "graph_hybrid_mode", False))
        self._auto_schema = bool(getattr(config, "graph_hybrid_auto_schema", True))
        self._migrate_on_startup = bool(getattr(config, "graph_hybrid_migrate_on_startup", False))

        self._driver = None
        self._connect()

    def _connect(self) -> None:
        """Establish connection to Neo4j."""
        try:
            from neo4j import GraphDatabase
            from app.services.rag.core.graph_hybrid import ensure_neo4j_schema, migrate_hybrid_labels

            self._driver = GraphDatabase.driver(
                self._uri,
                auth=(self._user, self._password),
            )
            # Test connection
            with self._driver.session(database=self._database) as session:
                session.run("RETURN 1")
                if self._auto_schema:
                    ensure_neo4j_schema(session, hybrid=self._hybrid_enabled)
                if self._hybrid_enabled and self._migrate_on_startup:
                    migrate_hybrid_labels(session)
            logger.info(f"Neo4j connected: {self._uri}")
        except ImportError:
            raise ImportError("neo4j package required: pip install neo4j")
        except Exception as e:
            logger.error(f"Neo4j connection failed: {e}")
            raise

    @property
    def backend(self) -> GraphBackend:
        return GraphBackend.NEO4J

    @property
    def driver(self):
        """Access the underlying Neo4j driver."""
        return self._driver

    def add_entity(
        self,
        entity_id: str,
        entity_type: str,
        name: str,
        properties: Optional[Dict[str, Any]] = None,
    ) -> bool:
        try:
            from app.services.rag.core.graph_hybrid import label_for_entity_type

            props = properties or {}
            label = label_for_entity_type(entity_type) if self._hybrid_enabled else None
            label_clause = f":{label}" if label else ""
            query = f"""
            MERGE (e:Entity{label_clause} {{entity_id: $entity_id}})
            ON CREATE SET
                e.name = $name,
                e.entity_type = $entity_type,
                e.created_at = datetime(),
                e += $properties
            ON MATCH SET
                e.updated_at = datetime(),
                e += $properties
            RETURN e
            """
            with self._driver.session(database=self._database) as session:
                session.run(
                    query,
                    entity_id=entity_id,
                    name=name,
                    entity_type=entity_type,
                    properties=props,
                )
            return True
        except Exception as e:
            logger.error(f"Neo4j add_entity error: {e}")
            return False

    def migrate_hybrid_labels(self) -> Dict[str, int]:
        """Backfill hybrid labels based on Entity.entity_type."""
        from app.services.rag.core.graph_hybrid import migrate_hybrid_labels

        with self._driver.session(database=self._database) as session:
            return migrate_hybrid_labels(session)

    def add_relationship(
        self,
        from_entity: str,
        to_entity: str,
        relationship_type: str,
        properties: Optional[Dict[str, Any]] = None,
    ) -> bool:
        try:
            props = properties or {}
            # Sanitize relationship type for Cypher
            rel_type = relationship_type.upper().replace(" ", "_")

            query = f"""
            MATCH (a:Entity {{entity_id: $from_id}})
            MATCH (b:Entity {{entity_id: $to_id}})
            MERGE (a)-[r:{rel_type}]->(b)
            ON CREATE SET r.created_at = datetime(), r += $properties
            ON MATCH SET r.updated_at = datetime(), r += $properties
            RETURN r
            """
            with self._driver.session(database=self._database) as session:
                session.run(
                    query,
                    from_id=from_entity,
                    to_id=to_entity,
                    properties=props,
                )
            return True
        except Exception as e:
            logger.error(f"Neo4j add_relationship error: {e}")
            return False

    def get_entity(self, entity_id: str) -> Optional[Dict[str, Any]]:
        try:
            query = """
            MATCH (e:Entity {entity_id: $entity_id})
            RETURN e
            """
            with self._driver.session(database=self._database) as session:
                result = session.run(query, entity_id=entity_id)
                record = result.single()
                if record:
                    node = record["e"]
                    return dict(node)
            return None
        except Exception as e:
            logger.error(f"Neo4j get_entity error: {e}")
            return None

    def get_neighbors(
        self,
        entity_id: str,
        relationship_types: Optional[List[str]] = None,
        max_hops: int = 1,
    ) -> List[Dict[str, Any]]:
        try:
            # Build relationship filter
            if relationship_types:
                rel_filter = "|".join(r.upper().replace(" ", "_") for r in relationship_types)
                rel_pattern = f"[r:{rel_filter}*1..{max_hops}]"
            else:
                rel_pattern = f"[r*1..{max_hops}]"

            query = f"""
            MATCH (start:Entity {{entity_id: $entity_id}})-{rel_pattern}-(neighbor:Entity)
            RETURN DISTINCT neighbor,
                   length(shortestPath((start)-[*]-(neighbor))) as distance
            ORDER BY distance
            LIMIT 50
            """
            neighbors = []
            with self._driver.session(database=self._database) as session:
                result = session.run(query, entity_id=entity_id)
                for record in result:
                    node_data = dict(record["neighbor"])
                    node_data["distance"] = record["distance"]
                    neighbors.append(node_data)
            return neighbors
        except Exception as e:
            logger.error(f"Neo4j get_neighbors error: {e}")
            return []

    def search_entities(
        self,
        query: str,
        entity_types: Optional[List[str]] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        try:
            # Use full-text search if available, otherwise CONTAINS
            type_filter = ""
            if entity_types:
                types_str = ", ".join(f"'{t}'" for t in entity_types)
                type_filter = f"AND e.entity_type IN [{types_str}]"

            cypher = f"""
            MATCH (e:Entity)
            WHERE (e.name CONTAINS $search_term OR e.entity_id CONTAINS $search_term)
            {type_filter}
            RETURN e
            LIMIT $max_results
            """
            results = []
            with self._driver.session(database=self._database) as session:
                result = session.run(cypher, search_term=query, max_results=limit)
                for record in result:
                    results.append(dict(record["e"]))
            return results
        except Exception as e:
            logger.error(f"Neo4j search_entities error: {e}")
            return []

    def get_context_for_query(
        self,
        query: str,
        max_tokens: int = 2000,
    ) -> str:
        """
        Build context from graph for a query.

        Strategy:
        1. Search for relevant entities
        2. Get their neighbors
        3. Build readable context string
        """
        try:
            # Find relevant entities
            entities = self.search_entities(query, limit=5)
            if not entities:
                return ""

            context_parts = []
            chars_per_token = 4
            max_chars = max_tokens * chars_per_token
            current_chars = 0

            for entity in entities:
                entity_id = entity.get("entity_id", "")
                entity_name = entity.get("name", entity_id)
                entity_type = entity.get("entity_type", "unknown")

                # Get relationships
                neighbors = self.get_neighbors(entity_id, max_hops=1)

                # Build context for this entity
                entity_context = f"[{entity_type}] {entity_name}"
                if neighbors:
                    relations = []
                    for n in neighbors[:5]:  # Limit neighbors
                        n_name = n.get("name", n.get("entity_id", "?"))
                        relations.append(n_name)
                    if relations:
                        entity_context += f" → relacionado com: {', '.join(relations)}"

                if current_chars + len(entity_context) > max_chars:
                    break

                context_parts.append(entity_context)
                current_chars += len(entity_context)

            return "\n".join(context_parts)
        except Exception as e:
            logger.error(f"Neo4j get_context_for_query error: {e}")
            return ""

    def persist(self) -> bool:
        # Neo4j persists automatically
        return True

    def close(self) -> None:
        if self._driver:
            self._driver.close()
            logger.info("Neo4j connection closed")


# =============================================================================
# FACTORY
# =============================================================================

# Singleton instances
_graph_instances: Dict[str, KnowledgeGraphProtocol] = {}
_lock = threading.Lock()


def get_knowledge_graph(
    backend: Optional[GraphBackend] = None,
    scope: str = "global",
    scope_id: Optional[str] = None,
    **kwargs,
) -> KnowledgeGraphProtocol:
    """
    Get or create a knowledge graph instance.

    Args:
        backend: GraphBackend.NETWORKX or GraphBackend.NEO4J.
                 If None, uses RAG_GRAPH_BACKEND env var.
        scope: Scope for data isolation (global, private, group, local)
        scope_id: Scope identifier (e.g., user_id, group_id)
        **kwargs: Additional arguments passed to the backend

    Returns:
        KnowledgeGraphProtocol implementation

    Example:
        # Use configured backend
        graph = get_knowledge_graph()

        # Explicit backend
        graph = get_knowledge_graph(backend=GraphBackend.NEO4J)

        # Scoped graph
        graph = get_knowledge_graph(scope="private", scope_id="user_123")
    """
    config = get_rag_config()

    # Determine backend
    if backend is None:
        backend_str = config.graph_backend.lower()
        try:
            backend = GraphBackend(backend_str)
        except ValueError:
            logger.warning(f"Unknown graph backend '{backend_str}', using networkx")
            backend = GraphBackend.NETWORKX

    # Cache key
    cache_key = f"{backend.value}:{scope}:{scope_id or 'default'}"

    with _lock:
        if cache_key in _graph_instances:
            return _graph_instances[cache_key]

        # Create new instance
        if backend == GraphBackend.NEO4J:
            try:
                graph = Neo4jAdapter(**kwargs)
                logger.info(f"Using Neo4j graph backend (scope={scope})")
            except Exception as e:
                logger.warning(f"Neo4j unavailable ({e}), falling back to NetworkX")
                graph = NetworkXAdapter(scope=scope, scope_id=scope_id, **kwargs)
        else:
            graph = NetworkXAdapter(scope=scope, scope_id=scope_id, **kwargs)
            logger.info(f"Using NetworkX graph backend (scope={scope})")

        _graph_instances[cache_key] = graph
        return graph


def reset_knowledge_graph(
    scope: str = "global",
    scope_id: Optional[str] = None,
) -> None:
    """Reset cached graph instance for a scope."""
    with _lock:
        keys_to_remove = [
            k for k in _graph_instances
            if k.endswith(f":{scope}:{scope_id or 'default'}")
        ]
        for key in keys_to_remove:
            instance = _graph_instances.pop(key, None)
            if instance:
                instance.close()


def close_all_graphs() -> None:
    """Close all cached graph instances."""
    with _lock:
        for key, instance in _graph_instances.items():
            try:
                instance.close()
            except Exception as e:
                logger.error(f"Error closing graph {key}: {e}")
        _graph_instances.clear()


def is_neo4j_available() -> bool:
    """Check if Neo4j is available and can be connected."""
    config = get_rag_config()
    try:
        from neo4j import GraphDatabase

        driver = GraphDatabase.driver(
            config.neo4j_uri,
            auth=(config.neo4j_user, config.neo4j_password),
        )
        with driver.session(database=config.neo4j_database) as session:
            session.run("RETURN 1")
        driver.close()
        return True
    except Exception:
        return False
