"""
Template Generator (NL -> UserTemplateV1 JSON)
"""

from __future__ import annotations

from typing import Any, Dict, Optional
import json
from loguru import logger

from app.schemas.smart_template import UserTemplateV1
from app.services.ai.model_registry import DEFAULT_JUDGE_MODEL
from app.services.ai.langgraph_legal_workflow import _call_model_any_async


def _extract_json_obj(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except Exception:
                    return None
    return None


async def generate_user_template_from_description(
    description: str,
    doc_kind: Optional[str] = None,
    doc_subtype: Optional[str] = None,
    model_id: Optional[str] = None,
) -> Dict[str, Any]:
    if not description:
        raise ValueError("Descricao obrigatoria para gerar template.")

    resolved_model = model_id or DEFAULT_JUDGE_MODEL
    fallback_model = "gpt-4o" if "gpt" not in resolved_model.lower() else "gemini-2.0-flash-001"

    hint_kind = doc_kind or ""
    hint_subtype = doc_subtype or ""

    prompt = f"""
Você é um especialista em documentos jurídicos brasileiros. Converta a descrição abaixo em um objeto JSON seguindo estritamente o schema:

UserTemplateV1 = {{
  "version": 1,
  "name": "string (nome do template)",
  "doc_kind": "PLEADING|APPEAL|JUDICIAL_DECISION|OFFICIAL|EXTRAJUDICIAL|LEGAL_NOTE|NOTARIAL|CONTRACT",
  "doc_subtype": "string (ex: PETICAO_INICIAL, CONTESTACAO, APELACAO)",
  "format": {{
    "numbering": "ROMAN|ARABIC|CLAUSE|NONE",
    "tone": "very_formal|formal|neutral|executive",
    "verbosity": "short|medium|long",
    "voice": "first_person|third_person|impersonal"
  }},
  "sections": [{{"title": "string", "required": true, "notes": "string_opcional"}}],
  "required_fields": [{{"name": "string", "type": "text|number|date|list|id|reference", "required": true, "on_missing": "block|mark_pending"}}],
  "checklist": [{{"id": "string", "level": "required|recommended|conditional|forbidden", "rule": "has_section|has_field|mentions_any|forbidden_phrase_any", "value": "string_ou_lista", "condition": "none|if_tutela|if_personal_data|if_appeal", "note": "string_opcional"}}]
}}

Regras:
1) Retorne APENAS o JSON, sem markdown nem explicações.
2) Use doc_kind="{hint_kind}" e doc_subtype="{hint_subtype}" se fornecidos.
3) Prefira seções concisas (máximo 12) e mantenha required_fields minimal.
4) Não invente regras de checklist fora do schema.
5) Nomes de seções devem estar em português jurídico brasileiro.

Descrição do documento:
{description}
""".strip()

    # Retry logic with temperature escalation
    temperatures = [0.2, 0.4, 0.6]
    models_to_try = [resolved_model, resolved_model, fallback_model]
    last_error = None

    for attempt, (temp, model) in enumerate(zip(temperatures, models_to_try)):
        try:
            logger.debug(f"[TemplateGenerator] Attempt {attempt + 1}/3 with model={model}, temp={temp}")
            raw = await _call_model_any_async(model, prompt, temperature=temp, max_tokens=10000)
            parsed = _extract_json_obj(raw or "")
            
            if parsed:
                if doc_kind and not parsed.get("doc_kind"):
                    parsed["doc_kind"] = doc_kind
                if doc_subtype and not parsed.get("doc_subtype"):
                    parsed["doc_subtype"] = doc_subtype

                validated = UserTemplateV1.model_validate(parsed)
                logger.info(f"[TemplateGenerator] Success on attempt {attempt + 1}")
                return validated.model_dump()
            else:
                last_error = "JSON inválido retornado pelo modelo"
                logger.warning(f"[TemplateGenerator] Attempt {attempt + 1} failed: invalid JSON")
        except Exception as e:
            last_error = str(e)
            logger.warning(f"[TemplateGenerator] Attempt {attempt + 1} failed: {e}")

    raise ValueError(f"Falha ao gerar template após 3 tentativas. Último erro: {last_error}")

