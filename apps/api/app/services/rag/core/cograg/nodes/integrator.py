"""
CogGRAG Integrator Node — Final answer synthesis.

Implements Phase 3 from CogGRAG paper (2503.06567v2):
- Synthesize verified sub-answers into coherent final response
- Handle abstain mode (when evidence is insufficient)
- Collect and deduplicate citations

Can use LLM for synthesis or rule-based concatenation.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger("rag.cograg.integrator")

try:
    from app.services.prompt_policies import EVIDENCE_POLICY_COGRAG
except Exception:
    EVIDENCE_POLICY_COGRAG = "Use APENAS as evidencias fornecidas. Se insuficientes, diga que e insuficiente. Nao invente."


# ═══════════════════════════════════════════════════════════════════════════
# Prompts (Portuguese Legal Domain)
# ═══════════════════════════════════════════════════════════════════════════

INTEGRATION_PROMPT = """Você é um assistente jurídico especializado.

{evidence_policy}

Sintetize as respostas abaixo em uma resposta final coerente. Preserve marcadores [ref:...] existentes.

<query>
{query}
</query>

<chunks>
{sub_answers_text}
</chunks>

**Instruções:**
1. Integre as respostas de forma lógica e fluida
2. Elimine redundâncias
3. Mantenha todas as citações legais relevantes e preserve [ref:...] quando presentes
4. Se houver conflitos, apresente as diferentes posições
5. Conclua com uma síntese objetiva
6. Use no máximo 4 parágrafos

**Resposta Integrada:**"""

ABSTAIN_PROMPT = """Você é um assistente jurídico.

{evidence_policy}

As evidências disponíveis são insuficientes para responder à pergunta com confiança.

<query>
{query}
</query>

**Motivos da Abstenção:**
{issues}

<chunks>
{partial_answers}
</chunks>

Redija uma resposta explicando que não é possível responder com certeza, indicando:
1. O que foi possível identificar nas evidências
2. Quais informações estão faltando
3. Sugestões de onde buscar a informação

**Resposta:**"""


# ═══════════════════════════════════════════════════════════════════════════
# LLM Integration
# ═══════════════════════════════════════════════════════════════════════════

async def _call_llm(prompt: str, model: str = "gemini-2.0-flash") -> str:
    """Call LLM for integration. Uses Gemini by default."""
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
                temperature=0.4,
                max_output_tokens=2048,
            ),
        )
        latency_ms = (time.perf_counter() - t0) * 1000.0
        try:
            from app.services.rag.core.metrics import get_latency_collector

            get_latency_collector().record("cograg.llm.integrator", latency_ms)
        except Exception:
            pass
        return response.text.strip() if response.text else ""
    except Exception as e:
        logger.warning(f"[CogGRAG:Integrator] LLM call failed: {e}")
        return ""


# ═══════════════════════════════════════════════════════════════════════════
# Integrator Node
# ═══════════════════════════════════════════════════════════════════════════

def _format_sub_answers(sub_answers: List[Dict[str, Any]]) -> str:
    """Format sub-answers for integration prompt."""
    if not sub_answers:
        return "Nenhuma resposta disponível."

    formatted = []
    for i, sa in enumerate(sub_answers, 1):
        question = sa.get("question", "")
        answer = sa.get("answer", "")
        confidence = sa.get("confidence", 0)
        citations = sa.get("citations", [])
        refs = sa.get("evidence_refs", []) or []

        citations_str = f" [{', '.join(citations)}]" if citations else ""
        refs_str = (" " + " ".join(f"[ref:{r}]" for r in refs)) if refs else ""
        formatted.append(
            f"{i}. **{question}** (confiança: {confidence:.0%})\n"
            f"   {answer}{citations_str}{refs_str}"
        )

    return "\n\n".join(formatted)


def _collect_citations(sub_answers: List[Dict[str, Any]]) -> List[str]:
    """Collect and deduplicate citations from all sub-answers."""
    seen: Set[str] = set()
    citations: List[str] = []

    for sa in sub_answers:
        for citation in sa.get("citations", []):
            normalized = citation.strip().lower()
            if normalized not in seen:
                seen.add(normalized)
                citations.append(citation.strip())

    return citations


def _rule_based_integration(
    query: str,
    sub_answers: List[Dict[str, Any]],
) -> str:
    """
    Simple rule-based integration (fallback when LLM unavailable).

    Concatenates answers with transitions.
    """
    if not sub_answers:
        return "Não foi possível encontrar informações relevantes para responder à pergunta."

    if len(sub_answers) == 1:
        return sub_answers[0].get("answer", "")

    parts = []
    for i, sa in enumerate(sub_answers):
        answer = sa.get("answer", "")
        if not answer:
            continue

        if i == 0:
            parts.append(answer)
        else:
            # Add transition
            parts.append(f"\n\nAlém disso, {answer[0].lower()}{answer[1:]}" if answer else "")

    return "".join(parts)


async def integrator_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    LangGraph node: synthesize final response from sub-answers.

    Reads from state:
        - query: Original question
        - sub_answers: Verified answers to integrate
        - verification_status: "approved" | "rejected" | "abstain"
        - verification_issues: Issues if abstaining
        - cograg_abstain_mode: Whether to explain when abstaining

    Writes to state:
        - integrated_response: Final synthesized answer
        - citations_used: Deduplicated list of citations
        - abstain_info: Info if abstaining
        - metrics.integrator_*
    """
    query: str = state.get("query", "")
    sub_answers: List[Dict[str, Any]] = state.get("sub_answers", [])
    verification_status: str = state.get("verification_status", "approved")
    verification_issues: List[str] = state.get("verification_issues", [])
    abstain_mode: bool = state.get("cograg_abstain_mode", True)
    start = time.time()

    if not query:
        logger.info("[CogGRAG:Integrator] No query → skip")
        return {
            "integrated_response": None,
            "citations_used": [],
            "abstain_info": None,
            "metrics": {
                **state.get("metrics", {}),
                "integrator_latency_ms": 0,
            },
        }

    logger.info(f"[CogGRAG:Integrator] Integrating {len(sub_answers)} answers (status: {verification_status})")

    # Collect citations
    citations = _collect_citations(sub_answers)

    # Handle abstain case
    if verification_status == "abstain":
        if abstain_mode:
            # Generate abstain explanation
            partial_answers = _format_sub_answers(sub_answers)
            issues_text = "\n".join(f"- {i}" for i in verification_issues) if verification_issues else "Evidências insuficientes"

            prompt = ABSTAIN_PROMPT.format(
                query=query,
                issues=issues_text,
                partial_answers=partial_answers,
                evidence_policy=EVIDENCE_POLICY_COGRAG.strip(),
            )
            response = await _call_llm(prompt)

            if not response:
                response = (
                    "Não foi possível responder à pergunta com as evidências disponíveis. "
                    "Recomenda-se consulta a fontes adicionais ou reformulação da pergunta."
                )

            latency = int((time.time() - start) * 1000)
            try:
                from app.services.rag.core.metrics import get_latency_collector

                get_latency_collector().record("cograg.node.integrator", float(latency))
            except Exception:
                pass

            return {
                "integrated_response": response,
                "citations_used": citations,
                "abstain_info": {
                    "reason": "insufficient_evidence",
                    "issues": verification_issues,
                    "partial_answer_count": len(sub_answers),
                },
                "metrics": {
                    **state.get("metrics", {}),
                    "integrator_latency_ms": latency,
                    "integrator_abstained": True,
                },
            }
        else:
            # Abstain without explanation
            latency = int((time.time() - start) * 1000)
            try:
                from app.services.rag.core.metrics import get_latency_collector

                get_latency_collector().record("cograg.node.integrator", float(latency))
            except Exception:
                pass
            return {
                "integrated_response": None,
                "citations_used": citations,
                "abstain_info": {
                    "reason": "insufficient_evidence",
                    "issues": verification_issues,
                },
                "metrics": {
                    **state.get("metrics", {}),
                    "integrator_latency_ms": latency,
                    "integrator_abstained": True,
                },
            }

    # Normal integration
    if not sub_answers:
        response = "Não foram encontradas evidências relevantes para responder à pergunta."
    elif len(sub_answers) == 1:
        # Single answer, no need for synthesis
        response = sub_answers[0].get("answer", "")
    else:
        # Multiple answers, synthesize
        sub_answers_text = _format_sub_answers(sub_answers)
        prompt = INTEGRATION_PROMPT.format(
            query=query,
            sub_answers_text=sub_answers_text,
            evidence_policy=EVIDENCE_POLICY_COGRAG.strip(),
        )
        response = await _call_llm(prompt)

        if not response:
            # Fallback to rule-based
            response = _rule_based_integration(query, sub_answers)

    latency = int((time.time() - start) * 1000)
    logger.info(f"[CogGRAG:Integrator] Response generated, {len(citations)} citations, {latency}ms")
    try:
        from app.services.rag.core.metrics import get_latency_collector

        get_latency_collector().record("cograg.node.integrator", float(latency))
    except Exception:
        pass

    return {
        "integrated_response": response,
        "citations_used": citations,
        "abstain_info": None,
        "metrics": {
            **state.get("metrics", {}),
            "integrator_latency_ms": latency,
            "integrator_abstained": False,
            "integrator_citations_count": len(citations),
            "integrator_sub_answers_used": len(sub_answers),
        },
    }
