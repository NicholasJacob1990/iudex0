"""
Neo4j MVP Graph Service for Legal RAG

Simple, deterministic GraphRAG without embedding training:
- Document → Chunk → Entity relationships
- Path-based queries with Cypher
- Multi-tenant security trimming
- Explainable connections for LLM context

Schema:
    Nodes:
    - Document (doc_hash, tenant_id, scope, case_id, title, source_type)
    - Chunk (chunk_uid, doc_hash, chunk_index, text_preview)
    - Entity (entity_type, entity_id, name, normalized)

    Relationships:
    - (:Document)-[:HAS_CHUNK]->(:Chunk)
    - (:Chunk)-[:MENTIONS]->(:Entity)
    - (:Chunk)-[:NEXT]->(:Chunk)  # sequence for neighbor expansion
    - (:Entity)-[:RELATED_TO]->(:Entity)  # optional heuristic

Usage:
    from app.services.rag.core.neo4j_mvp import get_neo4j_mvp

    neo4j = get_neo4j_mvp()

    # Ingest
    neo4j.ingest_document(doc_hash, chunks, metadata, tenant_id)

    # Query
    results = neo4j.query_related_chunks(
        entities=["art_5", "lei_8666"],
        tenant_id="tenant1",
        scope="global",
        max_hops=2
    )
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import (
    Any,
    Dict,
    List,
    Optional,
    Set,
    Tuple,
    Union,
)

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================


@dataclass
class Neo4jMVPConfig:
    """Configuration for Neo4j MVP service."""

    # Connection
    uri: str = "bolt://localhost:7687"
    user: str = "neo4j"
    password: str = "password"
    database: str = "iudex"

    # Pool settings
    max_connection_pool_size: int = 50
    connection_timeout: int = 30

    # Query settings
    max_hops: int = 2
    max_chunks_per_query: int = 50
    max_entities_per_chunk: int = 20

    # Ingest settings
    batch_size: int = 100
    create_indexes: bool = True

    @classmethod
    def from_env(cls) -> "Neo4jMVPConfig":
        """Load from environment variables."""
        return cls(
            uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
            user=os.getenv("NEO4J_USER", "neo4j"),
            password=os.getenv("NEO4J_PASSWORD", "password"),
            database=os.getenv("NEO4J_DATABASE", "iudex"),
            max_hops=int(os.getenv("NEO4J_MAX_HOPS", "2")),
            max_chunks_per_query=int(os.getenv("NEO4J_MAX_CHUNKS", "50")),
        )


# =============================================================================
# ENTITY TYPES (Legal Domain)
# =============================================================================


class EntityType(str, Enum):
    """Entity types extracted from legal documents."""
    ARTIGO = "artigo"      # Art. 5, § 1º, inciso II
    LEI = "lei"            # Lei 8.666/93
    SUMULA = "sumula"      # Súmula 331 TST
    PROCESSO = "processo"  # Número CNJ
    TRIBUNAL = "tribunal"  # STF, STJ, TRF
    TEMA = "tema"          # Tema 1234 STF
    PARTE = "parte"        # Nome de parte
    OAB = "oab"            # Número OAB


class Scope(str, Enum):
    """Access scope for documents."""
    GLOBAL = "global"
    PRIVATE = "private"
    GROUP = "group"
    LOCAL = "local"


# =============================================================================
# ENTITY EXTRACTOR (Regex-based, no LLM)
# =============================================================================


class LegalEntityExtractor:
    """
    Extract legal entities using regex patterns.

    No LLM needed - pure pattern matching for Brazilian legal citations.
    """

    PATTERNS = {
        EntityType.LEI: re.compile(
            r"(?:Lei|Decreto|MP|LC|Lei Complementar|Decreto-Lei|Portaria|Resolução)\s*"
            r"n?[oº]?\s*([\d.]+)(?:/|\s+de\s+)?(\d{2,4})?",
            re.IGNORECASE,
        ),
        EntityType.ARTIGO: re.compile(
            r"(?:Art|Artigo)\.?\s*(\d+)[oº]?(?:\s*,?\s*[§]\s*(\d+)[oº]?)?"
            r"(?:\s*,?\s*inciso\s+([IVXLCDM]+))?",
            re.IGNORECASE,
        ),
        EntityType.SUMULA: re.compile(
            r"S[úu]mula\s+(?:Vinculante\s+)?n?[oº]?\s*(\d+)\s*(?:do\s+)?(STF|STJ|TST|TSE)?",
            re.IGNORECASE,
        ),
        EntityType.PROCESSO: re.compile(
            r"(\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4})",
        ),
        EntityType.TRIBUNAL: re.compile(
            r"\b(STF|STJ|TST|TSE|TRF[1-5]?|TJ[A-Z]{2}|TRT\d{1,2})\b",
            re.IGNORECASE,
        ),
        EntityType.TEMA: re.compile(
            r"Tema\s+(?:n[oº]?\s*)?(\d+)\s*(?:do\s+)?(STF|STJ)?",
            re.IGNORECASE,
        ),
        EntityType.OAB: re.compile(
            r"OAB[/-]?\s*([A-Z]{2})\s*n?[oº]?\s*([\d.]+)",
            re.IGNORECASE,
        ),
    }

    @classmethod
    def extract(cls, text: str) -> List[Dict[str, Any]]:
        """
        Extract all entities from text.

        Returns:
            List of entity dicts with: entity_type, entity_id, name, metadata
        """
        entities: List[Dict[str, Any]] = []
        seen: Set[str] = set()

        # Lei/Decreto
        for match in cls.PATTERNS[EntityType.LEI].finditer(text):
            numero = match.group(1).replace(".", "")
            ano = match.group(2) or ""
            # Normalize 2-digit year to 4-digit
            if ano and len(ano) == 2:
                ano = f"19{ano}" if int(ano) > 50 else f"20{ano}"
            entity_id = f"lei_{numero}"
            if ano:
                entity_id += f"_{ano}"
            if entity_id not in seen:
                seen.add(entity_id)
                name = f"Lei {numero}"
                if ano:
                    name += f"/{ano}"
                entities.append({
                    "entity_type": EntityType.LEI.value,
                    "entity_id": entity_id,
                    "name": name,
                    "normalized": f"lei:{numero}/{ano}" if ano else f"lei:{numero}",
                    "metadata": {"numero": numero, "ano": ano},
                })

        # Artigo
        for match in cls.PATTERNS[EntityType.ARTIGO].finditer(text):
            artigo = match.group(1)
            paragrafo = match.group(2) or ""
            inciso = match.group(3) or ""
            entity_id = f"art_{artigo}"
            if paragrafo:
                entity_id += f"_p{paragrafo}"
            if inciso:
                entity_id += f"_i{inciso}"
            if entity_id not in seen:
                seen.add(entity_id)
                name = f"Art. {artigo}"
                if paragrafo:
                    name += f", § {paragrafo}"
                if inciso:
                    name += f", inciso {inciso}"
                entities.append({
                    "entity_type": EntityType.ARTIGO.value,
                    "entity_id": entity_id,
                    "name": name,
                    "normalized": entity_id,
                    "metadata": {"artigo": artigo, "paragrafo": paragrafo, "inciso": inciso},
                })

        # Súmula
        for match in cls.PATTERNS[EntityType.SUMULA].finditer(text):
            numero = match.group(1)
            tribunal = (match.group(2) or "STJ").upper()
            entity_id = f"sumula_{tribunal}_{numero}"
            if entity_id not in seen:
                seen.add(entity_id)
                entities.append({
                    "entity_type": EntityType.SUMULA.value,
                    "entity_id": entity_id,
                    "name": f"Súmula {numero} {tribunal}",
                    "normalized": f"sumula:{tribunal}:{numero}",
                    "metadata": {"numero": numero, "tribunal": tribunal},
                })

        # Processo (CNJ)
        for match in cls.PATTERNS[EntityType.PROCESSO].finditer(text):
            numero_cnj = match.group(1)
            entity_id = f"proc_{numero_cnj.replace('.', '_').replace('-', '_')}"
            if entity_id not in seen:
                seen.add(entity_id)
                entities.append({
                    "entity_type": EntityType.PROCESSO.value,
                    "entity_id": entity_id,
                    "name": f"Processo {numero_cnj}",
                    "normalized": f"cnj:{numero_cnj}",
                    "metadata": {"numero_cnj": numero_cnj},
                })

        # Tribunal
        for match in cls.PATTERNS[EntityType.TRIBUNAL].finditer(text):
            tribunal = match.group(1).upper()
            entity_id = f"tribunal_{tribunal}"
            if entity_id not in seen:
                seen.add(entity_id)
                entities.append({
                    "entity_type": EntityType.TRIBUNAL.value,
                    "entity_id": entity_id,
                    "name": tribunal,
                    "normalized": f"tribunal:{tribunal}",
                    "metadata": {"sigla": tribunal},
                })

        # Tema
        for match in cls.PATTERNS[EntityType.TEMA].finditer(text):
            numero = match.group(1)
            tribunal = (match.group(2) or "STF").upper()
            entity_id = f"tema_{tribunal}_{numero}"
            if entity_id not in seen:
                seen.add(entity_id)
                entities.append({
                    "entity_type": EntityType.TEMA.value,
                    "entity_id": entity_id,
                    "name": f"Tema {numero} {tribunal}",
                    "normalized": f"tema:{tribunal}:{numero}",
                    "metadata": {"numero": numero, "tribunal": tribunal},
                })

        # OAB
        for match in cls.PATTERNS[EntityType.OAB].finditer(text):
            uf = match.group(1).upper()
            numero = match.group(2).replace(".", "")
            entity_id = f"oab_{uf}_{numero}"
            if entity_id not in seen:
                seen.add(entity_id)
                entities.append({
                    "entity_type": EntityType.OAB.value,
                    "entity_id": entity_id,
                    "name": f"OAB/{uf} {numero}",
                    "normalized": f"oab:{uf}:{numero}",
                    "metadata": {"uf": uf, "numero": numero},
                })

        return entities


# =============================================================================
# CYPHER QUERIES
# =============================================================================


class CypherQueries:
    """Cypher query templates for Neo4j MVP."""

    # -------------------------------------------------------------------------
    # Schema Creation
    # -------------------------------------------------------------------------

    CREATE_CONSTRAINTS = """
    CREATE CONSTRAINT doc_hash IF NOT EXISTS
    FOR (d:Document) REQUIRE d.doc_hash IS UNIQUE;

    CREATE CONSTRAINT chunk_uid IF NOT EXISTS
    FOR (c:Chunk) REQUIRE c.chunk_uid IS UNIQUE;

    CREATE CONSTRAINT entity_id IF NOT EXISTS
    FOR (e:Entity) REQUIRE e.entity_id IS UNIQUE;
    """

    CREATE_INDEXES = """
    CREATE INDEX doc_tenant IF NOT EXISTS FOR (d:Document) ON (d.tenant_id);
    CREATE INDEX doc_scope IF NOT EXISTS FOR (d:Document) ON (d.scope);
    CREATE INDEX doc_case IF NOT EXISTS FOR (d:Document) ON (d.case_id);
    CREATE INDEX chunk_doc IF NOT EXISTS FOR (c:Chunk) ON (c.doc_hash);
    CREATE INDEX entity_type IF NOT EXISTS FOR (e:Entity) ON (e.entity_type);
    CREATE INDEX entity_normalized IF NOT EXISTS FOR (e:Entity) ON (e.normalized);
    """

    # -------------------------------------------------------------------------
    # Ingest
    # -------------------------------------------------------------------------

    MERGE_DOCUMENT = """
    MERGE (d:Document {doc_hash: $doc_hash})
    ON CREATE SET
        d.tenant_id = $tenant_id,
        d.scope = $scope,
        d.case_id = $case_id,
        d.group_ids = $group_ids,
        d.title = $title,
        d.source_type = $source_type,
        d.sigilo = $sigilo,
        d.allowed_users = $allowed_users,
        d.created_at = datetime()
    ON MATCH SET
        d.updated_at = datetime()
    RETURN d
    """

    MERGE_CHUNK = """
    MERGE (c:Chunk {chunk_uid: $chunk_uid})
    ON CREATE SET
        c.doc_hash = $doc_hash,
        c.chunk_index = $chunk_index,
        c.text_preview = $text_preview,
        c.token_count = $token_count,
        c.created_at = datetime()
    RETURN c
    """

    LINK_DOC_CHUNK = """
    MATCH (d:Document {doc_hash: $doc_hash})
    MATCH (c:Chunk {chunk_uid: $chunk_uid})
    MERGE (d)-[:HAS_CHUNK]->(c)
    """

    LINK_CHUNK_NEXT = """
    MATCH (c1:Chunk {chunk_uid: $prev_chunk_uid})
    MATCH (c2:Chunk {chunk_uid: $chunk_uid})
    MERGE (c1)-[:NEXT]->(c2)
    """

    MERGE_ENTITY = """
    MERGE (e:Entity {entity_id: $entity_id})
    ON CREATE SET
        e.entity_type = $entity_type,
        e.name = $name,
        e.normalized = $normalized,
        e.metadata = $metadata,
        e.created_at = datetime()
    RETURN e
    """

    LINK_CHUNK_ENTITY = """
    MATCH (c:Chunk {chunk_uid: $chunk_uid})
    MATCH (e:Entity {entity_id: $entity_id})
    MERGE (c)-[:MENTIONS]->(e)
    """

    LINK_ENTITY_RELATED = """
    MATCH (e1:Entity {entity_id: $entity1_id})
    MATCH (e2:Entity {entity_id: $entity2_id})
    MERGE (e1)-[:RELATED_TO]->(e2)
    """

    # -------------------------------------------------------------------------
    # Query: Find chunks by entities
    # -------------------------------------------------------------------------

    FIND_CHUNKS_BY_ENTITIES = """
    // Find chunks that mention any of the given entities
    MATCH (e:Entity)
    WHERE e.entity_id IN $entity_ids OR e.normalized IN $normalized_list
    MATCH (c:Chunk)-[:MENTIONS]->(e)
    MATCH (d:Document)-[:HAS_CHUNK]->(c)

    // Security trimming
    WHERE d.scope IN $allowed_scopes
      AND (d.tenant_id = $tenant_id OR d.scope = 'global')
      AND ($case_id IS NULL OR d.case_id = $case_id)
      AND (d.sigilo IS NULL OR d.sigilo = false OR $user_id IN d.allowed_users)

    RETURN DISTINCT
        c.chunk_uid AS chunk_uid,
        c.text_preview AS text_preview,
        c.chunk_index AS chunk_index,
        d.doc_hash AS doc_hash,
        d.title AS doc_title,
        d.source_type AS source_type,
        collect(DISTINCT e.name) AS matched_entities
    ORDER BY c.chunk_index
    LIMIT $limit
    """

    # -------------------------------------------------------------------------
    # Query: Expand with neighbors (NEXT relationship)
    # -------------------------------------------------------------------------

    EXPAND_NEIGHBORS = """
    MATCH (c:Chunk {chunk_uid: $chunk_uid})
    OPTIONAL MATCH (c)<-[:NEXT*1..{window}]-(prev:Chunk)
    OPTIONAL MATCH (c)-[:NEXT*1..{window}]->(next:Chunk)
    WITH c, collect(DISTINCT prev) + collect(DISTINCT next) AS neighbors

    UNWIND neighbors AS n
    MATCH (d:Document)-[:HAS_CHUNK]->(n)

    // Security check on neighbors too
    WHERE d.scope IN $allowed_scopes
      AND (d.tenant_id = $tenant_id OR d.scope = 'global')

    RETURN
        n.chunk_uid AS chunk_uid,
        n.text_preview AS text_preview,
        n.chunk_index AS chunk_index,
        d.doc_hash AS doc_hash
    ORDER BY n.chunk_index
    """

    # -------------------------------------------------------------------------
    # Query: Path-based traversal (for explainable RAG)
    # -------------------------------------------------------------------------

    FIND_PATHS = """
    // Find paths from query entities to document chunks
    MATCH (e:Entity)
    WHERE e.entity_id IN $entity_ids

    // Traverse up to N hops through entities and chunks
    MATCH path = (e)-[:RELATED_TO|MENTIONS*1..{max_hops}]-(target)
    WHERE (target:Chunk OR target:Entity)

    // If target is chunk, get its document
    OPTIONAL MATCH (d:Document)-[:HAS_CHUNK]->(target)
    WHERE target:Chunk

    // Security trimming
    WHERE d IS NULL OR (
        d.scope IN $allowed_scopes
        AND (d.tenant_id = $tenant_id OR d.scope = 'global')
    )

    RETURN
        e.name AS start_entity,
        target.name AS end_name,
        target.entity_id AS end_id,
        labels(target)[0] AS end_type,
        length(path) AS path_length,
        [n IN nodes(path) | coalesce(n.name, n.chunk_uid)] AS path_names,
        [r IN relationships(path) | type(r)] AS path_relations,
        d.doc_hash AS doc_hash,
        target.chunk_uid AS chunk_uid
    ORDER BY path_length
    LIMIT $limit
    """

    # -------------------------------------------------------------------------
    # Query: Co-occurrence (chunks mentioning multiple entities)
    # -------------------------------------------------------------------------

    FIND_COOCCURRENCE = """
    // Find chunks that mention multiple of the given entities
    MATCH (c:Chunk)
    MATCH (c)-[:MENTIONS]->(e:Entity)
    WHERE e.entity_id IN $entity_ids
    WITH c, collect(DISTINCT e.entity_id) AS matched, count(DISTINCT e) AS match_count
    WHERE match_count >= $min_matches

    MATCH (d:Document)-[:HAS_CHUNK]->(c)
    WHERE d.scope IN $allowed_scopes
      AND (d.tenant_id = $tenant_id OR d.scope = 'global')

    RETURN
        c.chunk_uid AS chunk_uid,
        c.text_preview AS text_preview,
        d.doc_hash AS doc_hash,
        d.title AS doc_title,
        matched AS matched_entities,
        match_count
    ORDER BY match_count DESC
    LIMIT $limit
    """

    # -------------------------------------------------------------------------
    # Stats
    # -------------------------------------------------------------------------

    GET_STATS = """
    MATCH (d:Document) WITH count(d) AS docs
    MATCH (c:Chunk) WITH docs, count(c) AS chunks
    MATCH (e:Entity) WITH docs, chunks, count(e) AS entities
    MATCH ()-[r:MENTIONS]->() WITH docs, chunks, entities, count(r) AS mentions
    MATCH ()-[r:HAS_CHUNK]->() WITH docs, chunks, entities, mentions, count(r) AS has_chunk
    MATCH ()-[r:NEXT]->() WITH docs, chunks, entities, mentions, has_chunk, count(r) AS next_rels
    RETURN docs, chunks, entities, mentions, has_chunk, next_rels
    """


# =============================================================================
# NEO4J MVP SERVICE
# =============================================================================


class Neo4jMVPService:
    """
    Neo4j MVP service for legal GraphRAG.

    Provides:
    - Document/Chunk/Entity ingest
    - Entity-based chunk retrieval
    - Path-based queries for explainable RAG
    - Multi-tenant security trimming
    """

    def __init__(self, config: Optional[Neo4jMVPConfig] = None):
        self.config = config or Neo4jMVPConfig.from_env()
        self._driver = None
        self._driver_lock = threading.Lock()
        self._initialized = False

        logger.info(f"Neo4jMVPService configured for {self.config.uri}")

    # -------------------------------------------------------------------------
    # Connection Management
    # -------------------------------------------------------------------------

    @property
    def driver(self):
        """Lazy driver initialization."""
        if self._driver is None:
            with self._driver_lock:
                if self._driver is None:
                    try:
                        from neo4j import GraphDatabase
                    except ImportError:
                        raise ImportError("Neo4j driver required: pip install neo4j")

                    self._driver = GraphDatabase.driver(
                        self.config.uri,
                        auth=(self.config.user, self.config.password),
                        max_connection_pool_size=self.config.max_connection_pool_size,
                    )
                    logger.info(f"Neo4j connected: {self.config.uri}")

                    if self.config.create_indexes and not self._initialized:
                        self._create_schema()
                        self._initialized = True

        return self._driver

    def close(self) -> None:
        """Close driver connection."""
        if self._driver:
            self._driver.close()
            self._driver = None
            logger.info("Neo4j connection closed")

    def _execute_read(
        self,
        query: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Execute read query."""
        with self.driver.session(database=self.config.database) as session:
            result = session.run(query, params or {})
            return [record.data() for record in result]

    def _execute_write(
        self,
        query: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Execute write query."""
        with self.driver.session(database=self.config.database) as session:
            result = session.execute_write(
                lambda tx: list(tx.run(query, params or {}))
            )
            return [record.data() for record in result]

    def _create_schema(self) -> None:
        """Create constraints and indexes."""
        try:
            # Split and execute each statement separately
            for stmt in CypherQueries.CREATE_CONSTRAINTS.strip().split(';'):
                stmt = stmt.strip()
                if stmt:
                    try:
                        self._execute_write(stmt)
                    except Exception as e:
                        logger.debug(f"Constraint may exist: {e}")

            for stmt in CypherQueries.CREATE_INDEXES.strip().split(';'):
                stmt = stmt.strip()
                if stmt:
                    try:
                        self._execute_write(stmt)
                    except Exception as e:
                        logger.debug(f"Index may exist: {e}")

            logger.info("Neo4j schema created/verified")
        except Exception as e:
            logger.warning(f"Schema creation warning: {e}")

    # -------------------------------------------------------------------------
    # Ingest
    # -------------------------------------------------------------------------

    def ingest_document(
        self,
        doc_hash: str,
        chunks: List[Dict[str, Any]],
        metadata: Dict[str, Any],
        tenant_id: str,
        scope: str = "global",
        case_id: Optional[str] = None,
        extract_entities: bool = True,
    ) -> Dict[str, Any]:
        """
        Ingest a document with its chunks into Neo4j.

        Args:
            doc_hash: Unique document identifier
            chunks: List of chunk dicts with 'chunk_uid', 'text', 'chunk_index'
            metadata: Document metadata (title, source_type, etc.)
            tenant_id: Tenant identifier
            scope: Access scope (global, private, group, local)
            case_id: Case identifier for local scope
            extract_entities: Whether to extract and link entities

        Returns:
            Dict with counts of created nodes/relationships
        """
        stats = {
            "document": 0,
            "chunks": 0,
            "entities": 0,
            "mentions": 0,
            "next_rels": 0,
        }

        # Create document node
        self._execute_write(
            CypherQueries.MERGE_DOCUMENT,
            {
                "doc_hash": doc_hash,
                "tenant_id": tenant_id,
                "scope": scope,
                "case_id": case_id,
                "group_ids": metadata.get("group_ids", []),
                "title": metadata.get("title", ""),
                "source_type": metadata.get("source_type", ""),
                "sigilo": metadata.get("sigilo", False),
                "allowed_users": metadata.get("allowed_users", []),
            }
        )
        stats["document"] = 1

        prev_chunk_uid = None
        all_entities: Dict[str, Dict[str, Any]] = {}

        for chunk in chunks:
            chunk_uid = chunk.get("chunk_uid")
            chunk_text = chunk.get("text", "")
            chunk_index = chunk.get("chunk_index", 0)

            if not chunk_uid:
                chunk_uid = hashlib.md5(
                    f"{doc_hash}:{chunk_index}".encode()
                ).hexdigest()

            # Create chunk node
            self._execute_write(
                CypherQueries.MERGE_CHUNK,
                {
                    "chunk_uid": chunk_uid,
                    "doc_hash": doc_hash,
                    "chunk_index": chunk_index,
                    "text_preview": chunk_text[:500] if chunk_text else "",
                    "token_count": chunk.get("token_count", len(chunk_text) // 4),
                }
            )
            stats["chunks"] += 1

            # Link document → chunk
            self._execute_write(
                CypherQueries.LINK_DOC_CHUNK,
                {"doc_hash": doc_hash, "chunk_uid": chunk_uid}
            )

            # Link previous → current (NEXT)
            if prev_chunk_uid:
                self._execute_write(
                    CypherQueries.LINK_CHUNK_NEXT,
                    {"prev_chunk_uid": prev_chunk_uid, "chunk_uid": chunk_uid}
                )
                stats["next_rels"] += 1

            prev_chunk_uid = chunk_uid

            # Extract and link entities
            if extract_entities and chunk_text:
                entities = LegalEntityExtractor.extract(chunk_text)

                for ent in entities[:self.config.max_entities_per_chunk]:
                    entity_id = ent["entity_id"]

                    # Merge entity
                    if entity_id not in all_entities:
                        self._execute_write(
                            CypherQueries.MERGE_ENTITY,
                            {
                                "entity_id": entity_id,
                                "entity_type": ent["entity_type"],
                                "name": ent["name"],
                                "normalized": ent["normalized"],
                                "metadata": str(ent.get("metadata", {})),
                            }
                        )
                        all_entities[entity_id] = ent
                        stats["entities"] += 1

                    # Link chunk → entity
                    self._execute_write(
                        CypherQueries.LINK_CHUNK_ENTITY,
                        {"chunk_uid": chunk_uid, "entity_id": entity_id}
                    )
                    stats["mentions"] += 1

        logger.info(
            f"Ingested doc {doc_hash}: {stats['chunks']} chunks, "
            f"{stats['entities']} entities, {stats['mentions']} mentions"
        )

        return stats

    # -------------------------------------------------------------------------
    # Query
    # -------------------------------------------------------------------------

    def query_chunks_by_entities(
        self,
        entity_ids: List[str],
        tenant_id: str,
        scope: str = "global",
        case_id: Optional[str] = None,
        user_id: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Find chunks that mention any of the given entities.

        Args:
            entity_ids: List of entity IDs to search for
            tenant_id: Tenant identifier
            scope: Access scope
            case_id: Case identifier (for local scope)
            user_id: User ID for sigilo check
            limit: Maximum chunks to return

        Returns:
            List of chunk dicts with matched entities
        """
        # Build normalized list for fuzzy matching
        normalized_list = [eid.replace("_", ":") for eid in entity_ids]

        # Allowed scopes based on access level
        allowed_scopes = ["global"]
        if scope in ["private", "group", "local"]:
            allowed_scopes.append(scope)

        results = self._execute_read(
            CypherQueries.FIND_CHUNKS_BY_ENTITIES,
            {
                "entity_ids": entity_ids,
                "normalized_list": normalized_list,
                "tenant_id": tenant_id,
                "allowed_scopes": allowed_scopes,
                "case_id": case_id,
                "user_id": user_id,
                "limit": limit,
            }
        )

        return results

    def query_chunks_by_text(
        self,
        query_text: str,
        tenant_id: str,
        scope: str = "global",
        case_id: Optional[str] = None,
        user_id: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Extract entities from query and find related chunks.

        This is the main GraphRAG entry point.
        """
        # Extract entities from query
        entities = LegalEntityExtractor.extract(query_text)
        entity_ids = [e["entity_id"] for e in entities]

        if not entity_ids:
            return []

        return self.query_chunks_by_entities(
            entity_ids=entity_ids,
            tenant_id=tenant_id,
            scope=scope,
            case_id=case_id,
            user_id=user_id,
            limit=limit,
        )

    def expand_with_neighbors(
        self,
        chunk_uid: str,
        tenant_id: str,
        scope: str = "global",
        window: int = 1,
    ) -> List[Dict[str, Any]]:
        """
        Get neighboring chunks using NEXT relationship.

        Useful for parent/neighbor expansion.
        """
        allowed_scopes = ["global"]
        if scope in ["private", "group", "local"]:
            allowed_scopes.append(scope)

        query = CypherQueries.EXPAND_NEIGHBORS.format(window=window)

        return self._execute_read(
            query,
            {
                "chunk_uid": chunk_uid,
                "tenant_id": tenant_id,
                "allowed_scopes": allowed_scopes,
            }
        )

    def find_paths(
        self,
        entity_ids: List[str],
        tenant_id: str,
        scope: str = "global",
        max_hops: int = 2,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Find paths from entities to other entities/chunks.

        Returns explainable paths for RAG context.
        """
        allowed_scopes = ["global"]
        if scope in ["private", "group", "local"]:
            allowed_scopes.append(scope)

        query = CypherQueries.FIND_PATHS.format(max_hops=max_hops)

        return self._execute_read(
            query,
            {
                "entity_ids": entity_ids,
                "tenant_id": tenant_id,
                "allowed_scopes": allowed_scopes,
                "limit": limit,
            }
        )

    def find_cooccurrence(
        self,
        entity_ids: List[str],
        tenant_id: str,
        scope: str = "global",
        min_matches: int = 2,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Find chunks that mention multiple of the given entities.

        Good for finding highly relevant chunks.
        """
        allowed_scopes = ["global"]
        if scope in ["private", "group", "local"]:
            allowed_scopes.append(scope)

        return self._execute_read(
            CypherQueries.FIND_COOCCURRENCE,
            {
                "entity_ids": entity_ids,
                "tenant_id": tenant_id,
                "allowed_scopes": allowed_scopes,
                "min_matches": min_matches,
                "limit": limit,
            }
        )

    # -------------------------------------------------------------------------
    # Entity Management
    # -------------------------------------------------------------------------

    def link_related_entities(
        self,
        entity1_id: str,
        entity2_id: str,
    ) -> bool:
        """Create RELATED_TO relationship between entities."""
        try:
            self._execute_write(
                CypherQueries.LINK_ENTITY_RELATED,
                {"entity1_id": entity1_id, "entity2_id": entity2_id}
            )
            return True
        except Exception as e:
            logger.error(f"Failed to link entities: {e}")
            return False

    # -------------------------------------------------------------------------
    # Stats
    # -------------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Get graph statistics."""
        try:
            results = self._execute_read(CypherQueries.GET_STATS)
            if results:
                return {
                    "connected": True,
                    "uri": self.config.uri,
                    **results[0],
                }
        except Exception as e:
            return {"connected": False, "error": str(e)}

        return {"connected": False}

    def health_check(self) -> bool:
        """Check if Neo4j is healthy."""
        try:
            result = self._execute_read("RETURN 1 AS ok")
            return result[0].get("ok") == 1
        except Exception:
            return False


# =============================================================================
# SINGLETON
# =============================================================================


_neo4j_mvp: Optional[Neo4jMVPService] = None
_neo4j_lock = threading.Lock()


def get_neo4j_mvp(config: Optional[Neo4jMVPConfig] = None) -> Neo4jMVPService:
    """Get or create Neo4j MVP service singleton."""
    global _neo4j_mvp

    with _neo4j_lock:
        if _neo4j_mvp is None:
            _neo4j_mvp = Neo4jMVPService(config)
        return _neo4j_mvp


def close_neo4j_mvp() -> None:
    """Close the Neo4j MVP singleton."""
    global _neo4j_mvp

    with _neo4j_lock:
        if _neo4j_mvp is not None:
            _neo4j_mvp.close()
            _neo4j_mvp = None


# =============================================================================
# RAG INTEGRATION HELPERS
# =============================================================================


def enrich_rag_with_graph(
    query: str,
    chunks: List[Dict[str, Any]],
    tenant_id: str,
    scope: str = "global",
    case_id: Optional[str] = None,
    max_graph_chunks: int = 10,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Enrich RAG results with graph-based chunks.

    Args:
        query: User query
        chunks: Chunks from vector/lexical search
        tenant_id: Tenant identifier
        scope: Access scope
        case_id: Case identifier
        max_graph_chunks: Max chunks to add from graph

    Returns:
        Tuple of (enriched_chunks, paths_for_explanation)
    """
    neo4j = get_neo4j_mvp()

    # Extract entities from query
    query_entities = LegalEntityExtractor.extract(query)
    entity_ids = [e["entity_id"] for e in query_entities]

    if not entity_ids:
        return chunks, []

    # Get chunks from graph
    graph_chunks = neo4j.query_chunks_by_entities(
        entity_ids=entity_ids,
        tenant_id=tenant_id,
        scope=scope,
        case_id=case_id,
        limit=max_graph_chunks,
    )

    # Get paths for explainability
    paths = neo4j.find_paths(
        entity_ids=entity_ids,
        tenant_id=tenant_id,
        scope=scope,
        max_hops=2,
        limit=10,
    )

    # Merge with existing chunks (deduplicate by chunk_uid)
    existing_uids = {c.get("chunk_uid") for c in chunks if c.get("chunk_uid")}

    for gc in graph_chunks:
        if gc["chunk_uid"] not in existing_uids:
            chunks.append({
                "chunk_uid": gc["chunk_uid"],
                "text": gc.get("text_preview", ""),
                "doc_hash": gc.get("doc_hash"),
                "doc_title": gc.get("doc_title"),
                "source": "graph",
                "matched_entities": gc.get("matched_entities", []),
            })
            existing_uids.add(gc["chunk_uid"])

    return chunks, paths


def build_graph_context(paths: List[Dict[str, Any]], max_chars: int = 500) -> str:
    """
    Build explainable context from graph paths.

    Returns a text block explaining relationships for the LLM.
    """
    if not paths:
        return ""

    lines = ["### Relações do Grafo de Conhecimento:\n"]
    current_chars = len(lines[0])

    for path in paths[:10]:
        start = path.get("start_entity", "")
        end = path.get("end_name", "")
        relations = path.get("path_relations", [])
        path_names = path.get("path_names", [])

        if relations and len(path_names) >= 2:
            # Build path description
            path_desc = f"- {path_names[0]}"
            for i, rel in enumerate(relations):
                if i + 1 < len(path_names):
                    path_desc += f" --[{rel}]--> {path_names[i+1]}"

            if current_chars + len(path_desc) + 1 > max_chars:
                break

            lines.append(path_desc)
            current_chars += len(path_desc) + 1

    return "\n".join(lines)


# =============================================================================
# MODULE EXPORTS
# =============================================================================


__all__ = [
    # Config
    "Neo4jMVPConfig",
    # Types
    "EntityType",
    "Scope",
    # Extractor
    "LegalEntityExtractor",
    # Service
    "Neo4jMVPService",
    # Singleton
    "get_neo4j_mvp",
    "close_neo4j_mvp",
    # RAG helpers
    "enrich_rag_with_graph",
    "build_graph_context",
]
