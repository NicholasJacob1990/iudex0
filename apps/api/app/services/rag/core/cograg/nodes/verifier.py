"""
CogGRAG Verifier Node — Dual-LLM consistency verification.

Implements Phase 3 from CogGRAG paper (2503.06567v2):
- LLM_ver checks if answers are consistent with evidence
- Detects hallucinations, unsupported claims, logical errors
- Triggers rethink if verification fails

Uses separate LLM call for verification (can be same or different model).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("rag.cograg.verifier")

try:
    from app.services.prompt_policies import EVIDENCE_POLICY_COGRAG
except Exception:
    EVIDENCE_POLICY_COGRAG = "Use APENAS as evidencias fornecidas. Se insuficientes, diga que e insuficiente. Nao invente."


# ═══════════════════════════════════════════════════════════════════════════
# Prompts (Portuguese Legal Domain)
# ═══════════════════════════════════════════════════════════════════════════

VERIFICATION_PROMPT = """Você é um verificador jurídico rigoroso.

{evidence_policy}

Analise se a resposta abaixo é consistente com as evidências fornecidas no bloco <chunks>.
Quando houver evidência em grafo (<KG_PATHS>/<KG_TRIPLES>), use-a para checar coerência relacional (não apenas presença de tokens).

<chunks>
{evidence}
</chunks>

<query>
{question}
</query>

**Resposta a Verificar:** {answer}

**Verifique:**
1. A resposta está fundamentada nas evidências?
2. Há afirmações sem suporte nas evidências (alucinações)?
3. As citações legais estão corretas?
4. Há erros lógicos ou contradições?
5. Se houver marcadores [ref:...], eles aparecem em <chunks> e são compatíveis com o que foi afirmado?
6. Se houver marcadores [path:...], eles aparecem em <KG_PATHS> e o caminho citado sustenta a afirmação (sentido/relacionamento)?

**Responda em JSON:**
```json
{{
  "is_consistent": true/false,
  "confidence": 0.0-1.0,
  "issues": ["lista de problemas encontrados"],
  "requires_new_search": true/false,
  "suggestion": "sugestão de correção se houver problemas"
}}
```"""

RETHINK_PROMPT = """A resposta anterior foi rejeitada pelo verificador. Reescreva a resposta corrigindo os problemas identificados.

{evidence_policy}

<chunks>
{evidence}
</chunks>

<query>
{question}
</query>

**Resposta Anterior:** {previous_answer}

**Problemas Identificados:**
{issues}

**Sugestão do Verificador:** {suggestion}

**Instruções:**
1. Corrija os problemas apontados
2. Baseie-se APENAS nas evidências
3. Se não houver evidência suficiente, indique claramente
4. Não invente informações
5. Preserve marcadores [ref:...] existentes; não crie refs novas se não houver evidência

**Nova Resposta:**"""


# ═══════════════════════════════════════════════════════════════════════════
# LLM Integration
# ═══════════════════════════════════════════════════════════════════════════

async def _call_llm(prompt: str, model: str = "gemini-2.0-flash") -> str:
    """Call LLM for verification. Uses Gemini by default."""
    try:
        from google import genai
        from google.genai.types import GenerateContentConfig

        client = genai.Client()
        t0 = time.perf_counter()
        response = await asyncio.to_thread(
            client.models.generate_content,
            model=model,
            contents=prompt,
            config=GenerateContentConfig(
                temperature=0.1,  # Lower temp for verification
                max_output_tokens=512,
            ),
        )
        latency_ms = (time.perf_counter() - t0) * 1000.0
        try:
            from app.services.rag.core.metrics import get_latency_collector

            get_latency_collector().record("cograg.llm.verifier", latency_ms)
        except Exception:
            pass
        return response.text.strip() if response.text else ""
    except Exception as e:
        logger.warning(f"[CogGRAG:Verifier] LLM call failed: {e}")
        return ""


def _parse_verification_result(response: str) -> Dict[str, Any]:
    """Parse JSON verification result from LLM response."""
    # Try to extract JSON from response
    import re

    # Look for JSON block
    json_match = re.search(r"```json\s*(.*?)\s*```", response, re.DOTALL)
    if json_match:
        json_str = json_match.group(1)
    else:
        # Try to find raw JSON
        json_match = re.search(r"\{[^{}]*\}", response, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
        else:
            # Fallback: assume approved if no JSON found
            return {
                "is_consistent": True,
                "confidence": 0.7,
                "issues": [],
                "requires_new_search": False,
                "suggestion": "",
            }

    try:
        result = json.loads(json_str)
        return {
            "is_consistent": bool(result.get("is_consistent", True)),
            "confidence": float(result.get("confidence", 0.7)),
            "issues": result.get("issues", []),
            "requires_new_search": bool(result.get("requires_new_search", False)),
            "suggestion": result.get("suggestion", ""),
        }
    except (json.JSONDecodeError, TypeError, ValueError):
        # Fallback: try to detect rejection signals
        lower_resp = response.lower()
        is_rejected = any(
            signal in lower_resp
            for signal in ["inconsistente", "não fundamentada", "alucinação", "incorreto", "falso"]
        )
        return {
            "is_consistent": not is_rejected,
            "confidence": 0.5,
            "issues": ["Não foi possível parsear resposta do verificador"],
            "requires_new_search": False,
            "suggestion": "",
        }


# ═══════════════════════════════════════════════════════════════════════════
# Evidence Formatting
# ═══════════════════════════════════════════════════════════════════════════

def _format_evidence_for_verification(evidence: Dict[str, Any], max_chunks: int = 3) -> str:
    """Format evidence for verification prompt (shorter than reasoner)."""
    chunks = []

    for key in ("local_results", "global_results", "chunk_results"):
        for chunk in evidence.get(key, [])[:max_chunks]:
            text = chunk.get("text", "") or chunk.get("preview", "")
            if text:
                ref_id = (
                    chunk.get("chunk_uid")
                    or chunk.get("_content_hash")
                    or chunk.get("id")
                    or ""
                )
                ref_tag = f"[ref:{ref_id}]" if ref_id else "[ref:unknown]"
                chunks.append(f"{ref_tag} {text[:300].strip()}")

    if not chunks:
        chunks_text = "Nenhuma evidência textual disponível."
    else:
        chunks_text = "\n".join(chunks[:max_chunks])

    paths = evidence.get("graph_paths") or []
    path_lines: List[str] = []
    for p in (paths or [])[:6]:
        if not isinstance(p, dict):
            continue
        uid = str(p.get("path_uid") or "").strip()
        text = str(p.get("path_text") or "").strip()
        if uid and text:
            path_lines.append(f"[path:{uid}] {text}")

    triples = evidence.get("graph_triples") or []
    triple_lines: List[str] = []
    for tr in (triples or [])[:10]:
        if isinstance(tr, dict) and tr.get("text"):
            triple_lines.append(str(tr["text"]))
        elif isinstance(tr, str):
            triple_lines.append(tr)

    blocks: List[str] = [chunks_text]
    if path_lines:
        blocks.append("\n<KG_PATHS>\n" + "\n".join(path_lines) + "\n</KG_PATHS>")
    if triple_lines:
        blocks.append("\n<KG_TRIPLES>\n" + "\n".join(triple_lines) + "\n</KG_TRIPLES>")

    return "\n".join(blocks).strip()


def _collect_valid_ref_ids(evidence: Dict[str, Any]) -> set:
    """Collect all valid [ref:...] ids from evidence chunks."""
    valid: set = set()
    for key in ("local_results", "global_results", "chunk_results"):
        for chunk in evidence.get(key, [])[:100]:
            rid = chunk.get("chunk_uid") or chunk.get("_content_hash") or chunk.get("id")
            if rid:
                valid.add(str(rid))
    return valid


def _collect_valid_path_ids(evidence: Dict[str, Any]) -> set:
    """Collect all valid [path:...] ids from evidence graph_paths."""
    valid: set = set()
    for p in (evidence.get("graph_paths") or [])[:200]:
        if isinstance(p, dict):
            uid = p.get("path_uid")
            if uid:
                valid.add(str(uid))
    return valid


def _collect_evidence_text(evidence: Dict[str, Any], *, max_total_chars: int = 12000) -> str:
    """Collect a concatenated evidence text snapshot for deterministic checks."""
    parts: List[str] = []
    total = 0
    for key in ("local_results", "global_results", "chunk_results"):
        for chunk in evidence.get(key, [])[:50]:
            text = chunk.get("text", "") or chunk.get("preview", "")
            if not text:
                continue
            snippet = text.strip()
            if not snippet:
                continue
            snippet = snippet[:900]
            parts.append(snippet)
            total += len(snippet)
            if total >= max_total_chars:
                return "\n\n".join(parts)[:max_total_chars]
    # Include graph triples as additional "evidence text" for deterministic matching.
    triples = evidence.get("graph_triples") or []
    if triples:
        parts.append("\n<KG_TRIPLES>")
        for tr in triples[:50]:
            if isinstance(tr, dict) and tr.get("text"):
                parts.append(str(tr["text"]))
            elif isinstance(tr, str):
                parts.append(tr)
        parts.append("</KG_TRIPLES>\n")

    # Include graph paths text (for deterministic snapshot + debugging).
    paths = evidence.get("graph_paths") or []
    if paths:
        parts.append("\n<KG_PATHS>")
        for p in paths[:50]:
            if not isinstance(p, dict):
                continue
            uid = str(p.get("path_uid") or "").strip()
            txt = str(p.get("path_text") or "").strip()
            if uid and txt:
                parts.append(f"[path:{uid}] {txt}")
        parts.append("</KG_PATHS>\n")

    return "\n\n".join(parts)[:max_total_chars]


def _extract_refs_from_answer(answer: str) -> List[str]:
    import re
    refs = re.findall(r"\[ref:([^\]]+)\]", answer or "")
    out: List[str] = []
    seen = set()
    for r in refs:
        rr = str(r).strip()
        if not rr or rr in seen:
            continue
        seen.add(rr)
        out.append(rr)
    return out


def _extract_paths_from_answer(answer: str) -> List[str]:
    import re
    paths = re.findall(r"\[path:([^\]]+)\]", answer or "")
    out: List[str] = []
    seen = set()
    for p in paths:
        pp = str(p).strip()
        if not pp or pp in seen:
            continue
        seen.add(pp)
        out.append(pp)
    return out


def _extract_legal_citations(answer: str) -> Dict[str, List[str]]:
    """
    Extract common Brazilian legal citation identifiers from an answer.

    Returns a dict with keys: cnj, art, lei, sumula.
    Values are normalized strings (e.g. "37", "8.112/90", "331").
    """
    import re

    text = answer or ""
    cnj = re.findall(r"\b\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}\b", text)
    arts = re.findall(r"\b[Aa]rt(?:igo)?\.?\s*(\d{1,4})", text)
    leis = re.findall(r"\b[Ll]ei\s+(?:n[º°]?\s*)?(\d+(?:\.\d+)?(?:/\d{2,4})?)", text)
    sumulas = re.findall(r"\b[Ss]úmula\s+(?:n[º°]?\s*)?(\d{1,4})", text)

    def _uniq(xs: List[str]) -> List[str]:
        out: List[str] = []
        seen = set()
        for x in xs:
            xx = str(x).strip()
            if not xx or xx in seen:
                continue
            seen.add(xx)
            out.append(xx)
        return out

    return {
        "cnj": _uniq(cnj),
        "art": _uniq(arts),
        "lei": _uniq(leis),
        "sumula": _uniq(sumulas),
    }


def _digits_pattern(digits: str) -> str:
    """
    Build a tolerant pattern that matches digits with optional non-digits between them.
    Example: "8112" -> "8\\D*1\\D*1\\D*2"
    """
    d = "".join(ch for ch in (digits or "") if ch.isdigit())
    if not d:
        return ""
    return r"\D*".join(list(d))


def _has_article_in_text(text: str, art_num: str) -> bool:
    import re
    n = "".join(ch for ch in (art_num or "") if ch.isdigit())
    if not n:
        return False
    pat = rf"\b(?:art(?:igo)?\.?)\s*0*{re.escape(n)}\s*[º°]?\b"
    return bool(re.search(pat, text, flags=re.IGNORECASE))


def _parse_law_id(law: str) -> Dict[str, str]:
    """
    Parse a law token extracted from answer (e.g. '8.112/90', '8666/93', '8112').
    Returns: {"num": "8112", "year": "90"} (year may be empty).
    """
    raw = (law or "").strip()
    if not raw:
        return {"num": "", "year": ""}
    if "/" in raw:
        left, right = raw.split("/", 1)
        num = "".join(ch for ch in left if ch.isdigit())
        year = "".join(ch for ch in right if ch.isdigit())
        if len(year) == 4:
            year = year[-2:]
        return {"num": num, "year": year}
    return {"num": "".join(ch for ch in raw if ch.isdigit()), "year": ""}


def _has_law_in_text(text: str, law_token: str) -> bool:
    import re
    parsed = _parse_law_id(law_token)
    num = parsed["num"]
    year = parsed["year"]
    if not num:
        return False

    num_pat = _digits_pattern(num)
    if not num_pat:
        return False

    # Require "lei" near number to avoid false positives.
    base = rf"\blei\b.{{0,80}}{num_pat}"
    if not year:
        return bool(re.search(base, text, flags=re.IGNORECASE))

    year2 = "".join(ch for ch in year if ch.isdigit())
    if not year2:
        return bool(re.search(base, text, flags=re.IGNORECASE))

    # Year can appear as "/90", "de 1990", "(1990)" etc.
    year_pat = rf"(?:/|de\s+|\(|,?\s*)(?:19|20)?{re.escape(year2)}\b"
    pat = rf"{base}.{{0,80}}{year_pat}"
    return bool(re.search(pat, text, flags=re.IGNORECASE))


def _has_sumula_in_text(text: str, sumula_num: str) -> bool:
    import re
    n = "".join(ch for ch in (sumula_num or "") if ch.isdigit())
    if not n:
        return False
    n_pat = _digits_pattern(n)
    if not n_pat:
        return False
    pat = rf"\bs[úu]mula\b.{{0,60}}{n_pat}\b"
    return bool(re.search(pat, text, flags=re.IGNORECASE))


def _has_cnj_in_text(text: str, cnj: str) -> bool:
    needle = (cnj or "").strip()
    return bool(needle) and (needle in (text or ""))


def _answer_is_abstaining(answer: str) -> bool:
    a = (answer or "").lower()
    return any(
        s in a
        for s in (
            "não encontrei evidência suficiente",
            "nao encontrei evidencia suficiente",
            "evidências insuficientes",
            "evidencias insuficientes",
            "não há evidência suficiente",
            "nao ha evidencia suficiente",
        )
    )


def _deterministic_verify_answer(answer_data: Dict[str, Any], evidence: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deterministic verification gate:
    - [ref:...] used in the answer must exist in evidence
    - Common legal citations (Art/Lei/Súmula/CNJ) must appear in evidence snapshot
    """
    answer = str(answer_data.get("answer", "") or "")
    issues: List[str] = []
    requires_new_search = False

    valid_refs = _collect_valid_ref_ids(evidence)
    valid_paths = _collect_valid_path_ids(evidence)
    referenced = []
    referenced_paths: List[str] = []

    # Prefer structured refs if present, also parse from text.
    structured_refs = answer_data.get("evidence_refs") or []
    if isinstance(structured_refs, list):
        for r in structured_refs:
            rr = str(r).strip()
            if rr and rr not in referenced:
                referenced.append(rr)
    for rr in _extract_refs_from_answer(answer):
        if rr not in referenced:
            referenced.append(rr)

    for pp in _extract_paths_from_answer(answer):
        if pp not in referenced_paths:
            referenced_paths.append(pp)

    invalid_refs = [r for r in referenced if valid_refs and r not in valid_refs]
    if invalid_refs:
        issues.append(f"Refs não existem nas evidências: {', '.join(invalid_refs[:10])}")
        requires_new_search = True

    invalid_paths = [p for p in referenced_paths if valid_paths and p not in valid_paths]
    if invalid_paths:
        issues.append(f"Paths não existem nas evidências: {', '.join(invalid_paths[:10])}")
        requires_new_search = True

    # Citation checks: only if the answer is not explicitly abstaining.
    if answer and not _answer_is_abstaining(answer):
        ev_text = _collect_evidence_text(evidence)
        cites = _extract_legal_citations(answer)

        # CNJ must match exactly.
        missing_cnj = [c for c in cites["cnj"] if not _has_cnj_in_text(ev_text, c)]
        if missing_cnj:
            issues.append(f"Número(s) CNJ citado(s) não aparecem nas evidências: {', '.join(missing_cnj[:5])}")
            requires_new_search = True

        # Articles: require "art(igo)" near number in evidence.
        missing_art = [n for n in cites["art"] if not _has_article_in_text(ev_text, n)]
        if missing_art:
            issues.append(f"Artigo(s) citado(s) não aparecem nas evidências: {', '.join(missing_art[:10])}")
            requires_new_search = True

        # Leis: tolerate format differences (Lei 8.112/90 vs Lei 8112 de 1990).
        missing_lei = [n for n in cites["lei"] if not _has_law_in_text(ev_text, n)]
        if missing_lei:
            issues.append(f"Lei(s) citada(s) não aparecem nas evidências: {', '.join(missing_lei[:10])}")
            requires_new_search = True

        # Súmulas: require "súmula" near number in evidence.
        missing_sum = [n for n in cites["sumula"] if not _has_sumula_in_text(ev_text, n)]
        if missing_sum:
            issues.append(f"Súmula(s) citada(s) não aparecem nas evidências: {', '.join(missing_sum[:10])}")
            requires_new_search = True

    return {
        "is_consistent": len(issues) == 0,
        "confidence": 0.9 if len(issues) == 0 else 0.2,
        "issues": issues,
        "requires_new_search": requires_new_search,
        "suggestion": "",
        "deterministic_gate": True,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Verifier Node
# ═══════════════════════════════════════════════════════════════════════════

async def verifier_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    LangGraph node: verify answers against evidence using dual-LLM pattern.

    Reads from state:
        - sub_answers: Generated answers to verify
        - evidence_map / refined_evidence: Evidence per node
        - rethink_count, max_rethink: Retry tracking
        - cograg_verification_enabled: Feature flag

    Writes to state:
        - verification_status: "approved" | "rejected" | "abstain"
        - verification_issues: List of issues found
        - requires_new_search: Whether to trigger query rewriter
        - metrics.verifier_*
    """
    sub_answers: List[Dict[str, Any]] = state.get("sub_answers", [])
    evidence_map: Dict[str, Any] = state.get("evidence_map", {})
    refined_evidence: Dict[str, Any] = state.get("refined_evidence", {})
    rethink_count: int = state.get("rethink_count", 0)
    max_rethink: int = state.get("max_rethink", 2)
    verification_enabled: bool = state.get("cograg_verification_enabled", False)
    start = time.time()

    # If upstream already abstained (policy), don't try to "approve" it away.
    if state.get("verification_status") == "abstain":
        return {
            "verification_status": "abstain",
            "verification_issues": state.get("verification_issues", []),
            "requires_new_search": False,
            "metrics": {
                **state.get("metrics", {}),
                "verifier_latency_ms": 0,
                "verifier_enabled": bool(verification_enabled),
                "verifier_skipped": "upstream_abstain",
            },
        }

    # If verification disabled, auto-approve
    if not verification_enabled:
        logger.debug("[CogGRAG:Verifier] Verification disabled → auto-approve")
        return {
            "verification_status": "approved",
            "verification_issues": [],
            "requires_new_search": False,
            "metrics": {
                **state.get("metrics", {}),
                "verifier_latency_ms": 0,
                "verifier_enabled": False,
            },
        }

    if not sub_answers:
        logger.info("[CogGRAG:Verifier] No answers to verify → skip")
        return {
            "verification_status": "approved",
            "verification_issues": [],
            "requires_new_search": False,
            "metrics": {
                **state.get("metrics", {}),
                "verifier_latency_ms": 0,
                "verifier_answers_checked": 0,
            },
        }

    logger.info(f"[CogGRAG:Verifier] Verifying {len(sub_answers)} answers (attempt {rethink_count + 1})")

    all_issues: List[str] = []
    rejected_count = 0
    requires_new_search = False
    max_concurrency = int(state.get("cograg_llm_max_concurrency") or 0)

    # Verify each answer
    async def verify_answer(answer_data: Dict[str, Any]) -> Dict[str, Any]:
        node_id = answer_data.get("node_id", "")
        question = answer_data.get("question", "")
        answer = answer_data.get("answer", "")

        if not answer:
            return {"node_id": node_id, "is_consistent": True, "issues": []}

        # Get evidence
        evidence = refined_evidence.get(node_id, evidence_map.get(node_id, {}))

        # Deterministic gate first (cheap + auditable).
        det = _deterministic_verify_answer(answer_data, evidence)
        if not det.get("is_consistent", True):
            return {
                "node_id": node_id,
                "question": question,
                **det,
            }

        # If deterministic passed, proceed with LLM verifier.
        evidence_text = _format_evidence_for_verification(evidence)

        # Call verifier LLM
        prompt = VERIFICATION_PROMPT.format(
            question=question,
            answer=answer,
            evidence=evidence_text,
            evidence_policy=EVIDENCE_POLICY_COGRAG.strip(),
        )
        response = await _call_llm(prompt)
        result = _parse_verification_result(response)

        # Merge: keep deterministic pass, add any LLM issues.
        if det.get("issues"):
            result["issues"] = list(det.get("issues", [])) + list(result.get("issues", []))
        result["requires_new_search"] = bool(result.get("requires_new_search", False)) or bool(det.get("requires_new_search", False))

        return {
            "node_id": node_id,
            "question": question,
            **result,
        }

    # Run verification in parallel
    if max_concurrency > 0:
        sem = asyncio.Semaphore(max_concurrency)

        async def _bounded_verify_answer(answer_data: Dict[str, Any]) -> Dict[str, Any]:
            await sem.acquire()
            try:
                return await verify_answer(answer_data)
            finally:
                sem.release()

        tasks = [_bounded_verify_answer(sa) for sa in sub_answers]
    else:
        tasks = [verify_answer(sa) for sa in sub_answers]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Aggregate results
    for res in results:
        if isinstance(res, Exception):
            logger.error(f"[CogGRAG:Verifier] Verification failed: {res}")
            continue

        if not res.get("is_consistent", True):
            rejected_count += 1
            issues = res.get("issues", [])
            if issues:
                all_issues.extend([f"[{res['node_id'][:8]}] {i}" for i in issues])

            if res.get("requires_new_search"):
                requires_new_search = True

    # Determine overall status
    if rejected_count == 0:
        status = "approved"
    elif rethink_count >= max_rethink:
        # Max retries reached, abstain if too many issues
        if rejected_count > len(sub_answers) // 2:
            status = "abstain"
        else:
            status = "approved"  # Accept partial
    else:
        status = "rejected"

    latency = int((time.time() - start) * 1000)
    logger.info(
        f"[CogGRAG:Verifier] Status: {status}, "
        f"rejected: {rejected_count}/{len(sub_answers)}, {latency}ms"
    )

    try:
        from app.services.rag.core.metrics import get_latency_collector

        get_latency_collector().record("cograg.node.verifier", float(latency))
    except Exception:
        pass

    return {
        "verification_status": status,
        "verification_issues": all_issues,
        "requires_new_search": requires_new_search,
        "metrics": {
            **state.get("metrics", {}),
            "verifier_latency_ms": latency,
            "verifier_enabled": True,
            "verifier_answers_checked": len(sub_answers),
            "verifier_rejected_count": rejected_count,
            "verifier_status": status,
            "verifier_llm_max_concurrency": max_concurrency,
        },
    }


# ═══════════════════════════════════════════════════════════════════════════
# Query Rewriter Node (for hallucination loop)
# ═══════════════════════════════════════════════════════════════════════════

async def query_rewriter_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    LangGraph node: rewrite query when verification requires new search.

    This implements the "hallucination loop" from CogGRAG where rejected
    answers trigger a refined search.

    Reads from state:
        - query: Original query
        - verification_issues: Issues that triggered rewrite
        - rethink_count

    Writes to state:
        - query: Refined query (optional)
        - rethink_count: Incremented
        - metrics.rewriter_*
    """
    query: str = state.get("query", "")
    issues: List[str] = state.get("verification_issues", [])
    rethink_count: int = state.get("rethink_count", 0)
    sub_questions: List[Dict[str, Any]] = list(state.get("sub_questions", []))
    start = time.time()

    logger.info(f"[CogGRAG:Rewriter] Rewriting query (attempt {rethink_count + 1})")

    # MVP rewrite strategy (deterministic):
    # - Group issues by node prefix "[deadbeef] ...".
    # - Extract key terms from issues and append them to the corresponding sub-questions.
    import re

    def _extract_terms(text: str) -> List[str]:
        stop = {
            "evidencias", "evidência", "evidencias", "insuficientes", "insuficiente",
            "citar", "cite", "citacao", "citação", "ref", "refs", "chunk", "chunks",
            "resposta", "inconsistente", "contradicao", "contradição", "falta",
            "precisa", "necessario", "necessária", "necessário", "nao", "não",
        }
        terms = re.findall(r"\b[\w\-]{4,}\b", (text or "").lower())
        out: List[str] = []
        for t in terms:
            if t in stop:
                continue
            if t.isdigit():
                continue
            if t not in out:
                out.append(t)
        return out[:8]

    issues_by_node: Dict[str, List[str]] = {}
    for issue in issues or []:
        m = re.match(r"^\[([0-9a-fA-F]{1,8})\]\s*(.*)$", str(issue).strip())
        if not m:
            continue
        node_prefix = m.group(1).lower()
        text = m.group(2)
        issues_by_node.setdefault(node_prefix, []).append(text)

    updated = 0
    added_terms_total = 0
    marker = "\n\n[CogRAG:rewrite]"

    new_sub_questions: List[Dict[str, Any]] = []
    for sq in sub_questions:
        node_id = str(sq.get("node_id", "") or "")
        prefix = node_id[:8].lower() if node_id else ""
        sq_text = str(sq.get("question", "") or "")

        if marker in sq_text:
            new_sub_questions.append(sq)
            continue

        issue_texts = issues_by_node.get(prefix, [])
        if not issue_texts:
            new_sub_questions.append(sq)
            continue

        terms: List[str] = []
        for it in issue_texts:
            for t in _extract_terms(it):
                if t not in terms:
                    terms.append(t)

        if not terms:
            new_sub_questions.append(sq)
            continue

        added_terms_total += len(terms)
        updated += 1

        new_sq = dict(sq)
        new_sq["question"] = f"{sq_text}{marker} termos_para_busca={', '.join(terms)}"
        new_sub_questions.append(new_sq)

    new_rethink_count = rethink_count + 1

    latency = int((time.time() - start) * 1000)

    return {
        "query": query,
        "sub_questions": new_sub_questions,
        "rethink_count": new_rethink_count,
        "metrics": {
            **state.get("metrics", {}),
            "rewriter_latency_ms": latency,
            "rewriter_attempts": new_rethink_count,
            "rewriter_subquestions_updated": updated,
            "rewriter_added_terms_total": added_terms_total,
        },
    }
