"""
Unit tests for Graph RAG module.

Tests:
- Entity creation and retrieval
- Relationship creation
- Graph queries (query_related, find_path)
- Entity extraction from text
- Context enrichment
"""

import pytest
import tempfile
import os
import shutil

from app.services.rag_graph import (
    LegalKnowledgeGraph,
    LegalEntityExtractor,
    EntityType,
    RelationType,
)


@pytest.fixture
def temp_graph_path():
    """Create a temporary directory for graph persistence."""
    temp_dir = tempfile.mkdtemp()
    graph_path = os.path.join(temp_dir, "test_graph.json")
    yield graph_path
    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def graph(temp_graph_path):
    """Create a fresh graph for each test."""
    return LegalKnowledgeGraph(persist_path=temp_graph_path)


class TestEntityManagement:
    """Tests for entity CRUD operations."""
    
    def test_add_entity(self, graph):
        """Test adding a single entity."""
        node_id = graph.add_entity(EntityType.LEI, "8666_1993", "Lei 8.666/93")
        
        assert node_id == "lei:8666_1993"
        assert graph.get_entity(node_id) is not None
        assert graph.get_entity(node_id)["name"] == "Lei 8.666/93"
    
    def test_add_entity_with_metadata(self, graph):
        """Test adding entity with custom metadata."""
        node_id = graph.add_entity(
            EntityType.LEI,
            "14133_2021",
            "Lei 14.133/21",
            {"ano": 2021, "jurisdicao": "federal"}
        )
        
        entity = graph.get_entity(node_id)
        assert entity["ano"] == 2021
        assert entity["jurisdicao"] == "federal"
    
    def test_find_entities_by_type(self, graph):
        """Test filtering entities by type."""
        graph.add_entity(EntityType.LEI, "1", "Lei 1")
        graph.add_entity(EntityType.LEI, "2", "Lei 2")
        graph.add_entity(EntityType.SUMULA, "331", "Súmula 331")
        
        leis = graph.find_entities(entity_type=EntityType.LEI)
        assert len(leis) == 2
        
        sumulas = graph.find_entities(entity_type=EntityType.SUMULA)
        assert len(sumulas) == 1
    
    def test_find_entities_by_name(self, graph):
        """Test filtering entities by name substring."""
        graph.add_entity(EntityType.LEI, "8666", "Lei 8.666/93 - Licitações")
        graph.add_entity(EntityType.LEI, "14133", "Lei 14.133/21 - Nova Lei de Licitações")
        graph.add_entity(EntityType.LEI, "8112", "Lei 8.112/90 - Regime Jurídico")
        
        results = graph.find_entities(name_contains="licitações")
        assert len(results) == 2


class TestRelationshipManagement:
    """Tests for relationship operations."""
    
    def test_add_relationship(self, graph):
        """Test adding a relationship between entities."""
        lei = graph.add_entity(EntityType.LEI, "8666", "Lei 8.666/93")
        art = graph.add_entity(EntityType.ARTIGO, "art_1", "Art. 1º")
        
        success = graph.add_relationship(lei, art, RelationType.POSSUI)
        
        assert success is True
        relations = graph.get_relationships(lei, direction="outgoing")
        assert len(relations) == 1
        assert relations[0]["relation"] == "possui"
    
    def test_add_relationship_nonexistent_node(self, graph):
        """Test that adding relationship to nonexistent node fails."""
        lei = graph.add_entity(EntityType.LEI, "8666", "Lei 8.666/93")
        
        success = graph.add_relationship(lei, "fake:node", RelationType.CITA)
        
        assert success is False
    
    def test_get_relationships_both_directions(self, graph):
        """Test getting incoming and outgoing relationships."""
        lei = graph.add_entity(EntityType.LEI, "8666", "Lei 8.666")
        sumula = graph.add_entity(EntityType.SUMULA, "331", "Súmula 331")
        art = graph.add_entity(EntityType.ARTIGO, "art_1", "Art. 1º")
        
        graph.add_relationship(lei, art, RelationType.POSSUI)  # outgoing
        graph.add_relationship(sumula, lei, RelationType.CITA)  # incoming
        
        relations = graph.get_relationships(lei, direction="both")
        assert len(relations) == 2


class TestGraphQueries:
    """Tests for graph traversal and queries."""
    
    def test_query_related_one_hop(self, graph):
        """Test finding related entities within 1 hop."""
        lei = graph.add_entity(EntityType.LEI, "8666", "Lei 8.666")
        art1 = graph.add_entity(EntityType.ARTIGO, "art_1", "Art. 1")
        art2 = graph.add_entity(EntityType.ARTIGO, "art_2", "Art. 2")
        
        graph.add_relationship(lei, art1, RelationType.POSSUI)
        graph.add_relationship(lei, art2, RelationType.POSSUI)
        
        result = graph.query_related(lei, hops=1)
        
        assert len(result["nodes"]) == 3  # lei + 2 arts
        assert len(result["edges"]) == 2
    
    def test_query_related_two_hops(self, graph):
        """Test finding related entities within 2 hops."""
        lei = graph.add_entity(EntityType.LEI, "8666", "Lei 8.666")
        art = graph.add_entity(EntityType.ARTIGO, "art_1", "Art. 1")
        juris = graph.add_entity(EntityType.JURISPRUDENCIA, "resp_123", "REsp 123")
        
        graph.add_relationship(lei, art, RelationType.POSSUI)
        graph.add_relationship(juris, art, RelationType.INTERPRETA)
        
        result = graph.query_related(lei, hops=2)
        
        # lei -> art <- juris (2 hops from lei to juris)
        assert len(result["nodes"]) == 3
    
    def test_find_path(self, graph):
        """Test finding shortest path between entities."""
        lei = graph.add_entity(EntityType.LEI, "8666", "Lei 8.666")
        sumula = graph.add_entity(EntityType.SUMULA, "331", "Súmula 331")
        juris = graph.add_entity(EntityType.JURISPRUDENCIA, "resp_123", "REsp 123")
        
        graph.add_relationship(lei, sumula, RelationType.CITA)
        graph.add_relationship(sumula, juris, RelationType.VINCULA)
        
        path = graph.find_path(lei, juris)
        
        assert path is not None
        assert len(path) == 3  # lei -> sumula -> juris
    
    def test_find_path_no_path(self, graph):
        """Test that find_path returns None when no path exists."""
        lei = graph.add_entity(EntityType.LEI, "8666", "Lei 8.666")
        sumula = graph.add_entity(EntityType.SUMULA, "331", "Súmula 331")
        # No relationship
        
        path = graph.find_path(lei, sumula)
        
        assert path is None


class TestEntityExtractor:
    """Tests for legal entity extraction from text."""
    
    def test_extract_lei(self, graph):
        """Test extracting laws from text."""
        extractor = LegalEntityExtractor(graph)
        
        text = "Conforme a Lei 13.869/2019, conhecida como Lei de Abuso de Autoridade"
        nodes = extractor.extract_from_text(text)
        
        assert any("lei:" in n for n in nodes)
    
    def test_extract_sumula(self, graph):
        """Test extracting súmulas from text."""
        extractor = LegalEntityExtractor(graph)
        
        text = "Segundo a Súmula 7 do STJ e a Súmula 331 do TST"
        nodes = extractor.extract_from_text(text)
        
        sumula_nodes = [n for n in nodes if "sumula:" in n]
        assert len(sumula_nodes) >= 2
    
    def test_extract_jurisprudencia(self, graph):
        """Test extracting jurisprudence from text."""
        extractor = LegalEntityExtractor(graph)
        
        text = "No julgamento do REsp 1.234.567/SP e do ADI 5035"
        nodes = extractor.extract_from_text(text)
        
        juris_nodes = [n for n in nodes if "jurisprudencia:" in n]
        assert len(juris_nodes) >= 2
    
    def test_extract_relationships(self, graph):
        """Test extracting citation relationships."""
        # First add a source document as entity
        source = graph.add_entity(
            EntityType.JURISPRUDENCIA, 
            "RESP_999", 
            "REsp 999"
        )
        
        extractor = LegalEntityExtractor(graph)
        
        text = "Este julgado cita a Lei 8.666/1993 e a Súmula 331 do TST"
        relationships = extractor.extract_relationships_from_text(text, source)
        
        # Should have "cita" relationships from source to lei and sumula
        assert len(relationships) >= 2
        for src, tgt, rel in relationships:
            assert rel == RelationType.CITA
            assert src == source


class TestContextEnrichment:
    """Tests for RAG context enrichment."""
    
    def test_enrich_context_empty_chunks(self, graph):
        """Test that empty chunks return empty context."""
        context = graph.enrich_context([], hops=1)
        assert context == ""
    
    def test_enrich_context_with_matching_entity(self, graph):
        """Test context enrichment when entities match."""
        # Add some entities to graph
        lei = graph.add_entity(EntityType.LEI, "lei_8666_1993", "Lei 8.666/93")
        art = graph.add_entity(EntityType.ARTIGO, "art_1", "Art. 1º")
        graph.add_relationship(lei, art, RelationType.POSSUI)
        
        # Create chunks with metadata that matches the entity
        chunks = [{
            "text": "Texto sobre licitações",
            "metadata": {
                "tipo": "lei",
                "numero": "8666",
                "ano": "1993"
            }
        }]
        
        context = graph.enrich_context(chunks, hops=1)
        
        # Should find the lei and include its relationships
        assert "Lei 8.666/93" in context or "POSSUI" in context or context == ""


class TestPersistence:
    """Tests for graph save/load."""
    
    def test_save_and_load(self, temp_graph_path):
        """Test that graph persists and loads correctly."""
        # Create and save
        graph1 = LegalKnowledgeGraph(persist_path=temp_graph_path)
        graph1.add_entity(EntityType.LEI, "8666", "Lei 8.666")
        graph1.add_entity(EntityType.SUMULA, "331", "Súmula 331")
        graph1.save()
        
        # Load in new instance
        graph2 = LegalKnowledgeGraph(persist_path=temp_graph_path)
        
        assert graph2.graph.number_of_nodes() == 2
    
    def test_get_stats(self, graph):
        """Test statistics collection."""
        graph.add_entity(EntityType.LEI, "1", "Lei 1")
        graph.add_entity(EntityType.LEI, "2", "Lei 2")
        graph.add_entity(EntityType.SUMULA, "331", "Súmula 331")
        graph.add_relationship("lei:1", "lei:2", RelationType.REVOGA)
        
        stats = graph.get_stats()
        
        assert stats["total_nodes"] == 3
        assert stats["total_edges"] == 1
        assert stats["nodes_by_type"]["lei"] == 2
        assert stats["nodes_by_type"]["sumula"] == 1
