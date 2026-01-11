"""
RAG Graph Module (v5.1) - Knowledge Graph for Legal Documents

Implements GraphRAG pattern:
- Nodes represent legal entities (Lei, Artigo, Súmula, Jurisprudência, Tese)
- Edges represent relationships (cita, aplica, revoga, vincula)

Uses NetworkX for in-memory graph with JSON persistence.

Ported from CLI to API layer for frontend agent integration.
"""

import json
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum

try:
    import networkx as nx
except ImportError:
    raise ImportError("NetworkX required: pip install networkx")

try:
    from loguru import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


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
# DATA CLASSES
# =============================================================================

@dataclass
class LegalEntity:
    """Base class for legal entities (graph nodes)."""
    entity_type: EntityType
    entity_id: str  # Unique ID within type (e.g., "lei_8666_1993")
    name: str       # Display name (e.g., "Lei 8.666/93")
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def node_id(self) -> str:
        """Global unique ID for graph."""
        return f"{self.entity_type.value}:{self.entity_id}"


@dataclass  
class LegalRelation:
    """Relationship between legal entities (graph edges)."""
    source_id: str      # Entity node_id
    target_id: str      # Entity node_id
    relation_type: RelationType
    weight: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# KNOWLEDGE GRAPH
# =============================================================================

class LegalKnowledgeGraph:
    """
    Knowledge Graph for Legal Documents.
    
    Enables GraphRAG queries like:
    - "Which laws are cited by decisions that apply Súmula X?"
    - "What articles are related to thesis Y?"
    
    Usage:
        graph = LegalKnowledgeGraph()
        graph.add_entity(EntityType.LEI, "8666_1993", "Lei 8.666/93", {"ano": 1993})
        graph.add_entity(EntityType.ARTIGO, "art_1_8666", "Art. 1º", {"lei": "8666"})
        graph.add_relationship("lei:8666_1993", "artigo:art_1_8666", RelationType.POSSUI)
        
        # Query
        related = graph.query_related("lei:8666_1993", hops=2)
    """
    
    # Default path inside API services
    DEFAULT_PERSIST_PATH = os.path.join(
        os.path.dirname(__file__), 
        "graph_db", 
        "legal_knowledge_graph.json"
    )
    
    def __init__(self, persist_path: str = None):
        """
        Initialize the knowledge graph.
        
        Args:
            persist_path: Path to JSON file for persistence
        """
        self.persist_path = persist_path or self.DEFAULT_PERSIST_PATH
        self.graph = nx.DiGraph()
        self._entity_index: Dict[str, LegalEntity] = {}
        
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
        entity_type: EntityType, 
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
        entity = LegalEntity(
            entity_type=entity_type,
            entity_id=entity_id,
            name=name,
            metadata=metadata or {}
        )
        
        node_id = entity.node_id
        
        # Add to NetworkX graph
        self.graph.add_node(
            node_id,
            entity_type=entity_type.value,
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
        entity_type: EntityType = None, 
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
            if entity_type and data.get("entity_type") != entity_type.value:
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
        relation_type: RelationType,
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
        
        self.graph.add_edge(
            source_id,
            target_id,
            relation=relation_type.value,
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
        relation_filter: List[RelationType] = None
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
        
        for _ in range(hops):
            next_frontier: Set[str] = set()
            
            for current in frontier:
                # Outgoing edges
                for _, target, data in self.graph.out_edges(current, data=True):
                    if relation_filter:
                        if data.get("relation") not in [r.value for r in relation_filter]:
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
                    if relation_filter:
                        if data.get("relation") not in [r.value for r in relation_filter]:
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
    
    def enrich_context(
        self,
        chunks: List[Dict[str, Any]],
        hops: int = 1
    ) -> str:
        """
        Enrich RAG chunks with knowledge graph context.
        
        Extracts entities from chunk metadata and adds related entities.
        This is the integration point with standard RAG.
        
        Args:
            chunks: RAG search results with metadata
            hops: Relationship depth to explore
            
        Returns:
            Formatted string with graph context for LLM prompt
        """
        extracted_entities: Set[str] = set()
        
        # Extract entities from chunk metadata
        for chunk in chunks:
            meta = chunk.get("metadata", {})
            
            # Lei extraction
            if "tipo" in meta and meta["tipo"] in ["lei", "decreto", "portaria"]:
                lei_id = f"{meta['tipo']}_{meta.get('numero', 'unknown')}_{meta.get('ano', '')}"
                node_id = f"lei:{lei_id}"
                if node_id in self.graph.nodes:
                    extracted_entities.add(node_id)
            
            # Súmula extraction
            if "tipo_decisao" in meta and "súmula" in meta.get("tipo_decisao", "").lower():
                sumula_id = f"{meta.get('tribunal', 'unknown')}_{meta.get('numero', '')}"
                node_id = f"sumula:{sumula_id}"
                if node_id in self.graph.nodes:
                    extracted_entities.add(node_id)
            
            # Jurisprudência extraction
            if "tribunal" in meta and "numero" in meta:
                juris_id = f"{meta['tribunal']}_{meta['numero']}"
                node_id = f"jurisprudencia:{juris_id}"
                if node_id in self.graph.nodes:
                    extracted_entities.add(node_id)
        
        if not extracted_entities:
            return ""
        
        # Build context from graph relationships
        context_parts = ["### 📊 CONTEXTO DO GRAFO DE CONHECIMENTO:\n"]
        
        for entity_id in extracted_entities:
            subgraph = self.query_related(entity_id, hops=hops)
            entity_data = self.get_entity(entity_id)
            
            if entity_data:
                context_parts.append(f"**{entity_data.get('name', entity_id)}**:")
                
                # Group by relationship type
                relations_by_type: Dict[str, List[str]] = {}
                for edge in subgraph["edges"]:
                    rel_type = edge["relation"]
                    if rel_type not in relations_by_type:
                        relations_by_type[rel_type] = []
                    
                    # Get the "other" node
                    other_id = edge["target"] if edge["source"] == entity_id else edge["source"]
                    other_data = self.get_entity(other_id)
                    if other_data:
                        relations_by_type[rel_type].append(other_data.get("name", other_id))
                
                for rel_type, targets in relations_by_type.items():
                    context_parts.append(f"  - {rel_type.upper()}: {', '.join(targets[:5])}")
                
                context_parts.append("")
        
        return "\n".join(context_parts)
    
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
    
    def __init__(self, graph: LegalKnowledgeGraph):
        self.graph = graph
    
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
# FACTORY & SINGLETON
# =============================================================================

_knowledge_graph_instance: Optional[LegalKnowledgeGraph] = None


def get_knowledge_graph(persist_path: str = None) -> LegalKnowledgeGraph:
    """
    Get or create the singleton knowledge graph instance.
    
    This is the main entry point for workflow integration.
    """
    global _knowledge_graph_instance
    
    if _knowledge_graph_instance is None:
        _knowledge_graph_instance = LegalKnowledgeGraph(persist_path)
    
    return _knowledge_graph_instance


def create_knowledge_graph(persist_path: str = None) -> LegalKnowledgeGraph:
    """Factory function to create a new knowledge graph instance (non-singleton)."""
    return LegalKnowledgeGraph(persist_path)
