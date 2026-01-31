"""
CogGRAG Reasoner Node — Bottom-up answer generation.

Implements Phase 3 from CogGRAG paper (2503.06567v2):
- Generate answers for leaf sub-questions using retrieved evidence
- Propagate answers up the tree (children → parent)
- Track confidence scores per answer

Uses LLM for answer generation (Gemini Flash by default).
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("rag.cograg.reasoner")

try:
    from app.services.prompt_policies import EVIDENCE_POLICY_COGRAG
except Exception:
    EVIDENCE_POLICY_COGRAG = "Use APENAS as evidencias fornecidas. Se insuficientes, diga que e insuficiente. Nao invente."


# ═══════════════════════════════════════════════════════════════════════════
# Prompts (Portuguese Legal Domain)
# ═══════════════════════════════════════════════════════════════════════════

LEAF_ANSWER_PROMPT = """Você é um assistente jurídico especializado.

{evidence_policy}

Responda usando apenas o conteúdo do bloco <chunks> e dos blocos de evidência estruturada (se existirem).
Se não houver evidência suficiente, diga explicitamente.

<chunks>
{evidence}
</chunks>

<query>
{question}
</query>

**Instruções adicionais:**
1. Baseie sua resposta EXCLUSIVAMENTE nas evidências acima
2. Se as evidências forem insuficientes, indique claramente
3. Cite as referências legais quando relevante (Art., Lei, Súmula)
4. Seja objetivo e direto (máximo 3 parágrafos)
5. Se houver conflito entre evidências, mencione as diferentes posições
6. Sempre que usar um trecho textual, inclua um ou mais marcadores [ref:...] no fim do parágrafo (use apenas refs que apareçam em <chunks>)
7. Sempre que usar evidência do grafo, inclua um ou mais marcadores [path:...] no fim do parágrafo (use apenas paths que apareçam em <KG_PATHS>)

**Resposta:**"""

SYNTHESIS_PROMPT = """Você é um assistente jurídico especializado.

{evidence_policy}

<query>
{question}
</query>

<chunks>
{sub_answers}
</chunks>

**Instruções:**
1. Integre as respostas das sub-perguntas de forma coerente
2. Mantenha consistência entre as partes
3. Destaque as referências legais mais relevantes
4. Se houver contradições entre sub-respostas, explique
5. Preserve marcadores [ref:...] e [path:...] existentes (não crie marcadores novos sem evidência)

**Resposta Sintetizada:**"""


# ═══════════════════════════════════════════════════════════════════════════
# LLM Integration (Lazy Import)
# ═══════════════════════════════════════════════════════════════════════════

async def _call_llm(prompt: str, model: str = "gemini-2.0-flash") -> str:
    """Call LLM for answer generation. Uses Gemini by default."""
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
                temperature=0.3,
                max_output_tokens=1024,
            ),
        )
        latency_ms = (time.perf_counter() - t0) * 1000.0
        try:
            from app.services.rag.core.metrics import get_latency_collector

            get_latency_collector().record("cograg.llm.reasoner", latency_ms)
        except Exception:
            pass
        return response.text.strip() if response.text else ""
    except Exception as e:
        logger.warning(f"[CogGRAG:Reasoner] LLM call failed: {e}")
        return ""


# ═══════════════════════════════════════════════════════════════════════════
# Evidence Formatting
# ═══════════════════════════════════════════════════════════════════════════

def _format_evidence_for_prompt(
    evidence: Dict[str, Any],
    max_chunks: int = 5,
    *,
    blocked_refs: Optional[set] = None,
    max_triples: int = 12,
    max_paths: int = 8,
) -> str:
    """Format evidence chunks for inclusion in LLM prompt."""
    chunks = []
    blocked_refs = blocked_refs or set()

    # Collect from all sources.
    # Evidence may be in:
    # - original keys: local_results/global_results/chunk_results
    # - refined key: chunks
    for key in ("local_results", "global_results", "chunk_results", "chunks"):
        for chunk in evidence.get(key, [])[:max_chunks]:
            text = chunk.get("text", "") or chunk.get("preview", "")
            if text:
                ref_id = (
                    chunk.get("chunk_uid")
                    or chunk.get("_content_hash")
                    or chunk.get("id")
                    or ""
                )
                if ref_id and str(ref_id) in blocked_refs:
                    continue
                ref_tag = f"[ref:{ref_id}]" if ref_id else "[ref:unknown]"

                metadata = chunk.get("metadata", {}) or {}
                doc_id = chunk.get("doc_id") or metadata.get("doc_id") or metadata.get("document_id")
                source_type = (
                    chunk.get("source_type")
                    or metadata.get("source_type")
                    or metadata.get("dataset")
                    or chunk.get("source")
                    or metadata.get("engine")
                    or ""
                )
                score = chunk.get("_quality_score", chunk.get("score", 0))

                header_bits = [ref_tag]
                if source_type:
                    header_bits.append(f"[fonte: {source_type}]")
                if doc_id:
                    header_bits.append(f"doc={doc_id}")
                try:
                    header_bits.append(f"score={float(score):.2f}")
                except Exception:
                    pass

                header = " ".join(header_bits)
                chunks.append(f"{header}\n{text[:500].strip()}")

    if not chunks:
        chunks_text = "Nenhuma evidência textual disponível."
    else:
        chunks_text = "\n".join(chunks[:max_chunks])

    # KG paths (referencable)
    paths = evidence.get("graph_paths") or []
    path_lines: List[str] = []
    for p in (paths or [])[:max_paths]:
        if not isinstance(p, dict):
            continue
        uid = str(p.get("path_uid") or "").strip()
        text = str(p.get("path_text") or "").strip()
        if not uid or not text:
            continue
        path_lines.append(f"[path:{uid}] {text}")

    # KG triples (MindMap-style KG prompting)
    triples = evidence.get("graph_triples") or []
    triple_lines: List[str] = []
    for tr in (triples or [])[:max_triples]:
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


def _compute_answer_confidence(
    answer: str,
    evidence: Dict[str, Any],
    has_conflicts: bool,
) -> float:
    """
    Compute confidence score for an answer.

    Factors:
    - Evidence quality (from refiner)
    - Evidence quantity
    - Presence of conflicts
    - Answer length/substance
    """
    if not answer:
        return 0.0

    confidence = 0.5  # Base

    # Evidence quantity bonus
    total_chunks = sum(
        len(evidence.get(k, []))
        for k in ("local_results", "global_results", "chunk_results")
    )
    if total_chunks >= 5:
        confidence += 0.2
    elif total_chunks >= 2:
        confidence += 0.1

    # Quality score bonus (if refined evidence available)
    quality = evidence.get("quality_score", 0)
    confidence += quality * 0.2

    # Conflict penalty
    if has_conflicts:
        confidence -= 0.15

    # Answer substance
    if len(answer) > 200:
        confidence += 0.1
    elif len(answer) < 50:
        confidence -= 0.1

    return max(0.0, min(1.0, confidence))


# ═══════════════════════════════════════════════════════════════════════════
# Reasoner Node
# ═══════════════════════════════════════════════════════════════════════════

async def reasoner_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    LangGraph node: generate answers bottom-up from sub-questions.

    Reads from state:
        - sub_questions: List of decomposed questions
        - evidence_map / refined_evidence: Evidence per node
        - mind_map: Tree structure (optional, for synthesis)
        - conflicts: Detected conflicts per node

    Writes to state:
        - sub_answers: List of {node_id, question, answer, confidence, citations}
        - verification_status: "pending" (ready for verifier)
        - metrics.reasoner_*
    """
    sub_questions: List[Dict[str, Any]] = state.get("sub_questions", [])
    evidence_map: Dict[str, Any] = state.get("evidence_map", {})
    refined_evidence: Dict[str, Any] = state.get("refined_evidence", {})
    conflicts: List[Dict[str, Any]] = state.get("conflicts", [])
    abstain_mode: bool = bool(state.get("cograg_abstain_mode", True))
    abstain_threshold: float = float(state.get("cograg_abstain_threshold", 0.3))
    similar_consultation: Dict[str, Any] = state.get("similar_consultation") or {}
    blocked_refs = set(similar_consultation.get("penalized_refs") or [])
    start = time.time()

    if not sub_questions:
        logger.info("[CogGRAG:Reasoner] No sub-questions → skip")
        return {
            "sub_answers": [],
            "verification_status": "approved",
            "metrics": {
                **state.get("metrics", {}),
                "reasoner_latency_ms": 0,
                "reasoner_answers_generated": 0,
            },
        }

    logger.info(f"[CogGRAG:Reasoner] Generating answers for {len(sub_questions)} sub-questions")

    # Build conflict lookup
    conflict_nodes = set()
    for c in conflicts:
        if c.get("type") == "intra_node":
            conflict_nodes.add(c.get("node_id", ""))
        elif c.get("type") == "cross_node":
            conflict_nodes.add(c.get("node_a", ""))
            conflict_nodes.add(c.get("node_b", ""))

    # Generate answers for each sub-question (parallel)
    async def generate_answer(sq: Dict[str, Any]) -> Dict[str, Any]:
        node_id = sq.get("node_id", "")
        question = sq.get("question", "")

        # Get evidence (prefer refined)
        evidence = refined_evidence.get(node_id, evidence_map.get(node_id, {}))
        has_conflicts = node_id in conflict_nodes

        # Format evidence for prompt
        evidence_text = _format_evidence_for_prompt(evidence, blocked_refs=blocked_refs)

        # Generate answer
        prompt = LEAF_ANSWER_PROMPT.format(
            question=question,
            evidence=evidence_text,
            evidence_policy=EVIDENCE_POLICY_COGRAG.strip(),
        )
        answer = await _call_llm(prompt)

        # Compute confidence
        confidence = _compute_answer_confidence(answer, evidence, has_conflicts)

        # Extract citations from answer (simple heuristic)
        import re
        citations = []
        art_matches = re.findall(r"[Aa]rt(?:igo)?\.?\s*\d+", answer)
        lei_matches = re.findall(r"[Ll]ei\s+(?:n[º°]?\s*)?\d+(?:\.\d+)?(?:/\d+)?", answer)
        sumula_matches = re.findall(r"[Ss]úmula\s+(?:n[º°]?\s*)?\d+", answer)
        citations.extend(art_matches + lei_matches + sumula_matches)

        # Extract evidence refs from answer, but only allow refs that exist in evidence.
        valid_refs = set()
        for key in ("local_results", "global_results", "chunk_results"):
            for chunk in evidence.get(key, [])[:20]:
                rid = chunk.get("chunk_uid") or chunk.get("_content_hash") or chunk.get("id")
                if rid:
                    rr = str(rid)
                    if rr in blocked_refs:
                        continue
                    valid_refs.add(rr)

        raw_refs = re.findall(r"\[ref:([^\]]+)\]", answer or "")
        evidence_refs = []
        seen = set()
        for r in raw_refs:
            rr = str(r).strip()
            if not rr or rr in seen:
                continue
            if valid_refs and rr not in valid_refs:
                continue
            seen.add(rr)
            evidence_refs.append(rr)

        return {
            "node_id": node_id,
            "question": question,
            "answer": answer,
            "confidence": round(confidence, 3),
            "citations": list(set(citations)),
            "evidence_refs": evidence_refs,
            "has_conflicts": has_conflicts,
        }

    # Run in parallel
    max_concurrency = int(state.get("cograg_llm_max_concurrency") or 0)
    if max_concurrency > 0:
        sem = asyncio.Semaphore(max_concurrency)

        async def _bounded_generate_answer(sq: Dict[str, Any]) -> Dict[str, Any]:
            await sem.acquire()
            try:
                return await generate_answer(sq)
            finally:
                sem.release()

        tasks = [_bounded_generate_answer(sq) for sq in sub_questions]
    else:
        tasks = [generate_answer(sq) for sq in sub_questions]
    sub_answers = await asyncio.gather(*tasks, return_exceptions=True)

    # Filter out exceptions
    valid_answers = []
    low_confidence_nodes: List[str] = []
    for sa in sub_answers:
        if isinstance(sa, Exception):
            logger.error(f"[CogGRAG:Reasoner] Answer generation failed: {sa}")
        else:
            valid_answers.append(sa)

    latency = int((time.time() - start) * 1000)
    avg_confidence = (
        sum(a["confidence"] for a in valid_answers) / len(valid_answers)
        if valid_answers else 0.0
    )

    if abstain_mode and valid_answers:
        for a in valid_answers:
            try:
                if float(a.get("confidence", 0.0)) < abstain_threshold:
                    low_confidence_nodes.append(str(a.get("node_id", ""))[:8])
            except Exception:
                continue

    logger.info(
        f"[CogGRAG:Reasoner] Generated {len(valid_answers)} answers, "
        f"avg confidence: {avg_confidence:.2f}, {latency}ms"
    )

    try:
        from app.services.rag.core.metrics import get_latency_collector

        get_latency_collector().record("cograg.node.reasoner", float(latency))
    except Exception:
        pass

    # Abstain policy (PLANO_COGRAG.md): if confidence is too low, do not proceed as if certain.
    if abstain_mode and (not valid_answers or avg_confidence < abstain_threshold):
        issues: List[str] = []
        if not valid_answers:
            issues.append("Não foi possível gerar respostas para as sub-perguntas.")
        else:
            if low_confidence_nodes:
                issues.append(
                    "Baixa confiança/ evidência insuficiente nos nós: "
                    + ", ".join([n for n in low_confidence_nodes if n])
                )
            issues.append(
                f"Confiança média abaixo do limiar ({avg_confidence:.2f} < {abstain_threshold:.2f})."
            )

        return {
            "sub_answers": valid_answers,
            "verification_status": "abstain",
            "verification_issues": issues,
            "metrics": {
                **state.get("metrics", {}),
                "reasoner_latency_ms": latency,
                "reasoner_answers_generated": len(valid_answers),
                "reasoner_avg_confidence": round(avg_confidence, 3),
                "reasoner_with_conflicts": sum(1 for a in valid_answers if a.get("has_conflicts")),
                "reasoner_abstained": True,
                "reasoner_abstain_threshold": abstain_threshold,
                "reasoner_llm_max_concurrency": max_concurrency,
            },
        }

    return {
        "sub_answers": valid_answers,
        "verification_status": "pending",
        "metrics": {
            **state.get("metrics", {}),
            "reasoner_latency_ms": latency,
            "reasoner_answers_generated": len(valid_answers),
            "reasoner_avg_confidence": round(avg_confidence, 3),
            "reasoner_with_conflicts": sum(1 for a in valid_answers if a.get("has_conflicts")),
            "reasoner_abstained": False,
            "reasoner_abstain_threshold": abstain_threshold,
            "reasoner_llm_max_concurrency": max_concurrency,
        },
    }
