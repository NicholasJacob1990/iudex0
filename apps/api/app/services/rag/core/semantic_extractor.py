"""
Semantic Entity Extractor using Neo4j Vector Index (with NetworkX fallback)

Extracts semantic legal entities using embeddings:

PRIMARY (Neo4j available):
- Stores seed concepts as entities with embeddings in Neo4j
- Uses db.index.vector.queryNodes for similarity search
- Leverages Neo4j 5.x native vector index for performance

FALLBACK (Neo4j unavailable):
- Stores embeddings in Python memory
- Uses numpy for cosine similarity
- Compatible with NetworkX-based graph

Architecture aligned with Neo4j documentation when available:
- Embeddings stored in entity nodes (e.embedding property)
- Vector index created on semantic entity label
- Similarity computed by Neo4j, not Python
"""

from __future__ import annotations

import hashlib
import logging
import threading
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


# =============================================================================
# GEMINI EMBEDDINGS SERVICE (fallback when OpenAI unavailable)
# =============================================================================


class LocalEmbeddingsService:
    """
    Local embeddings using sentence-transformers.

    No API key required - runs entirely locally.
    Uses multilingual model optimized for Portuguese legal text.
    """

    def __init__(self, model_name: str = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"):
        """
        Initialize local embeddings service.

        Args:
            model_name: HuggingFace model name. Good options:
                - paraphrase-multilingual-mpnet-base-v2 (768 dim, multilingual)
                - distiluse-base-multilingual-cased-v1 (512 dim, fast)
                - all-MiniLM-L6-v2 (384 dim, English-focused but fast)
        """
        self.model_name = model_name
        self._model = None
        self._cache: Dict[str, List[float]] = {}

    def _get_model(self):
        """Lazy initialization of sentence-transformers model."""
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            logger.info(f"Loading local embedding model: {self.model_name}")
            self._model = SentenceTransformer(self.model_name)
            logger.info(f"Model loaded. Dimension: {self._model.get_sentence_embedding_dimension()}")
        return self._model

    def embed_query(self, text: str, use_cache: bool = True) -> List[float]:
        """Generate embedding for a single query."""
        import hashlib
        cache_key = hashlib.sha256(text.encode()).hexdigest()

        if use_cache and cache_key in self._cache:
            return self._cache[cache_key]

        model = self._get_model()
        embedding = model.encode(text, convert_to_numpy=True).tolist()

        if use_cache:
            self._cache[cache_key] = embedding

        return embedding

    def embed_many(
        self,
        texts: List[str],
        show_progress: bool = False,
        batch_size: int = 32,
    ) -> List[List[float]]:
        """Generate embeddings for multiple texts."""
        model = self._get_model()
        embeddings = model.encode(
            texts,
            convert_to_numpy=True,
            show_progress_bar=show_progress,
            batch_size=batch_size,
        )
        return [e.tolist() for e in embeddings]


class GeminiEmbeddingsService:
    """
    Embeddings service using Google's Gemini API.

    Uses text-embedding-004 model (768 dimensions).
    Provides same interface as OpenAI embeddings service.
    """

    def __init__(self, api_key: Optional[str] = None):
        """Initialize Gemini embeddings service."""
        import os
        self.api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY or GOOGLE_API_KEY required")

        self.model = "text-embedding-004"
        self.dimension = 768  # Gemini embedding dimension
        self._client = None
        self._cache: Dict[str, List[float]] = {}

    def _get_client(self):
        """Lazy initialization of Gemini client."""
        if self._client is None:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            self._client = genai
        return self._client

    def embed_query(self, text: str, use_cache: bool = True) -> List[float]:
        """
        Generate embedding for a single query.

        Args:
            text: Text to embed
            use_cache: Whether to use cache

        Returns:
            List of floats representing the embedding
        """
        import hashlib
        cache_key = hashlib.sha256(text.encode()).hexdigest()

        if use_cache and cache_key in self._cache:
            return self._cache[cache_key]

        client = self._get_client()
        result = client.embed_content(
            model=f"models/{self.model}",
            content=text,
            task_type="retrieval_query",
        )
        embedding = list(result["embedding"])

        if use_cache:
            self._cache[cache_key] = embedding

        return embedding

    def embed_many(
        self,
        texts: List[str],
        show_progress: bool = False,
        batch_size: int = 100,
    ) -> List[List[float]]:
        """
        Generate embeddings for multiple texts.

        Args:
            texts: List of texts to embed
            show_progress: Whether to show progress
            batch_size: Batch size for API calls

        Returns:
            List of embeddings
        """
        client = self._get_client()
        embeddings = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]

            # Gemini supports batch embedding
            result = client.embed_content(
                model=f"models/{self.model}",
                content=batch,
                task_type="retrieval_document",
            )

            # Handle both single and batch results
            if isinstance(result["embedding"][0], list):
                embeddings.extend([list(e) for e in result["embedding"]])
            else:
                embeddings.append(list(result["embedding"]))

            if show_progress:
                logger.info(f"Embedded {min(i + batch_size, len(texts))}/{len(texts)}")

        return embeddings


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Calculate cosine similarity between two vectors (fallback mode)."""
    a_np = np.array(a)
    b_np = np.array(b)

    norm_a = np.linalg.norm(a_np)
    norm_b = np.linalg.norm(b_np)

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return float(np.dot(a_np, b_np) / (norm_a * norm_b))


# =============================================================================
# SEMANTIC ENTITY TYPES (descobertos via embedding similarity)
# =============================================================================

SEMANTIC_ENTITY_TYPES = {
    "tese": "Tese jurídica ou argumento legal estruturado",
    "conceito": "Conceito doutrinário ou técnico-jurídico",
    "principio": "Princípio jurídico (constitucional, processual, etc.)",
    "instituto": "Instituto jurídico (prescrição, decadência, etc.)",
    "fundamento": "Fundamento legal ou fático de uma decisão",
}

# Conceitos jurídicos pré-definidos para seed do grafo
# Esses conceitos são armazenados no Neo4j com embeddings para busca vetorial
LEGAL_CONCEPT_SEEDS = [
    # Princípios Constitucionais
    {"name": "Princípio da Legalidade", "type": "principio", "domain": "constitucional"},
    {"name": "Princípio do Contraditório", "type": "principio", "domain": "processual"},
    {"name": "Princípio da Ampla Defesa", "type": "principio", "domain": "processual"},
    {"name": "Princípio da Dignidade da Pessoa Humana", "type": "principio", "domain": "constitucional"},
    {"name": "Princípio da Igualdade", "type": "principio", "domain": "constitucional"},
    {"name": "Princípio da Proporcionalidade", "type": "principio", "domain": "constitucional"},
    {"name": "Princípio da Razoabilidade", "type": "principio", "domain": "constitucional"},
    {"name": "Princípio da Segurança Jurídica", "type": "principio", "domain": "constitucional"},
    {"name": "Princípio da Boa-Fé Objetiva", "type": "principio", "domain": "civil"},
    {"name": "Princípio da Função Social do Contrato", "type": "principio", "domain": "civil"},

    # Institutos Jurídicos
    {"name": "Prescrição", "type": "instituto", "domain": "civil"},
    {"name": "Decadência", "type": "instituto", "domain": "civil"},
    {"name": "Responsabilidade Civil Objetiva", "type": "instituto", "domain": "civil"},
    {"name": "Responsabilidade Civil Subjetiva", "type": "instituto", "domain": "civil"},
    {"name": "Dano Moral", "type": "instituto", "domain": "civil"},
    {"name": "Dano Material", "type": "instituto", "domain": "civil"},
    {"name": "Inversão do Ônus da Prova", "type": "instituto", "domain": "processual"},
    {"name": "Tutela Antecipada", "type": "instituto", "domain": "processual"},
    {"name": "Coisa Julgada", "type": "instituto", "domain": "processual"},
    {"name": "Litispendência", "type": "instituto", "domain": "processual"},

    # Conceitos Doutrinários
    {"name": "Boa-Fé Objetiva", "type": "conceito", "domain": "civil"},
    {"name": "Abuso de Direito", "type": "conceito", "domain": "civil"},
    {"name": "Teoria da Imprevisão", "type": "conceito", "domain": "civil"},
    {"name": "Enriquecimento Sem Causa", "type": "conceito", "domain": "civil"},
    {"name": "Venire Contra Factum Proprium", "type": "conceito", "domain": "civil"},
    {"name": "Supressio", "type": "conceito", "domain": "civil"},
    {"name": "Surrectio", "type": "conceito", "domain": "civil"},
    {"name": "Tu Quoque", "type": "conceito", "domain": "civil"},

    # Teses Jurídicas Comuns
    {"name": "Responsabilidade Objetiva do Estado", "type": "tese", "domain": "administrativo"},
    {"name": "Teoria do Risco Administrativo", "type": "tese", "domain": "administrativo"},
    {"name": "Presunção de Inocência", "type": "tese", "domain": "penal"},
    {"name": "In Dubio Pro Reo", "type": "tese", "domain": "penal"},
    {"name": "Teoria da Perda de Uma Chance", "type": "tese", "domain": "civil"},
]


# =============================================================================
# CYPHER QUERIES FOR SEMANTIC EXTRACTION
# =============================================================================


class SemanticCypherQueries:
    """Cypher queries for semantic entity operations."""

    # Create semantic entity with embedding
    # Uses dual label :Entity:SemanticEntity so FIND_PATHS traversal works
    CREATE_SEMANTIC_ENTITY = """
    MERGE (e:Entity:SemanticEntity {entity_id: $entity_id})
    ON CREATE SET
        e.name = $name,
        e.entity_type = $entity_type,
        e.domain = $domain,
        e.embedding = $embedding,
        e.is_seed = true,
        e.created_at = datetime()
    ON MATCH SET
        e.embedding = $embedding,
        e.updated_at = datetime()
    RETURN e
    """

    # Create vector index for semantic entities
    # Neo4j 5.x syntax
    CREATE_SEMANTIC_VECTOR_INDEX = """
    CREATE VECTOR INDEX semantic_entity_embedding IF NOT EXISTS
    FOR (n:SemanticEntity)
    ON (n.embedding)
    OPTIONS {indexConfig: {
        `vector.dimensions`: $dimension,
        `vector.similarity_function`: 'cosine'
    }}
    """

    # Alternative syntax for Neo4j 5.11+
    CREATE_SEMANTIC_VECTOR_INDEX_ALT = """
    CALL db.index.vector.createNodeIndex(
        'semantic_entity_embedding',
        'SemanticEntity',
        'embedding',
        $dimension,
        'cosine'
    )
    """

    # Query similar entities by vector
    SIMILAR_BY_VECTOR = """
    CALL db.index.vector.queryNodes(
        'semantic_entity_embedding',
        $top_k,
        $embedding
    ) YIELD node, score
    WHERE score >= $min_score
    RETURN node.entity_id AS entity_id,
           node.name AS name,
           node.entity_type AS entity_type,
           node.domain AS domain,
           score
    ORDER BY score DESC
    """

    # Check if vector index exists
    # Note: SHOW INDEXES doesn't support RETURN, so we just query and check if results exist
    CHECK_VECTOR_INDEX = """
    SHOW INDEXES WHERE name = 'semantic_entity_embedding'
    """

    # Get all seed entities
    GET_SEED_ENTITIES = """
    MATCH (e:Entity:SemanticEntity)
    WHERE e.is_seed = true
    RETURN e.entity_id AS entity_id,
           e.name AS name,
           e.entity_type AS entity_type,
           e.domain AS domain
    """

    # Create relationship between semantic entity and other entity
    # Uses RELATED_TO (aligned with FIND_PATHS traversal) with relation_subtype for provenance
    CREATE_SEMANTIC_RELATION = """
    MATCH (sem:Entity {entity_id: $sem_id})
    MATCH (other:Entity {entity_id: $other_id})
    MERGE (sem)-[r:RELATED_TO]->(other)
    ON CREATE SET
        r.weight = $weight,
        r.relation_subtype = 'semantic',
        r.layer = 'candidate',
        r.verified = false,
        r.candidate_type = 'semantic:vector_similarity',
        r.confidence = $weight,
        r.source = 'neo4j_semantic_relation',
        r.created_at = datetime()
    ON MATCH SET
        r.weight = $weight,
        r.updated_at = datetime()
    RETURN sem, r, other
    """


# =============================================================================
# SEMANTIC ENTITY EXTRACTOR (Neo4j-backed)
# =============================================================================


class SemanticEntityExtractor:
    """
    Extract and relate semantic legal entities using embeddings.

    PRIMARY MODE (Neo4j available):
    - Store seed concepts with embeddings in Neo4j
    - Find similar concepts via db.index.vector.queryNodes
    - Create semantic relationships based on vector similarity

    FALLBACK MODE (Neo4j unavailable):
    - Store seed embeddings in Python memory
    - Use numpy cosine_similarity for matching
    - Compatible with NetworkX graph backend

    Mode is auto-detected based on Neo4j availability.
    """

    def __init__(
        self,
        similarity_threshold: float = 0.75,
        max_entities_per_chunk: int = 10,
        embedding_dim: int = 3072,  # OpenAI text-embedding-3-large
    ):
        """
        Initialize the semantic extractor.

        Args:
            similarity_threshold: Minimum cosine similarity to consider a match
            max_entities_per_chunk: Maximum semantic entities to extract per chunk
            embedding_dim: Embedding dimension (3072 for text-embedding-3-large)
        """
        self.similarity_threshold = similarity_threshold
        self.max_entities_per_chunk = max_entities_per_chunk
        self.embedding_dim = embedding_dim

        self._neo4j_driver = None
        self._neo4j_database = "neo4j"
        self._embeddings_service = None
        self._initialized = False
        self._init_lock = threading.Lock()

        # Fallback mode: in-memory embeddings
        self._use_fallback = False
        self._seed_embeddings: Dict[str, List[float]] = {}

    def _get_neo4j_driver(self):
        """Get Neo4j driver (lazy initialization)."""
        if self._neo4j_driver is None:
            try:
                from neo4j import GraphDatabase
                import os
                from app.services.rag.config import get_rag_config

                cfg = get_rag_config()
                uri = os.getenv("NEO4J_URI", cfg.neo4j_uri)
                user = os.getenv("NEO4J_USER") or os.getenv("NEO4J_USERNAME") or cfg.neo4j_user
                password = os.getenv("NEO4J_PASSWORD", cfg.neo4j_password)
                self._neo4j_database = os.getenv("NEO4J_DATABASE", cfg.neo4j_database or "neo4j")

                self._neo4j_driver = GraphDatabase.driver(
                    uri, auth=(user, password)
                )
                logger.info(f"Neo4j driver connected for semantic extraction: {uri}")
            except ImportError:
                logger.warning("Neo4j driver not available - semantic extraction will be limited")
                return None
            except Exception as e:
                logger.error(f"Failed to connect to Neo4j: {e}")
                return None

        return self._neo4j_driver

    def _get_embeddings_service(self):
        """
        Lazy initialization of embeddings service.

        Priority:
        1. OpenAI (if OPENAI_API_KEY is set and valid)
        2. Gemini (if GEMINI_API_KEY or GOOGLE_API_KEY is set and valid)
        3. Local sentence-transformers (always available, no API key needed)
        """
        if self._embeddings_service is None:
            import os

            # Try OpenAI first
            openai_key = os.getenv("OPENAI_API_KEY")
            if openai_key and not openai_key.startswith("#"):
                try:
                    from app.services.rag.core.embeddings import get_embeddings_service
                    service = get_embeddings_service()
                    # Test if it works
                    service.embed_query("test", use_cache=False)
                    self._embeddings_service = service
                    logger.info("Using OpenAI embeddings service")
                    return self._embeddings_service
                except Exception as e:
                    logger.warning(f"OpenAI embeddings failed: {e}")

            # Try Gemini
            gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
            if gemini_key:
                try:
                    service = GeminiEmbeddingsService(api_key=gemini_key)
                    # Test if it works
                    service.embed_query("test", use_cache=False)
                    self._embeddings_service = service
                    logger.info("Using Gemini embeddings service")
                    return self._embeddings_service
                except Exception as e:
                    logger.warning(f"Gemini embeddings failed: {e}")

            # Fallback to local sentence-transformers (always works)
            try:
                self._embeddings_service = LocalEmbeddingsService()
                logger.info("Using local sentence-transformers embeddings (no API key needed)")
                return self._embeddings_service
            except Exception as e:
                logger.error(f"Local embeddings failed: {e}")
                raise RuntimeError(
                    "No embedding service available. Install sentence-transformers: "
                    "pip install sentence-transformers"
                )

        return self._embeddings_service

    def _execute_query(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Execute a Cypher query and return results."""
        driver = self._get_neo4j_driver()
        if driver is None:
            return []

        database = self._neo4j_database or "neo4j"

        with driver.session(database=database) as session:
            result = session.run(query, parameters or {})
            return [record.data() for record in result]

    def _execute_write(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Execute a write query within a transaction."""
        driver = self._get_neo4j_driver()
        if driver is None:
            return []

        database = self._neo4j_database or "neo4j"

        with driver.session(database=database) as session:
            result = session.execute_write(
                lambda tx: list(tx.run(query, parameters or {}))
            )
            return [record.data() for record in result]

    def _make_entity_id(self, entity_type: str, name: str) -> str:
        """Create a unique entity ID."""
        normalized = name.lower().replace(" ", "_")[:50]
        hash_suffix = hashlib.md5(name.encode()).hexdigest()[:8]
        return f"sem_{entity_type}_{normalized}_{hash_suffix}"

    def _create_vector_index(self) -> bool:
        """Create vector index for semantic entities if it doesn't exist."""
        try:
            # Check if index exists (SHOW INDEXES returns rows if found)
            result = self._execute_query(SemanticCypherQueries.CHECK_VECTOR_INDEX)
            if result:  # Index exists if any rows returned
                logger.debug("Semantic vector index already exists")
                return True

            # Try to create index using CALL syntax (works on Neo4j Aura)
            try:
                self._execute_write(
                    SemanticCypherQueries.CREATE_SEMANTIC_VECTOR_INDEX_ALT,
                    {"dimension": self.embedding_dim},
                )
                logger.info("Created semantic vector index (CALL syntax)")
                return True
            except Exception as e:
                logger.debug(f"CALL syntax failed: {e}")
                # Try DDL syntax (string format since parameters don't work in DDL)
                try:
                    create_query = f"""
                    CREATE VECTOR INDEX semantic_entity_embedding IF NOT EXISTS
                    FOR (n:SemanticEntity)
                    ON (n.embedding)
                    OPTIONS {{indexConfig: {{
                        `vector.dimensions`: {self.embedding_dim},
                        `vector.similarity_function`: 'cosine'
                    }}}}
                    """
                    self._execute_write(create_query)
                    logger.info("Created semantic vector index (DDL syntax)")
                    return True
                except Exception as e2:
                    logger.warning(f"Could not create vector index: {e2}")
                    return False

        except Exception as e:
            logger.warning(f"Failed to check/create vector index: {e}")
            return False

    def _initialize_seed_entities(self) -> bool:
        """
        Store seed concepts with their embeddings.

        PRIMARY: Neo4j with vector index
        FALLBACK: Python memory with numpy similarity
        """
        if self._initialized:
            return True

        with self._init_lock:
            if self._initialized:
                return True

            # Try Neo4j first
            driver = self._get_neo4j_driver()

            if driver is not None:
                try:
                    # Create vector index first
                    self._create_vector_index()

                    # Check if seeds already exist
                    existing = self._execute_query(SemanticCypherQueries.GET_SEED_ENTITIES)
                    if len(existing) >= len(LEGAL_CONCEPT_SEEDS):
                        logger.info(f"Seed entities already initialized in Neo4j ({len(existing)} found)")
                        self._use_fallback = False
                        self._initialized = True
                        return True

                    # Get embeddings service
                    service = self._get_embeddings_service()

                    # Embed all seed concepts
                    texts = [c["name"] for c in LEGAL_CONCEPT_SEEDS]
                    embeddings = service.embed_many(texts, show_progress=False)

                    # Store each seed entity with its embedding in Neo4j
                    stored_count = 0
                    for concept, embedding in zip(LEGAL_CONCEPT_SEEDS, embeddings):
                        entity_id = self._make_entity_id(concept["type"], concept["name"])

                        try:
                            self._execute_write(
                                SemanticCypherQueries.CREATE_SEMANTIC_ENTITY,
                                {
                                    "entity_id": entity_id,
                                    "name": concept["name"],
                                    "entity_type": concept["type"],
                                    "domain": concept.get("domain", "geral"),
                                    "embedding": embedding,
                                },
                            )
                            stored_count += 1
                        except Exception as e:
                            logger.warning(f"Failed to store seed entity {concept['name']}: {e}")

                    logger.info(f"Initialized {stored_count} seed entities in Neo4j with embeddings")
                    self._use_fallback = False
                    self._initialized = True
                    return True

                except Exception as e:
                    logger.warning(f"Neo4j initialization failed ({e}), falling back to in-memory mode")

            # Fallback: in-memory embeddings
            return self._initialize_fallback_mode()

    def _initialize_fallback_mode(self) -> bool:
        """Initialize in-memory embeddings (NetworkX-compatible fallback)."""
        try:
            logger.info("Using fallback mode: in-memory embeddings with numpy similarity")
            service = self._get_embeddings_service()

            # Embed all seed concepts
            texts = [c["name"] for c in LEGAL_CONCEPT_SEEDS]
            embeddings = service.embed_many(texts, show_progress=False)

            # Store in memory
            for concept, embedding in zip(LEGAL_CONCEPT_SEEDS, embeddings):
                entity_id = self._make_entity_id(concept["type"], concept["name"])
                self._seed_embeddings[entity_id] = embedding

            logger.info(f"Initialized {len(self._seed_embeddings)} seed embeddings in memory (fallback mode)")
            self._use_fallback = True
            self._initialized = True
            return True

        except Exception as e:
            error_msg = str(e)
            if "401" in error_msg or "invalid_api_key" in error_msg:
                logger.error(
                    "OpenAI API key is invalid. Please set a valid OPENAI_API_KEY. "
                    "Get one at: https://platform.openai.com/api-keys"
                )
            elif "403" in error_msg or "leaked" in error_msg.lower():
                logger.error(
                    "API key was reported as leaked/compromised. Please generate a new key. "
                    "OpenAI: https://platform.openai.com/api-keys | "
                    "Google: https://aistudio.google.com/apikey"
                )
            else:
                logger.error(f"Failed to initialize fallback mode: {e}")
            return False

    def extract(
        self,
        text: str,
        existing_entities: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, List]:
        """
        Extract semantic entities from text using embedding similarity.

        AUTO-DETECTS MODE:
        - Neo4j: Uses db.index.vector.queryNodes
        - Fallback: Uses numpy cosine similarity

        Args:
            text: Text to analyze
            existing_entities: Already extracted entities (from regex) to relate to

        Returns:
            Dict with 'entities' and 'relations' lists
        """
        if not text or len(text.strip()) < 50:
            return {"entities": [], "relations": []}

        # Ensure seeds are initialized (auto-detects mode)
        if not self._initialize_seed_entities():
            logger.warning("Seed entities not available - returning empty results")
            return {"entities": [], "relations": []}

        # Route to appropriate implementation
        if self._use_fallback:
            return self._extract_fallback(text, existing_entities)
        else:
            return self._extract_neo4j(text, existing_entities)

    def _extract_neo4j(
        self,
        text: str,
        existing_entities: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, List]:
        """Extract using Neo4j vector index."""
        try:
            service = self._get_embeddings_service()
            text_embedding = service.embed_query(text[:8000], use_cache=True)

            # Query Neo4j vector index
            results = self._execute_query(
                SemanticCypherQueries.SIMILAR_BY_VECTOR,
                {
                    "embedding": text_embedding,
                    "top_k": self.max_entities_per_chunk + 5,
                    "min_score": self.similarity_threshold,
                },
            )

            # Build entities list
            entities = []
            for r in results[:self.max_entities_per_chunk]:
                entities.append({
                    "entity_type": r["entity_type"],
                    "entity_id": r["entity_id"],
                    "name": r["name"],
                    "normalized": r["name"].lower().replace(" ", "_"),
                    "confidence": round(r["score"], 4),
                    "metadata": {
                        "source": "neo4j_vector_index",
                        "domain": r.get("domain", "geral"),
                        "similarity_score": round(r["score"], 4),
                    },
                })

            # Build relations
            relations = []
            if existing_entities and entities:
                for sem_ent in entities:
                    for exist_ent in existing_entities:
                        exist_id = exist_ent.get("entity_id", "")
                        if not exist_id:
                            continue
                        try:
                            self._execute_write(
                                SemanticCypherQueries.CREATE_SEMANTIC_RELATION,
                                {
                                    "sem_id": sem_ent["entity_id"],
                                    "other_id": exist_id,
                                    "weight": sem_ent["confidence"],
                                },
                            )
                            relations.append({
                                "source": sem_ent["entity_id"],
                                "target": exist_id,
                                "relation_type": "semantically_related",
                                "weight": sem_ent["confidence"],
                                "metadata": {"source": "neo4j_semantic_relation"},
                            })
                        except Exception as e:
                            logger.debug(f"Could not create semantic relation: {e}")

            return {"entities": entities, "relations": relations}

        except Exception as e:
            logger.error(f"Neo4j extraction failed: {e}")
            return {"entities": [], "relations": []}

    def _extract_fallback(
        self,
        text: str,
        existing_entities: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, List]:
        """Extract using in-memory embeddings (NetworkX-compatible fallback)."""
        try:
            service = self._get_embeddings_service()
            text_embedding = service.embed_query(text[:8000], use_cache=True)

            # Find similar seed concepts using numpy
            similarities: List[Tuple[str, float, Dict]] = []

            for concept in LEGAL_CONCEPT_SEEDS:
                entity_id = self._make_entity_id(concept["type"], concept["name"])
                seed_embedding = self._seed_embeddings.get(entity_id)

                if seed_embedding:
                    sim = cosine_similarity(text_embedding, seed_embedding)
                    if sim >= self.similarity_threshold:
                        similarities.append((entity_id, sim, concept))

            # Sort by similarity and take top matches
            similarities.sort(key=lambda x: x[1], reverse=True)
            top_matches = similarities[:self.max_entities_per_chunk]

            # Build entities list
            entities = []
            for entity_id, sim, concept in top_matches:
                entities.append({
                    "entity_type": concept["type"],
                    "entity_id": entity_id,
                    "name": concept["name"],
                    "normalized": concept["name"].lower().replace(" ", "_"),
                    "confidence": round(sim, 4),
                    "metadata": {
                        "source": "fallback_numpy_similarity",
                        "domain": concept.get("domain", "geral"),
                        "similarity_score": round(sim, 4),
                    },
                })

            # Build relations (in-memory only, not persisted)
            relations = []
            if existing_entities and entities:
                existing_names = [e.get("name", "") for e in existing_entities if e.get("name")]
                if existing_names:
                    try:
                        existing_embeddings = service.embed_many(existing_names, show_progress=False)

                        for sem_ent in entities:
                            sem_id = sem_ent["entity_id"]
                            sem_embedding = self._seed_embeddings.get(sem_id)
                            if not sem_embedding:
                                continue

                            for i, (exist_ent, exist_emb) in enumerate(zip(existing_entities, existing_embeddings)):
                                exist_id = exist_ent.get("entity_id", "")
                                if not exist_id:
                                    continue

                                sim = cosine_similarity(sem_embedding, exist_emb)
                                if sim >= 0.6:
                                    relations.append({
                                        "source": sem_id,
                                        "target": exist_id,
                                        "relation_type": "semantically_related",
                                        "weight": round(sim, 4),
                                        "metadata": {
                                            "source": "fallback_embedding_similarity",
                                            "similarity_score": round(sim, 4),
                                        },
                                    })
                    except Exception as e:
                        logger.warning(f"Failed to embed existing entities: {e}")

            return {"entities": entities, "relations": relations}

        except Exception as e:
            logger.error(f"Fallback extraction failed: {e}")
            return {"entities": [], "relations": []}

    async def extract_async(
        self,
        text: str,
        existing_entities: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, List]:
        """Async version - delegates to sync (Neo4j driver handles threading)."""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.extract, text, existing_entities)

    def find_similar_entities(
        self,
        query: str,
        top_k: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Find seed entities similar to a query.

        AUTO-DETECTS MODE:
        - Neo4j: Uses vector index
        - Fallback: Uses numpy similarity

        Args:
            query: Search query
            top_k: Number of results to return

        Returns:
            List of similar entities with scores
        """
        if not self._initialize_seed_entities():
            return []

        try:
            service = self._get_embeddings_service()
            query_embedding = service.embed_query(query, use_cache=True)

            if self._use_fallback:
                # Fallback: numpy similarity
                results = []
                for concept in LEGAL_CONCEPT_SEEDS:
                    entity_id = self._make_entity_id(concept["type"], concept["name"])
                    seed_embedding = self._seed_embeddings.get(entity_id)

                    if seed_embedding:
                        sim = cosine_similarity(query_embedding, seed_embedding)
                        results.append({
                            "entity_id": entity_id,
                            "name": concept["name"],
                            "type": concept["type"],
                            "domain": concept.get("domain", "geral"),
                            "similarity": round(sim, 4),
                        })

                results.sort(key=lambda x: x["similarity"], reverse=True)
                return results[:top_k]

            else:
                # Neo4j: vector index query
                results = self._execute_query(
                    SemanticCypherQueries.SIMILAR_BY_VECTOR,
                    {
                        "embedding": query_embedding,
                        "top_k": top_k,
                        "min_score": 0.0,
                    },
                )

                return [
                    {
                        "entity_id": r["entity_id"],
                        "name": r["name"],
                        "type": r["entity_type"],
                        "domain": r.get("domain", "geral"),
                        "similarity": round(r["score"], 4),
                    }
                    for r in results
                ]

        except Exception as e:
            logger.error(f"Failed to find similar entities: {e}")
            return []

    @property
    def mode(self) -> str:
        """Return current operating mode."""
        if not self._initialized:
            return "not_initialized"
        return "fallback_numpy" if self._use_fallback else "neo4j_vector_index"

    def close(self) -> None:
        """Close Neo4j driver connection."""
        if self._neo4j_driver is not None:
            self._neo4j_driver.close()
            self._neo4j_driver = None
            logger.info("Semantic extractor Neo4j connection closed")


# =============================================================================
# SINGLETON
# =============================================================================

_extractor: Optional[SemanticEntityExtractor] = None
_extractor_lock = threading.Lock()


def get_semantic_extractor(
    similarity_threshold: float = 0.5,
) -> SemanticEntityExtractor:
    """Get or create singleton semantic extractor."""
    global _extractor

    with _extractor_lock:
        if _extractor is None:
            _extractor = SemanticEntityExtractor(
                similarity_threshold=similarity_threshold
            )
        return _extractor


def close_semantic_extractor() -> None:
    """Close the global semantic extractor."""
    global _extractor

    with _extractor_lock:
        if _extractor is not None:
            _extractor.close()
            _extractor = None
