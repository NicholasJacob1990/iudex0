import hashlib
import json
import re
from typing import Any, Dict, List, Optional, Tuple


def _hash_id(prefix: str, seed: str) -> str:
    digest = hashlib.md5(seed.encode("utf-8", errors="ignore")).hexdigest()[:10]
    return f"{prefix}_{digest}"


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _map_severity(value: str) -> str:
    normalized = (value or "").strip().lower()
    if any(tok in normalized for tok in ("cr", "crit", "alta", "high")):
        return "warning"
    if any(tok in normalized for tok in ("media", "média", "medium")):
        return "warning"
    return "info"


def _truncate(value: str, max_chars: int = 220) -> str:
    cleaned = re.sub(r"\s+", " ", (value or "").strip())
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[:max_chars].rstrip() + "..."


def _extract_section_anchor(
    formatted_content: str,
    section_hint: str,
    max_chars: int = 3500,
) -> str:
    """
    Best-effort extraction of a formatted snippet around a section hint like:
      - "Seção 16. Ônus da Prova e a Plataforma Nacional"
      - "24. Ressarcimento ..."
    """
    text = formatted_content or ""
    if not text or not section_hint:
        return ""

    hint = section_hint.strip()
    # Prefer numeric section match
    num_match = re.search(r"\b(\d{1,3})\b", hint)
    if num_match:
        num = num_match.group(1)
        m = re.search(rf"^##\s+{re.escape(num)}\.", text, flags=re.MULTILINE)
        if m:
            start = m.start()
            next_m = re.search(r"^##\s+\d+\.", text[m.end():], flags=re.MULTILINE)
            end = m.end() + next_m.start() if next_m else len(text)
            snippet = text[start:min(end, start + max_chars)]
            return snippet.strip()

    # Fallback: title substring match (remove "Seção X." prefix)
    title = re.sub(r"^se[cç][aã]o\s+\d+\.\s*", "", hint, flags=re.IGNORECASE).strip()
    if title:
        try:
            m = re.search(re.escape(title[:80]), text, flags=re.IGNORECASE)
        except re.error:
            m = None
        if m:
            start = max(0, m.start() - 800)
            return text[start:m.start() + max_chars].strip()

    return ""


def _guess_reference_from_text(*values: str) -> Optional[str]:
    blob = " ".join([v for v in values if v]).strip()
    if not blob:
        return None
    # Acronyms (TUNEP, SUS, TRF, STF, etc.)
    acr = re.search(r"\b[A-Z]{4,8}\b", blob)
    if acr:
        return acr.group(0)
    if re.search(r"\bluciana\b", blob, flags=re.IGNORECASE):
        return "Juíza Luciana"
    return None


def build_preventive_hil_issues(
    preventive_audit: Dict[str, Any],
    *,
    formatted_content: str,
) -> List[Dict[str, Any]]:
    """
    Converts preventive fidelity audit JSON into the HIL "audit_issues" format
    consumed by /transcription/apply-revisions.

    Adds optional fields to improve LLM patching:
      - raw_evidence (snippets from RAW)
      - formatted_context (snippet from formatted content around the suggested section)
      - user_instruction (short, deterministic instruction)
    """
    if not isinstance(preventive_audit, dict):
        return []

    issues: List[Dict[str, Any]] = []

    for idx, item in enumerate(_as_list(preventive_audit.get("omissoes_criticas"))):
        obj = item if isinstance(item, dict) else {"impacto": _as_text(item)}
        tipo = _as_text(obj.get("tipo"))
        gravidade = _as_text(obj.get("gravidade"))
        impacto = _as_text(obj.get("impacto")) or _as_text(obj.get("descricao")) or _as_text(obj.get("trecho_raw"))
        local = _as_text(obj.get("localizacao_formatado"))
        raw_snippet = _as_text(obj.get("trecho_raw"))
        llm_formatted_snippet = _as_text(obj.get("trecho_formatado"))
        verdict = _as_text(obj.get("veredito"))

        description = f"Omissao critica{f' ({tipo})' if tipo else ''}: {_truncate(impacto or 'Conteudo omitido.')}"
        seed = json.dumps(obj, ensure_ascii=False, sort_keys=True)

        reference = _guess_reference_from_text(tipo, impacto, raw_snippet) or ""
        formatted_context = _extract_section_anchor(formatted_content, local)

        instruction = "Inserir no texto formatado a informacao presente no RAW, com 1-3 frases, preservando a estrutura existente."
        if tipo.lower() == "autor" and ("luciana" in raw_snippet.lower() or "luciana" in impacto.lower()):
            instruction = "Na introducao, incluir a referencia a Juiza Luciana conforme o RAW (sem inventar detalhes)."

        issue: Dict[str, Any] = {
            "id": _hash_id("preventive_omissao", seed + f":{idx}"),
            "type": "preventive_omissao",
            "fix_type": "content",
            "severity": _map_severity(gravidade),
            "description": description,
            "suggestion": "Inserir o trecho omitido com base no RAW.",
            "source": "preventive_audit",
            "origin": "preventive_audit",
        }
        if verdict:
            issue["verdict"] = verdict
        if reference:
            issue["reference"] = reference
        if local:
            issue["suggested_section"] = local
        if raw_snippet:
            issue["raw_evidence"] = [{"snippet": raw_snippet}]
        if formatted_context:
            issue["formatted_context"] = formatted_context
        # Prefer LLM-provided snippet, fall back to section anchor
        evidence_for_display = llm_formatted_snippet or (formatted_context[:500] if formatted_context else "")
        if evidence_for_display:
            issue["evidence_formatted"] = _truncate(evidence_for_display, 500)
        if instruction:
            issue["user_instruction"] = instruction
        issues.append(issue)

    for idx, item in enumerate(_as_list(preventive_audit.get("distorcoes"))):
        obj = item if isinstance(item, dict) else {"descricao": _as_text(item)}
        tipo = _as_text(obj.get("tipo"))
        gravidade = _as_text(obj.get("gravidade"))
        raw_snippet = _as_text(obj.get("trecho_raw"))
        formatted_snippet = _as_text(obj.get("trecho_formatado"))
        correction = _as_text(obj.get("correcao"))
        verdict = _as_text(obj.get("veredito"))

        parts = []
        if raw_snippet:
            parts.append(f'RAW: "{_truncate(raw_snippet, 120)}"')
        if formatted_snippet:
            parts.append(f'Formatado: "{_truncate(formatted_snippet, 120)}"')
        if correction:
            parts.append(f"Correcao: {_truncate(correction, 140)}")
        description = f"Distorcao{f' ({tipo})' if tipo else ''}: {_truncate(' | '.join(parts) or 'Revisar diferenca entre RAW e formatado.', 240)}"
        seed = json.dumps(obj, ensure_ascii=False, sort_keys=True)

        reference = _guess_reference_from_text(tipo, correction, formatted_snippet, raw_snippet) or ""
        instruction = "Corrigir no texto formatado para refletir exatamente o RAW, sem alterar a estrutura."
        if correction and formatted_snippet:
            instruction = f"Substituir '{formatted_snippet}' por '{correction}' no trecho correspondente."
        elif correction:
            instruction = f"Aplicar a correcao: {correction}."

        issue = {
            "id": _hash_id("preventive_distorcao", seed + f":{idx}"),
            "type": "preventive_distorcao",
            "fix_type": "content",
            "severity": _map_severity(gravidade),
            "description": description,
            "suggestion": f"Corrigir para: {_truncate(correction, 180)}" if correction else "Corrigir conforme RAW.",
            "source": "preventive_audit",
            "origin": "preventive_audit",
        }
        if verdict:
            issue["verdict"] = verdict
        if reference:
            issue["reference"] = reference
        if raw_snippet:
            issue["raw_evidence"] = [{"snippet": raw_snippet}]
        if formatted_snippet:
            issue["evidence_formatted"] = formatted_snippet
        if instruction:
            issue["user_instruction"] = instruction
        issues.append(issue)

    for idx, item in enumerate(_as_list(preventive_audit.get("alucinacoes"))):
        obj = item if isinstance(item, dict) else {"trecho_formatado": _as_text(item)}
        confidence = _as_text(obj.get("confianca"))
        trecho_formatado = _as_text(obj.get("trecho_formatado"))
        action = _as_text(obj.get("acao_sugerida"))
        verdict = _as_text(obj.get("veredito"))
        description = f"Possivel alucinacao{f' ({confidence})' if confidence else ''}: {_truncate(trecho_formatado or 'Trecho inexistente no RAW.', 220)}"
        seed = json.dumps(obj, ensure_ascii=False, sort_keys=True)

        issue = {
            "id": _hash_id("preventive_alucinacao", seed + f":{idx}"),
            "type": "preventive_alucinacao",
            "fix_type": "content",
            "severity": _map_severity(confidence),
            "description": description,
            "suggestion": f"Acao sugerida: {action}" if action else "Revisar e remover se nao houver suporte no RAW.",
            "source": "preventive_audit",
            "origin": "preventive_audit",
            "user_instruction": "Remover ou ajustar o trecho no texto formatado apenas se ele nao tiver suporte no RAW.",
        }
        if verdict:
            issue["verdict"] = verdict
        if trecho_formatado:
            issue["evidence_formatted"] = trecho_formatado
        issues.append(issue)

    # ── auditoria_fontes.erros_criticos → preventive_autoria ──
    fontes = preventive_audit.get("auditoria_fontes") or {}
    for idx, item in enumerate(_as_list(fontes.get("erros_criticos"))):
        obj = item if isinstance(item, dict) else {"correcao_sugerida": _as_text(item)}
        tipo = _as_text(obj.get("tipo"))
        gravidade = _as_text(obj.get("gravidade"))
        local = _as_text(obj.get("localizacao"))
        correcao = _as_text(obj.get("correcao_sugerida"))
        raw_snippet = _as_text(obj.get("trecho_raw"))
        formatted_snippet = _as_text(obj.get("trecho_formatado"))
        verdict = _as_text(obj.get("veredito"))

        description = f"Erro de autoria{f' ({tipo})' if tipo else ''}: {_truncate(correcao or formatted_snippet or 'Revisar atribuição de autoria.', 220)}"
        seed = json.dumps(obj, ensure_ascii=False, sort_keys=True)

        reference = _guess_reference_from_text(correcao, formatted_snippet, raw_snippet) or ""
        formatted_context = _extract_section_anchor(formatted_content, local) if local else ""

        instruction = correcao if correcao else "Corrigir a atribuição de autoria conforme indicado no RAW."

        issue: Dict[str, Any] = {
            "id": _hash_id("preventive_autoria", seed + f":{idx}"),
            "type": "preventive_autoria",
            "fix_type": "content",
            "severity": _map_severity(gravidade),
            "description": description,
            "suggestion": _truncate(correcao, 200) if correcao else "Corrigir autoria conforme RAW.",
            "source": "preventive_audit",
            "origin": "preventive_audit",
        }
        if verdict:
            issue["verdict"] = verdict
        if reference:
            issue["reference"] = reference
        if local:
            issue["suggested_section"] = local
        if raw_snippet:
            issue["raw_evidence"] = [{"snippet": raw_snippet}]
        if formatted_context:
            issue["formatted_context"] = formatted_context
        evidence_for_display = formatted_snippet or (formatted_context[:500] if formatted_context else "")
        if evidence_for_display:
            issue["evidence_formatted"] = _truncate(evidence_for_display, 500)
        if instruction:
            issue["user_instruction"] = instruction
        issues.append(issue)

    # ── auditoria_fontes.ambiguidades → preventive_autoria_ambiguidade ──
    for idx, item in enumerate(_as_list(fontes.get("ambiguidades"))):
        obj = item if isinstance(item, dict) else {"sugestao": _as_text(item)}
        local = _as_text(obj.get("localizacao"))
        problema = _as_text(obj.get("problema"))
        sugestao = _as_text(obj.get("sugestao"))
        verdict = _as_text(obj.get("veredito"))

        combined = f"{problema} {sugestao}".lower()
        # Ignore tooling/meta ambiguities that are not actionable text corrections.
        if (
            "resposta inválida da auditoria de fontes" in combined
            or "reexecutar auditoria de fontes para obter nota consolidada" in combined
        ):
            continue

        description = f"Ambiguidade de autoria: {_truncate(problema or sugestao or 'Revisar identificação de autor.', 220)}"
        seed = json.dumps(obj, ensure_ascii=False, sort_keys=True)

        reference = _guess_reference_from_text(problema, sugestao) or ""
        formatted_context = _extract_section_anchor(formatted_content, local) if local else ""

        instruction = sugestao if sugestao else "Revisar e esclarecer a identificação do autor no trecho indicado."

        issue = {
            "id": _hash_id("preventive_ambiguidade", seed + f":{idx}"),
            "type": "preventive_autoria_ambiguidade",
            "fix_type": "content",
            "severity": "info",
            "description": description,
            "suggestion": _truncate(sugestao, 200) if sugestao else "Esclarecer autoria.",
            "source": "preventive_audit",
            "origin": "preventive_audit",
        }
        if verdict:
            issue["verdict"] = verdict
        if reference:
            issue["reference"] = reference
        if local:
            issue["suggested_section"] = local
        if formatted_context:
            issue["formatted_context"] = formatted_context
        evidence_for_display = formatted_context[:500] if formatted_context else ""
        if evidence_for_display:
            issue["evidence_formatted"] = _truncate(evidence_for_display, 500)
        if instruction:
            issue["user_instruction"] = instruction
        issues.append(issue)

    for idx, item in enumerate(_as_list(preventive_audit.get("problemas_contexto"))):
        obj = item if isinstance(item, dict) else {"localizacao": _as_text(item)}
        tipo = _as_text(obj.get("tipo"))
        local = _as_text(obj.get("localizacao"))
        suggestion = _as_text(obj.get("sugestao"))
        llm_context_snippet = _as_text(obj.get("trecho_formatado"))
        verdict = _as_text(obj.get("veredito"))
        description = f"Problema de contexto{f' ({tipo})' if tipo else ''}: {_truncate(local or 'Revisar contexto e transicoes.', 220)}"
        seed = json.dumps(obj, ensure_ascii=False, sort_keys=True)

        issue = {
            "id": _hash_id("preventive_contexto", seed + f":{idx}"),
            "type": "preventive_contexto",
            "fix_type": "content",
            "severity": "info",
            "description": description,
            "suggestion": _truncate(suggestion, 200) if suggestion else "Ajustar transicao/contexto conforme necessario.",
            "source": "preventive_audit",
            "origin": "preventive_audit",
            "user_instruction": "Ajustar a transicao/contexto preservando o conteudo juridico e a estrutura do documento.",
        }
        if verdict:
            issue["verdict"] = verdict
        if local:
            issue["suggested_section"] = local
            formatted_context = _extract_section_anchor(formatted_content, local)
            if formatted_context:
                issue["formatted_context"] = formatted_context
        # Prefer LLM-provided snippet, fall back to section anchor
        evidence_for_display = llm_context_snippet or (formatted_context[:500] if local and formatted_context else "")
        if evidence_for_display:
            issue["evidence_formatted"] = _truncate(evidence_for_display, 500)
        issues.append(issue)

    return issues
