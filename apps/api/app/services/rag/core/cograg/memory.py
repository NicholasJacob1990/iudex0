"""
CognitiveMemory — Persistent consultation memory for CogRAG.

This module implements the PLANO_COGRAG.md intent:
- Store consultations as graph nodes in Neo4j: (:Consulta)-[:DECOMPOSTA_EM]->(:SubPergunta)
- Attach human corrections: (:Consulta)-[:CORRIGIDA_POR]->(:Correcao)
- Allow retrieving similar consultations for reuse (MVP similarity via keyword Jaccard)

Notes:
- Neo4j properties don't support nested dicts; we store structured payloads as JSON strings.
- Similarity is MVP (keywords). If you later add a vector index in Neo4j, swap the scoring method.
"""

from __future__ import annotations

import datetime as _dt
import json
import re
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple


def _now_utc_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def _json_dumps(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except Exception:
        return json.dumps(str(value), ensure_ascii=False, separators=(",", ":"))


def _extract_keywords_pt(query: str) -> List[str]:
    stopwords = {
        "o", "a", "os", "as", "um", "uma", "uns", "umas",
        "de", "da", "do", "das", "dos", "em", "na", "no", "nas", "nos",
        "para", "por", "com", "sem", "sobre", "entre", "até", "como",
        "que", "qual", "quais", "quando", "onde", "porque", "porquê",
        "e", "ou", "mas", "se", "não", "é", "são", "foi", "foram",
        "ser", "estar", "ter", "haver", "pode", "podem", "deve", "devem",
    }
    words = re.findall(r"\b\w{3,}\b", (query or "").lower())
    keywords = [w for w in words if w not in stopwords]
    return keywords[:25]


def _jaccard(a: Sequence[str], b: Sequence[str]) -> float:
    sa = set(a)
    sb = set(b)
    if not sa or not sb:
        return 0.0
    inter = sa & sb
    union = sa | sb
    return len(inter) / len(union) if union else 0.0


@dataclass
class SimilarConsultation:
    consulta_id: str
    similarity: float
    query: str
    created_at: Optional[str] = None
    mind_map: Optional[Dict[str, Any]] = None
    sub_questions: Optional[List[Dict[str, Any]]] = None
    sub_answers: Optional[List[Dict[str, Any]]] = None
    answer_summary: Optional[str] = None
    penalized_refs: Optional[List[str]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "consulta_id": self.consulta_id,
            "similarity": round(float(self.similarity), 3),
            "query": self.query,
            "created_at": self.created_at,
            "mind_map": self.mind_map,
            "sub_questions": self.sub_questions or [],
            "sub_answers": self.sub_answers or [],
            "answer_summary": self.answer_summary,
            "penalized_refs": self.penalized_refs or [],
        }


class CognitiveMemory:
    """
    CogRAG consultation memory with Neo4j persistence (preferred) and MVP similarity.
    """

    _CYPHER_STORE = """
    MERGE (c:Consulta {id: $consulta_id})
    SET c.tenant_id = $tenant_id,
        c.pergunta_usuario = $query,
        c.data = $created_at,
        c.scope = $scope,
        c.case_id = $case_id,
        c.keywords = $keywords,
        c.mind_map_json = $mind_map_json,
        c.evidence_map_json = $evidence_map_json,
        c.resposta_final = $integrated_response,
        c.citations_used = $citations_used,
        c.verification_status = $verification_status,
        c.verification_issues = $verification_issues
    WITH c
    UNWIND $sub_rows AS row
      MERGE (sp:SubPergunta {consulta_id: $consulta_id, node_id: row.node_id})
      SET sp.texto = row.question,
          sp.resposta = row.answer,
          sp.confidence = row.confidence,
          sp.citacoes = row.citations,
          sp.evidence_refs = row.evidence_refs
      MERGE (c)-[:DECOMPOSTA_EM]->(sp)
    RETURN c.id AS consulta_id
    """

    _CYPHER_LIST_RECENT = """
    MATCH (c:Consulta)
    WHERE c.tenant_id = $tenant_id
    RETURN c.id AS consulta_id,
           c.pergunta_usuario AS query,
           c.keywords AS keywords,
           c.data AS created_at,
           c.mind_map_json AS mind_map_json,
           c.resposta_final AS answer_summary
    ORDER BY c.data DESC
    LIMIT $limit
    """

    _CYPHER_LOAD_SUBPERGUNTAS = """
    MATCH (c:Consulta {id: $consulta_id})-[:DECOMPOSTA_EM]->(sp:SubPergunta)
    RETURN sp.node_id AS node_id,
           sp.texto AS question,
           sp.resposta AS answer,
           sp.confidence AS confidence,
           sp.citacoes AS citations,
           sp.evidence_refs AS evidence_refs
    ORDER BY sp.node_id ASC
    """

    _CYPHER_LIST_PENALTIES = """
    MATCH (c:Consulta {id: $consulta_id})-[:CORRIGIDA_POR]->(co:Correcao)
    RETURN co.bad_refs AS bad_refs
    """

    _CYPHER_APPLY_CORRECTION = """
    MATCH (c:Consulta {id: $consulta_id})
    WHERE c.tenant_id = $tenant_id
    CREATE (co:Correcao {
      id: $correcao_id,
      texto: $texto,
      usuario_id: $usuario_id,
      data: $created_at,
      tipo: $tipo,
      bad_refs: $bad_refs
    })
    MERGE (c)-[:CORRIGIDA_POR]->(co)
    RETURN co.id AS correcao_id
    """

    def __init__(self, neo4j: Any):
        self._neo4j = neo4j

    @staticmethod
    def is_available() -> bool:
        try:
            from app.services.rag.core.neo4j_mvp import get_neo4j_service  # noqa: F401
            return True
        except Exception:
            return False

    @classmethod
    def from_neo4j_service(cls) -> Optional["CognitiveMemory"]:
        try:
            from app.services.rag.core.neo4j_mvp import get_neo4j_service
            neo4j = get_neo4j_service()
            return cls(neo4j)
        except Exception:
            return None

    def store_consultation(
        self,
        *,
        query: str,
        tenant_id: str,
        scope: str,
        case_id: Optional[str],
        mind_map: Optional[Dict[str, Any]],
        sub_questions: List[Dict[str, Any]],
        evidence_map: Dict[str, Any],
        sub_answers: Optional[List[Dict[str, Any]]] = None,
        integrated_response: Optional[str] = None,
        citations_used: Optional[List[str]] = None,
        verification_status: Optional[str] = None,
        verification_issues: Optional[List[str]] = None,
        consulta_id: Optional[str] = None,
        created_at: Optional[str] = None,
    ) -> str:
        created_at = created_at or _now_utc_iso()
        consulta_id = consulta_id or str(uuid.uuid4())
        keywords = _extract_keywords_pt(query)

        # Build per-subquestion rows
        answers_by_node: Dict[str, Dict[str, Any]] = {a.get("node_id", ""): a for a in (sub_answers or [])}
        sub_rows: List[Dict[str, Any]] = []
        for sq in sub_questions:
            node_id = str(sq.get("node_id", "")).strip()
            question = sq.get("question", "")
            ans = answers_by_node.get(node_id, {})
            sub_rows.append(
                {
                    "node_id": node_id,
                    "question": question,
                    "answer": ans.get("answer"),
                    "confidence": ans.get("confidence"),
                    "citations": ans.get("citations") or [],
                    "evidence_refs": ans.get("evidence_refs") or [],
                }
            )

        params = {
            "consulta_id": consulta_id,
            "tenant_id": tenant_id,
            "query": query,
            "created_at": created_at,
            "scope": scope,
            "case_id": case_id,
            "keywords": keywords,
            "mind_map_json": _json_dumps(mind_map or {}),
            "evidence_map_json": _json_dumps(evidence_map or {}),
            "integrated_response": integrated_response,
            "citations_used": citations_used or [],
            "verification_status": verification_status or "",
            "verification_issues": verification_issues or [],
            "sub_rows": sub_rows,
        }

        self._neo4j._execute_write(self._CYPHER_STORE, params)
        return consulta_id

    def apply_correction(
        self,
        *,
        consulta_id: str,
        tenant_id: str,
        texto: str,
        usuario_id: str,
        tipo: str = "juridico",
        bad_refs: Optional[List[str]] = None,
        created_at: Optional[str] = None,
    ) -> str:
        created_at = created_at or _now_utc_iso()
        correcao_id = str(uuid.uuid4())
        params = {
            "consulta_id": consulta_id,
            "tenant_id": tenant_id,
            "correcao_id": correcao_id,
            "texto": texto,
            "usuario_id": usuario_id,
            "created_at": created_at,
            "tipo": tipo,
            "bad_refs": bad_refs or [],
        }
        rows = self._neo4j._execute_write(self._CYPHER_APPLY_CORRECTION, params)
        if rows and rows[0].get("correcao_id"):
            return str(rows[0]["correcao_id"])
        return correcao_id

    def find_similar_consultation(
        self,
        *,
        query: str,
        tenant_id: str,
        threshold: float = 0.85,
        limit: int = 1,
        max_candidates: int = 50,
        load_sub_answers: bool = True,
    ) -> Optional[SimilarConsultation]:
        query_keywords = _extract_keywords_pt(query)
        if not query_keywords:
            return None

        rows = self._neo4j._execute_read(
            self._CYPHER_LIST_RECENT,
            {"tenant_id": tenant_id, "limit": int(max_candidates)},
        )
        if not rows:
            return None

        scored: List[Tuple[float, Dict[str, Any]]] = []
        for r in rows:
            kw = r.get("keywords") or _extract_keywords_pt(r.get("query", ""))
            similarity = _jaccard(query_keywords, kw)
            if similarity >= float(threshold):
                scored.append((similarity, r))
        if not scored:
            return None

        scored.sort(key=lambda x: x[0], reverse=True)
        best_similarity, best = scored[0]

        mind_map: Optional[Dict[str, Any]] = None
        try:
            mm = best.get("mind_map_json") or "{}"
            mind_map = json.loads(mm) if isinstance(mm, str) else None
        except Exception:
            mind_map = None

        sub_answers: Optional[List[Dict[str, Any]]] = None
        if load_sub_answers:
            sub_rows = self._neo4j._execute_read(
                self._CYPHER_LOAD_SUBPERGUNTAS,
                {"consulta_id": best.get("consulta_id")},
            )
            sub_answers = [
                {
                    "node_id": sr.get("node_id"),
                    "question": sr.get("question"),
                    "answer": sr.get("answer"),
                    "confidence": sr.get("confidence"),
                    "citations": sr.get("citations") or [],
                    "evidence_refs": sr.get("evidence_refs") or [],
                }
                for sr in (sub_rows or [])
            ]

        # Aggregate penalties from corrections (bad refs)
        penalties_rows = self._neo4j._execute_read(
            self._CYPHER_LIST_PENALTIES,
            {"consulta_id": best.get("consulta_id")},
        )
        penalized: List[str] = []
        for pr in penalties_rows or []:
            bad = pr.get("bad_refs") or []
            if isinstance(bad, list):
                for b in bad:
                    bb = str(b).strip()
                    if bb and bb not in penalized:
                        penalized.append(bb)

        # Best effort: infer sub_questions list from stored sub_answers
        sub_questions = [{"node_id": sa.get("node_id"), "question": sa.get("question")} for sa in (sub_answers or [])]

        return SimilarConsultation(
            consulta_id=str(best.get("consulta_id")),
            similarity=float(best_similarity),
            query=str(best.get("query", "")),
            created_at=best.get("created_at"),
            mind_map=mind_map,
            sub_questions=sub_questions,
            sub_answers=sub_answers or [],
            answer_summary=best.get("answer_summary"),
            penalized_refs=penalized,
        )

