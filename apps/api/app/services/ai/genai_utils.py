from __future__ import annotations

from typing import Any, Optional


def _get(obj: Any, key: str, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def extract_genai_text(resp: Any) -> str:
    """
    Extrai texto de respostas do SDK `google-genai` (genai.Client.models.generate_content),
    tolerando diferenças entre versões (resp.text vs candidates/content/parts).
    """
    if resp is None:
        return ""

    text = _get(resp, "text", None)
    if isinstance(text, str) and text.strip():
        return text.strip()

    # Fallback: candidates[0].content.parts[0].text
    cands = _get(resp, "candidates", None) or []
    if not cands:
        return ""

    first = cands[0]
    content = _get(first, "content", None)
    parts = _get(content, "parts", None) or []
    if not parts:
        return ""

    part0 = parts[0]
    part_text = _get(part0, "text", None)
    if isinstance(part_text, str):
        return part_text.strip()

    return ""

