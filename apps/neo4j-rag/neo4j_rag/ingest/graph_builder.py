"""
Neo4j graph builder: stores documents, chunks, and entities.

Creates nodes and relationships following the schema:
- (:Document)-[:HAS_CHUNK]->(:Chunk)
- (:Chunk)-[:MENTIONS]->(:Entity)
- (:Entity)-[:SUBDISPOSITIVO_DE]->(:Entity)
- (:Entity)-[:PARTE_DE]->(:Entity)
- (:Chunk)-[:NEXT]->(:Chunk)
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from neo4j import GraphDatabase

from ..config import settings
from ..models import Chunk, Document, DocumentType, Entity, EntityType, SourceType

logger = logging.getLogger(__name__)

# ─── Regex patterns for entity extraction ─────────────────────────

_RE_ARTIGO = re.compile(
    r"Art\.?\s*(\d+[A-Za-z]?(?:-[A-Za-z])?)"
    r"(?:\s*,?\s*(?:par\.|§)\s*(\d+[ºo]?))?"
    r"(?:\s*,?\s*(?:inc\.|inciso)\s*([IVXLCDM]+))?"
    r"\s+(?:do|da|dos|das)\s+"
    r"([A-Z][A-Za-z0-9./\s]{1,30}?)(?:\s*[,;.\)]|$)",
    re.MULTILINE,
)

_RE_SUMULA = re.compile(
    r"S[úu]mula(?:\s+Vinculante)?\s+(\d+)(?:\s+(?:do|da)\s+(ST[FJ]|TST|TSE))?",
    re.IGNORECASE,
)

_RE_DECISAO = re.compile(
    r"(RE|REsp|ADI|ADPF|ADC|AgRg|AgInt|RCL|HC|MS|RMS|AI|ARE)\s+"
    r"(\d[\d.]+)",
    re.IGNORECASE,
)

_RE_TEMA = re.compile(r"Tema\s+(\d+)", re.IGNORECASE)

# Canonical siglas
_SIGLA_MAP = {
    "constituição federal": "CF", "constituicao federal": "CF", "crfb": "CF", "cf/88": "CF",
    "código civil": "CC", "codigo civil": "CC",
    "código de processo civil": "CPC", "codigo de processo civil": "CPC",
    "código tributário nacional": "CTN", "codigo tributario nacional": "CTN",
    "código de defesa do consumidor": "CDC", "codigo de defesa do consumidor": "CDC",
    "código penal": "CP", "codigo penal": "CP",
    "consolidação das leis do trabalho": "CLT", "consolidacao das leis do trabalho": "CLT",
}


@dataclass
class IngestStats:
    documents_created: int = 0
    chunks_created: int = 0
    entities_extracted: int = 0
    mentions_created: int = 0
    next_edges_created: int = 0
    pertence_a_created: int = 0
    subdispositivo_de_created: int = 0
    errors: List[str] = field(default_factory=list)


def _make_entity_id(name: str, entity_type: str) -> str:
    raw = f"{entity_type}:{name}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _normalize_lei_name(name: str) -> str:
    lower = name.lower().strip()
    for full, sigla in _SIGLA_MAP.items():
        if full in lower:
            return sigla
    return name.strip()


def _extract_entities_from_chunk(text: str) -> List[Entity]:
    """Extract legal entities from chunk text using regex."""
    entities: Dict[str, Entity] = {}

    # Articles with their Lei
    for m in _RE_ARTIGO.finditer(text):
        lei_name = _normalize_lei_name(m.group(4))
        art_num = m.group(1)
        art_name = f"Art. {art_num} do {lei_name}" if "do" not in lei_name and "da" not in lei_name else f"Art. {art_num} {lei_name}"

        # Create Lei entity
        lei_id = _make_entity_id(lei_name, "Lei")
        if lei_id not in entities:
            entities[lei_id] = Entity(
                id=lei_id, name=lei_name, entity_type=EntityType.LEI,
                normalized_name=lei_name,
            )

        # Create Artigo entity
        full_name = f"Art. {art_num}"
        if m.group(2):
            full_name += f" par.{m.group(2)}"
        if m.group(3):
            full_name += f" inc.{m.group(3)}"
        full_name += f" do {lei_name}" if "do" not in lei_name and "da" not in lei_name else f" {lei_name}"

        art_id = _make_entity_id(full_name, "Artigo")
        if art_id not in entities:
            entities[art_id] = Entity(
                id=art_id, name=full_name, entity_type=EntityType.ARTIGO,
                normalized_name=full_name,
                properties={"lei_pai": lei_name, "numero": art_num},
            )

    # Súmulas
    for m in _RE_SUMULA.finditer(text):
        tribunal = (m.group(2) or "").upper()
        name = f"Súmula {m.group(1)}"
        if tribunal:
            name += f" do {tribunal}"
        sid = _make_entity_id(name, "Sumula")
        if sid not in entities:
            entities[sid] = Entity(
                id=sid, name=name, entity_type=EntityType.SUMULA,
                normalized_name=name,
            )

    # Decisões
    for m in _RE_DECISAO.finditer(text):
        tipo = m.group(1).upper()
        numero = m.group(2).replace(".", "")
        name = f"{tipo} {numero}"
        did = _make_entity_id(name, "Decisao")
        if did not in entities:
            entities[did] = Entity(
                id=did, name=name, entity_type=EntityType.DECISAO,
                normalized_name=name,
            )

    # Temas
    for m in _RE_TEMA.finditer(text):
        name = f"Tema {m.group(1)}"
        tid = _make_entity_id(name, "Tema")
        if tid not in entities:
            entities[tid] = Entity(
                id=tid, name=name, entity_type=EntityType.TEMA,
                normalized_name=name,
            )

    return list(entities.values())


class GraphBuilder:
    """Manages Neo4j connection and graph construction."""

    def __init__(self):
        self._driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
        self._db = settings.neo4j_database

    def close(self):
        self._driver.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def ingest_document(
        self,
        doc: Document,
        chunks: List[Chunk],
    ) -> IngestStats:
        """Ingest a single document with its chunks into Neo4j.

        Uses a managed write transaction for atomicity — if any step fails,
        the entire document ingestion is rolled back.
        """
        stats = IngestStats()

        def _do_ingest(tx) -> Tuple[int, int]:
            """Execute all writes inside a single transaction."""
            # 1. Create Document node
            tx.run(
                "MERGE (d:Document {id: $id}) "
                "SET d.title = $title, d.source_type = $source_type, "
                "    d.document_type = $document_type, d.path = $path, "
                "    d.disciplina = $disciplina, d.ingested_at = datetime()",
                id=doc.id, title=doc.title, source_type=doc.source_type.value,
                document_type=doc.document_type.value, path=doc.path,
                disciplina=doc.disciplina,
            )

            # 2. Create Chunk nodes with embeddings
            for chunk in chunks:
                tx.run(
                    "MERGE (c:Chunk {id: $id}) "
                    "SET c.text = $text, c.doc_id = $doc_id, "
                    "    c.position = $position, c.hierarchy = $hierarchy, "
                    "    c.contextual_prefix = $prefix, "
                    "    c.embedding = $embedding",
                    id=chunk.id, text=chunk.text, doc_id=chunk.doc_id,
                    position=chunk.position, hierarchy=chunk.hierarchy,
                    prefix=chunk.contextual_prefix,
                    embedding=chunk.embedding,
                )

                # PART_OF relationship
                tx.run(
                    "MATCH (c:Chunk {id: $cid}), (d:Document {id: $did}) "
                    "MERGE (c)-[:PART_OF]->(d)",
                    cid=chunk.id, did=doc.id,
                )

                # 3. Extract and create entities + MENTIONS
                entities = _extract_entities_from_chunk(chunk.text)
                for entity in entities:
                    tx.run(
                        "MERGE (e:Entity {id: $id}) "
                        "SET e.name = $name, e.entity_type = $etype, "
                        "    e.normalized_name = $norm",
                        id=entity.id, name=entity.name,
                        etype=entity.entity_type.value,
                        norm=entity.normalized_name,
                    )
                    tx.run(
                        "MATCH (c:Chunk {id: $cid}), (e:Entity {id: $eid}) "
                        "MERGE (c)-[:MENTIONS]->(e)",
                        cid=chunk.id, eid=entity.id,
                    )

            # 4. Create NEXT edges between sequential chunks
            for i in range(len(chunks) - 1):
                tx.run(
                    "MATCH (a:Chunk {id: $aid}), (b:Chunk {id: $bid}) "
                    "MERGE (a)-[:NEXT]->(b)",
                    aid=chunks[i].id, bid=chunks[i + 1].id,
                )

            # 5. Create structural relationships between entities
            # PARTE_DE: Artigo -> Lei
            r1 = tx.run(
                "MATCH (a:Entity {entity_type: 'Artigo'}) "
                "WHERE a.name IS NOT NULL "
                "WITH a, a.name AS name "
                "WHERE name CONTAINS ' do ' OR name CONTAINS ' da ' "
                "WITH a, CASE "
                "  WHEN name CONTAINS ' do ' THEN split(name, ' do ')[1] "
                "  WHEN name CONTAINS ' da ' THEN split(name, ' da ')[1] "
                "  ELSE null END AS lei_name "
                "WHERE lei_name IS NOT NULL "
                "MATCH (l:Entity {entity_type: 'Lei', normalized_name: trim(lei_name)}) "
                "MERGE (a)-[:PARTE_DE]->(l) "
                "RETURN count(*) AS c"
            ).single()
            pertence = int(r1["c"] or 0) if r1 else 0

            # SUBDISPOSITIVO_DE: Art with par/inc -> base Art
            r2 = tx.run(
                "MATCH (s:Entity {entity_type: 'Artigo'}) "
                "WHERE s.name CONTAINS 'par.' OR s.name CONTAINS 'inc.' "
                "WITH s, "
                "  CASE "
                "    WHEN s.name CONTAINS 'par.' THEN split(s.name, ' par.')[0] "
                "    WHEN s.name CONTAINS 'inc.' THEN split(s.name, ' inc.')[0] "
                "  END + CASE "
                "    WHEN s.name CONTAINS ' do ' THEN ' do ' + split(s.name, ' do ')[1] "
                "    WHEN s.name CONTAINS ' da ' THEN ' da ' + split(s.name, ' da ')[1] "
                "    ELSE '' END AS parent_name "
                "MATCH (p:Entity {entity_type: 'Artigo', name: trim(parent_name)}) "
                "WHERE p <> s "
                "MERGE (s)-[:SUBDISPOSITIVO_DE]->(p) "
                "RETURN count(*) AS c"
            ).single()
            subdisp = int(r2["c"] or 0) if r2 else 0

            return pertence, subdisp

        with self._driver.session(database=self._db) as session:
            pertence, subdisp = session.execute_write(_do_ingest)

        stats.documents_created = 1
        stats.chunks_created = len(chunks)
        stats.entities_extracted = sum(
            len(_extract_entities_from_chunk(c.text)) for c in chunks
        )
        stats.mentions_created = stats.entities_extracted
        stats.next_edges_created = max(0, len(chunks) - 1)
        stats.pertence_a_created = pertence
        stats.subdispositivo_de_created = subdisp

        return stats

    def ingest_batch(
        self,
        documents: List[Tuple[Document, List[Chunk]]],
    ) -> IngestStats:
        """Ingest multiple documents."""
        total = IngestStats()
        for doc, chunks in documents:
            try:
                stats = self.ingest_document(doc, chunks)
                total.documents_created += stats.documents_created
                total.chunks_created += stats.chunks_created
                total.entities_extracted += stats.entities_extracted
                total.mentions_created += stats.mentions_created
                total.next_edges_created += stats.next_edges_created
                total.pertence_a_created += stats.pertence_a_created
                total.subdispositivo_de_created += stats.subdispositivo_de_created
            except Exception as e:
                total.errors.append(f"{doc.path}: {e}")
                logger.error(f"Failed to ingest {doc.path}: {e}")
        return total
