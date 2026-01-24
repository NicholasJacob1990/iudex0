"""
GraphRAG Service for Legal Knowledge Graphs

Implements:
1. LegalKnowledgeGraph - Entity/relationship management with scope isolation
2. ArgumentGraph - Legal argument structure extraction
3. Persistence by scope (private/group/global/local)
4. Integration with RAG ingestion pipeline
5. Token budget control for graph context

Uses NetworkX for graph storage with JSON persistence.
"""

from __future__ import annotations

import hashlib
import json
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
    Iterable,
    List,
    Optional,
    Protocol,
    Set,
    Tuple,
    Union,
)

try:
    import networkx as nx
except ImportError:
    raise ImportError("NetworkX required: pip install networkx")

from app.services.rag.config import get_rag_config

logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTS
# =============================================================================

def _get_graph_db_path() -> str:
    """Get graph database path from config or default."""
    config = get_rag_config()
    base_path = getattr(config, "graph_db_path", None)
    if base_path:
        return base_path
    # Default to a data directory relative to the app
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
        "data",
        "graph_db"
    )


def _get_default_token_budget() -> int:
    """Get default token budget for graph context."""
    config = get_rag_config()
    return getattr(config, "compression_token_budget", 2000)


CHARS_PER_TOKEN_ESTIMATE = 4  # rough estimate for Portuguese


# =============================================================================
# ENTITY TYPES
# =============================================================================


class EntityType(str, Enum):
    """Legal entity types for knowledge graph nodes."""

    LEI = "lei"
    ARTIGO = "artigo"
    SUMULA = "sumula"
    JURISPRUDENCIA = "jurisprudencia"
    TESE = "tese"
    TEMA = "tema"  # STF/STJ numbered themes
    DOCUMENTO = "documento"
    PARTE = "parte"
    TRIBUNAL = "tribunal"
    PROCESSO = "processo"
    RECURSO = "recurso"
    ACORDAO = "acordao"
    MINISTRO = "ministro"
    RELATOR = "relator"


class RelationType(str, Enum):
    """Relationship types for knowledge graph edges."""

    POSSUI = "possui"  # Lei --possui--> Artigo
    CITA = "cita"  # Jurisprudencia --cita--> Lei
    APLICA = "aplica"  # Jurisprudencia --aplica--> Sumula
    REVOGA = "revoga"  # Lei --revoga--> Lei
    ALTERA = "altera"  # Lei --altera--> Lei
    VINCULA = "vincula"  # Sumula --vincula--> Tese
    RELACIONADA = "relacionada"  # Tese --relacionada--> Tese
    INTERPRETA = "interpreta"  # Jurisprudencia --interpreta--> Artigo
    FUNDAMENTA = "fundamenta"  # Argumento --fundamenta--> Conclusao
    CONTRAPOE = "contrapoe"  # Tese --contrapoe--> Tese
    DERIVA = "deriva"  # Argumento --deriva--> Argumento
    JULGA = "julga"  # Tribunal --julga--> Processo
    RELATA = "relata"  # Ministro --relata--> Acordao
    RECURSO_DE = "recurso_de"  # Recurso --recurso_de--> Processo


class ArgumentType(str, Enum):
    """Types for ArgumentRAG nodes."""

    TESE = "tese"
    FUNDAMENTO = "fundamento"
    CONCLUSAO = "conclusao"
    PREMISSA = "premissa"
    EVIDENCIA = "evidencia"
    CONTRATESE = "contratese"


class Scope(str, Enum):
    """Access scope for graph partitions."""

    GLOBAL = "global"
    PRIVATE = "private"
    GROUP = "group"
    LOCAL = "local"


# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass
class Entity:
    """Base class for graph entities (nodes)."""

    entity_type: str
    entity_id: str  # Unique ID within type
    name: str  # Display name
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def node_id(self) -> str:
        """Global unique ID for graph."""
        return f"{self.entity_type}:{self.entity_id}"


@dataclass
class Relation:
    """Relationship between graph entities (edges)."""

    source_id: str  # Entity node_id
    target_id: str  # Entity node_id
    relation_type: str
    weight: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ArgumentNode:
    """Node in an argument structure."""

    arg_id: str
    arg_type: ArgumentType
    text: str
    confidence: float = 1.0
    source_chunk_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def node_id(self) -> str:
        return f"arg:{self.arg_type.value}:{self.arg_id}"


@dataclass
class ScopedGraphRef:
    """Reference to a scoped graph partition."""

    scope: Scope
    scope_id: str  # tenant_id for private, group_id for group, "global" for global
    persist_path: str


# =============================================================================
# GRAPH SCHEMA & PACKS
# =============================================================================


@dataclass(frozen=True)
class GraphSchema:
    """Schema definition for a knowledge graph domain."""
    name: str
    node_types: Tuple[str, ...]
    relation_types: Tuple[str, ...]


class BaseGraphPack(Protocol):
    """Protocol for domain-specific graph packs."""

    name: str
    schema: GraphSchema

    def extract_candidates(
        self, text: str
    ) -> List[Tuple[Union[str, Enum], str, str, Dict[str, Any]]]:
        ...

    def extract_relations(
        self,
        text: str,
        source_node_id: str,
        candidate_node_ids: Iterable[str],
    ) -> List[Tuple[str, str, Union[str, Enum], Dict[str, Any]]]:
        ...

    def seed_from_metadata(
        self, meta: Dict[str, Any]
    ) -> List[Union[str, Tuple[Union[str, Enum], str, str, Dict[str, Any]]]]:
        ...


def _normalize_graph_type(value: Union[str, Enum]) -> str:
    """Normalize entity/relation type to string."""
    return value.value if isinstance(value, Enum) else str(value)


# =============================================================================
# LEGAL ENTITY EXTRACTOR
# =============================================================================


class LegalEntityExtractor:
    """
    Extract legal entities from text using regex patterns.

    Identifies:
    - Laws (Lei 8.666/93, Decreto 9.412/2018)
    - Articles (Art. 1, SS 2)
    - Sumulas (Sumula 331 TST, Sumula Vinculante 13)
    - Jurisprudence (REsp 1.234.567/SP, ADI 1234)
    - Themes (Tema 1234 STF)
    - Processes (CNJ number format)
    """

    PATTERNS = {
        "lei": re.compile(
            r"(?:Lei|Decreto|MP|LC|Lei Complementar|Decreto-Lei|Portaria)\s*n?[o]?\s*"
            r"([\d.]+)(?:/|\s+de\s+)(\d{4})",
            re.IGNORECASE,
        ),
        "artigo": re.compile(
            r"(?:Art|Artigo)\.?\s*(\d+)[o]?(?:\s*,?\s*[SS]\s*(\d+)[o]?)?",
            re.IGNORECASE,
        ),
        "sumula": re.compile(
            r"S[uU]mula\s+(?:Vinculante\s+)?n?[o]?\s*(\d+)\s*(?:do\s+)?(STF|STJ|TST|TSE)?",
            re.IGNORECASE,
        ),
        "jurisprudencia": re.compile(
            r"(RE|REsp|AgRg|ADI|ADC|ADPF|HC|MS|RMS|RO|AI|ARE|Rcl|AgInt|EDcl|RHC|AREsp)\s*n?[o]?\s*([\d.]+)(?:/([\w]{2}))?",
            re.IGNORECASE,
        ),
        "tema": re.compile(
            r"Tema\s+(?:n[o]?\s*)?(\d+)\s*(?:do\s+)?(STF|STJ)?",
            re.IGNORECASE,
        ),
        "processo": re.compile(
            r"(\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4})",
            re.IGNORECASE,
        ),
        "tribunal": re.compile(
            r"\b(STF|STJ|TST|TSE|TRF\d?|TJSP|TJRJ|TJMG|TJRS|TJPR|TJSC|TRT\d{1,2})\b",
            re.IGNORECASE,
        ),
    }

    @classmethod
    def extract_candidates(
        cls, text: str
    ) -> List[Tuple[Union[str, Enum], str, str, Dict[str, Any]]]:
        """Extract legal entity candidates from text."""
        candidates: List[Tuple[Union[str, Enum], str, str, Dict[str, Any]]] = []
        seen: Set[str] = set()

        # Extract Leis
        for match in cls.PATTERNS["lei"].finditer(text):
            numero = match.group(1).replace(".", "")
            ano = match.group(2)
            entity_id = f"{numero}_{ano}"
            if entity_id not in seen:
                seen.add(entity_id)
                name = f"Lei {numero}/{ano}"
                candidates.append(
                    (EntityType.LEI, entity_id, name, {"numero": numero, "ano": int(ano)})
                )

        # Extract Sumulas
        for match in cls.PATTERNS["sumula"].finditer(text):
            numero = match.group(1)
            tribunal = (match.group(2) or "STJ").upper()
            entity_id = f"{tribunal}_{numero}"
            if entity_id not in seen:
                seen.add(entity_id)
                name = f"Sumula {numero} {tribunal}"
                candidates.append(
                    (
                        EntityType.SUMULA,
                        entity_id,
                        name,
                        {"numero": numero, "tribunal": tribunal},
                    )
                )

        # Extract Jurisprudencia
        for match in cls.PATTERNS["jurisprudencia"].finditer(text):
            tipo = match.group(1).upper()
            numero = match.group(2).replace(".", "")
            uf = (match.group(3) or "").upper()
            entity_id = f"{tipo}_{numero}_{uf}" if uf else f"{tipo}_{numero}"
            if entity_id not in seen:
                seen.add(entity_id)
                name = f"{tipo} {numero}" + (f"/{uf}" if uf else "")
                candidates.append(
                    (
                        EntityType.JURISPRUDENCIA,
                        entity_id,
                        name,
                        {"tipo": tipo, "numero": numero, "uf": uf},
                    )
                )

        # Extract Artigos
        for match in cls.PATTERNS["artigo"].finditer(text):
            artigo = match.group(1)
            paragrafo = match.group(2) or ""
            entity_id = f"art_{artigo}" + (f"_p{paragrafo}" if paragrafo else "")
            if entity_id not in seen:
                seen.add(entity_id)
                name = f"Art. {artigo}" + (f", SS {paragrafo}" if paragrafo else "")
                candidates.append(
                    (
                        EntityType.ARTIGO,
                        entity_id,
                        name,
                        {"artigo": artigo, "paragrafo": paragrafo},
                    )
                )

        # Extract Temas
        for match in cls.PATTERNS["tema"].finditer(text):
            numero = match.group(1)
            tribunal = (match.group(2) or "STF").upper()
            entity_id = f"tema_{tribunal}_{numero}"
            if entity_id not in seen:
                seen.add(entity_id)
                name = f"Tema {numero} {tribunal}"
                candidates.append(
                    (
                        EntityType.TEMA,
                        entity_id,
                        name,
                        {"numero": numero, "tribunal": tribunal},
                    )
                )

        # Extract Processos (CNJ format)
        for match in cls.PATTERNS["processo"].finditer(text):
            numero_cnj = match.group(1)
            entity_id = f"proc_{numero_cnj.replace('.', '_').replace('-', '_')}"
            if entity_id not in seen:
                seen.add(entity_id)
                name = f"Processo {numero_cnj}"
                candidates.append(
                    (
                        EntityType.PROCESSO,
                        entity_id,
                        name,
                        {"numero_cnj": numero_cnj},
                    )
                )

        # Extract Tribunais
        for match in cls.PATTERNS["tribunal"].finditer(text):
            tribunal = match.group(1).upper()
            entity_id = f"tribunal_{tribunal}"
            if entity_id not in seen:
                seen.add(entity_id)
                candidates.append(
                    (
                        EntityType.TRIBUNAL,
                        entity_id,
                        tribunal,
                        {"sigla": tribunal},
                    )
                )

        return candidates


# =============================================================================
# ARGUMENT EXTRACTOR
# =============================================================================


class ArgumentExtractor:
    """
    Extract argument structures from legal text.

    Identifies:
    - Teses (main legal positions)
    - Fundamentos (supporting grounds)
    - Conclusoes (conclusions)
    - Premissas (premises)
    """

    # Markers for argument components
    TESE_MARKERS = [
        r"(?:a\s+)?tese\s+(?:e\s+)?(?:de\s+)?que",
        r"defende[u-]?se\s+que",
        r"sustenta[u-]?se\s+que",
        r"entende[u-]?se\s+que",
        r"o\s+entendimento\s+(?:e\s+)?(?:de\s+)?que",
        r"firma[u-]?se\s+(?:a\s+)?(?:tese|entendimento)",
        r"a\s+jurispruden?cia\s+(?:e\s+)?(?:de\s+)?que",
        r"restou\s+decidido\s+que",
    ]

    FUNDAMENTO_MARKERS = [
        r"com\s+fundamento\s+(?:no|na|em)",
        r"fundament[ao][u-]?se\s+(?:no|na|em)",
        r"com\s+base\s+(?:no|na|em)",
        r"nos\s+termos\s+d[ao]",
        r"conforme\s+(?:o|a|os|as)",
        r"de\s+acordo\s+com",
        r"segundo\s+(?:o|a|os|as)",
        r"em\s+conformidade\s+com",
        r"a\s+teor\s+d[ao]",
    ]

    CONCLUSAO_MARKERS = [
        r"conclui[u-]?se\s+que",
        r"portanto",
        r"assim\s*,",
        r"dessa?\s+forma",
        r"por\s+conseguinte",
        r"logo\s*,",
        r"em\s+conclus[ao]o",
        r"diante\s+do\s+exposto",
        r"ante\s+o\s+exposto",
        r"pelo\s+exposto",
    ]

    @classmethod
    def extract_arguments(
        cls,
        text: str,
        source_chunk_id: Optional[str] = None,
    ) -> List[ArgumentNode]:
        """Extract argument nodes from legal text."""
        arguments: List[ArgumentNode] = []
        text_lower = text.lower()

        # Extract teses
        for marker in cls.TESE_MARKERS:
            for match in re.finditer(marker, text_lower, re.IGNORECASE):
                # Get surrounding context (up to next sentence)
                start = match.start()
                end = min(len(text), start + 500)
                context = text[start:end]
                # Find sentence boundary
                sent_end = context.find(".")
                if sent_end > 0:
                    context = context[: sent_end + 1]

                arg_id = hashlib.md5(context.encode()).hexdigest()[:12]
                arguments.append(
                    ArgumentNode(
                        arg_id=arg_id,
                        arg_type=ArgumentType.TESE,
                        text=context.strip(),
                        source_chunk_id=source_chunk_id,
                        metadata={"marker": marker},
                    )
                )

        # Extract fundamentos
        for marker in cls.FUNDAMENTO_MARKERS:
            for match in re.finditer(marker, text_lower, re.IGNORECASE):
                start = match.start()
                end = min(len(text), start + 400)
                context = text[start:end]
                sent_end = context.find(".")
                if sent_end > 0:
                    context = context[: sent_end + 1]

                arg_id = hashlib.md5(context.encode()).hexdigest()[:12]
                arguments.append(
                    ArgumentNode(
                        arg_id=arg_id,
                        arg_type=ArgumentType.FUNDAMENTO,
                        text=context.strip(),
                        source_chunk_id=source_chunk_id,
                        metadata={"marker": marker},
                    )
                )

        # Extract conclusoes
        for marker in cls.CONCLUSAO_MARKERS:
            for match in re.finditer(marker, text_lower, re.IGNORECASE):
                start = match.start()
                end = min(len(text), start + 300)
                context = text[start:end]
                sent_end = context.find(".")
                if sent_end > 0:
                    context = context[: sent_end + 1]

                arg_id = hashlib.md5(context.encode()).hexdigest()[:12]
                arguments.append(
                    ArgumentNode(
                        arg_id=arg_id,
                        arg_type=ArgumentType.CONCLUSAO,
                        text=context.strip(),
                        source_chunk_id=source_chunk_id,
                        metadata={"marker": marker},
                    )
                )

        return arguments


# =============================================================================
# LEGAL PACK
# =============================================================================


class LegalPack:
    """Domain pack for Brazilian legal entities."""

    name = "legal"
    schema = GraphSchema(
        name="legal",
        node_types=tuple(t.value for t in EntityType),
        relation_types=tuple(r.value for r in RelationType),
    )

    def extract_candidates(
        self, text: str
    ) -> List[Tuple[Union[str, Enum], str, str, Dict[str, Any]]]:
        """Extract entity candidates from text."""
        return LegalEntityExtractor.extract_candidates(text)

    def extract_relations(
        self,
        text: str,
        source_node_id: str,
        candidate_node_ids: Iterable[str],
    ) -> List[Tuple[str, str, Union[str, Enum], Dict[str, Any]]]:
        """Extract relations between entities."""
        return [
            (source_node_id, target_id, RelationType.CITA, {})
            for target_id in candidate_node_ids
            if target_id != source_node_id
        ]

    def seed_from_metadata(
        self, meta: Dict[str, Any]
    ) -> List[Union[str, Tuple[Union[str, Enum], str, str, Dict[str, Any]]]]:
        """Seed entities from document metadata."""
        seeds: List[Union[str, Tuple[Union[str, Enum], str, str, Dict[str, Any]]]] = []
        meta = meta or {}

        tipo = str(meta.get("tipo") or meta.get("source_type") or "").lower().strip()
        numero = str(meta.get("numero") or "").replace(".", "")
        ano = str(meta.get("ano") or "").strip()

        if tipo in {"lei", "decreto", "portaria"} and numero and ano:
            seeds.append(
                (
                    EntityType.LEI,
                    f"{numero}_{ano}",
                    f"Lei {numero}/{ano}",
                    {"numero": numero, "ano": ano},
                )
            )

        tipo_decisao = str(meta.get("tipo_decisao") or "").lower()
        tribunal = str(meta.get("tribunal") or "").strip().upper()
        if "sumula" in tipo_decisao and numero:
            seeds.append(
                (
                    EntityType.SUMULA,
                    f"{tribunal or 'STJ'}_{numero}",
                    f"Sumula {numero} {tribunal or 'STJ'}",
                    {"numero": numero, "tribunal": tribunal or "STJ"},
                )
            )

        if tribunal and numero:
            seeds.append(
                (
                    EntityType.JURISPRUDENCIA,
                    f"{tribunal}_{numero}",
                    f"{tribunal} {numero}",
                    {"tribunal": tribunal, "numero": numero},
                )
            )

        classe = str(meta.get("classe") or meta.get("tipo_juris") or "").strip().upper()
        uf = str(meta.get("uf") or "").strip().upper()
        if classe and numero:
            entity_id = f"{classe}_{numero}_{uf}" if uf else f"{classe}_{numero}"
            name = f"{classe} {numero}" + (f"/{uf}" if uf else "")
            seeds.append(
                (
                    EntityType.JURISPRUDENCIA,
                    entity_id,
                    name,
                    {"classe": classe, "numero": numero, "uf": uf},
                )
            )

        # Handle CNJ process number
        numero_cnj = str(meta.get("numero_cnj") or meta.get("processo") or "").strip()
        if numero_cnj and re.match(r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}", numero_cnj):
            entity_id = f"proc_{numero_cnj.replace('.', '_').replace('-', '_')}"
            seeds.append(
                (
                    EntityType.PROCESSO,
                    entity_id,
                    f"Processo {numero_cnj}",
                    {"numero_cnj": numero_cnj},
                )
            )

        return seeds


# =============================================================================
# KNOWLEDGE GRAPH (Core)
# =============================================================================


class LegalKnowledgeGraph:
    """
    Knowledge Graph with scope isolation for legal entities.

    Supports:
    - Entity (node) management
    - Relationship (edge) management
    - Graph traversal queries
    - Scope-based persistence (global/private/group/local)
    - Token budget control for context generation
    """

    def __init__(
        self,
        scope: Scope = Scope.GLOBAL,
        scope_id: str = "global",
        persist_path: Optional[str] = None,
        pack: Optional[BaseGraphPack] = None,
    ):
        """
        Initialize the knowledge graph.

        Args:
            scope: Access scope for this graph partition
            scope_id: Identifier for the scope (tenant_id, group_id, etc.)
            persist_path: Custom path for JSON persistence
            pack: Domain pack for entity extraction
        """
        self.scope = scope
        self.scope_id = scope_id
        self.pack = pack or LegalPack()

        # Determine persistence path
        if persist_path:
            self.persist_path = persist_path
        else:
            base_dir = _get_graph_db_path()
            scope_dir = os.path.join(base_dir, scope.value)
            os.makedirs(scope_dir, exist_ok=True)
            safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", scope_id)
            self.persist_path = os.path.join(scope_dir, f"{safe_id}.json")

        # Initialize graph
        self.graph = nx.DiGraph()
        self._entity_index: Dict[str, Entity] = {}
        self._lock = threading.RLock()

        # Load existing graph if present
        if os.path.exists(self.persist_path):
            self._load()
            logger.info(
                f"GraphRAG [{scope.value}/{scope_id}]: Loaded graph with "
                f"{self.graph.number_of_nodes()} nodes, {self.graph.number_of_edges()} edges"
            )
        else:
            logger.info(f"GraphRAG [{scope.value}/{scope_id}]: Initialized empty graph")

    # -------------------------------------------------------------------------
    # Entity Management
    # -------------------------------------------------------------------------

    def add_entity(
        self,
        entity_type: Union[str, Enum],
        entity_id: str,
        name: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Add a legal entity (node) to the graph.

        Returns:
            The node_id of the created/updated entity
        """
        entity_type_value = _normalize_graph_type(entity_type)
        entity = Entity(
            entity_type=entity_type_value,
            entity_id=entity_id,
            name=name,
            metadata=metadata or {},
        )

        node_id = entity.node_id

        with self._lock:
            self.graph.add_node(
                node_id,
                entity_type=entity_type_value,
                name=name,
                scope=self.scope.value,
                scope_id=self.scope_id,
                created_at=datetime.now().isoformat(),
                **entity.metadata,
            )
            self._entity_index[node_id] = entity

        return node_id

    def get_entity(self, node_id: str) -> Optional[Dict[str, Any]]:
        """Get entity data by node_id."""
        with self._lock:
            if node_id in self.graph.nodes:
                return dict(self.graph.nodes[node_id])
        return None

    def has_entity(self, node_id: str) -> bool:
        """Check if entity exists."""
        with self._lock:
            return node_id in self.graph.nodes

    def find_entities(
        self,
        entity_type: Optional[Union[str, Enum]] = None,
        name_contains: Optional[str] = None,
        **metadata_filters,
    ) -> List[str]:
        """
        Find entities matching criteria.

        Returns:
            List of matching node_ids
        """
        results: List[str] = []

        with self._lock:
            for node_id, data in self.graph.nodes(data=True):
                # Type filter
                if entity_type and data.get("entity_type") != _normalize_graph_type(
                    entity_type
                ):
                    continue

                # Name filter
                if name_contains:
                    name = data.get("name", "").lower()
                    if name_contains.lower() not in name:
                        continue

                # Metadata filters
                match = True
                for key, value in metadata_filters.items():
                    if data.get(key) != value:
                        match = False
                        break

                if match:
                    results.append(node_id)

        return results

    def remove_entity(self, node_id: str) -> bool:
        """Remove an entity and all its relationships."""
        with self._lock:
            if node_id in self.graph.nodes:
                self.graph.remove_node(node_id)
                self._entity_index.pop(node_id, None)
                return True
        return False

    # -------------------------------------------------------------------------
    # Relationship Management
    # -------------------------------------------------------------------------

    def add_relation(
        self,
        source_id: str,
        target_id: str,
        relation_type: Union[str, Enum],
        weight: float = 1.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Add a relationship (edge) between entities.

        Returns:
            True if edge was created, False if nodes don't exist
        """
        with self._lock:
            if source_id not in self.graph.nodes or target_id not in self.graph.nodes:
                logger.warning(
                    f"GraphRAG: Cannot add edge - node(s) not found: {source_id}, {target_id}"
                )
                return False

            relation_value = _normalize_graph_type(relation_type)
            self.graph.add_edge(
                source_id,
                target_id,
                relation=relation_value,
                weight=weight,
                created_at=datetime.now().isoformat(),
                **(metadata or {}),
            )

        return True

    # Alias for compatibility
    add_relationship = add_relation

    def get_relationships(
        self, node_id: str, direction: str = "both"
    ) -> List[Dict[str, Any]]:
        """
        Get all relationships for a node.

        Args:
            node_id: Entity node_id
            direction: "outgoing", "incoming", or "both"

        Returns:
            List of relationship dicts
        """
        results: List[Dict[str, Any]] = []

        with self._lock:
            if direction in ["outgoing", "both"]:
                for _, target, data in self.graph.out_edges(node_id, data=True):
                    results.append(
                        {
                            "source": node_id,
                            "target": target,
                            "relation": data.get("relation"),
                            "weight": data.get("weight", 1.0),
                        }
                    )

            if direction in ["incoming", "both"]:
                for source, _, data in self.graph.in_edges(node_id, data=True):
                    results.append(
                        {
                            "source": source,
                            "target": node_id,
                            "relation": data.get("relation"),
                            "weight": data.get("weight", 1.0),
                        }
                    )

        return results

    # -------------------------------------------------------------------------
    # Graph Queries (GraphRAG Core)
    # -------------------------------------------------------------------------

    def traverse(
        self,
        start_node_id: str,
        hops: int = 2,
        relation_filter: Optional[List[Union[str, Enum]]] = None,
        max_nodes: int = 50,
    ) -> Dict[str, Any]:
        """
        Traverse the graph from a starting node.

        This is the core GraphRAG query - finding related knowledge
        that wouldn't be found by pure semantic search.

        Args:
            start_node_id: Starting entity node_id
            hops: Maximum path length (default 2)
            relation_filter: Only follow these relation types
            max_nodes: Maximum nodes to return

        Returns:
            Dict with nodes and edges within the subgraph
        """
        config = get_rag_config()
        hops = hops or config.graph_hops
        max_nodes = max_nodes or config.graph_max_nodes

        with self._lock:
            if start_node_id not in self.graph.nodes:
                return {"nodes": [], "edges": [], "center": start_node_id}

            # BFS to find all nodes within N hops
            visited: Set[str] = {start_node_id}
            frontier: Set[str] = {start_node_id}
            all_edges: List[Dict[str, Any]] = []

            allowed = (
                {_normalize_graph_type(r) for r in relation_filter}
                if relation_filter
                else None
            )

            for _ in range(hops):
                if len(visited) >= max_nodes:
                    break

                next_frontier: Set[str] = set()

                for current in frontier:
                    # Outgoing edges
                    for _, target, data in self.graph.out_edges(current, data=True):
                        if allowed is not None and data.get("relation") not in allowed:
                            continue

                        if target not in visited and len(visited) < max_nodes:
                            next_frontier.add(target)
                            visited.add(target)

                        all_edges.append(
                            {
                                "source": current,
                                "target": target,
                                "relation": data.get("relation"),
                            }
                        )

                    # Incoming edges
                    for source, _, data in self.graph.in_edges(current, data=True):
                        if allowed is not None and data.get("relation") not in allowed:
                            continue

                        if source not in visited and len(visited) < max_nodes:
                            next_frontier.add(source)
                            visited.add(source)

                        all_edges.append(
                            {
                                "source": source,
                                "target": current,
                                "relation": data.get("relation"),
                            }
                        )

                frontier = next_frontier

            # Collect node data
            nodes = []
            for nid in visited:
                node_data = dict(self.graph.nodes[nid])
                node_data["node_id"] = nid
                nodes.append(node_data)

        return {"nodes": nodes, "edges": all_edges, "center": start_node_id}

    # Alias for compatibility
    query_related = traverse

    def find_path(
        self,
        source_id: str,
        target_id: str,
        max_hops: int = 4,
    ) -> Optional[List[str]]:
        """
        Find shortest path between two entities.

        Useful for answering questions like:
        "How is Lei X related to Sumula Y?"
        """
        with self._lock:
            try:
                path = nx.shortest_path(
                    self.graph, source_id, target_id, weight=None
                )
                if len(path) > max_hops + 1:
                    return None
                return path
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                return None

    def resolve_query_entities(self, text: str) -> List[str]:
        """Find entities mentioned in query text."""
        matches: Set[str] = set()

        with self._lock:
            seeds = self.pack.extract_candidates(text) if self.pack else []
            for seed in seeds:
                node_id, name = self._seed_to_node_id(seed)
                if node_id and node_id in self.graph.nodes:
                    matches.add(node_id)
                    continue
                if name:
                    for candidate in self.find_entities(name_contains=name):
                        matches.add(candidate)

        return list(matches)

    def _seed_to_node_id(
        self, seed: Union[str, Tuple[Union[str, Enum], str, str, Dict[str, Any]]]
    ) -> Tuple[Optional[str], Optional[str]]:
        """Convert a seed to node_id and name."""
        if isinstance(seed, str):
            return seed, None
        entity_type, entity_id, name, _ = seed
        node_id = f"{_normalize_graph_type(entity_type)}:{entity_id}"
        return node_id, name

    # -------------------------------------------------------------------------
    # Context Generation (with Token Budget)
    # -------------------------------------------------------------------------

    def get_context(
        self,
        entity_ids: Set[str],
        hops: int = 1,
        token_budget: Optional[int] = None,
    ) -> str:
        """
        Build context string from entities with token budget control.

        Args:
            entity_ids: Set of entity node_ids to include
            hops: How many hops to traverse
            token_budget: Maximum tokens for output

        Returns:
            Formatted context string
        """
        if not entity_ids:
            return ""

        if token_budget is None:
            token_budget = _get_default_token_budget()

        char_budget = token_budget * CHARS_PER_TOKEN_ESTIMATE
        context_parts: List[str] = ["### CONTEXTO DO GRAFO DE CONHECIMENTO:\n"]
        current_chars = len(context_parts[0])

        for entity_id in entity_ids:
            if current_chars >= char_budget:
                break

            subgraph = self.traverse(entity_id, hops=hops, max_nodes=20)
            entity_data = self.get_entity(entity_id)

            if not entity_data:
                continue

            entity_section = f"\n**{entity_data.get('name', entity_id)}**:"
            relations_by_type: Dict[str, List[str]] = {}

            for edge in subgraph["edges"]:
                rel_type = edge["relation"]
                if rel_type not in relations_by_type:
                    relations_by_type[rel_type] = []

                other_id = (
                    edge["target"] if edge["source"] == entity_id else edge["source"]
                )
                other_data = self.get_entity(other_id)
                if other_data:
                    relations_by_type[rel_type].append(
                        other_data.get("name", other_id)
                    )

            for rel_type, targets in relations_by_type.items():
                rel_line = f"\n  - {rel_type.upper()}: {', '.join(targets[:5])}"
                if current_chars + len(entity_section) + len(rel_line) > char_budget:
                    break
                entity_section += rel_line

            if current_chars + len(entity_section) <= char_budget:
                context_parts.append(entity_section)
                current_chars += len(entity_section)

        return "\n".join(context_parts)

    # Alias for compatibility
    build_context = get_context

    def query_context_from_text(
        self,
        text: str,
        hops: int = 2,
        token_budget: Optional[int] = None,
    ) -> Tuple[str, List[str]]:
        """
        Generate context from query text.

        Returns:
            Tuple of (context_string, list_of_matched_entity_ids)
        """
        entity_ids = set(self.resolve_query_entities(text))
        if not entity_ids:
            return "", []
        return self.get_context(entity_ids, hops, token_budget), list(entity_ids)

    def enrich_chunks(
        self,
        chunks: List[Dict[str, Any]],
        hops: int = 1,
        token_budget: Optional[int] = None,
    ) -> str:
        """
        Enrich RAG chunks with knowledge graph context.

        Args:
            chunks: List of chunk dicts with 'text' and 'metadata' keys
            hops: Traversal depth
            token_budget: Maximum tokens for context

        Returns:
            Context string to append to prompt
        """
        extracted_entities: Set[str] = set()

        for chunk in chunks:
            meta = chunk.get("metadata", {}) or {}
            seeds = self.pack.seed_from_metadata(meta) if self.pack else []

            if not seeds:
                chunk_text = chunk.get("text", "")
                if chunk_text and self.pack:
                    seeds = self.pack.extract_candidates(chunk_text)

            for seed in seeds:
                node_id, name = self._seed_to_node_id(seed)
                if node_id and node_id in self.graph.nodes:
                    extracted_entities.add(node_id)
                    continue
                if name:
                    for candidate in self.find_entities(name_contains=name):
                        extracted_entities.add(candidate)

        return self.get_context(extracted_entities, hops, token_budget)

    # -------------------------------------------------------------------------
    # Ingestion Pipeline Integration
    # -------------------------------------------------------------------------

    def ingest_text(
        self,
        text: str,
        source_doc_id: Optional[str] = None,
        source_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Ingest text into the knowledge graph.

        Extracts entities and relationships, adds them to the graph.

        Args:
            text: Text to process
            source_doc_id: Optional document ID for tracking
            source_metadata: Optional metadata to enrich entities

        Returns:
            Dict with counts of added entities and relationships
        """
        if not self.pack:
            return {"entities_added": 0, "relationships_added": 0}

        candidates = self.pack.extract_candidates(text)
        added_entities: List[str] = []
        added_relationships: List[Tuple[str, str, str]] = []

        # Add source document as entity if provided
        source_node_id = None
        if source_doc_id:
            source_node_id = self.add_entity(
                EntityType.DOCUMENTO,
                source_doc_id,
                f"Documento {source_doc_id}",
                source_metadata,
            )

        # Add extracted entities
        for entity_type, entity_id, name, metadata in candidates:
            node_id = self.add_entity(entity_type, entity_id, name, metadata)
            added_entities.append(node_id)

            # Create citation relationship from source doc
            if source_node_id and node_id != source_node_id:
                if self.add_relation(
                    source_node_id, node_id, RelationType.CITA
                ):
                    added_relationships.append(
                        (source_node_id, node_id, RelationType.CITA.value)
                    )

        # Extract inter-entity relationships
        if self.pack and added_entities:
            relations = self.pack.extract_relations(
                text, source_node_id or "", added_entities
            )
            for src, tgt, rel_type, meta in relations:
                if self.add_relation(src, tgt, rel_type, metadata=meta):
                    added_relationships.append((src, tgt, _normalize_graph_type(rel_type)))

        return {
            "entities_added": len(added_entities),
            "relationships_added": len(added_relationships),
            "entity_ids": added_entities,
        }

    # -------------------------------------------------------------------------
    # Persistence
    # -------------------------------------------------------------------------

    def save(self) -> None:
        """Persist graph to JSON file."""
        os.makedirs(os.path.dirname(self.persist_path), exist_ok=True)

        with self._lock:
            data = {
                "scope": self.scope.value,
                "scope_id": self.scope_id,
                "nodes": [
                    {"id": n, **self.graph.nodes[n]} for n in self.graph.nodes
                ],
                "edges": [
                    {"source": u, "target": v, **d}
                    for u, v, d in self.graph.edges(data=True)
                ],
                "metadata": {
                    "saved_at": datetime.now().isoformat(),
                    "node_count": self.graph.number_of_nodes(),
                    "edge_count": self.graph.number_of_edges(),
                },
            }

        with open(self.persist_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(f"GraphRAG: Saved graph to {self.persist_path}")

    def _load(self) -> None:
        """Load graph from JSON file."""
        try:
            with open(self.persist_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            with self._lock:
                for node in data.get("nodes", []):
                    node_id = node.pop("id")
                    self.graph.add_node(node_id, **node)

                for edge in data.get("edges", []):
                    source = edge.pop("source")
                    target = edge.pop("target")
                    self.graph.add_edge(source, target, **edge)

        except Exception as e:
            logger.error(f"GraphRAG: Failed to load graph: {e}")

    # -------------------------------------------------------------------------
    # Stats & Debug
    # -------------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Get graph statistics."""
        with self._lock:
            type_counts: Dict[str, int] = {}
            for _, data in self.graph.nodes(data=True):
                etype = data.get("entity_type", "unknown")
                type_counts[etype] = type_counts.get(etype, 0) + 1

            rel_counts: Dict[str, int] = {}
            for _, _, data in self.graph.edges(data=True):
                rtype = data.get("relation", "unknown")
                rel_counts[rtype] = rel_counts.get(rtype, 0) + 1

            return {
                "scope": self.scope.value,
                "scope_id": self.scope_id,
                "total_nodes": self.graph.number_of_nodes(),
                "total_edges": self.graph.number_of_edges(),
                "nodes_by_type": type_counts,
                "edges_by_type": rel_counts,
                "is_connected": (
                    nx.is_weakly_connected(self.graph)
                    if self.graph.number_of_nodes() > 0
                    else False
                ),
                "persist_path": self.persist_path,
            }


# =============================================================================
# ARGUMENT GRAPH
# =============================================================================


class ArgumentGraph:
    """
    Graph for legal argument structures.

    Manages:
    - Teses (legal positions)
    - Fundamentos (supporting grounds)
    - Conclusoes (conclusions)
    - Relationships between arguments
    """

    def __init__(
        self,
        scope: Scope = Scope.LOCAL,
        scope_id: str = "arguments",
        persist_path: Optional[str] = None,
    ):
        self.scope = scope
        self.scope_id = scope_id

        if persist_path:
            self.persist_path = persist_path
        else:
            base_dir = _get_graph_db_path()
            scope_dir = os.path.join(base_dir, "arguments", scope.value)
            os.makedirs(scope_dir, exist_ok=True)
            safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", scope_id)
            self.persist_path = os.path.join(scope_dir, f"{safe_id}.json")

        self.graph = nx.DiGraph()
        self._lock = threading.RLock()

        if os.path.exists(self.persist_path):
            self._load()

    def add_argument(self, arg: ArgumentNode) -> str:
        """Add an argument node to the graph."""
        with self._lock:
            self.graph.add_node(
                arg.node_id,
                arg_type=arg.arg_type.value,
                text=arg.text,
                confidence=arg.confidence,
                source_chunk_id=arg.source_chunk_id,
                created_at=datetime.now().isoformat(),
                **arg.metadata,
            )
        return arg.node_id

    def add_argument_relation(
        self,
        source_id: str,
        target_id: str,
        relation_type: RelationType,
        weight: float = 1.0,
    ) -> bool:
        """Add relationship between arguments."""
        with self._lock:
            if source_id not in self.graph.nodes or target_id not in self.graph.nodes:
                return False
            self.graph.add_edge(
                source_id,
                target_id,
                relation=relation_type.value,
                weight=weight,
            )
        return True

    def extract_and_add(
        self,
        text: str,
        source_chunk_id: Optional[str] = None,
    ) -> List[str]:
        """
        Extract arguments from text and add to graph.

        Returns:
            List of added argument node_ids
        """
        arguments = ArgumentExtractor.extract_arguments(text, source_chunk_id)
        added: List[str] = []

        for arg in arguments:
            node_id = self.add_argument(arg)
            added.append(node_id)

        # Link fundamentos to teses, conclusoes to fundamentos
        teses = [nid for nid in added if ":tese:" in nid]
        fundamentos = [nid for nid in added if ":fundamento:" in nid]
        conclusoes = [nid for nid in added if ":conclusao:" in nid]

        for fund in fundamentos:
            for tese in teses:
                self.add_argument_relation(fund, tese, RelationType.FUNDAMENTA)

        for conc in conclusoes:
            for fund in fundamentos:
                self.add_argument_relation(conc, fund, RelationType.DERIVA)

        return added

    def get_argument_chain(self, node_id: str, max_depth: int = 3) -> Dict[str, Any]:
        """Get the argument chain leading to/from a node."""
        with self._lock:
            if node_id not in self.graph.nodes:
                return {"nodes": [], "edges": []}

            visited: Set[str] = {node_id}
            frontier: Set[str] = {node_id}
            all_edges: List[Dict[str, Any]] = []

            for _ in range(max_depth):
                next_frontier: Set[str] = set()

                for current in frontier:
                    for _, target, data in self.graph.out_edges(current, data=True):
                        if target not in visited:
                            next_frontier.add(target)
                            visited.add(target)
                        all_edges.append(
                            {
                                "source": current,
                                "target": target,
                                "relation": data.get("relation"),
                            }
                        )

                    for source, _, data in self.graph.in_edges(current, data=True):
                        if source not in visited:
                            next_frontier.add(source)
                            visited.add(source)
                        all_edges.append(
                            {
                                "source": source,
                                "target": current,
                                "relation": data.get("relation"),
                            }
                        )

                frontier = next_frontier

            nodes = []
            for nid in visited:
                node_data = dict(self.graph.nodes[nid])
                node_data["node_id"] = nid
                nodes.append(node_data)

        return {"nodes": nodes, "edges": all_edges, "center": node_id}

    def build_argument_context(
        self,
        token_budget: Optional[int] = None,
    ) -> str:
        """Build context from all arguments with token budget."""
        if token_budget is None:
            token_budget = _get_default_token_budget()

        char_budget = token_budget * CHARS_PER_TOKEN_ESTIMATE
        parts: List[str] = ["### ESTRUTURA ARGUMENTATIVA:\n"]
        current_chars = len(parts[0])

        with self._lock:
            # Group by type
            by_type: Dict[str, List[Tuple[str, Dict[str, Any]]]] = {}
            for nid, data in self.graph.nodes(data=True):
                arg_type = data.get("arg_type", "unknown")
                if arg_type not in by_type:
                    by_type[arg_type] = []
                by_type[arg_type].append((nid, data))

            for arg_type in ["tese", "fundamento", "conclusao"]:
                if arg_type not in by_type:
                    continue

                section = f"\n**{arg_type.upper()}S:**"
                for nid, data in by_type[arg_type][:5]:
                    text = data.get("text", "")[:200]
                    item = f"\n  - {text}..."
                    if current_chars + len(section) + len(item) > char_budget:
                        break
                    section += item

                if current_chars + len(section) <= char_budget:
                    parts.append(section)
                    current_chars += len(section)

        return "\n".join(parts)

    def save(self) -> None:
        """Persist graph to JSON."""
        os.makedirs(os.path.dirname(self.persist_path), exist_ok=True)

        with self._lock:
            data = {
                "scope": self.scope.value,
                "scope_id": self.scope_id,
                "nodes": [
                    {"id": n, **self.graph.nodes[n]} for n in self.graph.nodes
                ],
                "edges": [
                    {"source": u, "target": v, **d}
                    for u, v, d in self.graph.edges(data=True)
                ],
            }

        with open(self.persist_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _load(self) -> None:
        """Load graph from JSON."""
        try:
            with open(self.persist_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            with self._lock:
                for node in data.get("nodes", []):
                    node_id = node.pop("id")
                    self.graph.add_node(node_id, **node)

                for edge in data.get("edges", []):
                    source = edge.pop("source")
                    target = edge.pop("target")
                    self.graph.add_edge(source, target, **edge)

        except Exception as e:
            logger.error(f"ArgumentGraph: Failed to load: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """Get argument graph statistics."""
        with self._lock:
            type_counts: Dict[str, int] = {}
            for _, data in self.graph.nodes(data=True):
                arg_type = data.get("arg_type", "unknown")
                type_counts[arg_type] = type_counts.get(arg_type, 0) + 1

            return {
                "scope": self.scope.value,
                "scope_id": self.scope_id,
                "total_arguments": self.graph.number_of_nodes(),
                "total_relations": self.graph.number_of_edges(),
                "arguments_by_type": type_counts,
                "persist_path": self.persist_path,
            }


# =============================================================================
# SCOPED GRAPH MANAGER
# =============================================================================


class ScopedGraphManager:
    """
    Manager for scoped knowledge graphs.

    Provides factory methods and caching for graph instances.
    """

    _instances: Dict[str, LegalKnowledgeGraph] = {}
    _argument_instances: Dict[str, ArgumentGraph] = {}
    _lock = threading.RLock()

    @classmethod
    def _make_key(cls, scope: Scope, scope_id: str) -> str:
        return f"{scope.value}:{scope_id}"

    @classmethod
    def get_knowledge_graph(
        cls,
        scope: Scope = Scope.GLOBAL,
        scope_id: str = "global",
    ) -> LegalKnowledgeGraph:
        """
        Get or create a scoped knowledge graph.

        Args:
            scope: Access scope
            scope_id: Scope identifier

        Returns:
            LegalKnowledgeGraph instance
        """
        key = cls._make_key(scope, scope_id)

        with cls._lock:
            if key not in cls._instances:
                cls._instances[key] = LegalKnowledgeGraph(scope=scope, scope_id=scope_id)
            return cls._instances[key]

    @classmethod
    def get_argument_graph(
        cls,
        scope: Scope = Scope.LOCAL,
        scope_id: str = "arguments",
    ) -> ArgumentGraph:
        """Get or create a scoped argument graph."""
        key = cls._make_key(scope, scope_id)

        with cls._lock:
            if key not in cls._argument_instances:
                cls._argument_instances[key] = ArgumentGraph(scope=scope, scope_id=scope_id)
            return cls._argument_instances[key]

    @classmethod
    def save_all(cls) -> None:
        """Save all cached graph instances."""
        with cls._lock:
            for graph in cls._instances.values():
                graph.save()
            for graph in cls._argument_instances.values():
                graph.save()

    @classmethod
    def clear_cache(cls) -> None:
        """Clear all cached graph instances."""
        with cls._lock:
            cls._instances.clear()
            cls._argument_instances.clear()

    @classmethod
    def get_cached_graphs(cls) -> Dict[str, Any]:
        """Get info about cached graphs."""
        with cls._lock:
            return {
                "knowledge_graphs": list(cls._instances.keys()),
                "argument_graphs": list(cls._argument_instances.keys()),
            }


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def get_scoped_knowledge_graph(
    scope: Union[str, Scope],
    scope_id: str,
) -> LegalKnowledgeGraph:
    """
    Get a scoped knowledge graph instance.

    Args:
        scope: "global", "private", "group", or "local" (or Scope enum)
        scope_id: Identifier for the scope

    Returns:
        LegalKnowledgeGraph instance
    """
    if isinstance(scope, str):
        scope = Scope(scope)
    return ScopedGraphManager.get_knowledge_graph(scope, scope_id)


def get_global_knowledge_graph() -> LegalKnowledgeGraph:
    """Get the global knowledge graph (shared across all tenants)."""
    return ScopedGraphManager.get_knowledge_graph(Scope.GLOBAL, "global")


def get_tenant_knowledge_graph(tenant_id: str) -> LegalKnowledgeGraph:
    """Get a private knowledge graph for a specific tenant."""
    return ScopedGraphManager.get_knowledge_graph(Scope.PRIVATE, tenant_id)


def get_group_knowledge_graph(group_id: str) -> LegalKnowledgeGraph:
    """Get a group knowledge graph."""
    return ScopedGraphManager.get_knowledge_graph(Scope.GROUP, group_id)


def get_case_knowledge_graph(case_id: str) -> LegalKnowledgeGraph:
    """Get a local knowledge graph for a specific case."""
    return ScopedGraphManager.get_knowledge_graph(Scope.LOCAL, case_id)


def get_case_argument_graph(case_id: str) -> ArgumentGraph:
    """Get an argument graph for a specific case."""
    return ScopedGraphManager.get_argument_graph(Scope.LOCAL, case_id)


# =============================================================================
# INGESTION INTEGRATION
# =============================================================================


def enrich_chunk_with_graph(
    chunk_text: str,
    chunk_metadata: Dict[str, Any],
    tenant_id: Optional[str] = None,
    group_ids: Optional[List[str]] = None,
    case_id: Optional[str] = None,
    include_global: bool = True,
    token_budget: Optional[int] = None,
) -> str:
    """
    Enrich a chunk with context from relevant knowledge graphs.

    Checks global, private, group, and local graphs based on parameters.

    Args:
        chunk_text: The chunk text
        chunk_metadata: Chunk metadata
        tenant_id: Tenant ID for private graph
        group_ids: Group IDs for group graphs
        case_id: Case ID for local graph
        include_global: Whether to include global graph
        token_budget: Token budget for context

    Returns:
        Combined context string
    """
    if token_budget is None:
        token_budget = _get_default_token_budget()

    contexts: List[str] = []
    remaining_budget = token_budget

    graphs_to_check: List[LegalKnowledgeGraph] = []

    if include_global:
        graphs_to_check.append(get_global_knowledge_graph())

    if tenant_id:
        graphs_to_check.append(get_tenant_knowledge_graph(tenant_id))

    if group_ids:
        for gid in group_ids:
            graphs_to_check.append(get_group_knowledge_graph(gid))

    if case_id:
        graphs_to_check.append(get_case_knowledge_graph(case_id))

    chunk_budget = remaining_budget // max(1, len(graphs_to_check))

    for graph in graphs_to_check:
        if remaining_budget <= 0:
            break

        context, _ = graph.query_context_from_text(
            chunk_text, hops=1, token_budget=min(chunk_budget, remaining_budget)
        )

        if context:
            contexts.append(context)
            remaining_budget -= len(context) // CHARS_PER_TOKEN_ESTIMATE

    return "\n\n".join(contexts) if contexts else ""


def ingest_to_graph(
    text: str,
    doc_id: str,
    metadata: Dict[str, Any],
    scope: Union[str, Scope] = Scope.GLOBAL,
    scope_id: str = "global",
    extract_arguments: bool = False,
) -> Dict[str, Any]:
    """
    Ingest text into the appropriate knowledge graph.

    Args:
        text: Text to ingest
        doc_id: Document identifier
        metadata: Document metadata
        scope: Target scope
        scope_id: Target scope identifier
        extract_arguments: Whether to also extract arguments

    Returns:
        Dict with ingestion results
    """
    if isinstance(scope, str):
        scope = Scope(scope)

    graph = get_scoped_knowledge_graph(scope, scope_id)
    result = graph.ingest_text(text, source_doc_id=doc_id, source_metadata=metadata)

    if extract_arguments:
        arg_graph = ScopedGraphManager.get_argument_graph(scope, scope_id)
        arg_ids = arg_graph.extract_and_add(text, source_chunk_id=doc_id)
        result["arguments_extracted"] = len(arg_ids)

    return result


# =============================================================================
# MODULE EXPORTS
# =============================================================================

__all__ = [
    # Enums
    "EntityType",
    "RelationType",
    "ArgumentType",
    "Scope",
    # Data classes
    "Entity",
    "Relation",
    "ArgumentNode",
    "ScopedGraphRef",
    "GraphSchema",
    # Main classes
    "LegalKnowledgeGraph",
    "ArgumentGraph",
    "LegalEntityExtractor",
    "ArgumentExtractor",
    "LegalPack",
    "ScopedGraphManager",
    # Helper functions
    "get_scoped_knowledge_graph",
    "get_global_knowledge_graph",
    "get_tenant_knowledge_graph",
    "get_group_knowledge_graph",
    "get_case_knowledge_graph",
    "get_case_argument_graph",
    # Integration functions
    "enrich_chunk_with_graph",
    "ingest_to_graph",
]
