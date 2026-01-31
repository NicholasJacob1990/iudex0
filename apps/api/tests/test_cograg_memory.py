"""
Tests for CogGRAG memory nodes.

Covers: ConsultationMemory, memory_check_node, memory_store_node.
"""

import json
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch

from app.services.rag.core.cograg.nodes.memory import (
    ConsultationMemory,
    memory_check_node,
    memory_store_node,
)


# ═══════════════════════════════════════════════════════════════════════════
# ConsultationMemory
# ═══════════════════════════════════════════════════════════════════════════

class TestConsultationMemory:
    @pytest.fixture
    def temp_memory(self, tmp_path):
        """Create a ConsultationMemory with a temp directory."""
        return ConsultationMemory(data_dir=tmp_path)

    def test_init_creates_directory(self, tmp_path):
        data_dir = tmp_path / "memory"
        memory = ConsultationMemory(data_dir=data_dir)
        assert data_dir.exists()

    def test_store_and_count(self, temp_memory):
        assert temp_memory.count() == 0

        entry_id = temp_memory.store(
            query="Qual o prazo prescricional para ações trabalhistas?",
            tenant_id="tenant1",
            mind_map={"root": "test"},
            sub_questions=[{"q": "sub1"}],
            evidence_map={"node1": {"evidence": "test"}},
        )

        assert entry_id is not None
        assert len(entry_id) == 16
        assert temp_memory.count() == 1
        assert temp_memory.count(tenant_id="tenant1") == 1
        assert temp_memory.count(tenant_id="tenant2") == 0

    def test_find_similar_exact_match(self, temp_memory):
        temp_memory.store(
            query="Quais os requisitos para rescisão indireta?",
            tenant_id="tenant1",
            mind_map=None,
            sub_questions=[],
            evidence_map={},
        )

        # Same query should have similarity = 1.0
        results = temp_memory.find_similar(
            query="Quais os requisitos para rescisão indireta?",
            tenant_id="tenant1",
            threshold=0.3,
        )

        assert len(results) == 1
        assert results[0]["similarity"] >= 0.9

    def test_find_similar_partial_match(self, temp_memory):
        temp_memory.store(
            query="Quais os requisitos para rescisão indireta do contrato de trabalho?",
            tenant_id="tenant1",
            mind_map=None,
            sub_questions=[],
            evidence_map={},
        )

        # Similar query should be found
        results = temp_memory.find_similar(
            query="rescisão indireta requisitos trabalhista",
            tenant_id="tenant1",
            threshold=0.2,
        )

        assert len(results) == 1
        assert results[0]["similarity"] >= 0.2

    def test_find_similar_filters_by_tenant(self, temp_memory):
        temp_memory.store(
            query="Prescrição trabalhista prazo",
            tenant_id="tenant1",
            mind_map=None,
            sub_questions=[],
            evidence_map={},
        )

        # Same query but different tenant
        results = temp_memory.find_similar(
            query="Prescrição trabalhista prazo",
            tenant_id="tenant2",
            threshold=0.1,
        )

        assert len(results) == 0

    def test_find_similar_below_threshold(self, temp_memory):
        temp_memory.store(
            query="Direito civil contratos imobiliários",
            tenant_id="tenant1",
            mind_map=None,
            sub_questions=[],
            evidence_map={},
        )

        # Completely different query
        results = temp_memory.find_similar(
            query="Processo penal recursos criminais",
            tenant_id="tenant1",
            threshold=0.5,
        )

        assert len(results) == 0

    def test_find_similar_limit(self, temp_memory):
        # Store 5 similar consultations
        for i in range(5):
            temp_memory.store(
                query=f"Prescrição trabalhista prazo consulta {i}",
                tenant_id="tenant1",
                mind_map=None,
                sub_questions=[],
                evidence_map={},
            )

        results = temp_memory.find_similar(
            query="Prescrição trabalhista prazo",
            tenant_id="tenant1",
            threshold=0.1,
            limit=2,
        )

        assert len(results) == 2

    def test_extract_keywords(self, temp_memory):
        keywords = temp_memory._extract_keywords(
            "Qual o prazo prescricional para ações trabalhistas no Brasil?"
        )

        # Should include meaningful words, exclude stopwords
        assert "prazo" in keywords
        assert "prescricional" in keywords
        assert "trabalhistas" in keywords
        assert "brasil" in keywords
        # Stopwords excluded
        assert "qual" not in keywords
        assert "para" not in keywords
        assert "no" not in keywords

    def test_index_persistence(self, tmp_path):
        # Create memory and store
        memory1 = ConsultationMemory(data_dir=tmp_path)
        memory1.store(
            query="Test query",
            tenant_id="t1",
            mind_map=None,
            sub_questions=[],
            evidence_map={},
        )

        # Create new instance (simulating restart)
        memory2 = ConsultationMemory(data_dir=tmp_path)
        assert memory2.count() == 1


# ═══════════════════════════════════════════════════════════════════════════
# Memory Check Node
# ═══════════════════════════════════════════════════════════════════════════

class TestMemoryCheckNode:
    @pytest.mark.asyncio
    async def test_disabled_by_default(self):
        state = {
            "query": "Test query",
            "tenant_id": "default",
            "cograg_memory_enabled": False,
            "cograg_memory_backend": "file",
            "metrics": {},
        }
        result = await memory_check_node(state)

        assert result["similar_consultation"] is None
        assert result["metrics"]["memory_check_enabled"] is False

    @pytest.mark.asyncio
    async def test_enabled_no_match(self, tmp_path):
        # Use empty temp memory
        with patch("app.services.rag.core.cograg.nodes.memory.get_consultation_memory") as mock:
            mock.return_value = ConsultationMemory(data_dir=tmp_path)

            state = {
                "query": "Test query with no matches",
                "tenant_id": "default",
                "cograg_memory_enabled": True,
                "cograg_memory_backend": "file",
                "metrics": {},
            }
            result = await memory_check_node(state)

            assert result["similar_consultation"] is None
            assert result["metrics"]["memory_check_enabled"] is True
            assert result["metrics"]["memory_check_found"] is False

    @pytest.mark.asyncio
    async def test_enabled_with_match(self, tmp_path):
        # Create memory with stored consultation
        memory = ConsultationMemory(data_dir=tmp_path)
        memory.store(
            query="Prescrição trabalhista prazo",
            tenant_id="default",
            mind_map={"test": True},
            sub_questions=[{"q": "sub"}],
            evidence_map={},
        )

        with patch("app.services.rag.core.cograg.nodes.memory.get_consultation_memory") as mock:
            mock.return_value = memory

            state = {
                "query": "Prescrição trabalhista prazo",
                "tenant_id": "default",
                "cograg_memory_enabled": True,
                "cograg_memory_backend": "file",
                "metrics": {},
            }
            result = await memory_check_node(state)

            assert result["similar_consultation"] is not None
            assert result["similar_consultation"]["similarity"] >= 0.5
            assert result["metrics"]["memory_check_found"] is True

    @pytest.mark.asyncio
    async def test_empty_query(self):
        state = {
            "query": "",
            "tenant_id": "default",
            "cograg_memory_enabled": True,
            "cograg_memory_backend": "file",
            "metrics": {},
        }
        result = await memory_check_node(state)

        assert result["similar_consultation"] is None


# ═══════════════════════════════════════════════════════════════════════════
# Memory Store Node
# ═══════════════════════════════════════════════════════════════════════════

class TestMemoryStoreNode:
    @pytest.mark.asyncio
    async def test_disabled_by_default(self):
        state = {
            "query": "Test query",
            "tenant_id": "default",
            "cograg_memory_enabled": False,
            "cograg_memory_backend": "file",
            "mind_map": {"test": True},
            "sub_questions": [],
            "evidence_map": {},
            "metrics": {},
        }
        result = await memory_store_node(state)

        assert result["metrics"]["memory_store_enabled"] is False

    @pytest.mark.asyncio
    async def test_stores_consultation(self, tmp_path):
        memory = ConsultationMemory(data_dir=tmp_path)

        with patch("app.services.rag.core.cograg.nodes.memory.get_consultation_memory") as mock:
            mock.return_value = memory

            state = {
                "query": "Test query for storage",
                "tenant_id": "default",
                "cograg_memory_enabled": True,
                "cograg_memory_backend": "file",
                "mind_map": {"root": "question"},
                "sub_questions": [{"q": "sub1"}],
                "evidence_map": {"n1": {"data": "test"}},
                "integrated_response": "Final answer",
                "metrics": {},
            }
            result = await memory_store_node(state)

            assert result["metrics"]["memory_store_enabled"] is True
            assert "memory_store_entry_id" in result["metrics"]
            assert memory.count() == 1

    @pytest.mark.asyncio
    async def test_empty_query(self):
        state = {
            "query": "",
            "tenant_id": "default",
            "cograg_memory_enabled": True,
            "cograg_memory_backend": "file",
            "metrics": {},
        }
        result = await memory_store_node(state)

        assert "memory_store_entry_id" not in result["metrics"]

    @pytest.mark.asyncio
    async def test_preserves_existing_metrics(self, tmp_path):
        memory = ConsultationMemory(data_dir=tmp_path)

        with patch("app.services.rag.core.cograg.nodes.memory.get_consultation_memory") as mock:
            mock.return_value = memory

            state = {
                "query": "Test",
                "tenant_id": "default",
                "cograg_memory_enabled": True,
                "cograg_memory_backend": "file",
                "mind_map": None,
                "sub_questions": [],
                "evidence_map": {},
                "metrics": {"existing": 42},
            }
            result = await memory_store_node(state)

            assert result["metrics"]["existing"] == 42
            assert result["metrics"]["memory_store_enabled"] is True
