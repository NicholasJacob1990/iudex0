"""
GLiNERExtractor — Zero-shot NER for Brazilian legal entities.

Complements LegalRegexExtractor by detecting entity variations that
regex patterns miss (e.g. "diploma licitatório", "norma geral de licitações").

Uses GLiNER (Generalist and Lightweight Model for NER) which runs on CPU
at ~300-500ms/chunk without any fine-tuning or API costs.

Usage in pipeline:
    pipe.add_component(GLiNERExtractor(), "gliner_extractor")
    pipe.connect("splitter", "gliner_extractor", input_config={"chunks": "splitter.chunks"})
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    from neo4j_graphrag.experimental.pipeline import Component, DataModel

    _HAS_NEO4J_GRAPHRAG = True
except ImportError:
    _HAS_NEO4J_GRAPHRAG = False

    class DataModel:  # type: ignore[no-redef]
        pass

    class Component:  # type: ignore[no-redef]
        pass


# =============================================================================
# DATA MODELS
# =============================================================================

if _HAS_NEO4J_GRAPHRAG:
    from neo4j_graphrag.experimental.pipeline import DataModel as _DM

    class GLiNERExtractionResult(_DM):
        """Result of GLiNER extraction: nodes and relationships."""
        nodes: List[Dict[str, Any]]
        relationships: List[Dict[str, Any]]
else:
    class GLiNERExtractionResult:  # type: ignore[no-redef]
        def __init__(self, nodes: list, relationships: list):
            self.nodes = nodes
            self.relationships = relationships


# =============================================================================
# COMPONENT
# =============================================================================

class GLiNERExtractor(Component if _HAS_NEO4J_GRAPHRAG else object):  # type: ignore[misc]
    """
    neo4j-graphrag Component that extracts legal entities via GLiNER zero-shot NER.

    GLiNER detects entities without fine-tuning by accepting a list of target
    entity labels at inference time. This captures variations that regex misses
    (e.g. "Lei nº 8.666/93" vs "diploma licitatório").

    The model is loaded once (singleton) and runs on CPU by default.
    """

    _model = None  # Class-level singleton

    LEGAL_LABELS = [
        "lei",
        "artigo",
        "sumula",
        "tribunal",
        "processo",
        "tema",
        "parte",
        "advogado",
        "juiz",
        "orgao_publico",
        "prazo",
        "valor_monetario",
        "data",
        "local",
        # Factual entity labels
        "pessoa",
        "empresa",
        "evento",
        "cpf",
        "cnpj",
    ]
    DEFAULT_LABELS = LEGAL_LABELS
    DOMAIN_LABEL_PRESETS = {
        "legal": LEGAL_LABELS,
        "general": [
            "person",
            "organization",
            "location",
            "event",
            "product",
            "date",
            "time",
            "money",
            "law",
            "document",
        ],
        "finance": [
            "company",
            "ticker",
            "index",
            "currency",
            "money",
            "date",
            "person",
            "organization",
            "location",
        ],
        "health": [
            "disease",
            "symptom",
            "drug",
            "treatment",
            "person",
            "organization",
            "date",
            "location",
        ],
    }

    def __init__(
        self,
        *,
        threshold: float = 0.5,
        create_relationships: bool = True,
        labels: Optional[List[str]] = None,
    ):
        """
        Args:
            threshold: Minimum confidence score for entity detection (0.0 - 1.0).
            create_relationships: If True, create RELATED_TO relationships
                between entities extracted from the same chunk.
            labels: Optional explicit label list for GLiNER (domain-specific).
                When omitted, reads GLINER_LABELS env var (CSV/JSON), then falls back
                to DEFAULT_LABELS.
        """
        if _HAS_NEO4J_GRAPHRAG:
            super().__init__()
        self._threshold = threshold
        self._create_relationships = create_relationships
        self._labels = labels or self._resolve_labels_from_env()

    @classmethod
    def _get_model(cls):
        """Lazy-load GLiNER model (singleton — loaded once per process)."""
        if cls._model is None:
            from gliner import GLiNER

            model_name = os.getenv("GLINER_MODEL", "urchade/gliner_medium-v2.1")
            logger.info("Loading GLiNER model: %s", model_name)
            cls._model = GLiNER.from_pretrained(model_name)
            logger.info("GLiNER model loaded successfully")
        return cls._model

    @classmethod
    def _resolve_labels_from_env(cls) -> List[str]:
        """
        Resolve extraction labels from env.

        Supported formats:
        - CSV: "person,organization,product"
        - JSON list: ["person","organization","product"]
        """
        raw = (os.getenv("GLINER_LABELS") or "").strip()
        if not raw:
            domain = (os.getenv("KG_BUILDER_DOMAIN") or "legal").strip().lower()
            return list(cls.DOMAIN_LABEL_PRESETS.get(domain, cls.DEFAULT_LABELS))

        labels: List[str] = []
        if raw.startswith("[") and raw.endswith("]"):
            try:
                import json

                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    labels = [str(x).strip().lower() for x in parsed if str(x).strip()]
            except Exception:
                labels = []
        else:
            labels = [part.strip().lower() for part in raw.split(",") if part.strip()]

        return labels or list(cls.DEFAULT_LABELS)

    async def run(self, chunks: List[Dict[str, Any]]) -> GLiNERExtractionResult:
        """
        Extract legal entities from chunks using GLiNER zero-shot NER.

        Args:
            chunks: List of chunk dicts with at least 'text' (and optionally 'chunk_uid').

        Returns:
            GLiNERExtractionResult with nodes and relationships.
        """
        model = self._get_model()
        all_nodes: List[Dict[str, Any]] = []
        all_rels: List[Dict[str, Any]] = []
        seen_ids: set = set()

        for chunk in chunks:
            text = chunk.get("text", "")
            if not text:
                continue

            chunk_uid = chunk.get("chunk_uid", "")

            # GLiNER predict_entities is synchronous — run in thread pool
            entities = await asyncio.to_thread(
                model.predict_entities,
                text,
                self._labels,
                threshold=self._threshold,
            )

            chunk_entity_ids = []
            for ent in entities:
                entity_id = _make_entity_id(ent["label"], ent["text"])

                if entity_id not in seen_ids:
                    seen_ids.add(entity_id)

                    label = _LABEL_MAP.get(ent["label"].lower(), "Entity")
                    all_nodes.append({
                        "id": entity_id,
                        "label": label,
                        "properties": {
                            "name": ent["text"],
                            "entity_type": ent["label"],
                            "confidence": round(ent["score"], 4),
                            "source": "gliner",
                        },
                    })

                chunk_entity_ids.append(entity_id)

                # Chunk -> Entity relationship
                if chunk_uid:
                    all_rels.append({
                        "start": chunk_uid,
                        "end": entity_id,
                        "type": "MENTIONS",
                        "properties": {"source": "gliner"},
                    })

            # Co-occurrence relationships within same chunk
            if self._create_relationships and len(chunk_entity_ids) > 1:
                for i, eid1 in enumerate(chunk_entity_ids):
                    for eid2 in chunk_entity_ids[i + 1:]:
                        all_rels.append({
                            "start": eid1,
                            "end": eid2,
                            "type": "RELATED_TO",
                            "properties": {"source": "gliner_co_occurrence"},
                        })

        logger.info(
            "GLiNERExtractor: %d nodes, %d relationships from %d chunks",
            len(all_nodes), len(all_rels), len(chunks),
        )

        return GLiNERExtractionResult(nodes=all_nodes, relationships=all_rels)


# =============================================================================
# HELPERS
# =============================================================================

_LABEL_MAP = {
    "lei": "Lei",
    "artigo": "Artigo",
    "sumula": "Sumula",
    "processo": "Processo",
    "tribunal": "Tribunal",
    "tema": "Tema",
    "parte": "Actor",
    "advogado": "Actor",
    "juiz": "Actor",
    "orgao_publico": "OrgaoPublico",
    "prazo": "Prazo",
    "valor_monetario": "ValorMonetario",
    "data": "DataJuridica",
    "local": "Local",
    "oab": "OAB",
    # Factual labels
    "pessoa": "Pessoa",
    "empresa": "Empresa",
    "evento": "Evento",
    "cpf": "Pessoa",
    "cnpj": "Empresa",
}


def _make_entity_id(label: str, text: str) -> str:
    """Generate deterministic entity ID from label + text."""
    normalized = text.strip().lower()
    raw = f"{label}:{normalized}"
    return f"gliner_{hashlib.md5(raw.encode()).hexdigest()[:12]}"
