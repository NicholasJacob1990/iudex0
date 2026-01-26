"""
B2 Citer/Verifier Node - Gate Pré-Debate

Verifica rastreabilidade de afirmações às fontes antes do debate.

Para cada claim no contexto de pesquisa:
- Extrai afirmações jurídicas relevantes
- Mapeia para trecho fonte (RAG results)
- Marca claims sem fonte como [VERIFICAR]
- Calcula cobertura e decide se força HIL

v1.0 - Implementação inicial
"""

from typing import Dict, Any, List, Optional
from loguru import logger

from app.services.api_call_tracker import billing_context
from app.services.ai.model_registry import get_api_model_name, DEFAULT_JUDGE_MODEL


def extract_json_strict(text: str, expect: str = "object") -> Optional[Any]:
    """
    Minimal strict JSON extractor.
    - Removes ```json fences
    - Tries to parse whole string
    - Falls back to first {...} or [...] block
    """
    import json
    import re

    if not text:
        return None
    raw = str(text).strip()
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw, flags=re.IGNORECASE)
    if fence_match:
        raw = fence_match.group(1).strip()
    try:
        return json.loads(raw)
    except Exception:
        pass

    if expect in ("array", "any"):
        arr_match = re.search(r"(\[[\s\S]*\])", raw)
        if arr_match:
            try:
                return json.loads(arr_match.group(1))
            except Exception:
                pass
    if expect in ("object", "any"):
        obj_match = re.search(r"(\{[\s\S]*\})", raw)
        if obj_match:
            try:
                return json.loads(obj_match.group(1))
            except Exception:
                pass
    return None


def _build_source_label(source: dict) -> str:
    """Helper to build human-readable source label."""
    if not isinstance(source, dict):
        return "Fonte"

    source_type = source.get("source", "") or ""
    metadata = source.get("metadata", {}) or {}

    if source_type == "lei":
        return f"{metadata.get('tipo', 'Lei')} {metadata.get('numero', '')}/{metadata.get('ano', '')} Art. {metadata.get('artigo', '')}"
    elif source_type == "juris":
        return f"{metadata.get('tribunal', '')} {metadata.get('numero', '')} - {metadata.get('tema', '')}"
    elif source_type == "sei":
        return f"SEI {metadata.get('processo_sei', '')} - {metadata.get('tipo_documento', '')}"
    elif source_type == "pecas_modelo":
        return f"Modelo: {metadata.get('tipo_peca', '')} - {metadata.get('area', '')}"
    else:
        return f"{source_type or 'Documento'}"


async def citer_verifier_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    🔍 B2 Citer/Verifier - Verifica rastreabilidade de afirmações às fontes.

    Para cada claim no contexto de pesquisa:
    - Extrai afirmações jurídicas relevantes
    - Mapeia para trecho fonte (RAG results)
    - Marca claims sem fonte como [VERIFICAR]
    - Calcula cobertura e decide se força HIL

    Gate obrigatório entre pesquisa e debate para garantir que o drafter
    só use informações verificadas.
    """
    logger.info("🔍 [Phase2] Citer/Verifier: Validando afirmações vs fontes...")

    research_context = (state.get("research_context") or "").strip()
    research_sources = state.get("research_sources") or []
    citations_map = state.get("citations_map") or {}

    # Skip if no research context
    if not research_context:
        logger.info("⏭️ Citer/Verifier: Sem contexto de pesquisa, pulando verificação")
        return {
            **state,
            "citer_verifier_result": {
                "skipped": True,
                "reason": "no_research_context",
                "coverage": 1.0,
                "verified_claims": [],
                "unverified_claims": [],
            },
            "verified_context": research_context,
        }

    # Build source index for matching
    source_texts = []
    for i, src in enumerate(research_sources):
        if isinstance(src, dict):
            text = src.get("text", "") or src.get("content", "") or ""
            metadata = src.get("metadata", {}) or {}
            source_texts.append({
                "index": i + 1,
                "text": text[:2000],  # Limit for matching
                "source_type": src.get("source", metadata.get("source_type", "unknown")),
                "label": _build_source_label(src),
            })

    # Also include citations_map entries
    for key, val in citations_map.items():
        if isinstance(val, dict):
            title = val.get("title", "") or ""
            snippet = val.get("snippet", "") or val.get("text", "") or ""
            source_texts.append({
                "index": f"web_{key}",
                "text": f"{title}\n{snippet}"[:1500],
                "source_type": "web",
                "label": f"[{key}] {title[:80]}",
            })

    if not source_texts:
        logger.info("⏭️ Citer/Verifier: Sem fontes disponíveis para verificação")
        # Without any sources, we can't verify legal claims; block debate early.
        final_markdown = (
            "# ⛔ Rastreabilidade insuficiente para minutar\n\n"
            "Nenhuma fonte (RAG/web) foi disponibilizada para verificação das afirmações.\n\n"
            "## Como resolver\n"
            "- Habilite `web_search` e/ou `deep_research`.\n"
            "- Verifique se o RAG local está ativo e com documentos indexados.\n"
            "- Anexe peças/decisões/documentos relevantes ao caso.\n"
        )
        return {
            **state,
            "citer_verifier_result": {
                "skipped": True,
                "reason": "no_sources",
                "coverage": 0.0,
                "verified_claims": [],
                "unverified_claims": [],
                "force_hil": True,
                "block_debate": True,
            },
            "verified_context": research_context,
            "citer_verifier_force_hil": True,  # Force HIL when no sources
            "final_markdown": final_markdown,
            "final_decision": "NEED_EVIDENCE",
            "final_decision_reasons": ["citer_verifier_no_sources"],
        }

    # Use LLM to extract and verify claims
    parse_failures = list(state.get("json_parse_failures") or [])

    # Build sources block for prompt
    sources_block = "\n".join([
        f"[FONTE {s['index']}] ({s['source_type']}) {s['label']}\n{s['text'][:800]}\n"
        for s in source_texts[:15]  # Limit to 15 sources
    ])

    prompt = f"""
# ROLE
Você é um verificador jurídico rigoroso. Sua tarefa é mapear afirmações às fontes.

# TASK
1. Extraia afirmações jurídicas relevantes do CONTEXTO DE PESQUISA abaixo
2. Para cada afirmação, verifique se há suporte em alguma FONTE
3. Classifique cada claim como "verified" (com fonte) ou "unverified" (sem fonte)

# CONTEXTO DE PESQUISA
{research_context[:8000]}

# FONTES DISPONÍVEIS
{sources_block}

# RULES
1. Afirmações factuais genéricas não precisam de fonte (ex: "O autor é pessoa jurídica")
2. Afirmações de DIREITO (leis, súmulas, jurisprudência) PRECISAM de fonte
3. Se a afirmação cita número específico (Lei X, Súmula Y), verifique se aparece nas fontes
4. Marque como "unverified" se não encontrar suporte explícito

# OUTPUT FORMAT
Retorne JSON válido:
```json
{{
  "claims": [
    {{
      "text": "afirmação extraída",
      "type": "direito|fato|argumento",
      "status": "verified|unverified",
      "source_refs": [1, 2],
      "confidence": 0.9,
      "needs_verification_tag": true
    }}
  ],
  "coverage": 0.85,
  "summary": "resumo da verificação",
  "critical_gaps": ["gap1", "gap2"]
}}
```
""".strip()

    response_text = ""
    model_used = None

    # Try GPT first (better at structured extraction)
    try:
        from app.services.ai.agent_clients import init_openai_client, call_openai_async
        gpt_client = init_openai_client()
        gpt_model = state.get("gpt_model") or "gpt-5.2"
        if gpt_client:
            with billing_context(node="citer_verifier", size="M"):
                response_text = await call_openai_async(
                    gpt_client,
                    prompt,
                    model=get_api_model_name(gpt_model),
                    temperature=0.1,
                    timeout=90
                )
            model_used = get_api_model_name(gpt_model)
    except Exception as e:
        logger.warning(f"⚠️ Citer/Verifier GPT falhou: {e}")

    # Fallback to Gemini/other model
    if not response_text:
        try:
            from app.services.ai.debate_subgraph import _call_model_any_async
            judge_model = state.get("judge_model") or DEFAULT_JUDGE_MODEL
            with billing_context(node="citer_verifier", size="M"):
                response_text = await _call_model_any_async(
                    judge_model,
                    prompt,
                    temperature=0.1,
                    max_tokens=4000,
                )
            model_used = judge_model
        except Exception as e:
            logger.warning(f"⚠️ Citer/Verifier fallback falhou: {e}")

    parsed = extract_json_strict(response_text, expect="object") or {}

    if not parsed and response_text:
        parse_failures.append({
            "node": "citer_verifier",
            "model": model_used,
            "reason": "parse_failed",
            "sample": response_text[:600],
        })

    claims = parsed.get("claims", []) or []
    coverage = parsed.get("coverage", 1.0)
    if isinstance(coverage, str):
        try:
            coverage = float(coverage)
        except ValueError:
            coverage = 1.0
    coverage = max(0.0, min(1.0, coverage))

    summary = parsed.get("summary", "") or ""
    critical_gaps = parsed.get("critical_gaps", []) or []

    verified_claims = [c for c in claims if c.get("status") == "verified"]
    unverified_claims = [c for c in claims if c.get("status") == "unverified"]

    # Build verified context by appending an explicit "pendências" list
    # (safe + deterministic; avoids brittle in-place text mutations).
    verified_context = research_context
    pending_lines: List[str] = []
    for claim in unverified_claims[:25]:
        text = (claim.get("text") or "").strip()
        if not text:
            continue
        if claim.get("needs_verification_tag"):
            pending_lines.append(f"- [VERIFICAR] {text[:400]}")
    if pending_lines:
        verified_context = (
            f"{research_context}\n\n"
            "## PENDÊNCIAS DE VERIFICAÇÃO (Citer/Verifier)\n"
            + "\n".join(pending_lines)
            + "\n"
        )

    # Determine if should force HIL
    min_coverage = float(state.get("citer_min_coverage", 0.6) or 0.6)
    force_hil = coverage < min_coverage or len(critical_gaps) > 2

    # Determine if should block debate entirely
    try:
        block_threshold = float(state.get("citer_block_debate_coverage", 0.3) or 0.3)
    except Exception:
        block_threshold = 0.3
    try:
        min_unverified = int(state.get("citer_block_debate_min_unverified", 1) or 1)
    except Exception:
        min_unverified = 1
    block_debate = coverage < block_threshold and len(unverified_claims) >= max(0, min_unverified)
    auto_approve_hil = bool(state.get("auto_approve_hil", False))
    force_hil_effective = bool(force_hil) or bool(block_debate)

    result = {
        "skipped": False,
        "coverage": round(coverage, 3),
        "verified_count": len(verified_claims),
        "unverified_count": len(unverified_claims),
        "verified_claims": verified_claims[:20],  # Limit for state size
        "unverified_claims": unverified_claims[:20],
        "critical_gaps": critical_gaps[:10],
        "summary": summary[:500],
        "model_used": model_used,
        "force_hil": force_hil,
        "block_debate": block_debate,
        "min_coverage": min_coverage,
        "block_threshold": block_threshold,
        "block_min_unverified": min_unverified,
    }

    logger.info(
        f"✅ Citer/Verifier: coverage={coverage:.1%}, "
        f"verified={len(verified_claims)}, unverified={len(unverified_claims)}, "
        f"force_hil={force_hil}, block={block_debate}"
    )

    # Emit event if job_manager available
    try:
        from app.services.job_manager import job_manager
        job_id = state.get("job_id")
        if job_id:
            job_manager.emit_event(
                job_id,
                "CITER_VERIFIER_COMPLETE",
                result,
            )
    except Exception:
        pass

    # If debate is blocked, produce a diagnostic markdown (do not proceed with empty document).
    final_markdown = None
    final_decision = None
    final_decision_reasons: List[str] = []
    if block_debate and not auto_approve_hil:
        final_decision = "NEED_EVIDENCE"
        final_decision_reasons = [
            "citer_verifier_block_debate",
            f"coverage_below_threshold:{round(coverage, 3)}<{round(block_threshold, 3)}",
            f"unverified_claims:{len(unverified_claims)}>=min:{min_unverified}",
        ]
        gaps_md = "\n".join(f"- {str(g).strip()}" for g in critical_gaps[:10] if str(g).strip()) or "- (nenhuma informada)"
        unverified_md = "\n".join(
            f"- {str(c.get('text') or '').strip()[:240]}"
            for c in unverified_claims[:20]
            if isinstance(c, dict) and str(c.get("text") or "").strip()
        ) or "- (nenhuma)"
        final_markdown = (
            "# ⛔ Rastreabilidade insuficiente para minutar\n\n"
            f"**Cobertura verificada:** {round(coverage * 100, 1)}% (mínimo configurado: {round(min_coverage * 100, 1)}%)\n\n"
            "O workflow bloqueou o debate/minuta porque muitas afirmações do contexto não conseguem ser rastreadas "
            "a fontes disponíveis (RAG/web).\n\n"
            "## Principais lacunas\n"
            f"{gaps_md}\n\n"
            "## Afirmações sem fonte (amostra)\n"
            f"{unverified_md}\n\n"
            "## Como resolver\n"
            "- Habilite `web_search`/`dense_research` ou amplie `rag_sources` (ex.: incluir `juris`/`lei`).\n"
            "- Aumente o `rag_top_k` e/ou permita `rag_retry_expand_scope`.\n"
            "- Forneça peças/decisões/anexos relevantes para o RAG local.\n"
        )

    return {
        **state,
        "citer_verifier_result": result,
        "verified_context": verified_context,
        # Prefer the verified/annotated context for downstream drafting.
        "research_context": verified_context,
        "citer_verifier_force_hil": force_hil,
        "citer_verifier_coverage": coverage,
        "citer_verifier_critical_gaps": critical_gaps,
        # Wire force_hil into existing HIL mechanics (soft): it will trigger final HIL if enabled.
        "quality_gate_force_hil": bool(state.get("quality_gate_force_hil", False)) or bool(force_hil_effective),
        # Early-exit payload when debate is blocked.
        "final_markdown": final_markdown or state.get("final_markdown"),
        "final_decision": final_decision or state.get("final_decision"),
        "final_decision_reasons": final_decision_reasons or state.get("final_decision_reasons", []),
        "json_parse_failures": parse_failures,
    }
