"""
Contextual Assistant API Endpoint

Provides a streaming chat assistant that can operate within any context
(workflow, document, corpus) with persistent conversation history.

Exposes:
- POST /assistant/chat: Send message with optional context (SSE streaming)
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.workflow import Workflow
from app.models.document import Document

router = APIRouter()
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class AssistantMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class AssistantRequest(BaseModel):
    message: str
    context_type: Optional[str] = None  # "workflow" | "document" | "corpus"
    context_id: Optional[str] = None
    conversation_history: List[AssistantMessage] = []


class AssistantResponse(BaseModel):
    content: str
    citations: List[Dict[str, Any]] = []


# ---------------------------------------------------------------------------
# SSE helpers (same pattern as chat.py)
# ---------------------------------------------------------------------------

def sse_data(payload: dict) -> str:
    """Format a single SSE data frame."""
    return f"data: {json.dumps(payload)}\n\n"


# ---------------------------------------------------------------------------
# Context loaders
# ---------------------------------------------------------------------------

async def _load_workflow_context(
    context_id: str,
    user: User,
    db: AsyncSession,
) -> tuple[str, list[dict]]:
    """Return (system_context_text, citations) for a workflow."""
    result = await db.execute(
        select(Workflow).where(
            Workflow.id == context_id,
            Workflow.user_id == str(user.id),
        )
    )
    wf = result.scalars().first()
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow nao encontrado")

    nodes_summary = ""
    graph = wf.graph_json or {}
    nodes = graph.get("nodes", [])
    for node in nodes:
        data = node.get("data", {})
        label = data.get("label", node.get("type", "?"))
        prompt_snippet = (data.get("prompt") or "")[:200]
        nodes_summary += f"  - [{node.get('type', '?')}] {label}"
        if prompt_snippet:
            nodes_summary += f": {prompt_snippet}"
        nodes_summary += "\n"

    context_text = (
        f"Voce esta ajudando o usuario no contexto do workflow \"{wf.name}\".\n"
        f"Descricao: {wf.description or '(sem descricao)'}\n"
        f"Nos do grafo ({len(nodes)}):\n{nodes_summary}\n"
        "Use essas informacoes para dar respostas contextuais sobre o workflow."
    )

    citations = [{"source": "workflow", "title": wf.name, "id": wf.id}]
    return context_text, citations


async def _load_document_context(
    context_id: str,
    user: User,
    db: AsyncSession,
) -> tuple[str, list[dict]]:
    """Return (system_context_text, citations) for a document."""
    result = await db.execute(
        select(Document).where(
            Document.id == context_id,
            Document.user_id == str(user.id),
        )
    )
    doc = result.scalars().first()
    if not doc:
        raise HTTPException(status_code=404, detail="Documento nao encontrado")

    context_text = (
        f"Voce esta ajudando o usuario no contexto do documento \"{doc.name}\".\n"
        f"Tipo: {doc.type.value if doc.type else 'desconhecido'}\n"
        f"Categoria: {doc.category.value if doc.category else 'nao definida'}\n"
        f"Status: {doc.status.value if doc.status else 'desconhecido'}\n"
        "Use essas informacoes para dar respostas contextuais sobre o documento."
    )

    citations = [{"source": "document", "title": doc.name, "id": doc.id}]
    return context_text, citations


async def _load_corpus_context(
    context_id: str,
    user: User,
    db: AsyncSession,
) -> tuple[str, list[dict]]:
    """Return (system_context_text, citations) for a corpus context."""
    # Corpus is a lighter context — just indicate the corpus scope
    context_text = (
        f"Voce esta ajudando o usuario no contexto do corpus (id: {context_id}).\n"
        "O usuario pode estar analisando resultados de busca no corpus.\n"
        "Ajude com interpretacao e analise dos resultados."
    )
    citations = [{"source": "corpus", "id": context_id}]
    return context_text, citations


# ---------------------------------------------------------------------------
# Streaming generator
# ---------------------------------------------------------------------------

async def _stream_assistant_response(
    message: str,
    system_prompt: str,
    conversation_history: List[AssistantMessage],
    citations: List[Dict[str, Any]],
):
    """Stream the assistant response via SSE using OpenAI-compatible API."""
    try:
        # Build messages list
        messages = [{"role": "system", "content": system_prompt}]

        for msg in conversation_history:
            messages.append({"role": msg.role, "content": msg.content})

        messages.append({"role": "user", "content": message})

        # Try OpenAI client first (most common), fallback to Claude
        client = None
        model = os.getenv("ASSISTANT_MODEL", "gpt-4o-mini")

        try:
            from app.services.ai.agent_clients import get_async_openai_client
            client = get_async_openai_client()
        except Exception:
            pass

        if client is None:
            # Fallback: try Claude via Anthropic
            try:
                from app.services.ai.agent_clients import get_async_claude_client
                claude_client = get_async_claude_client()
                if claude_client is not None:
                    # Use Anthropic messages API
                    async for chunk in _stream_claude(claude_client, messages, citations):
                        yield chunk
                    return
            except Exception as exc:
                logger.warning("Claude client fallback failed: %s", exc)

            # No client available
            yield sse_data({"content": "Nenhum provedor de IA configurado. Verifique as variaveis de ambiente."})
            yield sse_data({"done": True})
            return

        # OpenAI streaming
        stream = await client.chat.completions.create(
            model=model,
            messages=messages,
            stream=True,
            temperature=0.3,
            max_tokens=2048,
        )

        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                yield sse_data({"content": delta.content})

        # Send citations at the end if any
        if citations:
            yield sse_data({"citations": citations})

        yield sse_data({"done": True})

    except Exception as exc:
        logger.exception("Assistant streaming error: %s", exc)
        yield sse_data({"error": str(exc)})
        yield sse_data({"done": True})


async def _stream_claude(claude_client, messages: list, citations: list):
    """Stream response from Anthropic Claude API."""
    from app.services.ai.agent_clients import _is_anthropic_vertex_client

    system_content = ""
    chat_messages = []
    for msg in messages:
        if msg["role"] == "system":
            system_content += msg["content"] + "\n"
        else:
            chat_messages.append(msg)

    model = os.getenv("ASSISTANT_CLAUDE_MODEL", "claude-sonnet-4-20250514")

    kwargs: dict = {
        "model": model,
        "max_tokens": 2048,
        "messages": chat_messages,
    }
    if system_content.strip():
        kwargs["system"] = system_content.strip()

    async with claude_client.messages.stream(**kwargs) as stream:
        async for text in stream.text_stream:
            yield sse_data({"content": text})

    if citations:
        yield sse_data({"citations": citations})

    yield sse_data({"done": True})


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

SYSTEM_PROMPT_BASE = """Voce e o Assistente Contextual do Iudex, uma plataforma juridica com IA.

Suas responsabilidades:
- Ajudar o usuario a entender e trabalhar com o contexto atual (workflow, documento ou corpus)
- Responder perguntas sobre direito brasileiro
- Sugerir melhorias em workflows e documentos juridicos
- Ser conciso e preciso nas respostas

Regras:
- Responda sempre em portugues brasileiro
- Cite fontes quando possivel
- Seja direto e objetivo
- Se nao souber algo, diga claramente
"""


@router.post("/chat")
async def assistant_chat(
    request: AssistantRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Streaming contextual assistant chat.

    Accepts a message, optional context (workflow/document/corpus),
    and conversation history. Returns SSE stream.
    """
    system_prompt = SYSTEM_PROMPT_BASE
    citations: List[Dict[str, Any]] = []

    # Load context if provided
    if request.context_type and request.context_id:
        try:
            if request.context_type == "workflow":
                ctx_text, ctx_citations = await _load_workflow_context(
                    request.context_id, current_user, db
                )
            elif request.context_type == "document":
                ctx_text, ctx_citations = await _load_document_context(
                    request.context_id, current_user, db
                )
            elif request.context_type == "corpus":
                ctx_text, ctx_citations = await _load_corpus_context(
                    request.context_id, current_user, db
                )
            else:
                ctx_text, ctx_citations = "", []

            if ctx_text:
                system_prompt += f"\n\n## CONTEXTO ATUAL\n{ctx_text}"
            citations = ctx_citations

        except HTTPException:
            raise
        except Exception as exc:
            logger.warning("Failed to load context %s/%s: %s", request.context_type, request.context_id, exc)

    return StreamingResponse(
        _stream_assistant_response(
            message=request.message,
            system_prompt=system_prompt,
            conversation_history=request.conversation_history,
            citations=citations,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
