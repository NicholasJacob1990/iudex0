"""Pydantic models for the Neo4j RAG pipeline."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


# ─── Document Types ───────────────────────────────────────────────

class SourceType(str, Enum):
    CURSO_TREVO = "CursoTrevo"
    NICHOLAS = "TranscricaoNicholas"
    CEAP = "CEAP"


class DocumentType(str, Enum):
    LEGISLACAO = "legislacao"
    JURISPRUDENCIA = "jurisprudencia"
    TRANSCRICAO = "transcricao"
    QUESTAO = "questao"
    APOSTILA = "apostila"


# ─── Entity Types ─────────────────────────────────────────────────

class EntityType(str, Enum):
    LEI = "Lei"
    ARTIGO = "Artigo"
    SUMULA = "Sumula"
    DECISAO = "Decisao"
    TESE = "Tese"
    TEMA = "Tema"
    TRIBUNAL = "Tribunal"
    INSTITUTO = "Instituto"
    CONCEITO = "Conceito"
    PRINCIPIO = "Principio"
    DOUTRINA = "Doutrina"
    DOUTRINADOR = "Doutrinador"


# ─── Core Models ──────────────────────────────────────────────────

class Document(BaseModel):
    id: str
    title: str
    source_type: SourceType
    document_type: DocumentType
    path: str
    disciplina: str = ""
    ingested_at: Optional[datetime] = None


class Chunk(BaseModel):
    id: str
    text: str
    doc_id: str
    position: int
    hierarchy: List[str] = Field(default_factory=list)
    contextual_prefix: str = ""
    embedding: Optional[List[float]] = None
    parent_id: Optional[str] = None


class Entity(BaseModel):
    id: str
    name: str
    entity_type: EntityType
    normalized_name: str = ""
    properties: Dict[str, str] = Field(default_factory=dict)


# ─── Search Results ───────────────────────────────────────────────

class SearchResult(BaseModel):
    chunk_id: str
    text: str
    score: float
    source: str  # "vector", "fulltext", "graph", "rrf"
    doc_title: str = ""
    hierarchy: List[str] = Field(default_factory=list)
    entities: List[str] = Field(default_factory=list)


class RetrievalResult(BaseModel):
    query: str
    results: List[SearchResult]
    total_candidates: int = 0
    graph_hops_used: int = 0
