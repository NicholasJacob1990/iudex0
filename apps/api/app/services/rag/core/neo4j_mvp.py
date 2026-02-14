"""
Neo4j MVP Graph Service for Legal RAG

GraphRAG with dual extraction:
- Regex extraction: Articles, Laws, Súmulas, Themes, Courts (deterministic)
- Semantic extraction: Theses, Concepts, Principles, Institutes (LLM-based via Gemini)
- Document → Chunk → Entity relationships
- Path-based queries with Cypher
- Multi-tenant security trimming
- Explainable connections for LLM context

Schema:
    Nodes:
    - Document (doc_hash, tenant_id, scope, case_id, title, source_type)
    - Chunk (chunk_uid, doc_hash, chunk_index, text_preview)
    - Entity (entity_type, entity_id, name, normalized)
    - Fact (fact_id, text_preview, doc_hash, tenant_id, scope, case_id)
    - Claim (claim_id, text, claim_type, polarity, tenant_id, case_id)
    - Evidence (evidence_id, text, evidence_type, weight, tenant_id)
    - Actor (actor_id, name, role, tenant_id)
    - Issue (issue_id, text, domain, tenant_id, case_id)

    Relationships:
    - (:Document)-[:HAS_CHUNK]->(:Chunk)
    - (:Chunk)-[:MENTIONS]->(:Entity)
    - (:Chunk)-[:ASSERTS]->(:Fact)
    - (:Fact)-[:REFERS_TO]->(:Entity)
    - (:Chunk)-[:NEXT]->(:Chunk)  # sequence for neighbor expansion
    - (:Entity)-[:RELATED_TO]->(:Entity)  # semantic relations
    - (:Chunk)-[:CONTAINS_CLAIM]->(:Claim)
    - (:Claim)-[:SUPPORTS]->(:Claim)
    - (:Claim)-[:OPPOSES]->(:Claim)
    - (:Evidence)-[:EVIDENCES]->(:Claim)
    - (:Claim)-[:RAISES]->(:Issue)
    - (:Actor)-[:ARGUES]->(:Claim)
    - (:Claim)-[:CITES]->(:Entity)
    - (:Evidence)-[:CITES]->(:Entity)

Usage:
    from app.services.rag.core.neo4j_mvp import get_neo4j_mvp

    neo4j = get_neo4j_mvp()

    # Ingest with semantic extraction (uses Gemini Flash)
    neo4j.ingest_document(doc_hash, chunks, metadata, tenant_id, semantic_extraction=True)

    # Query
    results = neo4j.query_related_chunks(
        entities=["art_5", "lei_8666"],
        tenant_id="tenant1",
        scope="global",
        max_hops=2
    )
"""

from __future__ import annotations

import asyncio
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
    Set,
    Tuple,
    Union,
)

logger = logging.getLogger(__name__)

_RELATION_LABEL_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,40}$")
_DEFAULT_ALLOWED_RELATIONS: Set[str] = {
    "RELATED_TO",
    "CITA",
    "CITES",
    "APLICA",
    "REVOGA",
    "ALTERA",
    "FUNDAMENTA",
    "INTERPRETA",
    "PERTENCE_A",
    "REMETE_A",
    "CO_MENCIONA",
    "EXCEPCIONA",
    "REGULAMENTA",
    "PROFERIDA_POR",
    "FIXA_TESE",
    "JULGA_TEMA",
    "VINCULA",
    "MENTIONS",
    "BELONGS_TO",
}


# =============================================================================
# COMPOUND CITATION MODEL
# =============================================================================


@dataclass
class CompoundCitation:
    """
    Citação jurídica composta com hierarquia completa.

    Representa referências como:
    - "Lei 8.666/1993, Art. 23, § 1º, inciso II"
    - "Art. 5º, caput, da Constituição Federal"
    - "CLT, Art. 477, § 8º"
    - "CPC, Art. 1.015, parágrafo único"
    """
    full_text: str          # "Lei 8.666/1993, Art. 23, § 1º, inciso II"
    law: Optional[str]      # "Lei 8.666/1993"
    code: Optional[str]     # "CPC", "CLT", "CF"
    article: Optional[str]  # "Art. 23"
    paragraph: Optional[str]  # "§ 1º" ou "parágrafo único"
    inciso: Optional[str]   # "inciso II"
    alinea: Optional[str]   # "alínea 'a'"
    normalized_id: str      # "lei_8666_1993_art_23_p1_inc_ii"

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário serializável."""
        return {
            "full_text": self.full_text,
            "law": self.law,
            "code": self.code,
            "article": self.article,
            "paragraph": self.paragraph,
            "inciso": self.inciso,
            "alinea": self.alinea,
            "normalized_id": self.normalized_id,
        }


# =============================================================================
# ENV PARSING (matches app.services.rag.config._env_bool)
# =============================================================================


def _env_bool(name: str, default: bool = False) -> bool:
    """Parse boolean environment variable (consistent with config.py)."""
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.lower() in ("1", "true", "yes", "on")


def _env_first(*names: str) -> Optional[str]:
    """Return first non-empty environment value among aliases."""
    for name in names:
        value = os.getenv(name)
        if value is not None:
            value = value.strip()
            if value:
                return value
    return None


def _infer_neo4j_uri() -> str:
    """
    Resolve Neo4j URI with Aura-aware fallbacks.

    Priority:
    1. Explicit URI aliases (NEO4J_URI, NEO4J_URL, NEO4J_BOLT_URL)
    2. Aura instance id -> neo4j+s://<instance>.databases.neo4j.io
    3. Local development default.
    """
    aura_instance_id = _env_first("AURA_INSTANCEID")
    explicit_uri = _env_first("NEO4J_URI", "NEO4J_URL", "NEO4J_BOLT_URL")
    if explicit_uri:
        # If URI is still localhost but Aura instance id is present, prefer Aura.
        # This avoids accidental localhost fallback when migrating envs.
        if aura_instance_id and re.search(r"://(localhost|127\.0\.0\.1)(:\d+)?$", explicit_uri):
            return f"neo4j+s://{aura_instance_id}.databases.neo4j.io"
        return explicit_uri

    if aura_instance_id:
        return f"neo4j+s://{aura_instance_id}.databases.neo4j.io"

    # Local dev default: Iudex Docker maps Bolt to 8687 to avoid conflicting with Neo4j Desktop (7687).
    return "bolt://localhost:8687"


# =============================================================================
# CONFIGURATION
# =============================================================================


@dataclass
class Neo4jMVPConfig:
    """Configuration for Neo4j MVP service."""

    # Connection
    # Local dev default: Iudex Docker maps Bolt to 8687 to avoid conflicting with Neo4j Desktop (7687).
    uri: str = "bolt://localhost:8687"
    user: str = "neo4j"
    password: str = "password"
    database: str = "iudex"

    # Pool settings
    max_connection_pool_size: int = 50
    connection_timeout: int = 30
    liveness_check_timeout: Optional[float] = None

    # Query settings
    max_hops: int = 2
    max_chunks_per_query: int = 50
    max_entities_per_chunk: int = 20

    # Ingest settings
    batch_size: int = 200
    create_indexes: bool = True
    graph_hybrid_mode: bool = False
    graph_hybrid_auto_schema: bool = True
    graph_hybrid_migrate_on_startup: bool = False
    max_facts_per_chunk: int = 3

    # Phase 2 (optional): Neo4j-based retrieval helpers (no training required)
    enable_fulltext_indexes: bool = False
    enable_vector_index: bool = False
    vector_dimensions: int = 1024  # voyage-4-large default
    vector_similarity: str = "cosine"
    vector_property: str = "embedding"

    @classmethod
    def from_env(cls) -> "Neo4jMVPConfig":
        """Load from environment variables."""
        # NEO4J_VECTOR_DIM = chunk vector dimensions (voyage-4-large = 1024d).
        # NOTE: NEO4J_EMBEDDING_DIM was removed as fallback to avoid conflict with
        # graph_neo4j.py which uses it for KG embeddings (TransE/RotatE, 128d).
        dim_raw = os.getenv("NEO4J_VECTOR_DIM") or "1024"
        try:
            dim = int(dim_raw)
        except (TypeError, ValueError):
            dim = 1024
        uri = _infer_neo4j_uri()
        default_database = "neo4j" if uri.startswith(("neo4j+s://", "neo4j+ssc://")) else "iudex"
        liveness_raw = _env_first("NEO4J_LIVENESS_CHECK_TIMEOUT")
        try:
            liveness_timeout = float(liveness_raw) if liveness_raw is not None else None
        except (TypeError, ValueError):
            liveness_timeout = None
        return cls(
            uri=uri,
            user=_env_first("NEO4J_USER", "NEO4J_USERNAME") or "neo4j",
            password=_env_first("NEO4J_PASSWORD", "NEO4J_PASS") or "password",
            database=_env_first("NEO4J_DATABASE") or default_database,
            max_connection_pool_size=int(os.getenv("NEO4J_MAX_POOL_SIZE", "50")),
            connection_timeout=int(os.getenv("NEO4J_CONNECTION_TIMEOUT", "30")),
            liveness_check_timeout=liveness_timeout,
            max_hops=int(os.getenv("NEO4J_MAX_HOPS", "2")),
            max_chunks_per_query=int(os.getenv("NEO4J_MAX_CHUNKS", "50")),
            batch_size=int(os.getenv("NEO4J_BATCH_SIZE", "200")),
            create_indexes=_env_bool("NEO4J_CREATE_INDEXES", True),
            graph_hybrid_mode=_env_bool("RAG_GRAPH_HYBRID_MODE", False),
            graph_hybrid_auto_schema=_env_bool("RAG_GRAPH_HYBRID_AUTO_SCHEMA", True),
            graph_hybrid_migrate_on_startup=_env_bool("RAG_GRAPH_HYBRID_MIGRATE_ON_STARTUP", False),
            enable_fulltext_indexes=_env_bool("NEO4J_FULLTEXT_ENABLED", False),
            enable_vector_index=_env_bool("NEO4J_VECTOR_INDEX_ENABLED", False),
            vector_dimensions=dim,
            vector_similarity=os.getenv("NEO4J_VECTOR_SIMILARITY", "cosine"),
            vector_property=os.getenv("NEO4J_VECTOR_PROPERTY", "embedding"),
            max_facts_per_chunk=int(os.getenv("NEO4J_MAX_FACTS_PER_CHUNK", "3")),
        )


# =============================================================================
# ENTITY TYPES (Legal Domain)
# =============================================================================


class EntityType(str, Enum):
    """Entity types extracted from legal documents."""
    ARTIGO = "artigo"      # Art. 5, § 1º, inciso II
    LEI = "lei"            # Lei 8.666/93
    SUMULA = "sumula"      # Súmula 331 TST
    DECISAO = "decisao"    # REsp, RE, ADI, ADPF, HC, MS...
    TESE = "tese"          # Tese 390
    PROCESSO = "processo"  # Número CNJ
    TRIBUNAL = "tribunal"  # STF, STJ, TRF
    TEMA = "tema"          # Tema 1234 STF
    PARTE = "parte"        # Nome de parte
    OAB = "oab"            # Número OAB
    # Factual entity types
    CPF = "cpf"                        # CPF (XXX.XXX.XXX-XX)
    CNPJ = "cnpj"                      # CNPJ (XX.XXX.XXX/XXXX-XX)
    DATA_JURIDICA = "data_juridica"    # Datas (DD/MM/YYYY)
    VALOR_MONETARIO = "valor_monetario"  # R$ X.XXX,XX


class Scope(str, Enum):
    """Access scope for documents."""
    GLOBAL = "global"
    PRIVATE = "private"
    GROUP = "group"
    LOCAL = "local"


# =============================================================================
# FACTUAL VALIDATORS
# =============================================================================


def _validate_cpf(cpf: str) -> bool:
    """Validate CPF check digits (algoritmo Receita Federal)."""
    digits = re.sub(r"\D", "", cpf)
    if len(digits) != 11 or digits == digits[0] * 11:
        return False
    for i in (9, 10):
        val = sum(int(digits[j]) * ((i + 1) - j) for j in range(i))
        check = (val * 10 % 11) % 10
        if int(digits[i]) != check:
            return False
    return True


def _validate_cnpj(cnpj: str) -> bool:
    """Validate CNPJ check digits."""
    digits = re.sub(r"\D", "", cnpj)
    if len(digits) != 14 or digits == digits[0] * 14:
        return False
    weights1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    weights2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    for w, i in [(weights1, 12), (weights2, 13)]:
        val = sum(int(digits[j]) * w[j] for j in range(i))
        check = 11 - (val % 11)
        check = 0 if check >= 10 else check
        if int(digits[i]) != check:
            return False
    return True


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
        EntityType.DECISAO: re.compile(
            r"\b(REsp|RE|ADI|ADPF|AgRg|RMS|HC|MS)\s*(?:n?[oº]\s*)?([\d./-]{3,})",
            re.IGNORECASE,
        ),
        EntityType.TESE: re.compile(
            r"\bTese\s+(?:n?[oº]\s*)?(\d{1,6})\b",
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
        # Factual patterns (used when include_factual=True)
        EntityType.CPF: re.compile(
            r"\b(\d{3}\.\d{3}\.\d{3}-\d{2})\b",
        ),
        EntityType.CNPJ: re.compile(
            r"\b(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})\b",
        ),
        EntityType.DATA_JURIDICA: re.compile(
            r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})\b",
        ),
        EntityType.VALOR_MONETARIO: re.compile(
            r"R\$\s*([\d.]+,\d{2})\b",
        ),
    }

    @classmethod
    def extract(cls, text: str, *, include_factual: bool = False) -> List[Dict[str, Any]]:
        """
        Extract all entities from text.

        Args:
            text: Input text to extract entities from.
            include_factual: If True, also extract factual entities (CPF, CNPJ, dates, values).

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

        # Decisão
        for match in cls.PATTERNS[EntityType.DECISAO].finditer(text):
            tipo = (match.group(1) or "").upper()
            numero_raw = match.group(2) or ""
            numero = re.sub(r"[^\d]", "", numero_raw) or numero_raw.replace("/", "_").replace("-", "_")
            entity_id = f"decisao_{tipo.lower()}_{numero}"
            if entity_id not in seen:
                seen.add(entity_id)
                entities.append({
                    "entity_type": EntityType.DECISAO.value,
                    "entity_id": entity_id,
                    "name": f"{tipo} {numero_raw}",
                    "normalized": f"decisao:{tipo}:{numero}",
                    "metadata": {"tipo": tipo, "numero": numero_raw},
                })

        # Tese
        for match in cls.PATTERNS[EntityType.TESE].finditer(text):
            numero = match.group(1)
            entity_id = f"tese_{numero}"
            if entity_id not in seen:
                seen.add(entity_id)
                entities.append({
                    "entity_type": EntityType.TESE.value,
                    "entity_id": entity_id,
                    "name": f"Tese {numero}",
                    "normalized": f"tese:{numero}",
                    "metadata": {"numero": numero},
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

        if include_factual:
            cls._extract_factual(text, entities, seen)

        return entities

    @classmethod
    def _extract_factual(
        cls, text: str, entities: List[Dict[str, Any]], seen: Set[str],
    ) -> None:
        """Extract factual entities (CPF, CNPJ, dates, monetary values)."""
        # CPF (with check-digit validation)
        for match in cls.PATTERNS[EntityType.CPF].finditer(text):
            cpf = match.group(1)
            if not _validate_cpf(cpf):
                continue
            digits = re.sub(r"\D", "", cpf)
            entity_id = f"cpf_{digits}"
            if entity_id not in seen:
                seen.add(entity_id)
                entities.append({
                    "entity_type": EntityType.CPF.value,
                    "entity_id": entity_id,
                    "name": cpf,
                    "normalized": f"cpf:{digits}",
                    "metadata": {"cpf": cpf},
                })

        # CNPJ (with check-digit validation)
        for match in cls.PATTERNS[EntityType.CNPJ].finditer(text):
            cnpj = match.group(1)
            if not _validate_cnpj(cnpj):
                continue
            digits = re.sub(r"\D", "", cnpj)
            entity_id = f"cnpj_{digits}"
            if entity_id not in seen:
                seen.add(entity_id)
                entities.append({
                    "entity_type": EntityType.CNPJ.value,
                    "entity_id": entity_id,
                    "name": cnpj,
                    "normalized": f"cnpj:{digits}",
                    "metadata": {"cnpj": cnpj},
                })

        # Datas (DD/MM/YYYY)
        for match in cls.PATTERNS[EntityType.DATA_JURIDICA].finditer(text):
            dia = match.group(1).zfill(2)
            mes = match.group(2).zfill(2)
            ano = match.group(3)
            # Basic validation
            if not (1 <= int(dia) <= 31 and 1 <= int(mes) <= 12 and 1900 <= int(ano) <= 2100):
                continue
            date_str = f"{dia}/{mes}/{ano}"
            entity_id = f"data_{ano}{mes}{dia}"
            if entity_id not in seen:
                seen.add(entity_id)
                entities.append({
                    "entity_type": EntityType.DATA_JURIDICA.value,
                    "entity_id": entity_id,
                    "name": date_str,
                    "normalized": f"data:{ano}-{mes}-{dia}",
                    "metadata": {"dia": dia, "mes": mes, "ano": ano},
                })

        # Valores monetários (R$ X.XXX,XX)
        for match in cls.PATTERNS[EntityType.VALOR_MONETARIO].finditer(text):
            valor_raw = match.group(1)
            # Normalize: remove dots, replace comma with dot for numeric form
            valor_norm = valor_raw.replace(".", "").replace(",", ".")
            entity_id = f"valor_{valor_norm}"
            if entity_id not in seen:
                seen.add(entity_id)
                entities.append({
                    "entity_type": EntityType.VALOR_MONETARIO.value,
                    "entity_id": entity_id,
                    "name": f"R$ {valor_raw}",
                    "normalized": f"valor:{valor_norm}",
                    "metadata": {"valor": valor_raw, "valor_numerico": valor_norm},
                })

    # Patterns for detecting cross-references (remissões) between legal provisions
    REMISSION_PATTERNS = [
        # Combinado com
        re.compile(
            r"(?:c/c|combinado\s+com|em\s+conjunto\s+com|juntamente\s+com)\s+"
            r"(?:o\s+)?(?:art\.?|artigo)\s*(\d+)",
            re.IGNORECASE,
        ),
        # Nos termos de / Conforme / Segundo
        re.compile(
            r"(?:nos\s+termos\s+d[oa]|conforme|segundo|de\s+acordo\s+com)\s+"
            r"(?:o\s+)?(?:art\.?|artigo)\s*(\d+)",
            re.IGNORECASE,
        ),
        # Aplica-se / Incide
        re.compile(
            r"(?:aplica-?se|incide|observ[ae]r?)\s+(?:o\s+)?(?:disposto\s+n[oa]\s+)?"
            r"(?:art\.?|artigo)\s*(\d+)",
            re.IGNORECASE,
        ),
        # Remete / Refere-se
        re.compile(
            r"(?:remete|refere-?se|alude)\s+(?:a[oa]?\s+)?(?:art\.?|artigo)\s*(\d+)",
            re.IGNORECASE,
        ),
        # Por força do / Em razão do
        re.compile(
            r"(?:por\s+força\s+d[oa]|em\s+razão\s+d[oa]|com\s+base\s+n[oa])\s+"
            r"(?:art\.?|artigo)\s*(\d+)",
            re.IGNORECASE,
        ),
    ]

    @classmethod
    def extract_remissions(cls, text: str) -> List[Dict[str, Any]]:
        """
        Extract cross-references (remissões) between legal provisions.

        Identifies patterns like:
        - "c/c art. 927" (combinado com)
        - "nos termos do art. 186"
        - "aplica-se o art. 932"
        - "remete ao art. 933"

        Returns:
            List of remission dicts with: source_context, target_article,
            remission_type, position
        """
        remissions: List[Dict[str, Any]] = []

        # First, extract all entities to identify potential sources
        entities = cls.extract(text)
        entity_positions = []

        # Find positions of all articles in text
        for match in cls.PATTERNS[EntityType.ARTIGO].finditer(text):
            artigo = match.group(1)
            entity_positions.append({
                "artigo": artigo,
                "start": match.start(),
                "end": match.end(),
                "match": match.group(0),
            })

        # Find remission patterns
        remission_types = [
            "combinado_com",
            "nos_termos_de",
            "aplica_se",
            "remete_a",
            "por_forca_de",
        ]

        for pattern, rem_type in zip(cls.REMISSION_PATTERNS, remission_types):
            for match in pattern.finditer(text):
                target_article = match.group(1)
                position = match.start()

                # Find the nearest preceding article as potential source
                source_article = None
                min_distance = float("inf")
                for ep in entity_positions:
                    if ep["end"] < position:
                        distance = position - ep["end"]
                        if distance < min_distance and distance < 200:  # Max 200 chars
                            min_distance = distance
                            source_article = ep["artigo"]

                remissions.append({
                    "source_article": source_article,
                    "target_article": target_article,
                    "remission_type": rem_type,
                    "context": text[max(0, position - 50):position + len(match.group(0)) + 50].strip(),
                    "position": position,
                })

        # Also detect implicit remissions (articles mentioned in sequence)
        # Pattern: "arts. X e Y" or "arts. X, Y e Z"
        sequence_pattern = re.compile(
            r"(?:arts?\.?|artigos?)\s*(\d+)\s*(?:,\s*(\d+))*\s*(?:e|,)\s*(\d+)",
            re.IGNORECASE,
        )
        for match in sequence_pattern.finditer(text):
            articles = [g for g in match.groups() if g]
            if len(articles) >= 2:
                # Create remissions between sequential articles
                for i in range(len(articles) - 1):
                    remissions.append({
                        "source_article": articles[i],
                        "target_article": articles[i + 1],
                        "remission_type": "sequencia",
                        "context": match.group(0),
                        "position": match.start(),
                    })

        return remissions

    @classmethod
    def extract_with_remissions(cls, text: str) -> Dict[str, Any]:
        """
        Extract both entities and remissions from text.

        Returns:
            Dict with 'entities' and 'remissions' lists
        """
        return {
            "entities": cls.extract(text),
            "remissions": cls.extract_remissions(text),
        }

    # =========================================================================
    # COMPOUND CITATION EXTRACTION
    # =========================================================================

    # Mapa de códigos brasileiros e suas formas canônicas
    CODE_MAP: Dict[str, str] = {
        "cf": "CF",
        "constituição federal": "CF",
        "constituição": "CF",
        "cpc": "CPC",
        "código de processo civil": "CPC",
        "cód. proc. civil": "CPC",
        "cpp": "CPP",
        "código de processo penal": "CPP",
        "cc": "CC",
        "código civil": "CC",
        "cód. civil": "CC",
        "cp": "CP",
        "código penal": "CP",
        "cód. penal": "CP",
        "clt": "CLT",
        "consolidação das leis do trabalho": "CLT",
        "cdc": "CDC",
        "código de defesa do consumidor": "CDC",
        "cód. defesa consumidor": "CDC",
        "ctb": "CTB",
        "código de trânsito brasileiro": "CTB",
        "ctn": "CTN",
        "código tributário nacional": "CTN",
        "eca": "ECA",
        "estatuto da criança e do adolescente": "ECA",
        "lep": "LEP",
        "lei de execução penal": "LEP",
        "lindb": "LINDB",
        "lei de introdução às normas do direito brasileiro": "LINDB",
    }

    # Regex para numerais romanos
    _ROMAN_RE = re.compile(r"^[IVXLCDM]+$")

    # Regex composta que captura citações hierárquicas completas.
    # Grupo 1: Lei/Decreto/MP/LC etc com número e ano (opcional)
    # Grupo 2: Código abreviado (CPC, CLT, CF etc) (opcional)
    # O padrão continua capturando Art, §, inciso, alínea em sequência.
    COMPOUND_PATTERN = re.compile(
        r"(?:"
        # --- Opção A: Lei/Decreto/MP/LC + número ---
        r"(?P<law_type>Lei|Decreto|MP|LC|Lei Complementar|Decreto-Lei|Portaria|Resolução)"
        r"\s*n?[oº]?\s*(?P<law_num>[\d.]+)(?:/(?P<law_year>\d{2,4}))?"
        # --- Opção B: Código abreviado ---
        r"|(?P<code>CF|CPC|CPP|CC|CP|CLT|CDC|CTB|CTN|ECA|LEP|LINDB"
        r"|Constituição\s+Federal|Código\s+(?:de\s+)?(?:Processo\s+)?(?:Civil|Penal|Defesa\s+do\s+Consumidor)"
        r"|Consolidação\s+das\s+Leis\s+do\s+Trabalho)"
        r")"
        # --- Separador opcional ---
        r"(?:\s*,\s*|\s+)"
        # --- Artigo (obrigatório para compound) ---
        r"(?:Art\.?|Artigo)\s*(?P<art_num>\d+[\d.]*)[oº°]?"
        # --- Parágrafo (opcional) ---
        r"(?:"
        r"\s*,?\s*(?:"
        r"(?P<paragrafo>§§?\s*\d+[oº°]?)"
        r"|(?P<paragrafo_unico>par[áa]grafo\s+[úu]nico|caput|p\.?\s*[úu]\.?)"
        r")"
        r")?"
        # --- Inciso (opcional) ---
        r"(?:"
        r"\s*,?\s*(?:inciso|inc\.?)\s*(?P<inciso>[IVXLCDM]+|\d+)"
        r")?"
        # --- Alínea (opcional) ---
        r"(?:"
        r"\s*,?\s*(?:al[íi]nea|al\.?)\s*['\"]?(?P<alinea>[a-z])['\"]?"
        r")?",
        re.IGNORECASE,
    )

    # Padrão alternativo: Art. X ... da Lei/do Código (referência invertida)
    COMPOUND_PATTERN_INVERTED = re.compile(
        r"(?:Art\.?|Artigo)\s*(?P<art_num>\d+[\d.]*)[oº°]?"
        # --- Parágrafo (opcional) ---
        r"(?:"
        r"\s*,?\s*(?:"
        r"(?P<paragrafo>§§?\s*\d+[oº°]?)"
        r"|(?P<paragrafo_unico>par[áa]grafo\s+[úu]nico|caput|p\.?\s*[úu]\.?)"
        r")"
        r")?"
        # --- Inciso (opcional) ---
        r"(?:"
        r"\s*,?\s*(?:inciso|inc\.?)\s*(?P<inciso>[IVXLCDM]+|\d+)"
        r")?"
        # --- Alínea (opcional) ---
        r"(?:"
        r"\s*,?\s*(?:al[íi]nea|al\.?)\s*['\"]?(?P<alinea>[a-z])['\"]?"
        r")?"
        # --- "da/do" + Lei/Código ---
        r"\s*,?\s*(?:da|do|d[ao]s?)\s+"
        r"(?:"
        r"(?P<law_type>Lei|Decreto|MP|LC|Lei Complementar|Decreto-Lei)"
        r"\s*n?[oº]?\s*(?P<law_num>[\d.]+)(?:/(?P<law_year>\d{2,4}))?"
        r"|(?P<code>CF|CPC|CPP|CC|CP|CLT|CDC|CTB|CTN|ECA|LEP|LINDB"
        r"|Constituição\s+Federal|Código\s+(?:de\s+)?(?:Processo\s+)?(?:Civil|Penal|Defesa\s+do\s+Consumidor)"
        r"|Consolidação\s+das\s+Leis\s+do\s+Trabalho)"
        r")",
        re.IGNORECASE,
    )

    @classmethod
    def _normalize_roman(cls, value: str) -> str:
        """Converte numeral romano para minúsculas para normalização."""
        if value and cls._ROMAN_RE.match(value.upper()):
            return value.lower()
        return value.lower()

    @classmethod
    def _normalize_paragraph(cls, para: Optional[str], para_unico: Optional[str]) -> Optional[str]:
        """Normaliza o campo parágrafo para exibição."""
        if para_unico:
            pu = para_unico.strip().lower()
            if "caput" in pu:
                return "caput"
            return "parágrafo único"
        if para:
            # Extrai o número: "§ 1º" -> "§ 1º"
            return para.strip()
        return None

    @classmethod
    def _normalize_paragraph_id(cls, para: Optional[str], para_unico: Optional[str]) -> str:
        """Normaliza o parágrafo para o ID: § 1º -> p1, parágrafo único -> pu, caput -> caput."""
        if para_unico:
            pu = para_unico.strip().lower()
            if "caput" in pu:
                return "caput"
            return "pu"
        if para:
            nums = re.findall(r"\d+", para)
            if nums:
                return f"p{nums[0]}"
        return ""

    @classmethod
    def _normalize_code(cls, raw_code: str) -> str:
        """Normaliza nome de código para sigla canônica."""
        key = raw_code.strip().lower()
        return cls.CODE_MAP.get(key, raw_code.strip().upper())

    @classmethod
    def _build_normalized_id(
        cls,
        law: Optional[str],
        code: Optional[str],
        article: Optional[str],
        para: Optional[str],
        para_unico: Optional[str],
        inciso: Optional[str],
        alinea: Optional[str],
    ) -> str:
        """Constrói o normalized_id a partir dos componentes."""
        parts: List[str] = []

        if code:
            parts.append(cls._normalize_code(code).lower())
        elif law:
            # "Lei 8.666/1993" -> "lei_8666_1993"
            # Primeiro remove pontos de numeros (8.666 -> 8666)
            law_clean = law.strip().lower()
            law_clean = re.sub(r"(\d)\.(\d)", r"\1\2", law_clean)
            law_clean = re.sub(r"[/\s]+", "_", law_clean)
            law_clean = re.sub(r"_+", "_", law_clean).strip("_")
            parts.append(law_clean)

        if article:
            art_num = re.sub(r"[^0-9.]", "", article)
            art_num = art_num.replace(".", "")
            parts.append(f"art_{art_num}")

        p_id = cls._normalize_paragraph_id(para, para_unico)
        if p_id:
            parts.append(p_id)

        if inciso:
            parts.append(f"inc_{cls._normalize_roman(inciso)}")

        if alinea:
            parts.append(f"al_{alinea.lower()}")

        return "_".join(parts)

    @classmethod
    def _build_compound_from_match(cls, match: re.Match, text: str) -> Optional[CompoundCitation]:
        """Constrói CompoundCitation a partir de um match de regex."""
        groups = match.groupdict()

        art_num = groups.get("art_num")
        if not art_num:
            return None

        law_type = groups.get("law_type")
        law_num = groups.get("law_num")
        law_year = groups.get("law_year")
        raw_code = groups.get("code")
        para = groups.get("paragrafo")
        para_unico = groups.get("paragrafo_unico")
        inciso = groups.get("inciso")
        alinea = groups.get("alinea")

        # Montar campo law
        law: Optional[str] = None
        if law_type and law_num:
            law = f"{law_type} {law_num}"
            if law_year:
                # Normaliza ano de 2 dígitos
                if len(law_year) == 2:
                    law_year = f"19{law_year}" if int(law_year) > 50 else f"20{law_year}"
                law += f"/{law_year}"

        code: Optional[str] = None
        if raw_code:
            code = cls._normalize_code(raw_code)

        article = f"Art. {art_num}"
        paragraph = cls._normalize_paragraph(para, para_unico)
        inciso_str = f"inciso {inciso.upper()}" if inciso else None
        alinea_str = f"alínea '{alinea}'" if alinea else None

        normalized_id = cls._build_normalized_id(
            law=law, code=code, article=art_num,
            para=para, para_unico=para_unico,
            inciso=inciso, alinea=alinea,
        )

        full_text = match.group(0).strip()

        return CompoundCitation(
            full_text=full_text,
            law=law,
            code=code,
            article=article,
            paragraph=paragraph,
            inciso=inciso_str,
            alinea=alinea_str,
            normalized_id=normalized_id,
        )

    @classmethod
    def extract_compound_citations(cls, text: str) -> List[CompoundCitation]:
        """
        Extrai citações jurídicas compostas do texto.

        Captura referências hierárquicas completas como:
        - "Lei 8.666/1993, Art. 23, § 1º, inciso II"
        - "Art. 5º, caput, da Constituição Federal"
        - "CLT, Art. 477, § 8º"
        - "CPC, Art. 1.015, parágrafo único"

        Retorna lista de CompoundCitation com todos os componentes estruturados.
        Mantém compatibilidade com extract() simples — este método é complementar.
        """
        if not text or not text.strip():
            return []

        citations: List[CompoundCitation] = []
        seen_ids: Set[str] = set()

        # Padrão direto: Lei/Código + Art + §/inciso/alínea
        for match in cls.COMPOUND_PATTERN.finditer(text):
            citation = cls._build_compound_from_match(match, text)
            if citation and citation.normalized_id not in seen_ids:
                seen_ids.add(citation.normalized_id)
                citations.append(citation)

        # Padrão invertido: Art + §/inciso/alínea + da/do Lei/Código
        for match in cls.COMPOUND_PATTERN_INVERTED.finditer(text):
            citation = cls._build_compound_from_match(match, text)
            if citation and citation.normalized_id not in seen_ids:
                seen_ids.add(citation.normalized_id)
                citations.append(citation)

        return citations

    @classmethod
    def extract_all(cls, text: str, *, include_factual: bool = False) -> Dict[str, Any]:
        """
        Extrai entidades simples, citações compostas e remissões do texto.

        Método unificado que retorna todos os tipos de extração.

        Args:
            text: Input text.
            include_factual: If True, also extract CPF, CNPJ, dates, values.

        Returns:
            Dict com 'entities', 'compound_citations' e 'remissions'.
        """
        return {
            "entities": cls.extract(text, include_factual=include_factual),
            "compound_citations": cls.extract_compound_citations(text),
            "remissions": cls.extract_remissions(text),
        }


# =============================================================================
# FACT EXTRACTOR (Deterministic, no LLM)
# =============================================================================


class FactExtractor:
    """
    Extract "fatos" from a chunk of text (deterministic).

    Goal: generate a small set of fact-like snippets to connect local RAG
    narrative to Normas/Doutrina entities in Neo4j, without calling an LLM.
    """

    _SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")
    _WS = re.compile(r"\s+")
    _DATE = re.compile(
        r"\b(\d{1,2}/\d{1,2}/\d{2,4}|\d{1,2}\s+de\s+[a-zçãéíóú]+(?:\s+de)?\s+\d{4})\b",
        re.IGNORECASE,
    )
    _MONEY = re.compile(r"\bR\$\s*\d+[\d.]*,\d{2}\b")
    _VERB_HINT = re.compile(
        r"\b(celebr|assin|firm|contrat|pag|inadimpl|rescind|notific|entreg|ocorr|houve|aleg|afirm|requereu|ajuiz)\w*\b",
        re.IGNORECASE,
    )
    _LEGAL_CITATION = re.compile(
        r"\b(art\.?|lei\s+n|s[úu]mula|tema\s+\d+|stf|stj|tst|trf|tj[a-z]{2})\b",
        re.IGNORECASE,
    )

    @classmethod
    def extract(
        cls,
        text: str,
        max_facts: int = 3,
        min_chars: int = 40,
        max_chars: int = 320,
    ) -> List[str]:
        raw = (text or "").strip()
        if not raw:
            return []

        raw = cls._WS.sub(" ", raw)
        sentences = [s.strip() for s in cls._SENT_SPLIT.split(raw) if s and s.strip()]
        if not sentences:
            sentences = [raw]

        scored: List[Tuple[int, str]] = []
        seen: Set[str] = set()

        for s in sentences:
            s_clean = s.strip()
            if len(s_clean) < min_chars:
                continue
            s_clean = s_clean[:max_chars].strip()

            key = s_clean.lower()
            if key in seen:
                continue
            seen.add(key)

            score = 0
            if cls._DATE.search(s_clean):
                score += 3
            if cls._MONEY.search(s_clean):
                score += 2
            if cls._VERB_HINT.search(s_clean):
                score += 2

            # Penalize sentences that are mostly legal citations.
            if cls._LEGAL_CITATION.search(s_clean):
                score -= 2

            scored.append((score, s_clean))

        if not scored:
            preview = raw[:max_chars].strip()
            return [preview] if preview else []

        scored.sort(key=lambda t: (t[0], len(t[1])), reverse=True)
        return [s for _, s in scored[: max(1, int(max_facts or 1))]]


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

    CREATE CONSTRAINT fact_id IF NOT EXISTS
    FOR (f:Fact) REQUIRE f.fact_id IS UNIQUE;

    CREATE CONSTRAINT arg_claim_id IF NOT EXISTS
    FOR (c:Claim) REQUIRE c.claim_id IS UNIQUE;

    CREATE CONSTRAINT arg_evidence_id IF NOT EXISTS
    FOR (ev:Evidence) REQUIRE ev.evidence_id IS UNIQUE;

    CREATE CONSTRAINT arg_actor_id IF NOT EXISTS
    FOR (a:Actor) REQUIRE a.actor_id IS UNIQUE;

    CREATE CONSTRAINT arg_issue_id IF NOT EXISTS
    FOR (i:Issue) REQUIRE i.issue_id IS UNIQUE;

    CREATE CONSTRAINT tenant_metric_key IF NOT EXISTS
    FOR (m:TenantEntityMetric) REQUIRE (m.tenant_id, m.entity_id) IS UNIQUE;
    """

    CREATE_INDEXES = """
    CREATE INDEX doc_tenant IF NOT EXISTS FOR (d:Document) ON (d.tenant_id);
    CREATE INDEX doc_scope IF NOT EXISTS FOR (d:Document) ON (d.scope);
    CREATE INDEX doc_case IF NOT EXISTS FOR (d:Document) ON (d.case_id);
    CREATE INDEX doc_doc_id IF NOT EXISTS FOR (d:Document) ON (d.doc_id);
    CREATE INDEX chunk_doc IF NOT EXISTS FOR (c:Chunk) ON (c.doc_hash);
    CREATE INDEX entity_type IF NOT EXISTS FOR (e:Entity) ON (e.entity_type);
    CREATE INDEX entity_normalized IF NOT EXISTS FOR (e:Entity) ON (e.normalized);
    CREATE INDEX fact_doc IF NOT EXISTS FOR (f:Fact) ON (f.doc_hash);
    CREATE INDEX fact_doc_id IF NOT EXISTS FOR (f:Fact) ON (f.doc_id);
    CREATE INDEX fact_tenant IF NOT EXISTS FOR (f:Fact) ON (f.tenant_id);
    CREATE INDEX fact_case IF NOT EXISTS FOR (f:Fact) ON (f.case_id);
    CREATE INDEX arg_claim_tenant IF NOT EXISTS FOR (c:Claim) ON (c.tenant_id);
    CREATE INDEX arg_claim_case IF NOT EXISTS FOR (c:Claim) ON (c.case_id);
    CREATE INDEX arg_claim_type IF NOT EXISTS FOR (c:Claim) ON (c.claim_type);
    CREATE INDEX arg_evidence_tenant IF NOT EXISTS FOR (ev:Evidence) ON (ev.tenant_id);
    CREATE INDEX arg_evidence_doc IF NOT EXISTS FOR (ev:Evidence) ON (ev.doc_id);
    CREATE INDEX arg_actor_tenant IF NOT EXISTS FOR (a:Actor) ON (a.tenant_id);
    CREATE INDEX arg_issue_case IF NOT EXISTS FOR (i:Issue) ON (i.case_id);
    CREATE INDEX tenant_metric_tenant_score IF NOT EXISTS FOR (m:TenantEntityMetric) ON (m.tenant_id, m.pagerank_score);

    # CogRAG meta-cognition / memory (PLANO_COGRAG.md)
    CREATE INDEX tema_nome IF NOT EXISTS FOR (t:Tema) ON (t.nome);
    CREATE INDEX tema_tenant IF NOT EXISTS FOR (t:Tema) ON (t.tenant_id);
    CREATE INDEX consulta_id IF NOT EXISTS FOR (c:Consulta) ON (c.id);
    CREATE INDEX consulta_tenant IF NOT EXISTS FOR (c:Consulta) ON (c.tenant_id);
    CREATE INDEX subpergunta_consulta IF NOT EXISTS FOR (s:SubPergunta) ON (s.consulta_id);
    CREATE INDEX correcao_usuario IF NOT EXISTS FOR (c:Correcao) ON (c.usuario_id);
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
        d.doc_id = $doc_id,
        d.group_ids = $group_ids,
        d.title = $title,
        d.source_type = $source_type,
        d.sigilo = $sigilo,
        d.allowed_users = $allowed_users,
        d.created_at = datetime()
    ON MATCH SET
        d.doc_id = coalesce(d.doc_id, $doc_id),
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

    MERGE_FACT = """
    MERGE (f:Fact {fact_id: $fact_id})
    ON CREATE SET
        f.text = $text,
        f.text_preview = $text_preview,
        f.doc_hash = $doc_hash,
        f.doc_id = $doc_id,
        f.tenant_id = $tenant_id,
        f.scope = $scope,
        f.case_id = $case_id,
        f.metadata = $metadata,
        f.created_at = datetime()
    ON MATCH SET
        f.updated_at = datetime()
    RETURN f
    """

    LINK_CHUNK_FACT = """
    MATCH (c:Chunk {chunk_uid: $chunk_uid})
    MATCH (f:Fact {fact_id: $fact_id})
    MERGE (c)-[:ASSERTS]->(f)
    """

    LINK_FACT_ENTITY = """
    MATCH (f:Fact {fact_id: $fact_id})
    MATCH (e:Entity {entity_id: $entity_id})
    MERGE (f)-[:REFERS_TO]->(e)
    """

    # Batched ingest (UNWIND) to reduce round-trips on large documents
    MERGE_CHUNKS_BATCH = """
    UNWIND $rows AS row
    MERGE (c:Chunk {chunk_uid: row.chunk_uid})
    ON CREATE SET
        c.doc_hash = row.doc_hash,
        c.chunk_index = row.chunk_index,
        c.text_preview = row.text_preview,
        c.token_count = row.token_count,
        c.created_at = datetime()
    RETURN count(c) AS merged_chunks
    """

    LINK_DOC_CHUNKS_BATCH = """
    MATCH (d:Document {doc_hash: $doc_hash})
    UNWIND $rows AS row
    MATCH (c:Chunk {chunk_uid: row.chunk_uid})
    MERGE (d)-[:HAS_CHUNK]->(c)
    RETURN count(*) AS linked_doc_chunks
    """

    LINK_CHUNK_NEXT_BATCH = """
    UNWIND $rows AS row
    MATCH (c1:Chunk {chunk_uid: row.prev_chunk_uid})
    MATCH (c2:Chunk {chunk_uid: row.chunk_uid})
    MERGE (c1)-[:NEXT]->(c2)
    RETURN count(*) AS linked_next
    """

    LINK_CHUNK_ENTITIES_BATCH = """
    UNWIND $rows AS row
    MATCH (c:Chunk {chunk_uid: row.chunk_uid})
    MATCH (e:Entity {entity_id: row.entity_id})
    MERGE (c)-[:MENTIONS]->(e)
    RETURN count(*) AS linked_mentions
    """

    MERGE_FACTS_BATCH = """
    UNWIND $rows AS row
    MERGE (f:Fact {fact_id: row.fact_id})
    ON CREATE SET
        f.text = row.text,
        f.text_preview = row.text_preview,
        f.doc_hash = row.doc_hash,
        f.doc_id = row.doc_id,
        f.tenant_id = row.tenant_id,
        f.scope = row.scope,
        f.case_id = row.case_id,
        f.metadata = row.metadata,
        f.created_at = datetime()
    ON MATCH SET
        f.updated_at = datetime()
    RETURN count(f) AS merged_facts
    """

    LINK_CHUNK_FACTS_BATCH = """
    UNWIND $rows AS row
    MATCH (c:Chunk {chunk_uid: row.chunk_uid})
    MATCH (f:Fact {fact_id: row.fact_id})
    MERGE (c)-[:ASSERTS]->(f)
    RETURN count(*) AS linked_asserts
    """

    LINK_FACT_ENTITIES_BATCH = """
    UNWIND $rows AS row
    MATCH (f:Fact {fact_id: row.fact_id})
    MATCH (e:Entity {entity_id: row.entity_id})
    MERGE (f)-[:REFERS_TO]->(e)
    RETURN count(*) AS linked_fact_refs
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

    # NOTE: These templates intentionally avoid Python `.format()` because Cypher
    # uses `{ ... }` map literals and projections extensively.
    _WINDOW_TOKEN = "__WINDOW__"
    _MAX_HOPS_TOKEN = "__MAX_HOPS__"

    EXPAND_NEIGHBORS = """
    MATCH (c:Chunk {chunk_uid: $chunk_uid})
    OPTIONAL MATCH (c)<-[:NEXT*1..__WINDOW__]-(prev:Chunk)
    OPTIONAL MATCH (c)-[:NEXT*1..__WINDOW__]->(next:Chunk)
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

    # Entity-only traversal: does NOT cross into Argument nodes (Claim/Evidence/Actor/Issue).
    # Use this for factual/entity queries where argument contamination is undesirable.
    FIND_PATHS = """
    // Find paths from query entities to document chunks (entity-only mode)
    MATCH (e:Entity)
    WHERE e.entity_id IN $entity_ids

    // Traverse only entity/chunk relationships — no argument edges
    MATCH path = (e)-[:RELATED_TO|MENTIONS|ASSERTS|REFERS_TO*1..__MAX_HOPS__]-(target)
    WHERE (target:Chunk OR target:Entity)
      AND NOT (target:Claim OR target:Evidence OR target:Actor OR target:Issue)
      AND (
            $include_candidates = true
            OR all(r IN relationships(path) WHERE coalesce(r.layer, 'verified') <> 'candidate')
          )

    // Security trimming: all Chunk nodes in the path must be visible to the caller.
    AND all(n IN nodes(path) WHERE NOT (n:Chunk) OR exists {
        MATCH (d:Document)-[:HAS_CHUNK]->(n)
        WHERE d.scope IN $allowed_scopes
          AND (
                d.scope = 'global'
                OR d.tenant_id = $tenant_id
                OR (
                    d.scope = 'group'
                    AND coalesce(size($group_ids), 0) > 0
                    AND any(g IN $group_ids WHERE g IN coalesce(d.group_ids, []))
                )
            )
          AND ($case_id IS NULL OR d.case_id = $case_id)
          AND (
                d.sigilo IS NULL
                OR d.sigilo = false
                OR $user_id IS NULL
                OR $user_id IN coalesce(d.allowed_users, [])
            )
    })

    OPTIONAL MATCH (d:Document)-[:HAS_CHUNK]->(target)
    WHERE target:Chunk

    RETURN
        e.name AS start_entity,
        coalesce(target.name, target.entity_id, target.chunk_uid) AS end_name,
        coalesce(target.entity_id, target.chunk_uid) AS end_id,
        labels(target)[0] AS end_type,
        length(path) AS path_length,
        [n IN nodes(path) | coalesce(n.name, n.chunk_uid)] AS path_names,
        [r IN relationships(path) | type(r)] AS path_relations,
        [n IN nodes(path) | coalesce(n.entity_id, n.chunk_uid, n.doc_hash)] AS path_ids,
        [n IN nodes(path) | {
            labels: labels(n),
            entity_id: n.entity_id,
            chunk_uid: n.chunk_uid,
            doc_hash: n.doc_hash,
            name: n.name,
            entity_type: n.entity_type,
            normalized: n.normalized,
            chunk_index: n.chunk_index,
            text_preview: n.text_preview
        }] AS path_nodes,
        [r IN relationships(path) | {
            type: type(r),
            from_id: coalesce(startNode(r).entity_id, startNode(r).chunk_uid, startNode(r).doc_hash),
            to_id: coalesce(endNode(r).entity_id, endNode(r).chunk_uid, endNode(r).doc_hash),
            properties: properties(r)
        }] AS path_edges,
        d.doc_hash AS doc_hash,
        target.chunk_uid AS chunk_uid
    ORDER BY path_length
    LIMIT $limit
    """

    # Argument-aware traversal: includes Claim/Evidence/Actor/Issue nodes and
    # argument relationships (SUPPORTS, OPPOSES, etc.).
    # Includes security trimming for BOTH Chunk AND Claim/Evidence nodes.
    FIND_PATHS_WITH_ARGUMENTS = """
    // Find paths including argument graph (debate-aware mode)
    MATCH (e:Entity)
    WHERE e.entity_id IN $entity_ids

    // Traverse all relationship types including argument edges
    MATCH path = (e)-[:RELATED_TO|MENTIONS|ASSERTS|REFERS_TO|SUPPORTS|OPPOSES|EVIDENCES|ARGUES|RAISES|CITES|CONTAINS_CLAIM*1..__MAX_HOPS__]-(target)
    WHERE (target:Chunk OR target:Entity OR target:Claim OR target:Evidence)
      AND (
            $include_candidates = true
            OR all(r IN relationships(path) WHERE coalesce(r.layer, 'verified') <> 'candidate')
          )

    // Security trimming for Chunk nodes (document-level access control)
    AND all(n IN nodes(path) WHERE NOT (n:Chunk) OR exists {
        MATCH (d:Document)-[:HAS_CHUNK]->(n)
        WHERE d.scope IN $allowed_scopes
          AND (
                d.scope = 'global'
                OR d.tenant_id = $tenant_id
                OR (
                    d.scope = 'group'
                    AND coalesce(size($group_ids), 0) > 0
                    AND any(g IN $group_ids WHERE g IN coalesce(d.group_ids, []))
                )
            )
          AND ($case_id IS NULL OR d.case_id = $case_id)
          AND (
                d.sigilo IS NULL
                OR d.sigilo = false
                OR $user_id IS NULL
                OR $user_id IN coalesce(d.allowed_users, [])
            )
    })

    // Security trimming for Claim/Evidence nodes (tenant + case isolation)
    AND all(n IN nodes(path) WHERE NOT (n:Claim OR n:Evidence) OR (
        n.tenant_id = $tenant_id
        AND ($case_id IS NULL OR n.case_id IS NULL OR n.case_id = $case_id)
    ))

    OPTIONAL MATCH (d:Document)-[:HAS_CHUNK]->(target)
    WHERE target:Chunk

    RETURN
        e.name AS start_entity,
        coalesce(target.name, target.entity_id, target.chunk_uid) AS end_name,
        coalesce(target.entity_id, target.chunk_uid) AS end_id,
        labels(target)[0] AS end_type,
        length(path) AS path_length,
        [n IN nodes(path) | coalesce(n.name, n.chunk_uid)] AS path_names,
        [r IN relationships(path) | type(r)] AS path_relations,
        [n IN nodes(path) | coalesce(n.entity_id, n.chunk_uid, n.doc_hash)] AS path_ids,
        [n IN nodes(path) | {
            labels: labels(n),
            entity_id: n.entity_id,
            chunk_uid: n.chunk_uid,
            doc_hash: n.doc_hash,
            name: n.name,
            entity_type: n.entity_type,
            normalized: n.normalized,
            chunk_index: n.chunk_index,
            text_preview: n.text_preview
        }] AS path_nodes,
        [r IN relationships(path) | {
            type: type(r),
            from_id: coalesce(startNode(r).entity_id, startNode(r).chunk_uid, startNode(r).doc_hash),
            to_id: coalesce(endNode(r).entity_id, endNode(r).chunk_uid, endNode(r).doc_hash),
            properties: properties(r)
        }] AS path_edges,
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
      AND (
            d.scope = 'global'
            OR d.tenant_id = $tenant_id
            OR (
                d.scope = 'group'
                AND coalesce(size($group_ids), 0) > 0
                AND any(g IN $group_ids WHERE g IN coalesce(d.group_ids, []))
            )
        )
      AND ($case_id IS NULL OR d.case_id = $case_id)
      AND (
            d.sigilo IS NULL
            OR d.sigilo = false
            OR $user_id IS NULL
            OR $user_id IN coalesce(d.allowed_users, [])
        )

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
        self._async_driver = None
        self._driver_lock = threading.Lock()
        self._async_driver_lock: Optional[asyncio.Lock] = None
        self._initialized = False
        self._async_schema_building = False

        logger.info(f"Neo4jMVPService configured for {self.config.uri}")

    # -------------------------------------------------------------------------
    # Connection Management
    # -------------------------------------------------------------------------

    @staticmethod
    def _port_reachable(host: str, port: int, timeout: float = 1.0) -> bool:
        """Quick TCP check to see if host:port is reachable."""
        import socket
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except (OSError, socket.timeout):
            return False

    @property
    def driver(self):
        """Lazy driver initialization."""
        if self._driver is None:
            with self._driver_lock:
                if self._driver is None:
                    # Quick port check before trying the full driver
                    import re as _re
                    _m = _re.search(r'://([^:/]+):?(\d+)?', self.config.uri)
                    _host = _m.group(1) if _m else 'localhost'
                    _port = int(_m.group(2)) if _m and _m.group(2) else 7687
                    if not self._port_reachable(_host, _port, timeout=1.0):
                        hint = ""
                        if _host in {"localhost", "127.0.0.1"}:
                            hint = (
                                " Configure NEO4J_URI/NEO4J_USER/NEO4J_PASSWORD "
                                "(Aura: neo4j+s://<instance>.databases.neo4j.io) "
                                "ou inicie o Neo4j local."
                            )
                        raise ConnectionError(f"Neo4j port {_host}:{_port} not reachable.{hint}")

                    try:
                        from neo4j_rust_ext import GraphDatabase  # type: ignore
                        logger.info("Using neo4j-rust-ext driver")
                    except ImportError:
                        try:
                            from neo4j import GraphDatabase
                        except ImportError:
                            raise ImportError("Neo4j driver required: pip install neo4j")

                    driver_kwargs: Dict[str, Any] = {
                        "max_connection_pool_size": self.config.max_connection_pool_size,
                        "connection_timeout": self.config.connection_timeout,
                        "max_transaction_retry_time": 2,
                    }
                    if self.config.liveness_check_timeout is not None:
                        driver_kwargs["liveness_check_timeout"] = self.config.liveness_check_timeout

                    self._driver = GraphDatabase.driver(
                        self.config.uri,
                        auth=(self.config.user, self.config.password),
                        **driver_kwargs,
                    )
                    logger.info(f"Neo4j connected: {self.config.uri}")

                    if self.config.create_indexes and not self._initialized:
                        self._create_schema()
                        self._initialized = True

        return self._driver

    async def _get_async_driver_lock(self) -> asyncio.Lock:
        """Lazy async lock initialization bound to current event loop."""
        if self._async_driver_lock is None:
            self._async_driver_lock = asyncio.Lock()
        return self._async_driver_lock

    async def _get_async_driver(self):
        """Lazy async driver initialization."""
        if self._async_driver is None:
            lock = await self._get_async_driver_lock()
            async with lock:
                if self._async_driver is None:
                    import re as _re
                    _m = _re.search(r'://([^:/]+):?(\d+)?', self.config.uri)
                    _host = _m.group(1) if _m else "localhost"
                    _port = int(_m.group(2)) if _m and _m.group(2) else 7687
                    if not self._port_reachable(_host, _port, timeout=1.0):
                        hint = ""
                        if _host in {"localhost", "127.0.0.1"}:
                            hint = (
                                " Configure NEO4J_URI/NEO4J_USER/NEO4J_PASSWORD "
                                "(Aura: neo4j+s://<instance>.databases.neo4j.io) "
                                "ou inicie o Neo4j local."
                            )
                        raise ConnectionError(f"Neo4j port {_host}:{_port} not reachable.{hint}")

                    try:
                        from neo4j import AsyncGraphDatabase
                    except ImportError:
                        raise ImportError("Neo4j async driver required: pip install neo4j")

                    driver_kwargs: Dict[str, Any] = {
                        "max_connection_pool_size": self.config.max_connection_pool_size,
                        "connection_timeout": self.config.connection_timeout,
                        "max_transaction_retry_time": 2,
                    }
                    if self.config.liveness_check_timeout is not None:
                        driver_kwargs["liveness_check_timeout"] = self.config.liveness_check_timeout

                    self._async_driver = AsyncGraphDatabase.driver(
                        self.config.uri,
                        auth=(self.config.user, self.config.password),
                        **driver_kwargs,
                    )
                    logger.info(f"Neo4j async connected: {self.config.uri}")

                    if self.config.create_indexes and not self._initialized and not self._async_schema_building:
                        self._async_schema_building = True
                        try:
                            await self._create_schema_async()
                            self._initialized = True
                        finally:
                            self._async_schema_building = False

        return self._async_driver

    async def close_async(self) -> None:
        """Close async and sync Neo4j drivers."""
        if self._async_driver is not None:
            await self._async_driver.close()
            self._async_driver = None
            logger.info("Neo4j async connection closed")
        if self._driver is not None:
            self._driver.close()
            self._driver = None
            logger.info("Neo4j sync connection closed")

    def close(self) -> None:
        """Close driver connection."""
        if self._driver:
            self._driver.close()
            self._driver = None
            logger.info("Neo4j connection closed")
        if self._async_driver:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._async_driver.close())
            except RuntimeError:
                asyncio.run(self._async_driver.close())
            finally:
                self._async_driver = None
                logger.info("Neo4j async connection close scheduled")

    @staticmethod
    def _serialize_metadata(value: Any) -> str:
        """
        Neo4j properties do not support nested maps/dicts.
        Persist metadata as JSON string for consistent parsing downstream.
        """
        if value is None:
            return "{}"
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            return json.dumps(value, ensure_ascii=True)
        return str(value)

    def _database_candidates(self) -> List[str]:
        """
        Neo4j Community typically exposes only one user database (often called 'neo4j').
        If the configured database name doesn't exist, retry against 'neo4j'.
        """
        configured = (self.config.database or "").strip()
        candidates: List[str] = []
        if configured:
            candidates.append(configured)
        if "neo4j" not in candidates:
            candidates.append("neo4j")
        return candidates

    def _execute_read(
        self,
        query: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Execute read query."""
        try:
            from neo4j.exceptions import ClientError
        except Exception:
            ClientError = Exception  # type: ignore

        try:
            from neo4j.exceptions import ServiceUnavailable, SessionExpired
        except Exception:
            ServiceUnavailable = Exception  # type: ignore
            SessionExpired = Exception  # type: ignore

        def _should_reset_driver(exc: Exception) -> bool:
            if isinstance(exc, (ServiceUnavailable, SessionExpired)):  # type: ignore[arg-type]
                return True
            msg = str(exc).lower()
            return (
                "defunct connection" in msg
                or "bolt handshake" in msg
                or "connection reset" in msg
                or "couldn't connect to" in msg
            )

        last_db_not_found: Optional[Exception] = None
        for db in self._database_candidates():
            for attempt in (1, 2):
                try:
                    with self.driver.session(database=db) as session:
                        result = session.execute_read(
                            lambda tx: list(tx.run(query, params or {}))
                        )
                        return [record.data() for record in result]
                except ClientError as e:  # type: ignore
                    code = getattr(e, "code", "")
                    if code == "Neo.ClientError.Database.DatabaseNotFound" and db != "neo4j":
                        last_db_not_found = e
                        break
                    raise
                except Exception as e:
                    if attempt == 1 and _should_reset_driver(e):
                        logger.warning(f"Neo4j transient error, resetting driver and retrying: {e}")
                        try:
                            self.close()
                        except Exception:
                            pass
                        continue
                    raise

        if last_db_not_found:
            raise last_db_not_found
        raise RuntimeError("Failed to open Neo4j session for any candidate database")

    def _execute_write(
        self,
        query: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Execute write query."""
        try:
            from neo4j.exceptions import ClientError
        except Exception:
            ClientError = Exception  # type: ignore

        try:
            from neo4j.exceptions import ServiceUnavailable, SessionExpired
        except Exception:
            ServiceUnavailable = Exception  # type: ignore
            SessionExpired = Exception  # type: ignore

        def _should_reset_driver(exc: Exception) -> bool:
            if isinstance(exc, (ServiceUnavailable, SessionExpired)):  # type: ignore[arg-type]
                return True
            msg = str(exc).lower()
            return (
                "defunct connection" in msg
                or "bolt handshake" in msg
                or "connection reset" in msg
                or "couldn't connect to" in msg
            )

        last_db_not_found: Optional[Exception] = None
        for db in self._database_candidates():
            for attempt in (1, 2):
                try:
                    with self.driver.session(database=db) as session:
                        result = session.execute_write(
                            lambda tx: list(tx.run(query, params or {}))
                        )
                        return [record.data() for record in result]
                except ClientError as e:  # type: ignore
                    code = getattr(e, "code", "")
                    if code == "Neo.ClientError.Database.DatabaseNotFound" and db != "neo4j":
                        last_db_not_found = e
                        break
                    raise
                except Exception as e:
                    if attempt == 1 and _should_reset_driver(e):
                        logger.warning(f"Neo4j transient error, resetting driver and retrying: {e}")
                        try:
                            self.close()
                        except Exception:
                            pass
                        continue
                    raise

        if last_db_not_found:
            raise last_db_not_found
        raise RuntimeError("Failed to open Neo4j session for any candidate database")

    async def _execute_read_async(
        self,
        query: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Execute read query using AsyncSession/managed transaction."""
        try:
            from neo4j.exceptions import ClientError
        except Exception:
            ClientError = Exception  # type: ignore

        try:
            from neo4j.exceptions import ServiceUnavailable, SessionExpired
        except Exception:
            ServiceUnavailable = Exception  # type: ignore
            SessionExpired = Exception  # type: ignore

        def _should_reset_driver(exc: Exception) -> bool:
            if isinstance(exc, (ServiceUnavailable, SessionExpired)):  # type: ignore[arg-type]
                return True
            msg = str(exc).lower()
            return (
                "defunct connection" in msg
                or "bolt handshake" in msg
                or "connection reset" in msg
                or "couldn't connect to" in msg
            )

        async def _run_read(tx):
            result = await tx.run(query, params or {})
            return [record.data() async for record in result]

        last_db_not_found: Optional[Exception] = None
        for db in self._database_candidates():
            for attempt in (1, 2):
                try:
                    driver = await self._get_async_driver()
                    async with driver.session(database=db) as session:
                        return await session.execute_read(_run_read)
                except ClientError as e:  # type: ignore
                    code = getattr(e, "code", "")
                    if code == "Neo.ClientError.Database.DatabaseNotFound" and db != "neo4j":
                        last_db_not_found = e
                        break
                    raise
                except Exception as e:
                    if attempt == 1 and _should_reset_driver(e):
                        logger.warning(f"Neo4j async transient read error, resetting driver and retrying: {e}")
                        try:
                            await self.close_async()
                        except Exception:
                            pass
                        continue
                    raise

        if last_db_not_found:
            raise last_db_not_found
        raise RuntimeError("Failed to open Neo4j async read session for any candidate database")

    async def _execute_write_async(
        self,
        query: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Execute write query using AsyncSession/managed transaction."""
        try:
            from neo4j.exceptions import ClientError
        except Exception:
            ClientError = Exception  # type: ignore

        try:
            from neo4j.exceptions import ServiceUnavailable, SessionExpired
        except Exception:
            ServiceUnavailable = Exception  # type: ignore
            SessionExpired = Exception  # type: ignore

        def _should_reset_driver(exc: Exception) -> bool:
            if isinstance(exc, (ServiceUnavailable, SessionExpired)):  # type: ignore[arg-type]
                return True
            msg = str(exc).lower()
            return (
                "defunct connection" in msg
                or "bolt handshake" in msg
                or "connection reset" in msg
                or "couldn't connect to" in msg
            )

        async def _run_write(tx):
            result = await tx.run(query, params or {})
            return [record.data() async for record in result]

        last_db_not_found: Optional[Exception] = None
        for db in self._database_candidates():
            for attempt in (1, 2):
                try:
                    driver = await self._get_async_driver()
                    async with driver.session(database=db) as session:
                        return await session.execute_write(_run_write)
                except ClientError as e:  # type: ignore
                    code = getattr(e, "code", "")
                    if code == "Neo.ClientError.Database.DatabaseNotFound" and db != "neo4j":
                        last_db_not_found = e
                        break
                    raise
                except Exception as e:
                    if attempt == 1 and _should_reset_driver(e):
                        logger.warning(f"Neo4j async transient write error, resetting driver and retrying: {e}")
                        try:
                            await self.close_async()
                        except Exception:
                            pass
                        continue
                    raise

        if last_db_not_found:
            raise last_db_not_found
        raise RuntimeError("Failed to open Neo4j async write session for any candidate database")

    @staticmethod
    def _iter_batches(rows: List[Dict[str, Any]], batch_size: int) -> Iterable[List[Dict[str, Any]]]:
        """Yield rows in fixed-size batches."""
        size = max(1, int(batch_size or 1))
        for i in range(0, len(rows), size):
            yield rows[i:i + size]

    def _execute_write_rows(
        self,
        query: str,
        rows: List[Dict[str, Any]],
        extra_params: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Execute a write query using batched UNWIND rows."""
        if not rows:
            return
        for batch in self._iter_batches(rows, self.config.batch_size):
            params: Dict[str, Any] = {"rows": batch}
            if extra_params:
                params.update(extra_params)
            self._execute_write(query, params)

    async def _execute_write_rows_async(
        self,
        query: str,
        rows: List[Dict[str, Any]],
        extra_params: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Execute batched UNWIND write query with AsyncSession."""
        if not rows:
            return
        for batch in self._iter_batches(rows, self.config.batch_size):
            params: Dict[str, Any] = {"rows": batch}
            if extra_params:
                params.update(extra_params)
            await self._execute_write_async(query, params)

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

            # Optional: hybrid labels schema (label per entity_type)
            if self.config.graph_hybrid_mode and self.config.graph_hybrid_auto_schema:
                from app.services.rag.core.graph_hybrid import (
                    HYBRID_LABELS_BY_ENTITY_TYPE,
                    hybrid_schema_statements,
                    migrate_hybrid_labels,
                )

                labels = sorted(set(HYBRID_LABELS_BY_ENTITY_TYPE.values()))
                for stmt in hybrid_schema_statements(labels):
                    try:
                        self._execute_write(stmt)
                    except Exception as e:
                        logger.debug(f"Hybrid schema statement skipped: {e}")

                if self.config.graph_hybrid_migrate_on_startup:
                    # Use the same database fallback policy as _execute_*.
                    for db in self._database_candidates():
                        try:
                            with self.driver.session(database=db) as session:
                                migrate_hybrid_labels(session)
                            break
                        except Exception as e:
                            logger.debug(f"Hybrid migration skipped for database={db}: {e}")

            # Optional: Fulltext indexes (Neo4j native lexical search for UI/diagnostics)
            if self.config.enable_fulltext_indexes:
                fulltext_stmts = [
                    "CREATE FULLTEXT INDEX rag_entity_fulltext IF NOT EXISTS "
                    "FOR (e:Entity) ON EACH [e.name, e.entity_id, e.normalized]",
                    "CREATE FULLTEXT INDEX rag_chunk_fulltext IF NOT EXISTS "
                    "FOR (c:Chunk) ON EACH [c.text_preview]",
                    "CREATE FULLTEXT INDEX rag_doc_fulltext IF NOT EXISTS "
                    "FOR (d:Document) ON EACH [d.title]",
                ]
                for stmt in fulltext_stmts:
                    try:
                        self._execute_write(stmt)
                    except Exception as e:
                        logger.debug(f"Fulltext index statement skipped: {e}")

            # Optional: Vector index for Chunk embeddings (Neo4j native semantic seeds)
            if self.config.enable_vector_index:
                prop = (self.config.vector_property or "embedding").strip()
                if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", prop):
                    logger.warning("Invalid Neo4j vector property name: %r; falling back to 'embedding'", prop)
                    prop = "embedding"
                sim = (self.config.vector_similarity or "cosine").strip().lower()
                if sim not in ("cosine", "euclidean"):
                    logger.warning("Unsupported Neo4j vector similarity %r; falling back to 'cosine'", sim)
                    sim = "cosine"

                # Neo4j vector index requires a single label + single property.
                vector_stmt = (
                    "CREATE VECTOR INDEX rag_chunk_vector IF NOT EXISTS "
                    f"FOR (c:Chunk) ON (c.{prop}) "
                    "OPTIONS {indexConfig: {"
                    "`vector.dimensions`: $dim, "
                    f"`vector.similarity_function`: '{sim}'"
                    "}}"
                )
                try:
                    self._execute_write(vector_stmt, {"dim": int(self.config.vector_dimensions)})
                except Exception as e:
                    logger.debug(f"Vector index statement skipped: {e}")

            logger.info("Neo4j schema created/verified")
        except Exception as e:
            logger.warning(f"Schema creation warning: {e}")

    async def _create_schema_async(self) -> None:
        """Create constraints and indexes using async Neo4j sessions."""
        try:
            for stmt in CypherQueries.CREATE_CONSTRAINTS.strip().split(";"):
                stmt = stmt.strip()
                if stmt:
                    try:
                        await self._execute_write_async(stmt)
                    except Exception as e:
                        logger.debug(f"Async constraint may exist: {e}")

            for stmt in CypherQueries.CREATE_INDEXES.strip().split(";"):
                stmt = stmt.strip()
                if stmt:
                    try:
                        await self._execute_write_async(stmt)
                    except Exception as e:
                        logger.debug(f"Async index may exist: {e}")

            if self.config.graph_hybrid_mode and self.config.graph_hybrid_auto_schema:
                from app.services.rag.core.graph_hybrid import (
                    HYBRID_LABELS_BY_ENTITY_TYPE,
                    hybrid_schema_statements,
                )

                labels = sorted(set(HYBRID_LABELS_BY_ENTITY_TYPE.values()))
                for stmt in hybrid_schema_statements(labels):
                    try:
                        await self._execute_write_async(stmt)
                    except Exception as e:
                        logger.debug(f"Async hybrid schema statement skipped: {e}")

                if self.config.graph_hybrid_migrate_on_startup:
                    for entity_type, label in HYBRID_LABELS_BY_ENTITY_TYPE.items():
                        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", label):
                            continue
                        migrate_query = f"""
                        MATCH (e:Entity)
                        WHERE e.entity_type = $entity_type AND NOT (e:{label})
                        SET e:{label}
                        RETURN count(e) AS updated
                        """
                        try:
                            await self._execute_write_async(
                                migrate_query, {"entity_type": entity_type}
                            )
                        except Exception as e:
                            logger.debug(f"Async hybrid migration skipped for label={label}: {e}")

            if self.config.enable_fulltext_indexes:
                fulltext_stmts = [
                    "CREATE FULLTEXT INDEX rag_entity_fulltext IF NOT EXISTS "
                    "FOR (e:Entity) ON EACH [e.name, e.entity_id, e.normalized]",
                    "CREATE FULLTEXT INDEX rag_chunk_fulltext IF NOT EXISTS "
                    "FOR (c:Chunk) ON EACH [c.text_preview]",
                    "CREATE FULLTEXT INDEX rag_doc_fulltext IF NOT EXISTS "
                    "FOR (d:Document) ON EACH [d.title]",
                ]
                for stmt in fulltext_stmts:
                    try:
                        await self._execute_write_async(stmt)
                    except Exception as e:
                        logger.debug(f"Async fulltext index statement skipped: {e}")

            if self.config.enable_vector_index:
                prop = (self.config.vector_property or "embedding").strip()
                if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", prop):
                    logger.warning("Invalid Neo4j vector property name: %r; falling back to 'embedding'", prop)
                    prop = "embedding"
                sim = (self.config.vector_similarity or "cosine").strip().lower()
                if sim not in ("cosine", "euclidean"):
                    logger.warning("Unsupported Neo4j vector similarity %r; falling back to 'cosine'", sim)
                    sim = "cosine"

                vector_stmt = (
                    "CREATE VECTOR INDEX rag_chunk_vector IF NOT EXISTS "
                    f"FOR (c:Chunk) ON (c.{prop}) "
                    "OPTIONS {indexConfig: {"
                    "`vector.dimensions`: $dim, "
                    f"`vector.similarity_function`: '{sim}'"
                    "}}"
                )
                try:
                    await self._execute_write_async(
                        vector_stmt, {"dim": int(self.config.vector_dimensions)}
                    )
                except Exception as e:
                    logger.debug(f"Async vector index statement skipped: {e}")

            logger.info("Neo4j async schema created/verified")
        except Exception as e:
            logger.warning(f"Async schema creation warning: {e}")

    async def _merge_entity_async(self, ent: Dict[str, Any]) -> None:
        """Async variant of _merge_entity."""
        from app.services.rag.core.graph_hybrid import label_for_entity_type

        label = label_for_entity_type(ent.get("entity_type")) if self.config.graph_hybrid_mode else None
        label_clause = f":{label}" if label else ""

        query = f"""
        MERGE (e:Entity{label_clause} {{entity_id: $entity_id}})
        ON CREATE SET
            e.entity_type = $entity_type,
            e.name = $name,
            e.normalized = $normalized,
            e.metadata = $metadata,
            e.created_at = datetime()
        ON MATCH SET
            e.entity_type = $entity_type,
            e.name = $name,
            e.normalized = $normalized,
            e.metadata = $metadata,
            e.updated_at = datetime()
        RETURN e
        """

        await self._execute_write_async(
            query,
            {
                "entity_id": ent["entity_id"],
                "entity_type": ent["entity_type"],
                "name": ent["name"],
                "normalized": ent["normalized"],
                "metadata": self._serialize_metadata(ent.get("metadata", {})),
            },
        )

    def _merge_entity(self, ent: Dict[str, Any]) -> None:
        """Merge an Entity node, optionally applying a hybrid label."""
        from app.services.rag.core.graph_hybrid import label_for_entity_type

        label = label_for_entity_type(ent.get("entity_type")) if self.config.graph_hybrid_mode else None
        label_clause = f":{label}" if label else ""

        query = f"""
        MERGE (e:Entity{label_clause} {{entity_id: $entity_id}})
        ON CREATE SET
            e.entity_type = $entity_type,
            e.name = $name,
            e.normalized = $normalized,
            e.metadata = $metadata,
            e.created_at = datetime()
        ON MATCH SET
            e.entity_type = $entity_type,
            e.name = $name,
            e.normalized = $normalized,
            e.metadata = $metadata,
            e.updated_at = datetime()
        RETURN e
        """

        self._execute_write(
            query,
            {
                "entity_id": ent["entity_id"],
                "entity_type": ent["entity_type"],
                "name": ent["name"],
                "normalized": ent["normalized"],
                "metadata": self._serialize_metadata(ent.get("metadata", {})),
            },
        )

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
        semantic_extraction: bool = False,
        extract_facts: bool = False,
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
            extract_entities: Whether to extract and link entities (regex-based)
            semantic_extraction: Whether to use LLM (Gemini) for semantic entity extraction
                                (teses, conceitos, princípios, institutos)

        Returns:
            Dict with counts of created nodes/relationships
        """
        stats = {
            "document": 0,
            "chunks": 0,
            "entities": 0,
            "mentions": 0,
            "next_rels": 0,
            "semantic_entities": 0,
            "semantic_relations": 0,
            "facts": 0,
            "fact_refs": 0,
        }

        # Create document node
        doc_id_value = (
            (metadata or {}).get("doc_id")
            or (metadata or {}).get("document_id")
            or (metadata or {}).get("id")
        )
        if not doc_id_value and isinstance(doc_hash, str):
            # If the caller uses the document UUID as doc_hash, also expose it as doc_id.
            if re.match(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", doc_hash):
                doc_id_value = doc_hash

        self._execute_write(
            CypherQueries.MERGE_DOCUMENT,
            {
                "doc_hash": doc_hash,
                "tenant_id": tenant_id,
                "scope": scope,
                "case_id": case_id,
                "doc_id": doc_id_value,
                "group_ids": metadata.get("group_ids", []),
                "title": metadata.get("title", ""),
                "source_type": metadata.get("source_type", ""),
                "sigilo": metadata.get("sigilo", False),
                "allowed_users": metadata.get("allowed_users", []),
            }
        )
        stats["document"] = 1

        prepared_chunks: List[Dict[str, Any]] = []
        for idx, chunk in enumerate(chunks):
            chunk_uid = chunk.get("chunk_uid")
            chunk_text = chunk.get("text", "")
            chunk_index = int(chunk.get("chunk_index", idx))

            if not chunk_uid:
                chunk_uid = hashlib.md5(
                    f"{doc_hash}:{chunk_index}".encode()
                ).hexdigest()

            prepared_chunks.append(
                {
                    "chunk_uid": chunk_uid,
                    "text": chunk_text,
                    "chunk_index": chunk_index,
                    "token_count": int(chunk.get("token_count", max(1, len(chunk_text) // 4))),
                }
            )

        chunk_rows = [
            {
                "chunk_uid": chunk["chunk_uid"],
                "doc_hash": doc_hash,
                "chunk_index": chunk["chunk_index"],
                "text_preview": (chunk["text"] or "")[:500],
                "token_count": chunk["token_count"],
            }
            for chunk in prepared_chunks
        ]
        self._execute_write_rows(CypherQueries.MERGE_CHUNKS_BATCH, chunk_rows)
        stats["chunks"] = len(chunk_rows)

        doc_chunk_rows = [{"chunk_uid": chunk["chunk_uid"]} for chunk in prepared_chunks]
        self._execute_write_rows(
            CypherQueries.LINK_DOC_CHUNKS_BATCH,
            doc_chunk_rows,
            {"doc_hash": doc_hash},
        )

        next_rows: List[Dict[str, str]] = []
        for i in range(1, len(prepared_chunks)):
            next_rows.append(
                {
                    "prev_chunk_uid": prepared_chunks[i - 1]["chunk_uid"],
                    "chunk_uid": prepared_chunks[i]["chunk_uid"],
                }
            )
        self._execute_write_rows(CypherQueries.LINK_CHUNK_NEXT_BATCH, next_rows)
        stats["next_rels"] = len(next_rows)

        all_entities: Dict[str, Dict[str, Any]] = {}
        mention_rows: List[Dict[str, str]] = []
        fact_rows: List[Dict[str, Any]] = []
        chunk_fact_rows: List[Dict[str, str]] = []
        fact_entity_rows: List[Dict[str, str]] = []

        for chunk in prepared_chunks:
            chunk_uid = chunk["chunk_uid"]
            chunk_text = chunk.get("text", "")
            chunk_index = chunk.get("chunk_index", 0)

            # Extract and link entities
            chunk_entity_ids: List[str] = []
            if extract_entities and chunk_text:
                entities = LegalEntityExtractor.extract(chunk_text)

                for ent in entities[:self.config.max_entities_per_chunk]:
                    entity_id = ent["entity_id"]

                    # Merge entity
                    if entity_id not in all_entities:
                        self._merge_entity(ent)
                        all_entities[entity_id] = ent
                        stats["entities"] += 1

                    # Link chunk → entity
                    mention_rows.append({"chunk_uid": chunk_uid, "entity_id": entity_id})
                    chunk_entity_ids.append(entity_id)

            # Extract and link facts (local narrative -> connect to entities)
            if extract_facts and chunk_text:
                max_facts = max(1, int(self.config.max_facts_per_chunk or 1))
                for fact_text in FactExtractor.extract(chunk_text, max_facts=max_facts):
                    fact_norm = re.sub(r"\s+", " ", fact_text.strip().lower())
                    fact_hash = hashlib.sha256(
                        f"{doc_hash}:{chunk_uid}:{fact_norm}".encode()
                    ).hexdigest()[:24]
                    fact_id = f"fact_{fact_hash}"

                    fact_rows.append(
                        {
                            "fact_id": fact_id,
                            "text": fact_text[:2000],
                            "text_preview": fact_text[:320],
                            "doc_hash": doc_hash,
                            "doc_id": doc_id_value,
                            "tenant_id": tenant_id,
                            "scope": scope,
                            "case_id": case_id,
                            "metadata": self._serialize_metadata(
                                {"chunk_uid": chunk_uid, "chunk_index": chunk_index}
                            ),
                        }
                    )

                    chunk_fact_rows.append({"chunk_uid": chunk_uid, "fact_id": fact_id})

                    for entity_id in chunk_entity_ids:
                        fact_entity_rows.append({"fact_id": fact_id, "entity_id": entity_id})

        self._execute_write_rows(CypherQueries.LINK_CHUNK_ENTITIES_BATCH, mention_rows)
        stats["mentions"] = len(mention_rows)

        self._execute_write_rows(CypherQueries.MERGE_FACTS_BATCH, fact_rows)
        stats["facts"] = len(fact_rows)

        self._execute_write_rows(CypherQueries.LINK_CHUNK_FACTS_BATCH, chunk_fact_rows)

        self._execute_write_rows(CypherQueries.LINK_FACT_ENTITIES_BATCH, fact_entity_rows)
        stats["fact_refs"] = len(fact_entity_rows)

        # Semantic extraction (LLM-based) for teses, conceitos, princípios
        if semantic_extraction and prepared_chunks:
            try:
                from app.services.rag.core.semantic_extractor import get_semantic_extractor

                extractor = get_semantic_extractor()

                # Combine all chunk texts for semantic analysis
                full_text = "\n\n".join(
                    c.get("text", "")[:2000] for c in prepared_chunks[:10]  # Limit to avoid token overflow
                )

                # Get already extracted entities for relationship building
                existing_entities_list = list(all_entities.values())

                # Extract semantic entities
                semantic_result = extractor.extract(full_text, existing_entities_list)

                # Add semantic entities to graph
                for sem_ent in semantic_result.get("entities", []):
                    entity_id = sem_ent["entity_id"]
                    if entity_id not in all_entities:
                        self._merge_entity(sem_ent)
                        all_entities[entity_id] = sem_ent
                        stats["semantic_entities"] += 1

                        # Link to first chunk that likely contains it
                        if prepared_chunks:
                            first_chunk_uid = prepared_chunks[0]["chunk_uid"]
                            self._execute_write(
                                CypherQueries.LINK_CHUNK_ENTITY,
                                {"chunk_uid": first_chunk_uid, "entity_id": entity_id}
                            )
                            stats["mentions"] += 1

                # Create semantic relationships
                for rel in semantic_result.get("relations", []):
                    source = rel.get("source", "")
                    target = rel.get("target", "")

                    # Find source entity ID
                    source_id = None
                    for ent in all_entities.values():
                        if ent.get("normalized") == source or ent.get("entity_id") == source:
                            source_id = ent["entity_id"]
                            break

                    # Find target entity ID
                    target_id = None
                    for ent in all_entities.values():
                        if ent.get("normalized") == target or ent.get("entity_id") == target:
                            target_id = ent["entity_id"]
                            break

                    if source_id and target_id and source_id != target_id:
                        weight = rel.get("weight")
                        props: Dict[str, Any] = {
                            "source": "semantic_extractor",
                            "layer": "candidate",
                            "verified": False,
                            "candidate_type": "semantic:vector_similarity",
                            "tenant_id": tenant_id,
                            "doc_hash": doc_hash,
                        }
                        if isinstance(weight, (int, float)):
                            props["confidence"] = float(weight)
                            props["weight"] = float(weight)
                        ok = self.link_entities(
                            source_id,
                            target_id,
                            relation_type="RELATED_TO",
                            properties=props,
                        )
                        if ok:
                            stats["semantic_relations"] += 1

            except Exception as e:
                logger.warning(f"Semantic extraction failed for doc {doc_hash}: {e}")

        logger.info(
            f"Ingested doc {doc_hash}: {stats['chunks']} chunks, "
            f"{stats['entities']} entities, {stats['mentions']} mentions, "
            f"{stats['semantic_entities']} semantic entities, {stats['semantic_relations']} relations"
        )

        return stats

    async def ingest_document_async(
        self,
        doc_hash: str,
        chunks: List[Dict[str, Any]],
        metadata: Dict[str, Any],
        tenant_id: str,
        scope: str = "global",
        case_id: Optional[str] = None,
        extract_entities: bool = True,
        semantic_extraction: bool = False,
        extract_facts: bool = False,
    ) -> Dict[str, Any]:
        """Async ingest using AsyncNeo4j driver (no thread offload)."""
        stats = {
            "document": 0,
            "chunks": 0,
            "entities": 0,
            "mentions": 0,
            "next_rels": 0,
            "semantic_entities": 0,
            "semantic_relations": 0,
            "facts": 0,
            "fact_refs": 0,
        }

        doc_id_value = (
            (metadata or {}).get("doc_id")
            or (metadata or {}).get("document_id")
            or (metadata or {}).get("id")
        )
        if not doc_id_value and isinstance(doc_hash, str):
            if re.match(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", doc_hash):
                doc_id_value = doc_hash

        await self._execute_write_async(
            CypherQueries.MERGE_DOCUMENT,
            {
                "doc_hash": doc_hash,
                "tenant_id": tenant_id,
                "scope": scope,
                "case_id": case_id,
                "doc_id": doc_id_value,
                "group_ids": metadata.get("group_ids", []),
                "title": metadata.get("title", ""),
                "source_type": metadata.get("source_type", ""),
                "sigilo": metadata.get("sigilo", False),
                "allowed_users": metadata.get("allowed_users", []),
            },
        )
        stats["document"] = 1

        prepared_chunks: List[Dict[str, Any]] = []
        for idx, chunk in enumerate(chunks):
            chunk_uid = chunk.get("chunk_uid")
            chunk_text = chunk.get("text", "")
            chunk_index = int(chunk.get("chunk_index", idx))

            if not chunk_uid:
                chunk_uid = hashlib.md5(
                    f"{doc_hash}:{chunk_index}".encode()
                ).hexdigest()

            prepared_chunks.append(
                {
                    "chunk_uid": chunk_uid,
                    "text": chunk_text,
                    "chunk_index": chunk_index,
                    "token_count": int(chunk.get("token_count", max(1, len(chunk_text) // 4))),
                }
            )

        chunk_rows = [
            {
                "chunk_uid": chunk["chunk_uid"],
                "doc_hash": doc_hash,
                "chunk_index": chunk["chunk_index"],
                "text_preview": (chunk["text"] or "")[:500],
                "token_count": chunk["token_count"],
            }
            for chunk in prepared_chunks
        ]
        await self._execute_write_rows_async(CypherQueries.MERGE_CHUNKS_BATCH, chunk_rows)
        stats["chunks"] = len(chunk_rows)

        doc_chunk_rows = [{"chunk_uid": chunk["chunk_uid"]} for chunk in prepared_chunks]
        await self._execute_write_rows_async(
            CypherQueries.LINK_DOC_CHUNKS_BATCH,
            doc_chunk_rows,
            {"doc_hash": doc_hash},
        )

        next_rows: List[Dict[str, str]] = []
        for i in range(1, len(prepared_chunks)):
            next_rows.append(
                {
                    "prev_chunk_uid": prepared_chunks[i - 1]["chunk_uid"],
                    "chunk_uid": prepared_chunks[i]["chunk_uid"],
                }
            )
        await self._execute_write_rows_async(CypherQueries.LINK_CHUNK_NEXT_BATCH, next_rows)
        stats["next_rels"] = len(next_rows)

        all_entities: Dict[str, Dict[str, Any]] = {}
        mention_rows: List[Dict[str, str]] = []
        fact_rows: List[Dict[str, Any]] = []
        chunk_fact_rows: List[Dict[str, str]] = []
        fact_entity_rows: List[Dict[str, str]] = []

        for chunk in prepared_chunks:
            chunk_uid = chunk["chunk_uid"]
            chunk_text = chunk.get("text", "")
            chunk_index = chunk.get("chunk_index", 0)

            chunk_entity_ids: List[str] = []
            if extract_entities and chunk_text:
                entities = LegalEntityExtractor.extract(chunk_text)

                for ent in entities[:self.config.max_entities_per_chunk]:
                    entity_id = ent["entity_id"]

                    if entity_id not in all_entities:
                        await self._merge_entity_async(ent)
                        all_entities[entity_id] = ent
                        stats["entities"] += 1

                    mention_rows.append({"chunk_uid": chunk_uid, "entity_id": entity_id})
                    chunk_entity_ids.append(entity_id)

            if extract_facts and chunk_text:
                max_facts = max(1, int(self.config.max_facts_per_chunk or 1))
                for fact_text in FactExtractor.extract(chunk_text, max_facts=max_facts):
                    fact_norm = re.sub(r"\s+", " ", fact_text.strip().lower())
                    fact_hash = hashlib.sha256(
                        f"{doc_hash}:{chunk_uid}:{fact_norm}".encode()
                    ).hexdigest()[:24]
                    fact_id = f"fact_{fact_hash}"

                    fact_rows.append(
                        {
                            "fact_id": fact_id,
                            "text": fact_text[:2000],
                            "text_preview": fact_text[:320],
                            "doc_hash": doc_hash,
                            "doc_id": doc_id_value,
                            "tenant_id": tenant_id,
                            "scope": scope,
                            "case_id": case_id,
                            "metadata": self._serialize_metadata(
                                {"chunk_uid": chunk_uid, "chunk_index": chunk_index}
                            ),
                        }
                    )
                    chunk_fact_rows.append({"chunk_uid": chunk_uid, "fact_id": fact_id})
                    for entity_id in chunk_entity_ids:
                        fact_entity_rows.append({"fact_id": fact_id, "entity_id": entity_id})

        await self._execute_write_rows_async(CypherQueries.LINK_CHUNK_ENTITIES_BATCH, mention_rows)
        stats["mentions"] = len(mention_rows)

        await self._execute_write_rows_async(CypherQueries.MERGE_FACTS_BATCH, fact_rows)
        stats["facts"] = len(fact_rows)

        await self._execute_write_rows_async(CypherQueries.LINK_CHUNK_FACTS_BATCH, chunk_fact_rows)
        await self._execute_write_rows_async(CypherQueries.LINK_FACT_ENTITIES_BATCH, fact_entity_rows)
        stats["fact_refs"] = len(fact_entity_rows)

        if semantic_extraction and prepared_chunks:
            try:
                from app.services.rag.core.semantic_extractor import get_semantic_extractor

                extractor = get_semantic_extractor()
                full_text = "\n\n".join(
                    c.get("text", "")[:2000] for c in prepared_chunks[:10]
                )
                existing_entities_list = list(all_entities.values())

                semantic_result = await asyncio.to_thread(
                    extractor.extract, full_text, existing_entities_list
                )

                for sem_ent in semantic_result.get("entities", []):
                    entity_id = sem_ent["entity_id"]
                    if entity_id not in all_entities:
                        await self._merge_entity_async(sem_ent)
                        all_entities[entity_id] = sem_ent
                        stats["semantic_entities"] += 1

                        if prepared_chunks:
                            first_chunk_uid = prepared_chunks[0]["chunk_uid"]
                            await self._execute_write_async(
                                CypherQueries.LINK_CHUNK_ENTITY,
                                {"chunk_uid": first_chunk_uid, "entity_id": entity_id},
                            )
                            stats["mentions"] += 1

                for rel in semantic_result.get("relations", []):
                    source = rel.get("source", "")
                    target = rel.get("target", "")

                    source_id = None
                    for ent in all_entities.values():
                        if ent.get("normalized") == source or ent.get("entity_id") == source:
                            source_id = ent["entity_id"]
                            break

                    target_id = None
                    for ent in all_entities.values():
                        if ent.get("normalized") == target or ent.get("entity_id") == target:
                            target_id = ent["entity_id"]
                            break

                    if source_id and target_id and source_id != target_id:
                        weight = rel.get("weight")
                        props: Dict[str, Any] = {
                            "source": "semantic_extractor",
                            "layer": "candidate",
                            "verified": False,
                            "candidate_type": "semantic:vector_similarity",
                            "tenant_id": tenant_id,
                            "doc_hash": doc_hash,
                        }
                        if isinstance(weight, (int, float)):
                            props["confidence"] = float(weight)
                            props["weight"] = float(weight)
                        ok = await self.link_entities_async(
                            source_id,
                            target_id,
                            relation_type="RELATED_TO",
                            properties=props,
                        )
                        if ok:
                            stats["semantic_relations"] += 1

            except Exception as e:
                logger.warning(f"Semantic extraction failed for doc {doc_hash}: {e}")

        logger.info(
            f"Ingested doc {doc_hash} (async): {stats['chunks']} chunks, "
            f"{stats['entities']} entities, {stats['mentions']} mentions, "
            f"{stats['semantic_entities']} semantic entities, {stats['semantic_relations']} relations"
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

    async def query_chunks_by_entities_async(
        self,
        entity_ids: List[str],
        tenant_id: str,
        scope: str = "global",
        case_id: Optional[str] = None,
        user_id: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Async variant of query_chunks_by_entities."""
        normalized_list = [eid.replace("_", ":") for eid in entity_ids]

        allowed_scopes = ["global"]
        if scope in ["private", "group", "local"]:
            allowed_scopes.append(scope)

        return await self._execute_read_async(
            CypherQueries.FIND_CHUNKS_BY_ENTITIES,
            {
                "entity_ids": entity_ids,
                "normalized_list": normalized_list,
                "tenant_id": tenant_id,
                "allowed_scopes": allowed_scopes,
                "case_id": case_id,
                "user_id": user_id,
                "limit": limit,
            },
        )

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

    async def query_chunks_by_text_async(
        self,
        query_text: str,
        tenant_id: str,
        scope: str = "global",
        case_id: Optional[str] = None,
        user_id: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Async variant of query_chunks_by_text."""
        entities = LegalEntityExtractor.extract(query_text)
        entity_ids = [e["entity_id"] for e in entities]

        if not entity_ids:
            return []

        return await self.query_chunks_by_entities_async(
            entity_ids=entity_ids,
            tenant_id=tenant_id,
            scope=scope,
            case_id=case_id,
            user_id=user_id,
            limit=limit,
        )

    def search_chunks_fulltext(
        self,
        query_text: str,
        tenant_id: str,
        *,
        allowed_scopes: Optional[List[str]] = None,
        group_ids: Optional[List[str]] = None,
        case_id: Optional[str] = None,
        user_id: Optional[str] = None,
        limit: int = 20,
        index_name: str = "rag_chunk_fulltext",
    ) -> List[Dict[str, Any]]:
        """
        Lexical search using Neo4j fulltext index (optional Phase 2 backend).

        This is meant for:
        - UI/graph exploration (fast keyword search inside Chunk previews)
        - A/B comparison against OpenSearch BM25 without adding training

        Notes:
        - Requires `NEO4J_FULLTEXT_ENABLED=true` and schema creation on startup.
        - Returns only chunk previews (same field the graph stores).
        """
        if allowed_scopes is None:
            # Default: allow global + tenant-private documents.
            allowed_scopes = ["global", "private"]

        query = """
        CALL db.index.fulltext.queryNodes($index_name, $query_text) YIELD node, score
        WITH node AS c, score
        WHERE c:Chunk
        MATCH (d:Document)-[:HAS_CHUNK]->(c)
        WHERE d.scope IN $allowed_scopes
          AND (
                d.scope = 'global'
                OR d.tenant_id = $tenant_id
                OR (
                    d.scope = 'group'
                    AND coalesce(size($group_ids), 0) > 0
                    AND any(g IN $group_ids WHERE g IN coalesce(d.group_ids, []))
                )
            )
          AND ($case_id IS NULL OR d.case_id = $case_id)
          AND (
                d.sigilo IS NULL
                OR d.sigilo = false
                OR $user_id IS NULL
                OR $user_id IN coalesce(d.allowed_users, [])
            )
        RETURN
            c.chunk_uid AS chunk_uid,
            c.text_preview AS text,
            c.chunk_index AS chunk_index,
            d.doc_hash AS doc_hash,
            d.title AS doc_title,
            d.source_type AS source_type,
            score AS score
        ORDER BY score DESC
        LIMIT $limit
        """

        return self._execute_read(
            query,
            {
                "index_name": index_name,
                "query_text": query_text,
                "tenant_id": tenant_id,
                "allowed_scopes": allowed_scopes,
                "group_ids": group_ids or [],
                "case_id": case_id,
                "user_id": user_id,
                "limit": limit,
            },
        )

    async def search_chunks_fulltext_async(
        self,
        query_text: str,
        tenant_id: str,
        *,
        allowed_scopes: Optional[List[str]] = None,
        group_ids: Optional[List[str]] = None,
        case_id: Optional[str] = None,
        user_id: Optional[str] = None,
        limit: int = 20,
        index_name: str = "rag_chunk_fulltext",
    ) -> List[Dict[str, Any]]:
        """Async variant of search_chunks_fulltext."""
        if allowed_scopes is None:
            allowed_scopes = ["global", "private"]

        query = """
        CALL db.index.fulltext.queryNodes($index_name, $query_text) YIELD node, score
        WITH node AS c, score
        WHERE c:Chunk
        MATCH (d:Document)-[:HAS_CHUNK]->(c)
        WHERE d.scope IN $allowed_scopes
          AND (
                d.scope = 'global'
                OR d.tenant_id = $tenant_id
                OR (
                    d.scope = 'group'
                    AND coalesce(size($group_ids), 0) > 0
                    AND any(g IN $group_ids WHERE g IN coalesce(d.group_ids, []))
                )
            )
          AND ($case_id IS NULL OR d.case_id = $case_id)
          AND (
                d.sigilo IS NULL
                OR d.sigilo = false
                OR $user_id IS NULL
                OR $user_id IN coalesce(d.allowed_users, [])
            )
        RETURN
            c.chunk_uid AS chunk_uid,
            c.text_preview AS text,
            c.chunk_index AS chunk_index,
            d.doc_hash AS doc_hash,
            d.title AS doc_title,
            d.source_type AS source_type,
            score AS score
        ORDER BY score DESC
        LIMIT $limit
        """

        return await self._execute_read_async(
            query,
            {
                "index_name": index_name,
                "query_text": query_text,
                "tenant_id": tenant_id,
                "allowed_scopes": allowed_scopes,
                "group_ids": group_ids or [],
                "case_id": case_id,
                "user_id": user_id,
                "limit": limit,
            },
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

        w = max(1, min(int(window or 1), 10))
        query = CypherQueries.EXPAND_NEIGHBORS.replace(CypherQueries._WINDOW_TOKEN, str(w))

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
        *,
        allowed_scopes: Optional[List[str]] = None,
        group_ids: Optional[List[str]] = None,
        case_id: Optional[str] = None,
        user_id: Optional[str] = None,
        max_hops: int = 2,
        limit: int = 20,
        include_arguments: bool = False,
        include_candidates: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Find paths from entities to other entities/chunks.

        Args:
            include_arguments: If True, use argument-aware traversal that
                crosses into Claim/Evidence nodes (with security trimming).
                If False (default), use entity-only traversal that stays
                within Entity/Chunk graph space.

        Returns explainable paths for RAG context.
        """
        if allowed_scopes is None:
            allowed_scopes = ["global"]
            if scope in ["private", "group", "local"]:
                allowed_scopes.append(scope)

        hops = max(1, min(int(max_hops or 1), 5))
        base_query = (
            CypherQueries.FIND_PATHS_WITH_ARGUMENTS if include_arguments
            else CypherQueries.FIND_PATHS
        )
        query = base_query.replace(CypherQueries._MAX_HOPS_TOKEN, str(hops))

        return self._execute_read(
            query,
            {
                "entity_ids": entity_ids,
                "tenant_id": tenant_id,
                "allowed_scopes": allowed_scopes,
                "group_ids": group_ids or [],
                "case_id": case_id,
                "user_id": user_id,
                "limit": limit,
                "include_candidates": bool(include_candidates),
            }
        )

    async def find_paths_async(
        self,
        entity_ids: List[str],
        tenant_id: str,
        scope: str = "global",
        *,
        allowed_scopes: Optional[List[str]] = None,
        group_ids: Optional[List[str]] = None,
        case_id: Optional[str] = None,
        user_id: Optional[str] = None,
        max_hops: int = 2,
        limit: int = 20,
        include_arguments: bool = False,
        include_candidates: bool = False,
    ) -> List[Dict[str, Any]]:
        """Async variant of find_paths."""
        if allowed_scopes is None:
            allowed_scopes = ["global"]
            if scope in ["private", "group", "local"]:
                allowed_scopes.append(scope)

        hops = max(1, min(int(max_hops or 1), 5))
        base_query = (
            CypherQueries.FIND_PATHS_WITH_ARGUMENTS if include_arguments
            else CypherQueries.FIND_PATHS
        )
        query = base_query.replace(CypherQueries._MAX_HOPS_TOKEN, str(hops))

        return await self._execute_read_async(
            query,
            {
                "entity_ids": entity_ids,
                "tenant_id": tenant_id,
                "allowed_scopes": allowed_scopes,
                "group_ids": group_ids or [],
                "case_id": case_id,
                "user_id": user_id,
                "limit": limit,
                "include_candidates": bool(include_candidates),
            },
        )

    def find_cooccurrence(
        self,
        entity_ids: List[str],
        tenant_id: str,
        scope: str = "global",
        *,
        allowed_scopes: Optional[List[str]] = None,
        group_ids: Optional[List[str]] = None,
        case_id: Optional[str] = None,
        user_id: Optional[str] = None,
        min_matches: int = 2,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Find chunks that mention multiple of the given entities.

        Good for finding highly relevant chunks.
        """
        if allowed_scopes is None:
            allowed_scopes = ["global"]
            if scope in ["private", "group", "local"]:
                allowed_scopes.append(scope)

        return self._execute_read(
            CypherQueries.FIND_COOCCURRENCE,
            {
                "entity_ids": entity_ids,
                "tenant_id": tenant_id,
                "allowed_scopes": allowed_scopes,
                "group_ids": group_ids or [],
                "case_id": case_id,
                "user_id": user_id,
                "min_matches": min_matches,
                "limit": limit,
            }
        )

    async def find_cooccurrence_async(
        self,
        entity_ids: List[str],
        tenant_id: str,
        scope: str = "global",
        *,
        allowed_scopes: Optional[List[str]] = None,
        group_ids: Optional[List[str]] = None,
        case_id: Optional[str] = None,
        user_id: Optional[str] = None,
        min_matches: int = 2,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Async variant of find_cooccurrence."""
        if allowed_scopes is None:
            allowed_scopes = ["global"]
            if scope in ["private", "group", "local"]:
                allowed_scopes.append(scope)

        return await self._execute_read_async(
            CypherQueries.FIND_COOCCURRENCE,
            {
                "entity_ids": entity_ids,
                "tenant_id": tenant_id,
                "allowed_scopes": allowed_scopes,
                "group_ids": group_ids or [],
                "case_id": case_id,
                "user_id": user_id,
                "min_matches": min_matches,
                "limit": limit,
            },
        )

    # -------------------------------------------------------------------------
    # Entity Management
    # -------------------------------------------------------------------------

    def _sanitize_relation_type(self, relation_type: str) -> str:
        """
        Validate relation label for dynamic Cypher relationship creation.

        Any invalid/unknown type falls back to RELATED_TO.
        """
        rel = (relation_type or "").strip().upper()
        if not rel or not _RELATION_LABEL_RE.fullmatch(rel):
            return "RELATED_TO"

        allowed = set(_DEFAULT_ALLOWED_RELATIONS)
        try:
            from app.services.rag.core.kg_builder.legal_schema import LEGAL_RELATIONSHIP_TYPES

            for item in LEGAL_RELATIONSHIP_TYPES:
                label = str(item.get("label", "")).strip().upper()
                if label and _RELATION_LABEL_RE.fullmatch(label):
                    allowed.add(label)
        except Exception:
            pass

        return rel if rel in allowed else "RELATED_TO"

    def link_entities(
        self,
        entity1_id: str,
        entity2_id: str,
        relation_type: str = "RELATED_TO",
        properties: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Create a typed relationship between entities (validated whitelist)."""
        rel = self._sanitize_relation_type(relation_type)
        props: Dict[str, Any] = dict(properties or {})

        # ------------------------------------------------------------------
        # Transparency-first candidate workflow (3 states)
        #
        # - Verified/core edges: typed relationships used for traversal/querying.
        # - Candidate edges: exploratory/inferred; ignored by default in Ask/Minutas.
        # - Promotion: admin/offline can flip flags (and optionally migrate type).
        #
        # Contract:
        # - Any edge with layer='candidate' OR verified=false OR candidate_type set
        #   must be persisted as candidate (layer=candidate, verified=false).
        # - Catch-all RELATED_TO is candidate by default (unless explicitly verified).
        # - CO_MENCIONA is always candidate.
        # ------------------------------------------------------------------

        layer = str(props.get("layer") or "").strip().lower() or None
        verified_val = props.get("verified", None)
        has_candidate_type = bool(props.get("candidate_type"))

        # Default: RELATED_TO is exploratory/candidate unless explicitly verified.
        if rel == "RELATED_TO" and layer is None and verified_val is None and not has_candidate_type:
            layer = "candidate"
            verified_val = False

        if layer == "candidate" or verified_val is False or has_candidate_type:
            props["layer"] = "candidate"
            props["verified"] = False
            props.setdefault("candidate_type", f"rel:{rel.lower()}")
        elif layer == "verified" or verified_val is True:
            props["layer"] = "verified"
            props["verified"] = True

        # CO_MENCIONA is always candidate (article co-occurrence exploration).
        if rel == "CO_MENCIONA":
            props["layer"] = "candidate"
            props["verified"] = False
            props.setdefault("candidate_type", "graph:co_menciona")
            props.setdefault("dimension", "horizontal")
        query = f"""
        MATCH (e1:Entity {{entity_id: $entity1_id}})
        MATCH (e2:Entity {{entity_id: $entity2_id}})
        MERGE (e1)-[r:{rel}]->(e2)
        ON CREATE SET r.created_at = datetime()
        SET r.updated_at = datetime()
        SET r += $properties
        """
        try:
            self._execute_write(
                query,
                {
                    "entity1_id": entity1_id,
                    "entity2_id": entity2_id,
                    "properties": props,
                },
            )
            return True
        except Exception as e:
            logger.error(f"Failed to link entities with type {rel}: {e}")
            return False

    async def link_entities_async(
        self,
        entity1_id: str,
        entity2_id: str,
        relation_type: str = "RELATED_TO",
        properties: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Async variant of link_entities."""
        rel = self._sanitize_relation_type(relation_type)
        props: Dict[str, Any] = dict(properties or {})

        layer = str(props.get("layer") or "").strip().lower() or None
        verified_val = props.get("verified", None)
        has_candidate_type = bool(props.get("candidate_type"))

        if rel == "RELATED_TO" and layer is None and verified_val is None and not has_candidate_type:
            layer = "candidate"
            verified_val = False

        if layer == "candidate" or verified_val is False or has_candidate_type:
            props["layer"] = "candidate"
            props["verified"] = False
            props.setdefault("candidate_type", f"rel:{rel.lower()}")
        elif layer == "verified" or verified_val is True:
            props["layer"] = "verified"
            props["verified"] = True

        if rel == "CO_MENCIONA":
            props["layer"] = "candidate"
            props["verified"] = False
            props.setdefault("candidate_type", "graph:co_menciona")
            props.setdefault("dimension", "horizontal")
        query = f"""
        MATCH (e1:Entity {{entity_id: $entity1_id}})
        MATCH (e2:Entity {{entity_id: $entity2_id}})
        MERGE (e1)-[r:{rel}]->(e2)
        ON CREATE SET r.created_at = datetime()
        SET r.updated_at = datetime()
        SET r += $properties
        """
        try:
            await self._execute_write_async(
                query,
                {
                    "entity1_id": entity1_id,
                    "entity2_id": entity2_id,
                    "properties": props,
                },
            )
            return True
        except Exception as e:
            logger.error(f"Failed to link entities with type {rel} (async): {e}")
            return False

    def link_related_entities(
        self,
        entity1_id: str,
        entity2_id: str,
    ) -> bool:
        """Create RELATED_TO relationship between entities."""
        return self.link_entities(entity1_id, entity2_id, relation_type="RELATED_TO")

    async def link_related_entities_async(
        self,
        entity1_id: str,
        entity2_id: str,
    ) -> bool:
        """Async variant of link_related_entities."""
        return await self.link_entities_async(entity1_id, entity2_id, relation_type="RELATED_TO")

    # -------------------------------------------------------------------------
    # Candidate Graph (Transparency-First Hybrid)
    # -------------------------------------------------------------------------

    def recompute_candidate_comentions(
        self,
        *,
        tenant_id: str,
        include_global: bool = False,
        min_cooccurrences: int = 2,
        max_pairs: int = 20000,
    ) -> Dict[str, Any]:
        """
        Build/update candidate Artigo–Artigo co-mention edges.

        These edges are intended for exploration only and must be ignored by default
        in Ask/Minutas/GraphRAG unless explicitly requested.

        Stored as:
          (:Entity:Artigo)-[:CO_MENCIONA {layer:'candidate', verified:false, tenant_id, co_occurrences, weight, samples}]->(:Entity:Artigo)

        Notes:
        - Does NOT create official REMETE_A (only explicit remissions are allowed there).
        - Skips pairs that already have an official REMETE_A in either direction.
        """
        min_co = max(1, int(min_cooccurrences or 2))
        max_pairs = max(1, min(int(max_pairs or 20000), 200000))

        delete_query = """
        MATCH ()-[r:CO_MENCIONA]->()
        WHERE r.layer = 'candidate' AND r.tenant_id = $tenant_id
        DELETE r
        """

        build_query = """
        // Candidate co-mentions between Artigos via chunk co-occurrence
        MATCH (d:Document)-[:HAS_CHUNK]->(c:Chunk)-[:MENTIONS]->(a1:Entity:Artigo)
        MATCH (c)-[:MENTIONS]->(a2:Entity:Artigo)
        WHERE a1.entity_id < a2.entity_id
          AND (d.tenant_id = $tenant_id OR ($include_global = true AND d.scope = 'global'))
          AND (d.sigilo IS NULL OR d.sigilo = false)
          AND NOT (a1)-[:REMETE_A]->(a2)
          AND NOT (a2)-[:REMETE_A]->(a1)
        WITH a1, a2, count(DISTINCT c) AS co,
             collect(DISTINCT c.text_preview)[0..3] AS samples
        WHERE co >= $min_cooccurrences
        ORDER BY co DESC
        LIMIT $max_pairs
        MERGE (a1)-[r:CO_MENCIONA]->(a2)
        ON CREATE SET r.created_at = datetime()
        SET r.updated_at = datetime(),
            r.layer = 'candidate',
            r.verified = false,
            r.candidate_type = 'graph:co_menciona',
            r.dimension = 'horizontal',
            r.tenant_id = $tenant_id,
            r.co_occurrences = co,
            r.weight = toFloat(co),
            r.samples = samples
        RETURN count(r) AS edges
        """

        try:
            self._execute_write(delete_query, {"tenant_id": tenant_id})
            rows = self._execute_write(
                build_query,
                {
                    "tenant_id": tenant_id,
                    "include_global": bool(include_global),
                    "min_cooccurrences": min_co,
                    "max_pairs": max_pairs,
                },
            )
            edges = int(rows[0]["edges"]) if rows else 0
            return {
                "ok": True,
                "tenant_id": tenant_id,
                "include_global": bool(include_global),
                "min_cooccurrences": min_co,
                "max_pairs": max_pairs,
                "edges": edges,
            }
        except Exception as e:
            logger.error("Failed to recompute candidate co-mentions: %s", e)
            return {"ok": False, "error": str(e)}

    def get_candidate_edge_stats(
        self,
        *,
        tenant_id: str,
        limit: int = 50,
        candidate_type_prefix: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Aggregate candidate edges by candidate_type.

        Intended for offline/admin workflows to decide what should be promoted.
        """
        limit = max(1, min(int(limit or 50), 500))
        prefix = (candidate_type_prefix or "").strip()

        query = """
        MATCH ()-[r]->()
        WHERE coalesce(r.layer, 'verified') = 'candidate'
          AND r.tenant_id = $tenant_id
          AND ($prefix = '' OR coalesce(r.candidate_type, '') STARTS WITH $prefix)
        WITH
            coalesce(r.candidate_type, 'unknown') AS candidate_type,
            type(r) AS rel_type,
            count(*) AS edges,
            round(avg(toFloat(coalesce(r.confidence, r.weight, 0.0))), 4) AS avg_confidence,
            sum(CASE WHEN coalesce(r.evidence, '') <> '' THEN 1 ELSE 0 END) AS with_evidence,
            count(DISTINCT coalesce(r.doc_hash, '')) AS distinct_docs
        RETURN candidate_type, rel_type, edges, avg_confidence, with_evidence, distinct_docs
        ORDER BY edges DESC
        LIMIT $limit
        """
        return self._execute_read(
            query,
            {"tenant_id": tenant_id, "limit": limit, "prefix": prefix},
        )

    def promote_candidate_edges(
        self,
        *,
        tenant_id: str,
        candidate_type: str,
        min_confidence: float = 0.0,
        require_evidence: bool = False,
        max_edges: int = 5000,
        promote_to_typed: bool = False,
    ) -> Dict[str, Any]:
        """
        Promote candidate edges to verified (and optionally migrate RELATED_TO -> typed relationship).

        Safety rails:
        - Always scoped by tenant_id and candidate_type.
        - Optional confidence/evidence filters.
        """
        cand = (candidate_type or "").strip()
        if not cand:
            return {"ok": False, "error": "candidate_type_required"}

        max_edges = max(1, min(int(max_edges or 5000), 50000))
        min_conf = max(0.0, min(float(min_confidence or 0.0), 1.0))
        req_ev = bool(require_evidence)

        if not promote_to_typed:
            query = """
            MATCH ()-[r]->()
            WHERE coalesce(r.layer, 'verified') = 'candidate'
              AND r.tenant_id = $tenant_id
              AND r.candidate_type = $candidate_type
              AND toFloat(coalesce(r.confidence, r.weight, 0.0)) >= $min_conf
              AND (NOT $require_evidence OR coalesce(r.evidence, '') <> '')
            WITH r LIMIT $max_edges
            SET r.layer = 'verified',
                r.verified = true,
                r.promoted_at = datetime()
            RETURN count(r) AS promoted
            """
            try:
                rows = self._execute_write(
                    query,
                    {
                        "tenant_id": tenant_id,
                        "candidate_type": cand,
                        "min_conf": min_conf,
                        "require_evidence": req_ev,
                        "max_edges": max_edges,
                    },
                )
                promoted = int(rows[0]["promoted"]) if rows else 0
                return {
                    "ok": True,
                    "tenant_id": tenant_id,
                    "candidate_type": cand,
                    "promote_to_typed": False,
                    "promoted": promoted,
                }
            except Exception as e:
                return {"ok": False, "error": str(e)}

        # Typed migration: only supports RELATED_TO -> <typed> promotion.
        # We infer intended relationship label from candidate_type suffix (after last ":").
        intended_raw = cand.split(":")[-1].strip().upper()
        intended = self._sanitize_relation_type(intended_raw)
        if intended in ("RELATED_TO", "CO_MENCIONA"):
            return {"ok": False, "error": f"cannot_promote_to_typed:{intended_raw}"}

        query = f"""
        MATCH (a:Entity)-[r:RELATED_TO]->(b:Entity)
        WHERE coalesce(r.layer, 'verified') = 'candidate'
          AND r.tenant_id = $tenant_id
          AND r.candidate_type = $candidate_type
          AND toFloat(coalesce(r.confidence, r.weight, 0.0)) >= $min_conf
          AND (NOT $require_evidence OR coalesce(r.evidence, '') <> '')
        WITH a, b, r LIMIT $max_edges
        MERGE (a)-[rv:{intended}]->(b)
        ON CREATE SET rv.created_at = datetime()
        SET rv.updated_at = datetime(),
            rv.layer = 'verified',
            rv.verified = true,
            rv.promoted_at = datetime(),
            rv.dimension = coalesce(r.dimension, rv.dimension),
            rv.evidence = coalesce(r.evidence, rv.evidence),
            rv.confidence = coalesce(r.confidence, r.weight, rv.confidence),
            rv.candidate_type = r.candidate_type
        DELETE r
        RETURN count(rv) AS promoted
        """
        try:
            rows = self._execute_write(
                query,
                {
                    "tenant_id": tenant_id,
                    "candidate_type": cand,
                    "min_conf": min_conf,
                    "require_evidence": req_ev,
                    "max_edges": max_edges,
                },
            )
            promoted = int(rows[0]["promoted"]) if rows else 0
            return {
                "ok": True,
                "tenant_id": tenant_id,
                "candidate_type": cand,
                "promote_to_typed": True,
                "relationship_type": intended,
                "promoted": promoted,
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

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

    def health_check(self, timeout: float = 5.0) -> bool:
        """Check if Neo4j is healthy (with timeout guard)."""
        import concurrent.futures
        def _check():
            try:
                result = self._execute_read("RETURN 1 AS ok")
                return result[0].get("ok") == 1
            except Exception:
                return False
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_check)
                return future.result(timeout=timeout)
        except (concurrent.futures.TimeoutError, Exception):
            logger.warning("Neo4j health_check timed out or failed")
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
    "CompoundCitation",
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
