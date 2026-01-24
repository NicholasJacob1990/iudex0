"""
Neo4j Graph RAG Integration

Provides scalable graph storage with:
- Entity embeddings (TransE, RotatE, ComplEx)
- Reasoning paths with explainable traversals
- Cypher queries for legal relationships
- Integration with existing LegalKnowledgeGraph

Designed for Brazilian legal domain with support for:
- Laws, Articles, Sumulas, Jurisprudence
- Citation networks and amendment histories
- Court hierarchies and precedent chains
"""

from __future__ import annotations

import hashlib
import logging
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import (
    Any,
    Dict,
    Iterator,
    List,
    Optional,
    Set,
    Tuple,
    Union,
)

import numpy as np

from app.services.rag.core.graph_rag import (
    EntityType,
    RelationType,
    Scope,
    LegalEntityExtractor,
)

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================


class EmbeddingMethod(str, Enum):
    """Knowledge graph embedding methods."""
    TRANSE = "transe"      # Translation-based: h + r = t
    ROTATE = "rotate"      # Rotation-based: h * r = t (complex space)
    COMPLEX = "complex"    # ComplEx: uses complex-valued embeddings
    DISTMULT = "distmult"  # Diagonal bilinear model


@dataclass
class Neo4jConfig:
    """Configuration for Neo4j connection and embeddings."""

    # Connection settings
    uri: str = "bolt://localhost:7687"
    user: str = "neo4j"
    password: str = "password"
    database: str = "iudex"

    # Connection pool settings
    max_connection_lifetime: int = 3600
    max_connection_pool_size: int = 50
    connection_acquisition_timeout: int = 60

    # Entity embedding configuration
    embedding_dim: int = 128
    embedding_method: EmbeddingMethod = EmbeddingMethod.ROTATE
    embedding_margin: float = 1.0  # Margin for TransE
    embedding_gamma: float = 12.0  # Margin for RotatE

    # Query configuration
    max_hops: int = 3
    max_paths: int = 10
    max_results: int = 100
    query_timeout: int = 30  # seconds

    # Index configuration
    create_indexes: bool = True
    use_vector_index: bool = True
    vector_similarity: str = "cosine"  # cosine, euclidean

    @classmethod
    def from_env(cls) -> "Neo4jConfig":
        """Load configuration from environment variables."""
        return cls(
            uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
            user=os.getenv("NEO4J_USER", "neo4j"),
            password=os.getenv("NEO4J_PASSWORD", "password"),
            database=os.getenv("NEO4J_DATABASE", "iudex"),
            embedding_dim=int(os.getenv("NEO4J_EMBEDDING_DIM", "128")),
            embedding_method=EmbeddingMethod(
                os.getenv("NEO4J_EMBEDDING_METHOD", "rotate")
            ),
            max_hops=int(os.getenv("NEO4J_MAX_HOPS", "3")),
            max_paths=int(os.getenv("NEO4J_MAX_PATHS", "10")),
        )


@dataclass
class ReasoningPath:
    """
    Represents an explainable reasoning path in the graph.

    Example path:
        Art. 5 CF/88 --FUNDAMENTA--> Sumula 123 STF --CITA--> RE 12345
    """
    start_entity: str
    end_entity: str
    path: List[Tuple[str, str, str]]  # [(node1, relationship, node2), ...]
    score: float
    explanation: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def length(self) -> int:
        """Number of hops in the path."""
        return len(self.path)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "start_entity": self.start_entity,
            "end_entity": self.end_entity,
            "path": [
                {"from": p[0], "relationship": p[1], "to": p[2]}
                for p in self.path
            ],
            "score": self.score,
            "explanation": self.explanation,
            "length": self.length,
            "metadata": self.metadata,
        }


@dataclass
class EntityEmbedding:
    """Entity embedding with metadata."""
    entity_id: str
    entity_type: str
    embedding: np.ndarray
    method: EmbeddingMethod
    created_at: datetime = field(default_factory=datetime.now)

    def similarity(self, other: "EntityEmbedding") -> float:
        """Compute cosine similarity with another embedding."""
        norm_self = np.linalg.norm(self.embedding)
        norm_other = np.linalg.norm(other.embedding)
        if norm_self == 0 or norm_other == 0:
            return 0.0
        return float(np.dot(self.embedding, other.embedding) / (norm_self * norm_other))


# =============================================================================
# CYPHER QUERY TEMPLATES
# =============================================================================


class CypherTemplates:
    """
    Cypher query templates for legal domain patterns.

    Templates use parameter placeholders ($param) for safe query execution.
    """

    # -------------------------------------------------------------------------
    # Entity Creation
    # -------------------------------------------------------------------------

    CREATE_ENTITY = """
    MERGE (e:{label} {{entity_id: $entity_id}})
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

    CREATE_ENTITY_WITH_EMBEDDING = """
    MERGE (e:{label} {{entity_id: $entity_id}})
    ON CREATE SET
        e.name = $name,
        e.entity_type = $entity_type,
        e.embedding = $embedding,
        e.embedding_method = $embedding_method,
        e.created_at = datetime(),
        e += $properties
    ON MATCH SET
        e.embedding = $embedding,
        e.embedding_method = $embedding_method,
        e.updated_at = datetime(),
        e += $properties
    RETURN e
    """

    # -------------------------------------------------------------------------
    # Relationship Creation
    # -------------------------------------------------------------------------

    CREATE_RELATIONSHIP = """
    MATCH (from {{entity_id: $from_id}})
    MATCH (to {{entity_id: $to_id}})
    MERGE (from)-[r:{rel_type}]->(to)
    ON CREATE SET
        r.created_at = datetime(),
        r.weight = $weight,
        r += $properties
    ON MATCH SET
        r.updated_at = datetime(),
        r.weight = $weight,
        r += $properties
    RETURN from, r, to
    """

    # -------------------------------------------------------------------------
    # Legal Citation Patterns
    # -------------------------------------------------------------------------

    # Find all decisions citing a specific law article
    CITING_DECISIONS = """
    MATCH (art:ARTIGO {entity_id: $article_id})
    OPTIONAL MATCH (lei:LEI)-[:POSSUI]->(art)
    MATCH (dec)-[c:CITA|APLICA|INTERPRETA]->(art)
    WHERE dec:JURISPRUDENCIA OR dec:ACORDAO OR dec:SUMULA
    {court_filter}
    RETURN dec.entity_id AS decision_id,
           dec.name AS decision_name,
           type(c) AS citation_type,
           lei.name AS law_name,
           dec.tribunal AS court,
           dec.data_julgamento AS decision_date
    ORDER BY dec.data_julgamento DESC
    LIMIT $limit
    """

    # Get amendment history of a law
    LAW_AMENDMENTS = """
    MATCH path = (lei:LEI {{entity_id: $law_id}})<-[:ALTERA|REVOGA*1..5]-(alteracao:LEI)
    RETURN lei.name AS original_law,
           [n IN nodes(path)[1..] | {{
               law_id: n.entity_id,
               name: n.name,
               year: n.ano,
               type: CASE
                   WHEN (n)-[:REVOGA]->(lei) THEN 'revogacao'
                   ELSE 'alteracao'
               END
           }}] AS amendments
    ORDER BY alteracao.ano DESC
    """

    # Find related sumulas by topic/theme
    RELATED_SUMULAS = """
    MATCH (s:SUMULA)
    WHERE toLower(s.name) CONTAINS toLower($topic)
       OR toLower(s.ementa) CONTAINS toLower($topic)
       OR ANY(tag IN s.tags WHERE toLower(tag) CONTAINS toLower($topic))
    {court_filter}
    OPTIONAL MATCH (s)-[:VINCULA]->(t:TESE)
    OPTIONAL MATCH (s)<-[:CITA]-(dec)
    WITH s, t, count(dec) AS citation_count
    RETURN s.entity_id AS sumula_id,
           s.name AS sumula_name,
           s.tribunal AS court,
           s.ementa AS summary,
           collect(DISTINCT t.text)[0..3] AS theses,
           citation_count
    ORDER BY citation_count DESC
    LIMIT $limit
    """

    # -------------------------------------------------------------------------
    # Reasoning Path Queries
    # -------------------------------------------------------------------------

    # Find shortest path between two entities
    SHORTEST_PATH = """
    MATCH path = shortestPath(
        (start {{entity_id: $start_id}})-[*1..{max_hops}]-(end {{entity_id: $end_id}})
    )
    {relationship_filter}
    RETURN path,
           length(path) AS hops,
           [r IN relationships(path) | type(r)] AS relationship_types,
           [n IN nodes(path) | n.name] AS node_names
    """

    # Find all paths between entities (with scoring)
    ALL_PATHS = """
    MATCH path = (start {{entity_id: $start_id}})-[*1..{max_hops}]-(end {{entity_id: $end_id}})
    {relationship_filter}
    WITH path,
         length(path) AS hops,
         reduce(s = 0.0, r IN relationships(path) | s + coalesce(r.weight, 1.0)) AS total_weight
    RETURN path,
           hops,
           total_weight,
           [r IN relationships(path) | type(r)] AS relationship_types,
           [n IN nodes(path) | {{id: n.entity_id, name: n.name, type: n.entity_type}}] AS nodes
    ORDER BY hops ASC, total_weight DESC
    LIMIT $limit
    """

    # Find paths from entity to any matching pattern
    PATHS_TO_PATTERN = """
    MATCH path = (start {{entity_id: $start_id}})-[*1..{max_hops}]->(end:{target_label})
    {relationship_filter}
    WITH path, end,
         length(path) AS hops,
         reduce(s = 0.0, r IN relationships(path) | s + coalesce(r.weight, 1.0)) AS total_weight
    RETURN path,
           end.entity_id AS end_id,
           end.name AS end_name,
           hops,
           total_weight,
           [r IN relationships(path) | type(r)] AS relationship_types
    ORDER BY hops ASC, total_weight DESC
    LIMIT $limit
    """

    # -------------------------------------------------------------------------
    # Similarity Queries (Vector Index)
    # -------------------------------------------------------------------------

    SIMILAR_BY_EMBEDDING = """
    MATCH (e {{entity_id: $entity_id}})
    WHERE e.embedding IS NOT NULL
    CALL db.index.vector.queryNodes(
        '{index_name}',
        $top_k,
        e.embedding
    ) YIELD node, score
    WHERE node.entity_id <> $entity_id
    RETURN node.entity_id AS entity_id,
           node.name AS name,
           node.entity_type AS entity_type,
           score
    ORDER BY score DESC
    """

    SIMILAR_BY_VECTOR = """
    CALL db.index.vector.queryNodes(
        '{index_name}',
        $top_k,
        $embedding
    ) YIELD node, score
    RETURN node.entity_id AS entity_id,
           node.name AS name,
           node.entity_type AS entity_type,
           score
    ORDER BY score DESC
    """

    # -------------------------------------------------------------------------
    # Graph Traversal
    # -------------------------------------------------------------------------

    TRAVERSE_FROM_ENTITY = """
    MATCH (start {{entity_id: $entity_id}})
    CALL apoc.path.subgraphNodes(start, {{
        maxLevel: $max_hops,
        {relationship_filter}
        limit: $max_nodes
    }}) YIELD node
    WITH collect(DISTINCT node) AS nodes
    UNWIND nodes AS n
    OPTIONAL MATCH (n)-[r]->(m)
    WHERE m IN nodes
    RETURN nodes,
           collect(DISTINCT {{
               from: n.entity_id,
               to: m.entity_id,
               type: type(r),
               weight: r.weight
           }}) AS edges
    """

    # Alternative traversal without APOC
    TRAVERSE_BFS = """
    MATCH (start {{entity_id: $entity_id}})
    MATCH path = (start)-[*1..{max_hops}]-(connected)
    {relationship_filter}
    WITH DISTINCT connected
    LIMIT $max_nodes
    MATCH (connected)-[r]->(other)
    WHERE (start)-[*0..{max_hops}]-(other)
    RETURN collect(DISTINCT {{
               id: connected.entity_id,
               name: connected.name,
               type: connected.entity_type
           }}) AS nodes,
           collect(DISTINCT {{
               from: connected.entity_id,
               to: other.entity_id,
               type: type(r)
           }}) AS edges
    """

    # -------------------------------------------------------------------------
    # Legal-Specific Aggregations
    # -------------------------------------------------------------------------

    # Court hierarchy and precedent strength
    PRECEDENT_CHAIN = """
    MATCH (dec {{entity_id: $decision_id}})
    MATCH path = (dec)-[:CITA|APLICA*1..{max_hops}]->(precedent)
    WHERE precedent:SUMULA OR precedent:JURISPRUDENCIA OR precedent:ACORDAO
    WITH precedent,
         min(length(path)) AS distance,
         count(path) AS citation_strength
    RETURN precedent.entity_id AS precedent_id,
           precedent.name AS precedent_name,
           precedent.tribunal AS court,
           distance,
           citation_strength,
           CASE precedent.tribunal
               WHEN 'STF' THEN 5
               WHEN 'STJ' THEN 4
               WHEN 'TST' THEN 4
               WHEN 'TSE' THEN 4
               ELSE 3
           END AS court_weight
    ORDER BY court_weight DESC, distance ASC, citation_strength DESC
    LIMIT $limit
    """

    # Topic clustering by co-citation
    TOPIC_CLUSTER = """
    MATCH (e1)-[:CITA]->(common)<-[:CITA]-(e2)
    WHERE e1.entity_id = $entity_id
      AND e1 <> e2
    WITH e2, count(common) AS co_citations, collect(common.name)[0..5] AS shared_citations
    WHERE co_citations >= $min_co_citations
    RETURN e2.entity_id AS related_id,
           e2.name AS related_name,
           e2.entity_type AS related_type,
           co_citations,
           shared_citations
    ORDER BY co_citations DESC
    LIMIT $limit
    """

    # -------------------------------------------------------------------------
    # Index Management
    # -------------------------------------------------------------------------

    CREATE_ENTITY_INDEX = """
    CREATE INDEX {index_name} IF NOT EXISTS
    FOR (n:{label})
    ON (n.entity_id)
    """

    CREATE_FULLTEXT_INDEX = """
    CREATE FULLTEXT INDEX {index_name} IF NOT EXISTS
    FOR (n:{labels})
    ON EACH [n.name, n.ementa, n.texto]
    """

    CREATE_VECTOR_INDEX = """
    CALL db.index.vector.createNodeIndex(
        '{index_name}',
        '{label}',
        'embedding',
        $dimension,
        '{similarity}'
    )
    """

    # -------------------------------------------------------------------------
    # Statistics
    # -------------------------------------------------------------------------

    GRAPH_STATS = """
    CALL apoc.meta.stats() YIELD labels, relTypesCount
    RETURN labels, relTypesCount
    """

    ENTITY_COUNTS = """
    MATCH (n)
    WHERE n:LEI OR n:ARTIGO OR n:SUMULA OR n:JURISPRUDENCIA OR n:ACORDAO
    RETURN labels(n)[0] AS entity_type, count(n) AS count
    ORDER BY count DESC
    """

    RELATIONSHIP_COUNTS = """
    MATCH ()-[r]->()
    RETURN type(r) AS relationship_type, count(r) AS count
    ORDER BY count DESC
    """


# =============================================================================
# NEO4J GRAPH RAG
# =============================================================================


class Neo4jGraphRAG:
    """
    Neo4j-backed Graph RAG with entity embeddings.

    Features:
    - Scalable graph storage with Neo4j
    - Knowledge graph embeddings (TransE, RotatE, ComplEx)
    - Explainable reasoning paths
    - Legal-specific Cypher queries
    - Integration with existing LegalKnowledgeGraph
    """

    def __init__(self, config: Optional[Neo4jConfig] = None):
        """
        Initialize Neo4j Graph RAG.

        Args:
            config: Neo4j configuration (uses env vars if not provided)
        """
        self.config = config or Neo4jConfig.from_env()
        self._driver = None
        self._driver_lock = threading.Lock()

        # Entity embeddings cache
        self._entity_embeddings: Dict[str, np.ndarray] = {}
        self._relation_embeddings: Dict[str, np.ndarray] = {}
        self._embeddings_lock = threading.RLock()

        # Initialize random number generator for embeddings
        self._rng = np.random.default_rng(42)

        logger.info(
            f"Neo4jGraphRAG initialized with {self.config.embedding_method.value} "
            f"embeddings (dim={self.config.embedding_dim})"
        )

    # =========================================================================
    # Connection Management
    # =========================================================================

    @property
    def driver(self):
        """
        Lazy Neo4j driver initialization.

        Returns:
            Neo4j driver instance

        Raises:
            ImportError: If neo4j package is not installed
        """
        if self._driver is None:
            with self._driver_lock:
                if self._driver is None:
                    try:
                        from neo4j import GraphDatabase
                    except ImportError:
                        raise ImportError(
                            "Neo4j driver required: pip install neo4j"
                        )

                    self._driver = GraphDatabase.driver(
                        self.config.uri,
                        auth=(self.config.user, self.config.password),
                        max_connection_lifetime=self.config.max_connection_lifetime,
                        max_connection_pool_size=self.config.max_connection_pool_size,
                        connection_acquisition_timeout=self.config.connection_acquisition_timeout,
                    )
                    logger.info(f"Neo4j driver connected to {self.config.uri}")

                    if self.config.create_indexes:
                        self._create_indexes()

        return self._driver

    def close(self) -> None:
        """Close the Neo4j driver connection."""
        if self._driver is not None:
            self._driver.close()
            self._driver = None
            logger.info("Neo4j driver connection closed")

    def _execute_query(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None,
        database: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Execute a Cypher query and return results.

        Args:
            query: Cypher query string
            parameters: Query parameters
            database: Database name (uses config default if not provided)

        Returns:
            List of result records as dictionaries
        """
        db = database or self.config.database
        parameters = parameters or {}

        with self.driver.session(database=db) as session:
            result = session.run(query, parameters)
            return [record.data() for record in result]

    def _execute_write(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None,
        database: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Execute a write query within a transaction."""
        db = database or self.config.database
        parameters = parameters or {}

        with self.driver.session(database=db) as session:
            result = session.execute_write(
                lambda tx: list(tx.run(query, parameters))
            )
            return [record.data() for record in result]

    def _create_indexes(self) -> None:
        """Create necessary indexes for efficient queries."""
        try:
            # Entity type indexes
            for entity_type in EntityType:
                label = entity_type.value.upper()
                index_name = f"idx_{label.lower()}_entity_id"
                query = CypherTemplates.CREATE_ENTITY_INDEX.format(
                    index_name=index_name,
                    label=label,
                )
                try:
                    self._execute_write(query)
                except Exception as e:
                    logger.debug(f"Index {index_name} may already exist: {e}")

            # Vector index for embeddings
            if self.config.use_vector_index:
                for label in ["LEI", "SUMULA", "JURISPRUDENCIA", "ACORDAO"]:
                    try:
                        self._execute_write(
                            CypherTemplates.CREATE_VECTOR_INDEX.format(
                                index_name=f"vec_{label.lower()}",
                                label=label,
                                similarity=self.config.vector_similarity,
                            ),
                            {"dimension": self.config.embedding_dim},
                        )
                    except Exception as e:
                        logger.debug(f"Vector index for {label} may already exist: {e}")

            logger.info("Neo4j indexes created/verified")

        except Exception as e:
            logger.warning(f"Could not create all indexes: {e}")

    # =========================================================================
    # Entity Operations
    # =========================================================================

    def add_entity(
        self,
        entity_type: Union[str, EntityType],
        entity_id: str,
        properties: Dict[str, Any],
        embedding: Optional[np.ndarray] = None,
    ) -> str:
        """
        Add entity to graph.

        Args:
            entity_type: Type of entity (LEI, ARTIGO, SUMULA, etc.)
            entity_id: Unique identifier for the entity
            properties: Entity properties (name, metadata, etc.)
            embedding: Optional pre-computed embedding vector

        Returns:
            Entity ID
        """
        if isinstance(entity_type, EntityType):
            entity_type = entity_type.value

        label = entity_type.upper()
        name = properties.pop("name", entity_id)

        if embedding is not None:
            query = CypherTemplates.CREATE_ENTITY_WITH_EMBEDDING.format(label=label)
            params = {
                "entity_id": entity_id,
                "name": name,
                "entity_type": entity_type,
                "embedding": embedding.tolist(),
                "embedding_method": self.config.embedding_method.value,
                "properties": properties,
            }
        else:
            query = CypherTemplates.CREATE_ENTITY.format(label=label)
            params = {
                "entity_id": entity_id,
                "name": name,
                "entity_type": entity_type,
                "properties": properties,
            }

        self._execute_write(query, params)

        # Cache embedding if provided
        if embedding is not None:
            with self._embeddings_lock:
                self._entity_embeddings[entity_id] = embedding

        return entity_id

    def add_relationship(
        self,
        from_id: str,
        to_id: str,
        rel_type: Union[str, RelationType],
        properties: Optional[Dict[str, Any]] = None,
        weight: float = 1.0,
    ) -> bool:
        """
        Add relationship between entities.

        Args:
            from_id: Source entity ID
            to_id: Target entity ID
            rel_type: Relationship type (CITA, ALTERA, REVOGA, etc.)
            properties: Optional relationship properties
            weight: Relationship weight for path scoring

        Returns:
            True if relationship was created
        """
        if isinstance(rel_type, RelationType):
            rel_type = rel_type.value

        rel_type_upper = rel_type.upper()
        query = CypherTemplates.CREATE_RELATIONSHIP.format(rel_type=rel_type_upper)

        try:
            self._execute_write(
                query,
                {
                    "from_id": from_id,
                    "to_id": to_id,
                    "weight": weight,
                    "properties": properties or {},
                },
            )
            return True
        except Exception as e:
            logger.error(f"Failed to create relationship: {e}")
            return False

    def get_entity(self, entity_id: str) -> Optional[Dict[str, Any]]:
        """Get entity by ID."""
        query = """
        MATCH (e {entity_id: $entity_id})
        RETURN e
        """
        results = self._execute_query(query, {"entity_id": entity_id})
        if results:
            return dict(results[0]["e"])
        return None

    def delete_entity(self, entity_id: str) -> bool:
        """Delete entity and all its relationships."""
        query = """
        MATCH (e {entity_id: $entity_id})
        DETACH DELETE e
        RETURN count(e) > 0 AS deleted
        """
        results = self._execute_write(query, {"entity_id": entity_id})

        # Remove from cache
        with self._embeddings_lock:
            self._entity_embeddings.pop(entity_id, None)

        return results[0].get("deleted", False) if results else False

    # =========================================================================
    # Entity Embeddings (TransE / RotatE / ComplEx)
    # =========================================================================

    def compute_entity_embeddings(
        self,
        method: Optional[EmbeddingMethod] = None,
        epochs: int = 100,
        learning_rate: float = 0.01,
        batch_size: int = 256,
        use_advanced_trainer: bool = True,
    ) -> Dict[str, np.ndarray]:
        """
        Compute entity embeddings using knowledge graph embedding methods.

        Implements TransE, RotatE, ComplEx, and DistMult algorithms.

        Args:
            method: Embedding method (uses config default if not provided)
            epochs: Training epochs
            learning_rate: Learning rate
            batch_size: Batch size for training
            use_advanced_trainer: Use the advanced trainer with negative sampling

        Returns:
            Dictionary mapping entity_id to embedding vector
        """
        method = method or self.config.embedding_method
        dim = self.config.embedding_dim

        # Load all triples from Neo4j
        triples = self._load_triples()
        if not triples:
            logger.warning("No triples found for embedding computation")
            return {}

        logger.info(f"Loaded {len(triples)} triples for embedding training")

        # Use advanced trainer if available and requested
        if use_advanced_trainer:
            try:
                return self._train_with_advanced_trainer(
                    triples, method, epochs, learning_rate, batch_size
                )
            except ImportError:
                logger.warning(
                    "Advanced trainer not available, falling back to basic training"
                )
            except Exception as e:
                logger.warning(f"Advanced trainer failed: {e}, falling back to basic")

        # Fallback to basic training
        return self._train_basic(triples, method, epochs, learning_rate, batch_size)

    def _train_with_advanced_trainer(
        self,
        triples: List[Tuple[str, str, str]],
        method: EmbeddingMethod,
        epochs: int,
        learning_rate: float,
        batch_size: int,
    ) -> Dict[str, np.ndarray]:
        """Train using the advanced EmbeddingTrainer with negative sampling."""
        from app.services.rag.core.embedding_trainer import (
            EmbeddingTrainer,
            TrainingConfig,
            EmbeddingMethod as TrainerMethod,
            NegativeSamplingStrategy,
        )
        from app.services.rag.config import get_rag_config

        rag_config = get_rag_config()
        emb_config = rag_config.get_embedding_training_config()

        # Map method enum
        method_map = {
            EmbeddingMethod.TRANSE: TrainerMethod.TRANSE,
            EmbeddingMethod.ROTATE: TrainerMethod.ROTATE,
            EmbeddingMethod.COMPLEX: TrainerMethod.ROTATE,  # ComplEx uses RotatE implementation
            EmbeddingMethod.DISTMULT: TrainerMethod.DISTMULT,
        }

        strategy_map = {
            "uniform": NegativeSamplingStrategy.UNIFORM,
            "self_adv": NegativeSamplingStrategy.SELF_ADVERSARIAL,
            "bernoulli": NegativeSamplingStrategy.BERNOULLI,
        }

        config = TrainingConfig(
            embedding_dim=self.config.embedding_dim,
            method=method_map.get(method, TrainerMethod.ROTATE),
            epochs=epochs or emb_config.get("epochs", 200),
            batch_size=batch_size or emb_config.get("batch_size", 512),
            learning_rate=learning_rate or emb_config.get("learning_rate", 0.001),
            negative_samples=emb_config.get("negative_samples", 10),
            negative_strategy=strategy_map.get(
                emb_config.get("negative_strategy", "self_adv"),
                NegativeSamplingStrategy.SELF_ADVERSARIAL,
            ),
            patience=emb_config.get("patience", 20),
            checkpoint_dir=emb_config.get("checkpoint_dir", "data/embeddings/checkpoints"),
            margin_transe=self.config.embedding_margin,
            gamma_rotate=self.config.embedding_gamma,
        )

        trainer = EmbeddingTrainer(triples, config)
        results = trainer.train()

        # Store embeddings in cache and Neo4j
        entity_emb = results["entity_embeddings"]
        entity_to_idx = results["entity_to_idx"]
        relation_emb = results["relation_embeddings"]
        relation_to_idx = results["relation_to_idx"]

        dim = self.config.embedding_dim

        with self._embeddings_lock:
            for entity_id, idx in entity_to_idx.items():
                emb = entity_emb[idx]
                # For complex methods, take real part for similarity
                if method in [EmbeddingMethod.ROTATE, EmbeddingMethod.COMPLEX]:
                    if len(emb) > dim:
                        emb = emb[:dim]
                self._entity_embeddings[entity_id] = emb

            for relation_id, idx in relation_to_idx.items():
                self._relation_embeddings[relation_id] = relation_emb[idx]

        # Store in Neo4j
        self._store_embeddings_in_neo4j()

        logger.info(
            f"Advanced trainer completed: {len(entity_to_idx)} entities, "
            f"MRR={results.get('metrics', {}).get('mrr', 0):.4f}"
        )

        return dict(self._entity_embeddings)

    def _train_basic(
        self,
        triples: List[Tuple[str, str, str]],
        method: EmbeddingMethod,
        epochs: int,
        learning_rate: float,
        batch_size: int,
    ) -> Dict[str, np.ndarray]:
        """Basic training without negative sampling (original implementation)."""
        dim = self.config.embedding_dim

        # Get unique entities and relations
        entities: Set[str] = set()
        relations: Set[str] = set()
        for h, r, t in triples:
            entities.add(h)
            entities.add(t)
            relations.add(r)

        entity_list = sorted(entities)
        relation_list = sorted(relations)
        entity_to_idx = {e: i for i, e in enumerate(entity_list)}
        relation_to_idx = {r: i for i, r in enumerate(relation_list)}

        n_entities = len(entity_list)
        n_relations = len(relation_list)

        logger.info(
            f"Computing {method.value} embeddings for {n_entities} entities "
            f"and {n_relations} relations"
        )

        # Initialize embeddings
        if method == EmbeddingMethod.ROTATE or method == EmbeddingMethod.COMPLEX:
            # Complex-valued embeddings (stored as 2*dim real values)
            entity_emb = self._rng.uniform(-1, 1, (n_entities, dim * 2)).astype(np.float32)
            relation_emb = self._rng.uniform(-np.pi, np.pi, (n_relations, dim)).astype(np.float32)
        else:
            # Real-valued embeddings
            entity_emb = self._rng.uniform(-1, 1, (n_entities, dim)).astype(np.float32)
            relation_emb = self._rng.uniform(-1, 1, (n_relations, dim)).astype(np.float32)

        # Normalize initial embeddings
        entity_emb /= np.linalg.norm(entity_emb, axis=1, keepdims=True) + 1e-8

        # Training loop (simplified SGD)
        triples_list = list(triples)
        for epoch in range(epochs):
            total_loss = 0.0
            np.random.shuffle(triples_list)

            for batch_start in range(0, len(triples_list), batch_size):
                batch = triples_list[batch_start:batch_start + batch_size]

                for h, r, t in batch:
                    h_idx = entity_to_idx[h]
                    r_idx = relation_to_idx[r]
                    t_idx = entity_to_idx[t]

                    h_emb = entity_emb[h_idx]
                    r_emb = relation_emb[r_idx]
                    t_emb = entity_emb[t_idx]

                    # Compute score and gradient based on method
                    if method == EmbeddingMethod.TRANSE:
                        score, grad_h, grad_r, grad_t = self._transe_gradient(
                            h_emb, r_emb, t_emb
                        )
                    elif method == EmbeddingMethod.ROTATE:
                        score, grad_h, grad_r, grad_t = self._rotate_gradient(
                            h_emb, r_emb, t_emb
                        )
                    elif method == EmbeddingMethod.COMPLEX:
                        score, grad_h, grad_r, grad_t = self._complex_gradient(
                            h_emb, r_emb, t_emb
                        )
                    else:  # DISTMULT
                        score, grad_h, grad_r, grad_t = self._distmult_gradient(
                            h_emb, r_emb, t_emb
                        )

                    total_loss += score

                    # Update embeddings
                    entity_emb[h_idx] -= learning_rate * grad_h
                    relation_emb[r_idx] -= learning_rate * grad_r
                    entity_emb[t_idx] -= learning_rate * grad_t

                    # Normalize
                    entity_emb[h_idx] /= np.linalg.norm(entity_emb[h_idx]) + 1e-8
                    entity_emb[t_idx] /= np.linalg.norm(entity_emb[t_idx]) + 1e-8

            if (epoch + 1) % 10 == 0:
                logger.debug(f"Epoch {epoch + 1}/{epochs}, Loss: {total_loss:.4f}")

        # Store embeddings
        with self._embeddings_lock:
            for entity_id, idx in entity_to_idx.items():
                emb = entity_emb[idx]
                # For complex methods, take real part for similarity
                if method in [EmbeddingMethod.ROTATE, EmbeddingMethod.COMPLEX]:
                    emb = emb[:dim]  # Take first half (real part)
                self._entity_embeddings[entity_id] = emb

            for relation_id, idx in relation_to_idx.items():
                self._relation_embeddings[relation_id] = relation_emb[idx]

        # Update embeddings in Neo4j
        self._store_embeddings_in_neo4j()

        logger.info(f"Computed and stored embeddings for {n_entities} entities")
        return dict(self._entity_embeddings)

    def _load_triples(self) -> List[Tuple[str, str, str]]:
        """Load all triples (head, relation, tail) from Neo4j."""
        query = """
        MATCH (h)-[r]->(t)
        WHERE h.entity_id IS NOT NULL AND t.entity_id IS NOT NULL
        RETURN h.entity_id AS head, type(r) AS relation, t.entity_id AS tail
        """
        results = self._execute_query(query)
        return [(r["head"], r["relation"], r["tail"]) for r in results]

    def _store_embeddings_in_neo4j(self) -> None:
        """Store computed embeddings back in Neo4j for vector search."""
        query = """
        MATCH (e {entity_id: $entity_id})
        SET e.embedding = $embedding,
            e.embedding_method = $method,
            e.embedding_updated = datetime()
        """

        with self._embeddings_lock:
            for entity_id, embedding in self._entity_embeddings.items():
                try:
                    self._execute_write(
                        query,
                        {
                            "entity_id": entity_id,
                            "embedding": embedding.tolist(),
                            "method": self.config.embedding_method.value,
                        },
                    )
                except Exception as e:
                    logger.debug(f"Could not store embedding for {entity_id}: {e}")

    def _transe_score(
        self,
        head: np.ndarray,
        relation: np.ndarray,
        tail: np.ndarray,
    ) -> float:
        """
        TransE score: ||h + r - t||

        Lower score = better fit
        """
        return float(np.linalg.norm(head + relation - tail))

    def _transe_gradient(
        self,
        head: np.ndarray,
        relation: np.ndarray,
        tail: np.ndarray,
    ) -> Tuple[float, np.ndarray, np.ndarray, np.ndarray]:
        """Compute TransE gradient."""
        diff = head + relation - tail
        score = float(np.linalg.norm(diff))

        if score > 1e-8:
            grad = diff / score
        else:
            grad = np.zeros_like(diff)

        margin_loss = max(0, self.config.embedding_margin + score)

        return margin_loss, grad, grad, -grad

    def _rotate_score(
        self,
        head: np.ndarray,
        relation: np.ndarray,
        tail: np.ndarray,
    ) -> float:
        """
        RotatE score: ||h o r - t|| in complex space

        h and t are complex vectors, r is phase rotation
        """
        dim = len(relation)

        # Split into real and imaginary parts
        h_re, h_im = head[:dim], head[dim:]
        t_re, t_im = tail[:dim], tail[dim:]

        # r is phase angle, compute rotation
        r_re = np.cos(relation)
        r_im = np.sin(relation)

        # Complex multiplication: (h_re + i*h_im) * (r_re + i*r_im)
        rot_re = h_re * r_re - h_im * r_im
        rot_im = h_re * r_im + h_im * r_re

        # Distance from rotated h to t
        diff_re = rot_re - t_re
        diff_im = rot_im - t_im

        return float(np.sqrt(np.sum(diff_re**2 + diff_im**2)))

    def _rotate_gradient(
        self,
        head: np.ndarray,
        relation: np.ndarray,
        tail: np.ndarray,
    ) -> Tuple[float, np.ndarray, np.ndarray, np.ndarray]:
        """Compute RotatE gradient."""
        dim = len(relation)

        h_re, h_im = head[:dim], head[dim:]
        t_re, t_im = tail[:dim], tail[dim:]

        r_re = np.cos(relation)
        r_im = np.sin(relation)

        rot_re = h_re * r_re - h_im * r_im
        rot_im = h_re * r_im + h_im * r_re

        diff_re = rot_re - t_re
        diff_im = rot_im - t_im

        score = float(np.sqrt(np.sum(diff_re**2 + diff_im**2) + 1e-8))
        margin_loss = max(0, self.config.embedding_gamma - score)

        # Simplified gradients
        grad_h = np.concatenate([
            diff_re * r_re + diff_im * r_im,
            -diff_re * r_im + diff_im * r_re,
        ]) / (score + 1e-8)

        grad_r = (
            diff_re * (-h_re * r_im - h_im * r_re) +
            diff_im * (h_re * r_re - h_im * r_im)
        ) / (score + 1e-8)

        grad_t = np.concatenate([-diff_re, -diff_im]) / (score + 1e-8)

        return margin_loss, grad_h, grad_r, grad_t

    def _complex_gradient(
        self,
        head: np.ndarray,
        relation: np.ndarray,
        tail: np.ndarray,
    ) -> Tuple[float, np.ndarray, np.ndarray, np.ndarray]:
        """Compute ComplEx gradient (simplified)."""
        # ComplEx uses trilinear product in complex space
        # Simplified to real-valued approximation
        dim = len(relation)

        h_re, h_im = head[:dim], head[dim:]
        t_re, t_im = tail[:dim], tail[dim:]
        r_re, r_im = relation[:dim//2], relation[dim//2:] if dim > 1 else (relation, np.zeros_like(relation))

        score = float(
            np.sum(h_re * r_re * t_re) +
            np.sum(h_im * r_re * t_im) +
            np.sum(h_re * r_im * t_im) -
            np.sum(h_im * r_im * t_re)
        )

        # Simplified gradients
        grad_h = np.concatenate([r_re * t_re + r_im * t_im, r_re * t_im - r_im * t_re])
        grad_t = np.concatenate([h_re * r_re - h_im * r_im, h_im * r_re + h_re * r_im])
        grad_r = np.concatenate([h_re * t_re + h_im * t_im, h_re * t_im - h_im * t_re])[:len(relation)]

        return -score, -grad_h, -grad_r, -grad_t  # Maximize score

    def _distmult_gradient(
        self,
        head: np.ndarray,
        relation: np.ndarray,
        tail: np.ndarray,
    ) -> Tuple[float, np.ndarray, np.ndarray, np.ndarray]:
        """Compute DistMult gradient."""
        score = float(np.sum(head * relation * tail))

        grad_h = relation * tail
        grad_r = head * tail
        grad_t = head * relation

        return -score, -grad_h, -grad_r, -grad_t  # Maximize score

    def get_similar_entities(
        self,
        entity_id: str,
        top_k: int = 10,
        entity_type_filter: Optional[str] = None,
    ) -> List[Tuple[str, float]]:
        """
        Find similar entities by embedding similarity.

        Args:
            entity_id: Source entity ID
            top_k: Number of results to return
            entity_type_filter: Optional filter by entity type

        Returns:
            List of (entity_id, similarity_score) tuples
        """
        # Try vector index first
        if self.config.use_vector_index:
            try:
                query = CypherTemplates.SIMILAR_BY_EMBEDDING.format(
                    index_name=f"vec_{entity_type_filter.lower()}" if entity_type_filter else "vec_lei"
                )
                results = self._execute_query(
                    query,
                    {"entity_id": entity_id, "top_k": top_k + 1},  # +1 to exclude self
                )
                return [(r["entity_id"], r["score"]) for r in results[:top_k]]
            except Exception as e:
                logger.debug(f"Vector index query failed, using cached embeddings: {e}")

        # Fall back to cached embeddings
        with self._embeddings_lock:
            if entity_id not in self._entity_embeddings:
                return []

            source_emb = self._entity_embeddings[entity_id]
            similarities: List[Tuple[str, float]] = []

            for other_id, other_emb in self._entity_embeddings.items():
                if other_id == entity_id:
                    continue

                # Cosine similarity
                norm_src = np.linalg.norm(source_emb)
                norm_other = np.linalg.norm(other_emb)
                if norm_src > 0 and norm_other > 0:
                    sim = float(np.dot(source_emb, other_emb) / (norm_src * norm_other))
                    similarities.append((other_id, sim))

            similarities.sort(key=lambda x: x[1], reverse=True)
            return similarities[:top_k]

    # =========================================================================
    # Reasoning Paths
    # =========================================================================

    def find_reasoning_paths(
        self,
        start_entity: str,
        end_entity: Optional[str] = None,
        max_hops: Optional[int] = None,
        relationship_types: Optional[List[str]] = None,
    ) -> List[ReasoningPath]:
        """
        Find explainable reasoning paths.

        Args:
            start_entity: Starting entity ID
            end_entity: Target entity ID (if None, finds paths to any entity)
            max_hops: Maximum path length
            relationship_types: Allowed relationship types

        Returns:
            List of ReasoningPath objects
        """
        max_hops = max_hops or self.config.max_hops

        # Build relationship filter
        rel_filter = ""
        if relationship_types:
            rel_types = "|".join(r.upper() for r in relationship_types)
            rel_filter = f"WHERE ALL(r IN relationships(path) WHERE type(r) IN ['{rel_types}'])"

        if end_entity:
            query = CypherTemplates.ALL_PATHS.format(
                max_hops=max_hops,
                relationship_filter=rel_filter,
            )
            params = {
                "start_id": start_entity,
                "end_id": end_entity,
                "limit": self.config.max_paths,
            }
        else:
            # Find paths to any interesting entity
            query = CypherTemplates.PATHS_TO_PATTERN.format(
                max_hops=max_hops,
                target_label="SUMULA|JURISPRUDENCIA|ACORDAO",
                relationship_filter=rel_filter,
            )
            params = {
                "start_id": start_entity,
                "limit": self.config.max_paths,
            }

        try:
            results = self._execute_query(query, params)
        except Exception as e:
            logger.error(f"Path query failed: {e}")
            return []

        paths: List[ReasoningPath] = []
        for record in results:
            path_nodes = record.get("nodes", [])
            rel_types = record.get("relationship_types", [])

            if len(path_nodes) < 2:
                continue

            # Build path tuples
            path_tuples: List[Tuple[str, str, str]] = []
            for i in range(len(rel_types)):
                if i < len(path_nodes) - 1:
                    path_tuples.append((
                        path_nodes[i].get("name", path_nodes[i].get("id", "")),
                        rel_types[i],
                        path_nodes[i + 1].get("name", path_nodes[i + 1].get("id", "")),
                    ))

            # Score based on path length and weights
            hops = record.get("hops", len(path_tuples))
            weight = record.get("total_weight", hops)
            score = 1.0 / (hops + 0.1) * (weight / max(1, hops))

            end_id = end_entity or record.get("end_id", path_nodes[-1].get("id", ""))

            paths.append(ReasoningPath(
                start_entity=start_entity,
                end_entity=end_id,
                path=path_tuples,
                score=score,
                explanation=self._generate_path_explanation(path_tuples),
                metadata={"hops": hops, "weight": weight},
            ))

        # Sort by score
        paths.sort(key=lambda p: p.score, reverse=True)
        return paths[:self.config.max_paths]

    def explain_path(self, path: ReasoningPath) -> str:
        """
        Generate natural language explanation for a path.

        Example output:
            "Art. 5 da CF/88 FUNDAMENTA a Sumula 123 do STF, que por sua vez
             CITA o RE 12345/SP, estabelecendo precedente sobre..."
        """
        return path.explanation

    def _generate_path_explanation(
        self,
        path_tuples: List[Tuple[str, str, str]],
    ) -> str:
        """Generate natural language explanation for path tuples."""
        if not path_tuples:
            return ""

        # Relationship type to Portuguese verb mapping
        rel_verbs = {
            "CITA": "cita",
            "APLICA": "aplica",
            "FUNDAMENTA": "fundamenta",
            "REVOGA": "revoga",
            "ALTERA": "altera",
            "VINCULA": "vincula",
            "INTERPRETA": "interpreta",
            "RELACIONADA": "se relaciona com",
            "CONTRAPOE": "se contrapoe a",
            "DERIVA": "deriva de",
            "JULGA": "julga",
            "RELATA": "relata",
            "RECURSO_DE": "e recurso de",
            "POSSUI": "possui",
        }

        parts = []
        for i, (node1, rel, node2) in enumerate(path_tuples):
            verb = rel_verbs.get(rel.upper(), rel.lower())

            if i == 0:
                parts.append(f"{node1} {verb} {node2}")
            else:
                parts.append(f"que {verb} {node2}")

        return ", ".join(parts) + "."

    # =========================================================================
    # Legal-Specific Queries
    # =========================================================================

    def get_citing_decisions(
        self,
        law_article: str,
        court: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Get court decisions citing a specific article.

        Args:
            law_article: Article entity ID
            court: Optional court filter (STF, STJ, etc.)
            limit: Maximum results

        Returns:
            List of citing decisions with metadata
        """
        court_filter = ""
        if court:
            court_filter = f"AND dec.tribunal = '{court.upper()}'"

        query = CypherTemplates.CITING_DECISIONS.format(court_filter=court_filter)

        return self._execute_query(
            query,
            {"article_id": law_article, "limit": limit},
        )

    def get_law_amendments(
        self,
        law_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Get amendment history of a law.

        Args:
            law_id: Law entity ID

        Returns:
            List of amendments in chronological order
        """
        return self._execute_query(
            CypherTemplates.LAW_AMENDMENTS,
            {"law_id": law_id},
        )

    def get_related_sumulas(
        self,
        topic: str,
        courts: Optional[List[str]] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Get sumulas related to a topic.

        Args:
            topic: Topic keyword or phrase
            courts: Optional list of courts to filter by
            limit: Maximum results

        Returns:
            List of related sumulas with citation counts
        """
        court_filter = ""
        if courts:
            court_list = "', '".join(c.upper() for c in courts)
            court_filter = f"AND s.tribunal IN ['{court_list}']"

        query = CypherTemplates.RELATED_SUMULAS.format(court_filter=court_filter)

        return self._execute_query(
            query,
            {"topic": topic, "limit": limit},
        )

    def get_precedent_chain(
        self,
        decision_id: str,
        max_hops: int = 3,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Get the precedent chain for a decision.

        Returns precedents ordered by court hierarchy and citation strength.
        """
        query = CypherTemplates.PRECEDENT_CHAIN.format(max_hops=max_hops)

        return self._execute_query(
            query,
            {"decision_id": decision_id, "limit": limit},
        )

    def get_co_citation_cluster(
        self,
        entity_id: str,
        min_co_citations: int = 2,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Find entities in the same citation cluster.

        Entities that cite many of the same sources are likely topically related.
        """
        return self._execute_query(
            CypherTemplates.TOPIC_CLUSTER,
            {
                "entity_id": entity_id,
                "min_co_citations": min_co_citations,
                "limit": limit,
            },
        )

    # =========================================================================
    # RAG Integration
    # =========================================================================

    def enrich_results(
        self,
        results: List[Dict[str, Any]],
        query: str,
        max_enrichments_per_result: int = 3,
    ) -> List[Dict[str, Any]]:
        """
        Enrich RAG results with graph context.

        For each result, adds:
        - Related entities from the graph
        - Citation context
        - Reasoning paths to relevant precedents

        Args:
            results: List of RAG results (chunks)
            query: Original query text
            max_enrichments_per_result: Max enrichments per result

        Returns:
            Enriched results with graph context
        """
        # Extract entities from query
        query_entities = LegalEntityExtractor.extract_candidates(query)
        query_entity_ids = {
            f"{_normalize_entity_type(e[0])}:{e[1]}"
            for e in query_entities
        }

        enriched_results = []

        for result in results:
            enriched = dict(result)
            graph_context = []

            # Extract entities from result text
            text = result.get("text", "") or result.get("content", "")
            result_entities = LegalEntityExtractor.extract_candidates(text)

            for entity in result_entities[:max_enrichments_per_result]:
                entity_type, entity_id, name, meta = entity
                full_id = f"{_normalize_entity_type(entity_type)}:{entity_id}"

                # Get entity from graph
                entity_data = self.get_entity(full_id)
                if entity_data:
                    # Find reasoning paths to query entities
                    paths = []
                    for query_eid in query_entity_ids:
                        found_paths = self.find_reasoning_paths(
                            full_id, query_eid, max_hops=2
                        )
                        paths.extend(found_paths[:1])  # Take best path to each

                    graph_context.append({
                        "entity_id": full_id,
                        "name": name,
                        "type": _normalize_entity_type(entity_type),
                        "data": entity_data,
                        "reasoning_paths": [p.to_dict() for p in paths[:2]],
                    })

            enriched["graph_context"] = graph_context
            enriched_results.append(enriched)

        return enriched_results

    def get_graph_context(
        self,
        entities: List[str],
        max_hops: int = 2,
        max_context_tokens: int = 500,
    ) -> str:
        """
        Generate graph context string for LLM.

        Args:
            entities: List of entity IDs
            max_hops: Maximum traversal depth
            max_context_tokens: Token budget for context

        Returns:
            Formatted context string
        """
        if not entities:
            return ""

        # Estimate ~4 chars per token
        char_budget = max_context_tokens * 4

        context_parts = ["### CONTEXTO DO GRAFO (Neo4j):\n"]
        current_chars = len(context_parts[0])

        for entity_id in entities:
            if current_chars >= char_budget:
                break

            entity = self.get_entity(entity_id)
            if not entity:
                continue

            name = entity.get("name", entity_id)
            entity_section = f"\n**{name}**:"

            # Get related entities
            paths = self.find_reasoning_paths(entity_id, max_hops=max_hops)

            for path in paths[:3]:
                path_str = f"\n  - {path.explanation}"
                if current_chars + len(entity_section) + len(path_str) > char_budget:
                    break
                entity_section += path_str

            if current_chars + len(entity_section) <= char_budget:
                context_parts.append(entity_section)
                current_chars += len(entity_section)

        return "\n".join(context_parts)

    def traverse(
        self,
        start_entity: str,
        max_hops: int = 2,
        max_nodes: int = 50,
        relationship_types: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Traverse graph from starting entity.

        Compatible with LegalKnowledgeGraph.traverse() interface.
        """
        rel_filter = ""
        if relationship_types:
            rel_list = ", ".join(f"'{r.upper()}'" for r in relationship_types)
            rel_filter = f"relationshipFilter: [{rel_list}],"

        query = CypherTemplates.TRAVERSE_BFS.format(
            max_hops=max_hops,
            relationship_filter=f"WHERE type(r) IN [{rel_filter}]" if relationship_types else "",
        )

        try:
            results = self._execute_query(
                query,
                {
                    "entity_id": start_entity,
                    "max_hops": max_hops,
                    "max_nodes": max_nodes,
                },
            )

            if results:
                return {
                    "nodes": results[0].get("nodes", []),
                    "edges": results[0].get("edges", []),
                    "center": start_entity,
                }
        except Exception as e:
            logger.error(f"Traversal query failed: {e}")

        return {"nodes": [], "edges": [], "center": start_entity}

    # =========================================================================
    # Statistics & Health
    # =========================================================================

    def get_stats(self) -> Dict[str, Any]:
        """Get graph statistics."""
        try:
            entity_counts = self._execute_query(CypherTemplates.ENTITY_COUNTS)
            rel_counts = self._execute_query(CypherTemplates.RELATIONSHIP_COUNTS)

            return {
                "connected": True,
                "uri": self.config.uri,
                "database": self.config.database,
                "entities": {r["entity_type"]: r["count"] for r in entity_counts},
                "relationships": {r["relationship_type"]: r["count"] for r in rel_counts},
                "total_entities": sum(r["count"] for r in entity_counts),
                "total_relationships": sum(r["count"] for r in rel_counts),
                "embedding_method": self.config.embedding_method.value,
                "embedding_dim": self.config.embedding_dim,
                "cached_embeddings": len(self._entity_embeddings),
            }
        except Exception as e:
            return {
                "connected": False,
                "error": str(e),
                "uri": self.config.uri,
            }

    def health_check(self) -> bool:
        """Check if Neo4j connection is healthy."""
        try:
            result = self._execute_query("RETURN 1 AS ok")
            return result[0].get("ok") == 1
        except Exception:
            return False


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def _normalize_entity_type(entity_type: Union[str, Enum]) -> str:
    """Normalize entity type to string."""
    if isinstance(entity_type, Enum):
        return entity_type.value
    return str(entity_type).lower()


# =============================================================================
# FACTORY FUNCTIONS
# =============================================================================


_neo4j_instance: Optional[Neo4jGraphRAG] = None
_instance_lock = threading.Lock()


def get_neo4j_graph_rag(
    config: Optional[Neo4jConfig] = None,
    force_new: bool = False,
) -> Neo4jGraphRAG:
    """
    Get Neo4j Graph RAG singleton instance.

    Args:
        config: Optional configuration (uses env vars if not provided)
        force_new: Force creation of new instance

    Returns:
        Neo4jGraphRAG instance
    """
    global _neo4j_instance

    with _instance_lock:
        if _neo4j_instance is None or force_new:
            _neo4j_instance = Neo4jGraphRAG(config)
        return _neo4j_instance


def close_neo4j_graph_rag() -> None:
    """Close the global Neo4j instance."""
    global _neo4j_instance

    with _instance_lock:
        if _neo4j_instance is not None:
            _neo4j_instance.close()
            _neo4j_instance = None


# =============================================================================
# BRIDGE TO EXISTING GRAPH RAG
# =============================================================================


class Neo4jLegalKnowledgeGraphBridge:
    """
    Bridge class that provides LegalKnowledgeGraph interface backed by Neo4j.

    Allows gradual migration from NetworkX to Neo4j while maintaining
    API compatibility with existing code.
    """

    def __init__(
        self,
        scope: Scope = Scope.GLOBAL,
        scope_id: str = "global",
        neo4j_config: Optional[Neo4jConfig] = None,
    ):
        self.scope = scope
        self.scope_id = scope_id
        self._neo4j = get_neo4j_graph_rag(neo4j_config)

    def add_entity(
        self,
        entity_type: Union[str, Enum],
        entity_id: str,
        name: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Add entity (LegalKnowledgeGraph compatible)."""
        properties = metadata or {}
        properties["name"] = name
        properties["scope"] = self.scope.value
        properties["scope_id"] = self.scope_id

        return self._neo4j.add_entity(entity_type, entity_id, properties)

    def add_relation(
        self,
        source_id: str,
        target_id: str,
        relation_type: Union[str, Enum],
        weight: float = 1.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Add relationship (LegalKnowledgeGraph compatible)."""
        return self._neo4j.add_relationship(
            source_id, target_id, relation_type, metadata, weight
        )

    # Alias for compatibility
    add_relationship = add_relation

    def traverse(
        self,
        start_node_id: str,
        hops: int = 2,
        relation_filter: Optional[List[Union[str, Enum]]] = None,
        max_nodes: int = 50,
    ) -> Dict[str, Any]:
        """Traverse graph (LegalKnowledgeGraph compatible)."""
        rel_types = None
        if relation_filter:
            rel_types = [
                r.value if isinstance(r, Enum) else r
                for r in relation_filter
            ]

        return self._neo4j.traverse(start_node_id, hops, max_nodes, rel_types)

    def get_context(
        self,
        entity_ids: Set[str],
        hops: int = 1,
        token_budget: Optional[int] = None,
    ) -> str:
        """Get context (LegalKnowledgeGraph compatible)."""
        return self._neo4j.get_graph_context(
            list(entity_ids), hops, token_budget or 500
        )

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics (LegalKnowledgeGraph compatible)."""
        stats = self._neo4j.get_stats()
        stats["scope"] = self.scope.value
        stats["scope_id"] = self.scope_id
        stats["backend"] = "neo4j"
        return stats


# =============================================================================
# MODULE EXPORTS
# =============================================================================


__all__ = [
    # Configuration
    "EmbeddingMethod",
    "Neo4jConfig",
    # Data classes
    "ReasoningPath",
    "EntityEmbedding",
    # Cypher templates
    "CypherTemplates",
    # Main class
    "Neo4jGraphRAG",
    # Bridge class
    "Neo4jLegalKnowledgeGraphBridge",
    # Factory functions
    "get_neo4j_graph_rag",
    "close_neo4j_graph_rag",
]
