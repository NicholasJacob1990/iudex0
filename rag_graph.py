"""
RAG Graph Module (v5.0) - Knowledge Graph for Legal Documents

Implements GraphRAG pattern from Sandeco's book (Cap. 1.8):
- Nodes represent legal entities (Lei, Artigo, Súmula, Jurisprudência, Tese)
- Edges represent relationships (cita, aplica, revoga, vincula)

Uses NetworkX for in-memory graph with JSON persistence.
"""

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Protocol, Set, Tuple, Union
from dataclasses import dataclass, field
from enum import Enum

try:
    import networkx as nx
except ImportError:
    raise ImportError("NetworkX required: pip install networkx")

logger = logging.getLogger(__name__)

try:
    from legal_pack import LegalPack as ExternalLegalPack, LEGAL_PACK as EXTERNAL_LEGAL_PACK
except Exception:
    ExternalLegalPack = None
    EXTERNAL_LEGAL_PACK = None


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


class RelationType(str, Enum):
    """Relationship types for knowledge graph edges."""
    POSSUI = "possui"           # Lei --possui--> Artigo
    CITA = "cita"               # Jurisprudencia --cita--> Lei
    APLICA = "aplica"           # Jurisprudencia --aplica--> Súmula
    REVOGA = "revoga"           # Lei --revoga--> Lei
    ALTERA = "altera"           # Lei --altera--> Lei
    VINCULA = "vincula"         # Súmula --vincula--> Tese
    RELACIONADA = "relacionada" # Tese --relacionada--> Tese
    INTERPRETA = "interpreta"   # Jurisprudencia --interpreta--> Artigo


# =============================================================================
# GENERIC SCHEMA & PACKS
# =============================================================================


@dataclass(frozen=True)
class GraphSchema:
    name: str
    node_types: Tuple[str, ...]
    relation_types: Tuple[str, ...]


class BaseGraphPack(Protocol):
    name: str
    schema: GraphSchema

    def extract_candidates(self, text: str) -> List[Tuple[Union[str, Enum], str, str, Dict[str, Any]]]:
        ...

    def extract_relations(
        self,
        text: str,
        source_node_id: str,
        candidate_node_ids: Iterable[str],
    ) -> List[Tuple[str, str, Union[str, Enum], Dict[str, Any]]]:
        ...

    def seed_from_metadata(self, meta: Dict[str, Any]) -> List[Union[str, Tuple[Union[str, Enum], str, str, Dict[str, Any]]]]:
        ...


def _normalize_graph_type(value: Union[str, Enum]) -> str:
    return value.value if isinstance(value, Enum) else str(value)


class GenericPack:
    name = "generic"
    schema = GraphSchema(name="generic", node_types=tuple(), relation_types=tuple())

    def extract_candidates(self, text: str) -> List[Tuple[str, str, str, Dict[str, Any]]]:
        return []

    def extract_relations(
        self,
        text: str,
        source_node_id: str,
        candidate_node_ids: Iterable[str],
    ) -> List[Tuple[str, str, str, Dict[str, Any]]]:
        return []

    def seed_from_metadata(self, meta: Dict[str, Any]) -> List[Union[str, Tuple[str, str, str, Dict[str, Any]]]]:
        return []


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class Entity:
    """Base class for graph entities (nodes)."""
    entity_type: str
    entity_id: str  # Unique ID within type (e.g., "lei_8666_1993")
    name: str       # Display name (e.g., "Lei 8.666/93")
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def node_id(self) -> str:
        """Global unique ID for graph."""
        return f"{self.entity_type}:{self.entity_id}"


@dataclass  
class Relation:
    """Relationship between graph entities (edges)."""
    source_id: str      # Entity node_id
    target_id: str      # Entity node_id
    relation_type: str
    weight: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# KNOWLEDGE GRAPH
# =============================================================================

class LegalEntity(Entity):
    """Legacy alias for backward compatibility."""


class LegalRelation(Relation):
    """Legacy alias for backward compatibility."""


class KnowledgeGraph:
    """
    Knowledge Graph core (domain-agnostic).
    
    Enables GraphRAG queries across domains when paired with a pack.
    """

    DEFAULT_PERSIST_PATH = os.path.join(
        os.path.dirname(__file__),
        "graph_db",
        "knowledge_graph.json"
    )

    def __init__(self, persist_path: str = None, pack: Optional[BaseGraphPack] = None):
        """
        Initialize the knowledge graph.
        
        Args:
            persist_path: Path to JSON file for persistence
        """
        self.persist_path = persist_path or self.DEFAULT_PERSIST_PATH
        self.pack = pack or GenericPack()
        self.graph = nx.DiGraph()
        self._entity_index: Dict[str, Entity] = {}
        
        # Try to load existing graph
        if os.path.exists(self.persist_path):
            self._load()
            logger.info(f"GraphRAG: Loaded graph with {self.graph.number_of_nodes()} nodes, {self.graph.number_of_edges()} edges")
        else:
            logger.info("GraphRAG: Initialized empty graph")
    
    # -------------------------------------------------------------------------
    # Entity Management
    # -------------------------------------------------------------------------
    
    def add_entity(
        self, 
        entity_type: Union[str, Enum],
        entity_id: str, 
        name: str, 
        metadata: Dict[str, Any] = None
    ) -> str:
        """
        Add a legal entity (node) to the graph.
        
        Args:
            entity_type: Type of entity (LEI, ARTIGO, SUMULA, etc.)
            entity_id: Unique ID within the type
            name: Display name
            metadata: Additional attributes
            
        Returns:
            The node_id of the created entity
        """
        entity_type_value = _normalize_graph_type(entity_type)
        entity = Entity(
            entity_type=entity_type_value,
            entity_id=entity_id,
            name=name,
            metadata=metadata or {}
        )
        
        node_id = entity.node_id
        
        # Add to NetworkX graph
        self.graph.add_node(
            node_id,
            entity_type=entity_type_value,
            name=name,
            **entity.metadata
        )
        
        # Index for fast lookup
        self._entity_index[node_id] = entity
        
        return node_id
    
    def get_entity(self, node_id: str) -> Optional[Dict[str, Any]]:
        """Get entity data by node_id."""
        if node_id in self.graph.nodes:
            return dict(self.graph.nodes[node_id])
        return None
    
    def find_entities(
        self, 
        entity_type: Union[str, Enum] = None,
        name_contains: str = None,
        **metadata_filters
    ) -> List[str]:
        """
        Find entities matching criteria.
        
        Args:
            entity_type: Filter by type
            name_contains: Substring match on name (case-insensitive)
            **metadata_filters: Exact match on metadata fields
            
        Returns:
            List of matching node_ids
        """
        results = []
        
        for node_id, data in self.graph.nodes(data=True):
            # Type filter
            if entity_type and data.get("entity_type") != _normalize_graph_type(entity_type):
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
    
    # -------------------------------------------------------------------------
    # Relationship Management
    # -------------------------------------------------------------------------
    
    def add_relationship(
        self,
        source_id: str,
        target_id: str,
        relation_type: Union[str, Enum],
        weight: float = 1.0,
        metadata: Dict[str, Any] = None
    ) -> bool:
        """
        Add a relationship (edge) between entities.
        
        Args:
            source_id: Source entity node_id
            target_id: Target entity node_id
            relation_type: Type of relationship
            weight: Edge weight (default 1.0)
            metadata: Additional edge attributes
            
        Returns:
            True if edge was created, False if nodes don't exist
        """
        if source_id not in self.graph.nodes or target_id not in self.graph.nodes:
            logger.warning(f"GraphRAG: Cannot add edge - node(s) not found: {source_id}, {target_id}")
            return False
        
        relation_value = _normalize_graph_type(relation_type)
        self.graph.add_edge(
            source_id,
            target_id,
            relation=relation_value,
            weight=weight,
            **(metadata or {})
        )
        
        return True
    
    def get_relationships(
        self, 
        node_id: str, 
        direction: str = "both"
    ) -> List[Dict[str, Any]]:
        """
        Get all relationships for a node.
        
        Args:
            node_id: Entity node_id
            direction: "outgoing", "incoming", or "both"
            
        Returns:
            List of relationship dicts with source, target, type
        """
        results = []
        
        if direction in ["outgoing", "both"]:
            for _, target, data in self.graph.out_edges(node_id, data=True):
                results.append({
                    "source": node_id,
                    "target": target,
                    "relation": data.get("relation"),
                    "weight": data.get("weight", 1.0)
                })
        
        if direction in ["incoming", "both"]:
            for source, _, data in self.graph.in_edges(node_id, data=True):
                results.append({
                    "source": source,
                    "target": node_id,
                    "relation": data.get("relation"),
                    "weight": data.get("weight", 1.0)
                })
        
        return results
    
    # -------------------------------------------------------------------------
    # Graph Queries (GraphRAG Core)
    # -------------------------------------------------------------------------
    
    def query_related(
        self,
        node_id: str,
        hops: int = 2,
        relation_filter: List[Union[str, Enum]] = None
    ) -> Dict[str, Any]:
        """
        Find all entities connected to a node within N hops.
        
        This is the core GraphRAG query - finding related knowledge
        that wouldn't be found by pure semantic search.
        
        Args:
            node_id: Starting entity node_id
            hops: Maximum path length (default 2)
            relation_filter: Only follow these relation types
            
        Returns:
            Dict with nodes and edges within the subgraph
        """
        if node_id not in self.graph.nodes:
            return {"nodes": [], "edges": []}
        
        # BFS to find all nodes within N hops
        visited: Set[str] = {node_id}
        frontier: Set[str] = {node_id}
        all_edges: List[Dict] = []
        
        allowed = {_normalize_graph_type(r) for r in relation_filter} if relation_filter else None
        for _ in range(hops):
            next_frontier: Set[str] = set()
            
            for current in frontier:
                # Outgoing edges
                for _, target, data in self.graph.out_edges(current, data=True):
                    if allowed is not None:
                        if data.get("relation") not in allowed:
                            continue
                    
                    if target not in visited:
                        next_frontier.add(target)
                        visited.add(target)
                    
                    all_edges.append({
                        "source": current,
                        "target": target,
                        "relation": data.get("relation")
                    })
                
                # Incoming edges
                for source, _, data in self.graph.in_edges(current, data=True):
                    if allowed is not None:
                        if data.get("relation") not in allowed:
                            continue
                    
                    if source not in visited:
                        next_frontier.add(source)
                        visited.add(source)
                    
                    all_edges.append({
                        "source": source,
                        "target": current,
                        "relation": data.get("relation")
                    })
            
            frontier = next_frontier
        
        # Collect node data
        nodes = []
        for nid in visited:
            node_data = dict(self.graph.nodes[nid])
            node_data["node_id"] = nid
            nodes.append(node_data)
        
        return {
            "nodes": nodes,
            "edges": all_edges,
            "center": node_id
        }
    
    def find_path(
        self,
        source_id: str,
        target_id: str,
        max_hops: int = 4
    ) -> Optional[List[str]]:
        """
        Find shortest path between two entities.
        
        Useful for answering questions like:
        "How is Lei X related to Súmula Y?"
        
        Args:
            source_id: Source entity node_id
            target_id: Target entity node_id
            max_hops: Maximum path length
            
        Returns:
            List of node_ids in path, or None if no path exists
        """
        try:
            path = nx.shortest_path(
                self.graph, 
                source_id, 
                target_id,
                weight=None  # Unweighted for now
            )
            
            if len(path) > max_hops + 1:
                return None  # Path too long
            
            return path
        except nx.NetworkXNoPath:
            return None
        except nx.NodeNotFound:
            return None
    
    def _build_context_for_entities(
        self,
        entity_ids: Set[str],
        hops: int
    ) -> str:
        if not entity_ids:
            return ""

        context_parts = ["### 📊 CONTEXTO DO GRAFO DE CONHECIMENTO:\n"]

        for entity_id in entity_ids:
            subgraph = self.query_related(entity_id, hops=hops)
            entity_data = self.get_entity(entity_id)

            if entity_data:
                context_parts.append(f"**{entity_data.get('name', entity_id)}**:")

                relations_by_type: Dict[str, List[str]] = {}
                for edge in subgraph["edges"]:
                    rel_type = edge["relation"]
                    if rel_type not in relations_by_type:
                        relations_by_type[rel_type] = []

                    other_id = edge["target"] if edge["source"] == entity_id else edge["source"]
                    other_data = self.get_entity(other_id)
                    if other_data:
                        relations_by_type[rel_type].append(other_data.get("name", other_id))

                for rel_type, targets in relations_by_type.items():
                    context_parts.append(f"  - {rel_type.upper()}: {', '.join(targets[:5])}")

                context_parts.append("")

        return "\n".join(context_parts)

    def _seed_to_node_id(
        self,
        seed: Union[str, Tuple[Union[str, Enum], str, str, Dict[str, Any]]]
    ) -> Tuple[Optional[str], Optional[str]]:
        if isinstance(seed, str):
            return seed, None
        entity_type, entity_id, name, _ = seed
        node_id = f"{_normalize_graph_type(entity_type)}:{entity_id}"
        return node_id, name

    def resolve_query_entities(self, text: str) -> List[str]:
        matches: Set[str] = set()
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

    def query_context_from_text(
        self,
        text: str,
        hops: int = 2
    ) -> Tuple[str, List[str]]:
        entity_ids = set(self.resolve_query_entities(text))
        if not entity_ids:
            return "", []
        return self._build_context_for_entities(entity_ids, hops), list(entity_ids)

    def enrich_context(
        self,
        chunks: List[Dict[str, Any]],
        hops: int = 1
    ) -> str:
        """
        Enrich RAG chunks with knowledge graph context.
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

        return self._build_context_for_entities(extracted_entities, hops)
    
    # -------------------------------------------------------------------------
    # Persistence
    # -------------------------------------------------------------------------
    
    def save(self):
        """Persist graph to JSON file."""
        os.makedirs(os.path.dirname(self.persist_path), exist_ok=True)
        
        data = {
            "nodes": [
                {"id": n, **self.graph.nodes[n]} 
                for n in self.graph.nodes
            ],
            "edges": [
                {"source": u, "target": v, **d}
                for u, v, d in self.graph.edges(data=True)
            ],
            "metadata": {
                "saved_at": datetime.now().isoformat(),
                "node_count": self.graph.number_of_nodes(),
                "edge_count": self.graph.number_of_edges()
            }
        }
        
        with open(self.persist_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"GraphRAG: Saved graph to {self.persist_path}")
    
    def _load(self):
        """Load graph from JSON file."""
        try:
            with open(self.persist_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Reconstruct graph
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
        # Count by entity type
        type_counts: Dict[str, int] = {}
        for _, data in self.graph.nodes(data=True):
            etype = data.get("entity_type", "unknown")
            type_counts[etype] = type_counts.get(etype, 0) + 1
        
        # Count by relation type
        rel_counts: Dict[str, int] = {}
        for _, _, data in self.graph.edges(data=True):
            rtype = data.get("relation", "unknown")
            rel_counts[rtype] = rel_counts.get(rtype, 0) + 1
        
        return {
            "total_nodes": self.graph.number_of_nodes(),
            "total_edges": self.graph.number_of_edges(),
            "nodes_by_type": type_counts,
            "edges_by_type": rel_counts,
            "is_connected": nx.is_weakly_connected(self.graph) if self.graph.number_of_nodes() > 0 else False
        }


# =============================================================================
# ENTITY EXTRACTOR (Auto-populate graph from text)
# =============================================================================

class LegalEntityExtractor:
    """
    Extract legal entities from text to auto-populate knowledge graph.
    
    Uses regex patterns to identify:
    - Laws (Lei 8.666/93, Decreto 9.412/2018)
    - Articles (Art. 1º, § 2º)
    - Súmulas (Súmula 331 TST, Súmula Vinculante 13)
    - Jurisprudence (REsp 1.234.567/SP, ADI 1234)
    """
    
    # Regex patterns for Brazilian legal entities
    import re
    
    PATTERNS = {
        "lei": re.compile(
            r"(?:Lei|Decreto|MP|LC|Lei Complementar|Decreto-Lei)\s*n?[º°]?\s*"
            r"([\d.]+)(?:/|\s+de\s+)(\d{4})",
            re.IGNORECASE
        ),
        "artigo": re.compile(
            r"(?:Art|Artigo)\.?\s*(\d+)[º°]?(?:\s*,?\s*§\s*(\d+)[º°]?)?",
            re.IGNORECASE
        ),
        "sumula": re.compile(
            r"Súmula\s+(?:Vinculante\s+)?n?[º°]?\s*(\d+)\s*(?:do\s+)?(STF|STJ|TST|TSE)?",
            re.IGNORECASE
        ),
        "jurisprudencia": re.compile(
            r"(RE|REsp|AgRg|ADI|ADC|ADPF|HC|MS|RMS|RO)\s*n?[º°]?\s*([\d.]+)(?:/([\w]{2}))?",
            re.IGNORECASE
        )
    }
    
    def __init__(self, graph: KnowledgeGraph):
        self.graph = graph

    @classmethod
    def extract_candidates(
        cls,
        text: str
    ) -> List[Tuple[Union[str, Enum], str, str, Dict[str, Any]]]:
        candidates: List[Tuple[Union[str, Enum], str, str, Dict[str, Any]]] = []

        for match in cls.PATTERNS["lei"].finditer(text):
            numero = match.group(1).replace(".", "")
            ano = match.group(2)
            entity_id = f"{numero}_{ano}"
            name = f"Lei {numero}/{ano}"
            candidates.append((EntityType.LEI, entity_id, name, {"numero": numero, "ano": int(ano)}))

        for match in cls.PATTERNS["sumula"].finditer(text):
            numero = match.group(1)
            tribunal = match.group(2) or "STJ"
            entity_id = f"{tribunal}_{numero}"
            name = f"Súmula {numero} {tribunal}"
            candidates.append((EntityType.SUMULA, entity_id, name, {"numero": numero, "tribunal": tribunal}))

        for match in cls.PATTERNS["jurisprudencia"].finditer(text):
            tipo = match.group(1).upper()
            numero = match.group(2).replace(".", "")
            uf = match.group(3) or ""
            entity_id = f"{tipo}_{numero}_{uf}" if uf else f"{tipo}_{numero}"
            name = f"{tipo} {numero}" + (f"/{uf}" if uf else "")
            candidates.append((EntityType.JURISPRUDENCIA, entity_id, name, {"tipo": tipo, "numero": numero, "uf": uf}))

        for match in cls.PATTERNS["artigo"].finditer(text):
            artigo = match.group(1)
            paragrafo = match.group(2) or ""
            entity_id = f"art_{artigo}" + (f"_p{paragrafo}" if paragrafo else "")
            name = f"Art. {artigo}" + (f", § {paragrafo}" if paragrafo else "")
            candidates.append((EntityType.ARTIGO, entity_id, name, {"artigo": artigo, "paragrafo": paragrafo}))

        return candidates
    
    def extract_from_text(self, text: str) -> List[str]:
        """
        Extract and add entities from text.
        
        Args:
            text: Legal text to analyze
            
        Returns:
            List of created node_ids
        """
        created: List[str] = []
        
        # Extract Leis
        for match in self.PATTERNS["lei"].finditer(text):
            numero = match.group(1).replace(".", "")
            ano = match.group(2)
            entity_id = f"{numero}_{ano}"
            name = f"Lei {numero}/{ano}"
            
            node_id = self.graph.add_entity(
                EntityType.LEI,
                entity_id,
                name,
                {"numero": numero, "ano": int(ano)}
            )
            created.append(node_id)
        
        # Extract Súmulas
        for match in self.PATTERNS["sumula"].finditer(text):
            numero = match.group(1)
            tribunal = match.group(2) or "STJ"
            entity_id = f"{tribunal}_{numero}"
            name = f"Súmula {numero} {tribunal}"
            
            node_id = self.graph.add_entity(
                EntityType.SUMULA,
                entity_id,
                name,
                {"numero": numero, "tribunal": tribunal}
            )
            created.append(node_id)
        
        # Extract Jurisprudência
        for match in self.PATTERNS["jurisprudencia"].finditer(text):
            tipo = match.group(1).upper()
            numero = match.group(2).replace(".", "")
            uf = match.group(3) or ""
            entity_id = f"{tipo}_{numero}_{uf}" if uf else f"{tipo}_{numero}"
            name = f"{tipo} {numero}" + (f"/{uf}" if uf else "")
            
            node_id = self.graph.add_entity(
                EntityType.JURISPRUDENCIA,
                entity_id,
                name,
                {"tipo": tipo, "numero": numero, "uf": uf}
            )
            created.append(node_id)
        
        return created
    
    def extract_relationships_from_text(
        self, 
        text: str, 
        source_entity_id: str
    ) -> List[Tuple[str, str, RelationType]]:
        """
        Extract relationships: what does a document cite?
        
        Args:
            text: Text of the document
            source_entity_id: The node_id of the document being analyzed
            
        Returns:
            List of (source, target, relation_type) tuples
        """
        relationships = []
        
        # First extract all entities from text
        created = self.extract_from_text(text)
        
        # Create "cita" relationships from source to all extracted entities
        for target_id in created:
            if target_id != source_entity_id:
                success = self.graph.add_relationship(
                    source_entity_id,
                    target_id,
                    RelationType.CITA
                )
                if success:
                    relationships.append((source_entity_id, target_id, RelationType.CITA))
        
        return relationships


# =============================================================================
# LEGAL PACK (DOMAIN)
# =============================================================================

class LegalPack:
    name = "legal"
    schema = GraphSchema(
        name="legal",
        node_types=tuple(t.value for t in EntityType),
        relation_types=tuple(r.value for r in RelationType),
    )

    def extract_candidates(self, text: str) -> List[Tuple[Union[str, Enum], str, str, Dict[str, Any]]]:
        return LegalEntityExtractor.extract_candidates(text)

    def extract_relations(
        self,
        text: str,
        source_node_id: str,
        candidate_node_ids: Iterable[str],
    ) -> List[Tuple[str, str, Union[str, Enum], Dict[str, Any]]]:
        return [
            (source_node_id, target_id, RelationType.CITA, {})
            for target_id in candidate_node_ids
            if target_id != source_node_id
        ]

    def seed_from_metadata(
        self,
        meta: Dict[str, Any]
    ) -> List[Union[str, Tuple[Union[str, Enum], str, str, Dict[str, Any]]]]:
        seeds: List[Union[str, Tuple[Union[str, Enum], str, str, Dict[str, Any]]]] = []
        meta = meta or {}

        tipo = str(meta.get("tipo") or meta.get("source_type") or "").lower().strip()
        numero = str(meta.get("numero") or "").replace(".", "")
        ano = str(meta.get("ano") or "").strip()

        if tipo in {"lei", "decreto", "portaria"} and numero and ano:
            seeds.append((EntityType.LEI, f"{numero}_{ano}", f"Lei {numero}/{ano}", {"numero": numero, "ano": ano}))

        tipo_decisao = str(meta.get("tipo_decisao") or "").lower()
        tribunal = str(meta.get("tribunal") or "").strip().upper()
        if "sumula" in tipo_decisao and numero:
            seeds.append((EntityType.SUMULA, f"{tribunal or 'STJ'}_{numero}", f"Súmula {numero} {tribunal or 'STJ'}", {"numero": numero, "tribunal": tribunal or "STJ"}))

        if tribunal and numero:
            seeds.append((EntityType.JURISPRUDENCIA, f"{tribunal}_{numero}", f"{tribunal} {numero}", {"tribunal": tribunal, "numero": numero}))

        classe = str(meta.get("classe") or meta.get("tipo_juris") or "").strip().upper()
        uf = str(meta.get("uf") or "").strip().upper()
        if classe and numero:
            entity_id = f"{classe}_{numero}_{uf}" if uf else f"{classe}_{numero}"
            name = f"{classe} {numero}" + (f"/{uf}" if uf else "")
            seeds.append((EntityType.JURISPRUDENCIA, entity_id, name, {"classe": classe, "numero": numero, "uf": uf}))

        return seeds


class LegalKnowledgeGraph(KnowledgeGraph):
    DEFAULT_PERSIST_PATH = os.path.join(
        os.path.dirname(__file__),
        "graph_db",
        "legal_knowledge_graph.json"
    )

    def __init__(self, persist_path: str = None, pack: Optional[BaseGraphPack] = None):
        default_pack = pack
        if default_pack is None:
            default_pack = EXTERNAL_LEGAL_PACK or LegalPack()
        super().__init__(persist_path=persist_path, pack=default_pack)


# =============================================================================
# FACTORY
# =============================================================================

def create_knowledge_graph(
    persist_path: str = None,
    pack: Optional[BaseGraphPack] = None
) -> KnowledgeGraph:
    """Factory function to create knowledge graph instance."""
    if pack is not None:
        return KnowledgeGraph(persist_path=persist_path, pack=pack)
    return LegalKnowledgeGraph(persist_path)


# =============================================================================
# MAIN (Testing)
# =============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Test graph creation
    graph = LegalKnowledgeGraph()
    
    # Add sample entities
    lei_8666 = graph.add_entity(
        EntityType.LEI, 
        "8666_1993", 
        "Lei 8.666/93 - Licitações",
        {"ano": 1993, "jurisdicao": "federal"}
    )
    
    art_1 = graph.add_entity(
        EntityType.ARTIGO,
        "art_1_8666",
        "Art. 1º da Lei 8.666/93",
        {"numero": "1", "lei": "8666"}
    )
    
    sumula_331 = graph.add_entity(
        EntityType.SUMULA,
        "TST_331",
        "Súmula 331 TST",
        {"tribunal": "TST", "numero": "331"}
    )
    
    # Add relationships
    graph.add_relationship(lei_8666, art_1, RelationType.POSSUI)
    graph.add_relationship(sumula_331, lei_8666, RelationType.CITA)
    
    # Test query
    related = graph.query_related(lei_8666, hops=2)
    print(f"Related to Lei 8.666: {related}")
    
    # Test stats
    print(f"Stats: {graph.get_stats()}")
    
    # Test extractor
    extractor = LegalEntityExtractor(graph)
    test_text = """
    Conforme a Lei 13.869/2019 (Lei de Abuso de Autoridade) e a 
    Súmula 7 do STJ, bem como o REsp 1.234.567/SP...
    """
    extracted = extractor.extract_from_text(test_text)
    print(f"Extracted: {extracted}")
    
    # Save
    graph.save()
