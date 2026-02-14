"""
ArgumentLLMExtractor — Extract claims, evidence, stance via Gemini Flash structured output.

Uses google-genai SDK with response_json_schema for guaranteed JSON extraction.
Cost: ~$0.01/document (Gemini Flash pricing).

Usage:
    extractor = ArgumentLLMExtractor()
    result = await extractor.extract(text, chunk_uid="c1", doc_id="d1", tenant_id="t1")
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# JSON SCHEMA for structured extraction
# =============================================================================

ARGUMENT_EXTRACTION_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "claims": {
            "type": "array",
            "description": "Teses e contrateses jurídicas extraídas do texto",
            "items": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "Texto da tese/contratese (máximo 250 caracteres)",
                    },
                    "claim_type": {
                        "type": "string",
                        "enum": ["tese", "contratese", "fato", "conclusao"],
                        "description": "Tipo da alegação",
                    },
                    "polarity": {
                        "type": "integer",
                        "enum": [1, -1, 0],
                        "description": "+1 para afirmação, -1 para negação, 0 para neutro",
                    },
                    "confidence": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 1,
                        "description": "Confiança na extração (0.0 a 1.0)",
                    },
                    "supports": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Índices de claims que esta tese suporta",
                    },
                    "opposes": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Índices de claims que esta tese contesta",
                    },
                    "cited_entities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Entidades jurídicas citadas (ex: 'Lei 8.666/93', 'Art. 5º')",
                    },
                },
                "required": ["text", "claim_type", "polarity", "confidence"],
            },
            "maxItems": 10,
        },
        "evidence": {
            "type": "array",
            "description": "Evidências documentais encontradas",
            "items": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "Descrição da evidência (máximo 200 caracteres)",
                    },
                    "evidence_type": {
                        "type": "string",
                        "enum": ["jurisprudencia", "doutrina", "fato", "legislacao", "documento", "pericia"],
                        "description": "Tipo da evidência",
                    },
                    "stance": {
                        "type": "string",
                        "enum": ["pro", "contra", "neutro"],
                        "description": "Posição da evidência em relação às teses",
                    },
                    "supports_claims": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Índices de claims que esta evidência suporta",
                    },
                },
                "required": ["text", "evidence_type", "stance"],
            },
            "maxItems": 8,
        },
        "actors": {
            "type": "array",
            "description": "Atores processuais mencionados",
            "items": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Nome ou designação do ator",
                    },
                    "role": {
                        "type": "string",
                        "enum": ["autor", "reu", "juiz", "relator", "perito", "testemunha", "advogado", "mp", "parte"],
                        "description": "Papel processual",
                    },
                    "stance": {
                        "type": "string",
                        "enum": ["asserts", "disputes", "neutral"],
                        "description": "Posição argumentativa do ator",
                    },
                    "argues_claims": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Índices de claims que este ator defende",
                    },
                },
                "required": ["name", "role"],
            },
            "maxItems": 6,
        },
        "issues": {
            "type": "array",
            "description": "Questões jurídicas controvertidas",
            "items": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "Descrição da questão (máximo 200 caracteres)",
                    },
                    "domain": {
                        "type": "string",
                        "enum": ["constitucional", "civil", "penal", "trabalhista", "tributario", "administrativo", "processual", "outro"],
                        "description": "Área do direito",
                    },
                    "raised_by_claims": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Índices de claims que levantam esta questão",
                    },
                },
                "required": ["text", "domain"],
            },
            "maxItems": 4,
        },
    },
    "required": ["claims", "evidence"],
    "additionalProperties": False,
}


# =============================================================================
# PROMPT
# =============================================================================

EXTRACTION_PROMPT = """Analise o texto jurídico abaixo e extraia a estrutura argumentativa.

INSTRUÇÕES:
1. Identifique TESES (afirmações jurídicas) e CONTRATESES (contestações)
2. Identifique EVIDÊNCIAS (documentos, jurisprudências, fatos que suportam/contestam)
3. Identifique ATORES (partes, juízes, advogados) e suas posições
4. Identifique QUESTÕES JURÍDICAS controvertidas
5. Conecte claims entre si via supports/opposes (índices no array)
6. Conecte evidence a claims via supports_claims (índices no array)

REGRAS:
- Textos de claims: máximo 250 caracteres, em português
- Textos de evidência: máximo 200 caracteres
- Polarity: +1 para afirmação, -1 para negação/contestação, 0 para neutro
- Extraia SOMENTE o que estiver EXPLÍCITO no texto (anti-contaminação).
- Se uma tese/evidência/ator NÃO tiver âncora textual clara, OMITA.
- Confidence: use apenas valores altos (0.9 a 1.0) quando explícito; caso contrário, OMITA o item.
- cited_entities: entidades legais mencionadas (Lei X, Art. Y, Súmula Z)

TEXTO:
{text}
"""


# =============================================================================
# EXTRACTOR
# =============================================================================

class ArgumentLLMExtractor:
    """
    Extract argument structures from legal text using Gemini Flash.

    Uses structured output (response_json_schema) for guaranteed valid JSON.
    """

    def __init__(
        self,
        *,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ):
        # Keep ArgumentRAG extraction independent from chat models.
        # Prefer a fast "flash" model, but allow explicit override.
        self._model = (
            model
            or os.getenv("ARGUMENT_LLM_MODEL")
            or os.getenv("GEMINI_3_FLASH_API_MODEL")
            or os.getenv("KG_BUILDER_LLM_MODEL")
            or "gemini-2.0-flash"
        )
        self._api_key = api_key or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._client = None

    def _get_client(self):
        """Lazy client initialization."""
        if self._client is not None:
            return self._client

        try:
            from google import genai
            self._client = genai.Client(api_key=self._api_key)
            return self._client
        except ImportError:
            raise ImportError("google-genai not installed. Run: pip install google-genai")

    async def extract(
        self,
        text: str,
        *,
        chunk_uid: str = "",
        doc_id: str = "",
        tenant_id: str = "",
        max_text_len: int = 8000,
    ) -> Dict[str, Any]:
        """
        Extract argument structures from text using Gemini Flash.

        Args:
            text: Legal text to analyze
            chunk_uid: Chunk UID for provenance
            doc_id: Document ID for provenance
            tenant_id: Tenant ID
            max_text_len: Max text length to send to LLM

        Returns:
            Extracted argument structure dict (claims, evidence, actors, issues)
        """
        if not text or not text.strip():
            return {"claims": [], "evidence": [], "actors": [], "issues": []}

        text = text[:max_text_len]
        prompt = EXTRACTION_PROMPT.format(text=text)

        try:
            client = self._get_client()
            from google.genai import types as genai_types

            config = genai_types.GenerateContentConfig(
                max_output_tokens=self._max_tokens,
                temperature=self._temperature,
                response_mime_type="application/json",
                response_json_schema=ARGUMENT_EXTRACTION_SCHEMA,
            )

            response = await client.aio.models.generate_content(
                model=self._model,
                contents=prompt,
                config=config,
            )

            # Extract text from response
            result_text = ""
            if hasattr(response, "text"):
                result_text = response.text
            elif hasattr(response, "candidates") and response.candidates:
                for part in response.candidates[0].content.parts:
                    if hasattr(part, "text"):
                        result_text += part.text

            if not result_text:
                logger.warning("Empty response from Gemini for chunk %s", chunk_uid)
                return {"claims": [], "evidence": [], "actors": [], "issues": []}

            import json
            result = json.loads(result_text)

            # Validate structure
            if not isinstance(result, dict):
                return {"claims": [], "evidence": [], "actors": [], "issues": []}

            # Conservative post-filter to avoid "reasoning contamination":
            # keep only high-confidence items unless explicitly configured.
            min_conf = float(os.getenv("ARGUMENT_LLM_MIN_CONFIDENCE", "0.85") or "0.85")
            try:
                claims = [
                    c for c in (result.get("claims") or [])
                    if isinstance(c, dict) and float(c.get("confidence", 0.0) or 0.0) >= min_conf
                ]
                evidence = [
                    e for e in (result.get("evidence") or [])
                    if isinstance(e, dict)
                ]
                actors = [a for a in (result.get("actors") or []) if isinstance(a, dict)]
                issues = [i for i in (result.get("issues") or []) if isinstance(i, dict)]
                result = {"claims": claims, "evidence": evidence, "actors": actors, "issues": issues}
            except Exception:
                # Fail-open (but still returns whatever was parsed)
                pass

            logger.info(
                "LLM extracted %d claims, %d evidence, %d actors, %d issues from chunk %s",
                len(result.get("claims", [])),
                len(result.get("evidence", [])),
                len(result.get("actors", [])),
                len(result.get("issues", [])),
                chunk_uid,
            )

            return result

        except Exception as e:
            logger.error("LLM extraction failed for chunk %s: %s", chunk_uid, e)
            return {"claims": [], "evidence": [], "actors": [], "issues": []}

    async def extract_and_ingest(
        self,
        text: str,
        *,
        chunk_uid: str,
        doc_id: str,
        doc_hash: str,
        tenant_id: str,
        case_id: Optional[str] = None,
        scope: str = "global",
    ) -> Dict[str, Any]:
        """
        Extract argument structures and ingest into Neo4j.

        Combines LLM extraction with ArgumentNeo4jService ingest.
        Returns stats dict.
        """
        result = await self.extract(
            text, chunk_uid=chunk_uid, doc_id=doc_id, tenant_id=tenant_id,
        )

        if not result.get("claims"):
            return {"llm_claims": 0, "llm_evidence": 0, "ingested": False}

        try:
            from app.services.rag.core.argument_neo4j import get_argument_neo4j, ArgumentCypher

            svc = get_argument_neo4j()
            stats = {"llm_claims": 0, "llm_evidence": 0, "llm_actors": 0, "llm_relationships": 0}
            cite_links = 0

            # Ingest claims
            claim_ids = []
            for i, claim in enumerate(result.get("claims", [])):
                import hashlib
                claim_id = hashlib.sha256(
                    f"llm:{doc_id}:{chunk_uid}:{i}".encode()
                ).hexdigest()[:16]

                svc._execute_write(ArgumentCypher.MERGE_CLAIM, {
                    "claim_id": claim_id,
                    "text": claim["text"][:260],
                    "claim_type": claim.get("claim_type", "tese"),
                    "polarity": claim.get("polarity", 0),
                    "confidence": claim.get("confidence", 0.7),
                    "source_chunk_uid": chunk_uid,
                    "tenant_id": tenant_id,
                    "case_id": case_id,
                    "scope": scope,
                })
                claim_ids.append(claim_id)
                stats["llm_claims"] += 1

                # Link chunk -> claim
                try:
                    svc._execute_write(ArgumentCypher.LINK_CHUNK_CLAIM, {
                        "chunk_uid": chunk_uid,
                        "claim_id": claim_id,
                    })
                    stats["llm_relationships"] += 1
                except Exception:
                    pass

                # Claim-to-claim relationships
                for sup_idx in claim.get("supports", []):
                    if 0 <= sup_idx < len(claim_ids) and sup_idx != i:
                        try:
                            svc._execute_write(ArgumentCypher.LINK_CLAIM_SUPPORTS, {
                                "from_claim_id": claim_id,
                                "to_claim_id": claim_ids[sup_idx],
                                "weight": claim.get("confidence", 0.7),
                            })
                            stats["llm_relationships"] += 1
                        except Exception:
                            pass

                for opp_idx in claim.get("opposes", []):
                    if 0 <= opp_idx < len(claim_ids) and opp_idx != i:
                        try:
                            svc._execute_write(ArgumentCypher.LINK_CLAIM_OPPOSES, {
                                "from_claim_id": claim_id,
                                "to_claim_id": claim_ids[opp_idx],
                                "weight": claim.get("confidence", 0.7),
                            })
                            stats["llm_relationships"] += 1
                        except Exception:
                            pass

                # Link claim -> cited legal entities (best-effort, only if entity_id resolves)
                cited = claim.get("cited_entities") or []
                if isinstance(cited, list) and cited:
                    try:
                        from app.services.rag.core.neo4j_mvp import Neo4jEntityExtractor
                    except Exception:
                        Neo4jEntityExtractor = None
                    for raw in cited[:8]:
                        if not raw or not isinstance(raw, str):
                            continue
                        ent_id = ""
                        if Neo4jEntityExtractor is not None:
                            try:
                                extracted = Neo4jEntityExtractor.extract(raw)
                                if extracted and isinstance(extracted, list):
                                    ent_id = str(extracted[0].get("entity_id") or "").strip()
                            except Exception:
                                ent_id = ""
                        if not ent_id:
                            continue
                        try:
                            svc._execute_write(ArgumentCypher.LINK_CLAIM_ENTITY, {
                                "claim_id": claim_id,
                                "entity_id": ent_id,
                            })
                            cite_links += 1
                            stats["llm_relationships"] += 1
                        except Exception:
                            pass

            # Ingest evidence
            for j, ev in enumerate(result.get("evidence", [])):
                import hashlib
                evidence_id = hashlib.sha256(
                    f"llm_ev:{doc_id}:{chunk_uid}:{j}".encode()
                ).hexdigest()[:16]

                from app.services.rag.core.kg_builder.evidence_scorer import score_evidence
                weight = score_evidence(ev)

                svc._execute_write(ArgumentCypher.MERGE_EVIDENCE, {
                    "evidence_id": evidence_id,
                    "text": ev["text"][:500],
                    "evidence_type": ev.get("evidence_type", "documento"),
                    "weight": weight,
                    "doc_id": doc_id,
                    "chunk_id": chunk_uid,
                    "source_chunk_uid": chunk_uid,
                    "tenant_id": tenant_id,
                    "scope": scope,
                    "title": ev["text"][:80],
                })
                stats["llm_evidence"] += 1

                # Link evidence -> claims
                for claim_idx in ev.get("supports_claims", []):
                    if 0 <= claim_idx < len(claim_ids):
                        stance = "contra" if ev.get("stance") == "contra" else "pro"
                        try:
                            svc._execute_write(ArgumentCypher.LINK_EVIDENCE_CLAIM, {
                                "evidence_id": evidence_id,
                                "claim_id": claim_ids[claim_idx],
                                "stance": stance,
                                "weight": weight,
                            })
                            stats["llm_relationships"] += 1
                        except Exception:
                            pass

            # Ingest actors
            for actor in result.get("actors", []):
                import hashlib
                actor_id = hashlib.sha256(
                    f"actor:{actor['name']}".encode()
                ).hexdigest()[:16]

                svc._execute_write(ArgumentCypher.MERGE_ACTOR, {
                    "actor_id": actor_id,
                    "name": actor["name"],
                    "role": actor.get("role", "parte"),
                    "tenant_id": tenant_id,
                })
                stats["llm_actors"] += 1

                # Link actor -> claims
                for claim_idx in actor.get("argues_claims", []):
                    if 0 <= claim_idx < len(claim_ids):
                        try:
                            svc._execute_write(ArgumentCypher.LINK_ACTOR_CLAIM, {
                                "actor_id": actor_id,
                                "claim_id": claim_ids[claim_idx],
                                "stance": actor.get("stance", "neutral"),
                            })
                            stats["llm_relationships"] += 1
                        except Exception:
                            pass

            # Ingest issues
            for issue in result.get("issues", []):
                import hashlib
                issue_id = hashlib.sha256(
                    f"issue:{issue['text']}".encode()
                ).hexdigest()[:16]

                svc._execute_write(ArgumentCypher.MERGE_ISSUE, {
                    "issue_id": issue_id,
                    "text": issue["text"][:200],
                    "domain": issue.get("domain", "outro"),
                    "tenant_id": tenant_id,
                    "case_id": case_id,
                })

                # Link claims -> issues
                for claim_idx in issue.get("raised_by_claims", []):
                    if 0 <= claim_idx < len(claim_ids):
                        try:
                            svc._execute_write(ArgumentCypher.LINK_CLAIM_ISSUE, {
                                "claim_id": claim_ids[claim_idx],
                                "issue_id": issue_id,
                            })
                            stats["llm_relationships"] += 1
                        except Exception:
                            pass

            stats["ingested"] = True
            stats["llm_cite_links"] = cite_links
            return stats

        except Exception as e:
            logger.error("LLM ingest failed for chunk %s: %s", chunk_uid, e)
            return {"llm_claims": 0, "llm_evidence": 0, "ingested": False, "error": str(e)}
