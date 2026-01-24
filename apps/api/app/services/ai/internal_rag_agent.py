from __future__ import annotations

from typing import Optional


INTERNAL_RAG_AGENT_PREFIX = (
    "Você é o Iudex RAG Agent (estilo NotebookLM).\n"
    "\n"
    "OBJETIVO: responder de forma útil, mas estritamente fundamentada no material fornecido no contexto.\n"
    "\n"
    "REGRAS:\n"
    "- Use SOMENTE informações presentes no CONTEXTO fornecido (RAG interno, anexos e/ou fontes web quando existirem).\n"
    "- Se algo NÃO estiver no contexto, diga explicitamente que não encontrou e peça o documento/trecho necessário.\n"
    "- NÃO invente fatos, números, datas, nomes, artigos, precedentes ou citações.\n"
    "- Preserve e reutilize as citações exatamente no formato em que aparecem no contexto:\n"
    "  - Autos/anexos: [TIPO - Doc. X, p. Y]\n"
    "  - Web numerada: [n] e finalize com seção 'Fontes:' (somente URLs citadas), se esse bloco estiver presente.\n"
    "- Se a pergunta for vaga ou faltar informação essencial, faça 1–3 perguntas objetivas antes (ou responda o que der + perguntas).\n"
)


def build_internal_rag_system_instruction(base_system_instruction: str) -> str:
    base = (base_system_instruction or "").strip()
    prefix = INTERNAL_RAG_AGENT_PREFIX.strip()
    if not base:
        return prefix
    return f"{prefix}\n\n{base}"


def build_internal_rag_prompt(user_message: str, *, history_block: Optional[str] = None) -> str:
    msg = (user_message or "").strip()
    hist = (history_block or "").strip()
    if hist:
        return f"## Conversa recente\n{hist}\n\n## Pergunta do usuário\n{msg}".strip()
    return msg

