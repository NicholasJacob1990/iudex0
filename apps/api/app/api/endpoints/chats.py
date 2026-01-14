"""
Endpoints de Chat e Geração de Documentos
"""

import asyncio
import json
import os
import re
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Body
from fastapi.responses import StreamingResponse
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import desc
from sqlalchemy.orm.attributes import flag_modified

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.time_utils import utcnow
from app.models.chat import Chat, ChatMessage, ChatMode
from app.models.user import User
from app.models.document import Document, DocumentStatus, DocumentType
from app.schemas.chat import (
    ChatCreate, 
    ChatDuplicate,
    ChatResponse, 
    ChatUpdate, 
    MessageCreate, 
    MessageResponse,
    GenerateDocumentRequest,
    GenerateDocumentResponse,
    OutlineRequest,
    OutlineResponse
)
from functools import lru_cache
from app.services.document_generator import DocumentGenerator
from app.services.mention_parser import MentionService
from app.services.token_budget_service import TokenBudgetService
from app.services.command_service import CommandService
from app.services.ai.orchestrator import MultiAgentOrchestrator
from app.services.ai.agent_clients import (
    get_gpt_client,
    get_gemini_client,
    get_async_claude_client,
    get_xai_client,
    get_openrouter_client,
    get_async_xai_client,
    get_async_openrouter_client,
    build_system_instruction,
    stream_openai_async,
    stream_anthropic_async,
    stream_vertex_gemini_async,
    call_openai_async,
    call_anthropic_async,
    call_vertex_gemini_async,
)
from app.services.ai.model_registry import get_api_model_name, get_model_config, validate_model_id, DEFAULT_JUDGE_MODEL, get_thinking_category
from app.services.ai.thinking_parser import inject_thinking_prompt, ThinkingStreamParser
from app.services.model_registry import get_model_config as get_budget_model_config
from app.services.ai.langgraph_legal_workflow import outline_node
from app.services.chat_service import ChatService
from app.services.web_search_service import web_search_service, build_web_context, is_breadth_first
from app.services.rag_module import create_rag_manager, get_knowledge_graph
from app.services.ai.citations import to_perplexity
from app.services.ai.citations.base import render_perplexity, stable_numbering
from app.services.ai.agent_clients import _is_anthropic_vertex_client
from app.services.ai.genai_utils import extract_genai_text

chat_service = ChatService()

router = APIRouter()

# Lazy singleton: evita inicialização pesada (RAG/embeddings) em import-time.
@lru_cache(maxsize=1)
def get_document_generator() -> DocumentGenerator:
    return DocumentGenerator()

@lru_cache(maxsize=1)
def get_chat_orchestrator() -> MultiAgentOrchestrator:
    return MultiAgentOrchestrator()

@lru_cache(maxsize=1)
def get_rag_manager():
    try:
        return create_rag_manager()
    except Exception as exc:
        logger.warning(f"⚠️ RAGManager não pôde ser inicializado: {exc}")
        return None

mention_service = MentionService()
token_service = TokenBudgetService()
command_service = CommandService()


def sse_event(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"

def chunk_text(text: str, chunk_size: int = 24):
    for i in range(0, len(text), chunk_size):
        yield text[i:i + chunk_size]


HISTORY_LIMIT = 12
SUMMARY_RECENT_KEEP = 6
SUMMARY_MIN_MESSAGES = 12
SUMMARY_UPDATE_EVERY = 6
SUMMARY_MAX_CHARS = 1200
SUMMARY_SNIPPET_CHARS = 180
HISTORY_BUFFER_TOKENS = 1000
HISTORY_DEFAULT_MAX_OUTPUT = 4096
HISTORY_MAX_FETCH = 120


def _normalize_snippet(text: str, max_len: int = SUMMARY_SNIPPET_CHARS) -> str:
    compact = " ".join(str(text or "").split())
    if len(compact) <= max_len:
        return compact
    return f"{compact[:max_len].rstrip()}..."


def _build_safe_thinking_summary(
    *,
    dense_research: bool,
    web_search: bool,
    used_context: bool,
    used_outline: bool
) -> Optional[str]:
    steps = ["Interpretou a solicitacao e o objetivo."]

    if dense_research:
        steps.append("Aplicou pesquisa profunda e consolidou evidencias relevantes.")
    elif web_search:
        steps.append("Realizou pesquisa web quando pertinente.")

    if used_context:
        steps.append("Considerou o contexto e materiais fornecidos.")

    if used_outline:
        steps.append("Seguiu a estrutura sugerida para organizar a resposta.")

    steps.append("Sintetizou a resposta de forma objetiva.")

    max_steps = 4
    if len(steps) > max_steps:
        steps = steps[:max_steps - 1] + [steps[-1]]

    summary = "Resumo do raciocinio (seguro):\n- " + "\n- ".join(steps)
    return summary


async def _get_recent_messages(db: AsyncSession, chat_id: str, limit: int) -> List[ChatMessage]:
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.chat_id == chat_id)
        .order_by(desc(ChatMessage.created_at))
        .limit(limit)
    )
    return result.scalars().all()


def _serialize_history(messages: List[ChatMessage]) -> List[dict]:
    items: List[dict] = []
    for msg in reversed(messages or []):
        role = str(msg.role or "").lower()
        if role not in ("user", "assistant"):
            continue
        content = str(msg.content or "").strip()
        if not content:
            continue
        items.append({"role": role, "content": content})
    return items


def _build_summary(history: List[dict]) -> str:
    if not history:
        return ""
    lines: List[str] = []
    for item in history[-SUMMARY_RECENT_KEEP:]:
        role = str(item.get("role") or "").lower()
        label = "Usuário" if role == "user" else "Assistente"
        content = _normalize_snippet(item.get("content", ""))
        if not content:
            continue
        lines.append(f"- {label}: {content}")
        if len(lines) >= SUMMARY_RECENT_KEEP:
            break
    summary = "\n".join(lines).strip()
    if len(summary) > SUMMARY_MAX_CHARS:
        summary = summary[:SUMMARY_MAX_CHARS].rstrip()
    return summary


def _build_history_block(summary_text: Optional[str], history: List[dict]) -> str:
    parts: List[str] = []
    if summary_text:
        parts.append("### RESUMO DA CONVERSA")
        parts.append(str(summary_text).strip())
    if history:
        parts.append("### ÚLTIMAS MENSAGENS")
        for item in history[-HISTORY_LIMIT:]:
            role = str(item.get("role") or "").lower()
            content = str(item.get("content") or "").strip()
            if not content:
                continue
            label = "Usuário" if role == "user" else "Assistente"
            parts.append(f"{label}: {content}")
    return "\n".join(parts).strip()


def _estimate_token_usage(prompt: str, output: str, model_id: str, label: Optional[str] = None) -> dict:
    cfg = get_budget_model_config(model_id) if model_id else get_budget_model_config(DEFAULT_JUDGE_MODEL)
    context_window = cfg.get("context_window", 0)
    provider = cfg.get("provider", "unknown")
    input_tokens = token_service.estimate_tokens(prompt)
    output_tokens = token_service.estimate_tokens(output)
    total_tokens = input_tokens + output_tokens
    percent_used = (total_tokens / context_window * 100) if context_window else 0
    return {
        "provider": provider,
        "model": label or model_id,
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
        },
        "limits": {
            "context_window": context_window,
            "percent_used": percent_used,
        },
        "estimated": True,
    }


def _maybe_update_conversation_summary(chat: Chat, history_payload: List[dict]) -> bool:
    if not chat or len(history_payload) < SUMMARY_MIN_MESSAGES:
        return False

    pending = int(chat.context.get("summary_pending_turns", 0)) + 1
    chat.context["summary_pending_turns"] = pending
    if pending < SUMMARY_UPDATE_EVERY:
        return True

    chat.context["summary_pending_turns"] = 0
    summary = _build_summary(history_payload)
    if summary:
        chat.context["conversation_summary"] = summary
    return True


def _infer_history_model_ids(message: str, requested_model: Optional[str], chat_context: dict) -> List[str]:
    message_lower = message.lower()
    if "@todos" in message_lower or "@all" in message_lower:
        return ["gpt-5.2", "claude-4.5-sonnet", "gemini-3-flash"]

    targets: List[str] = []
    if "@gpt" in message_lower:
        targets.append("gpt-5.2")
    if "@claude" in message_lower:
        targets.append("claude-4.5-sonnet")
    if "@gemini" in message_lower:
        targets.append("gemini-3-flash")
    if targets:
        return targets

    if requested_model:
        return [requested_model]

    ctx_model = chat_context.get("model")
    if isinstance(ctx_model, str) and ctx_model.strip():
        return [ctx_model.strip()]

    return [DEFAULT_JUDGE_MODEL]


def _get_min_context_window(model_ids: List[str]) -> tuple[int, int]:
    context_window = None
    max_output = None
    for model_id in model_ids:
        cfg = get_budget_model_config(model_id)
        ctx = cfg.get("context_window", 0)
        out = cfg.get("max_output", HISTORY_DEFAULT_MAX_OUTPUT)
        if context_window is None or ctx < context_window:
            context_window = ctx
        if max_output is None or out < max_output:
            max_output = out
    return context_window or 0, max_output or HISTORY_DEFAULT_MAX_OUTPUT


def _estimate_history_tokens(history: List[dict]) -> int:
    total = 0
    for item in history:
        role = str(item.get("role") or "").strip().lower() or "user"
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        total += token_service.estimate_tokens(f"{role}: {content}")
    return total


def _trim_history_to_budget(history: List[dict], max_tokens: int) -> List[dict]:
    if max_tokens <= 0 or not history:
        return []
    total = 0
    trimmed: List[dict] = []
    for item in reversed(history):
        role = str(item.get("role") or "").strip().lower() or "user"
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        item_tokens = token_service.estimate_tokens(f"{role}: {content}")
        if total + item_tokens > max_tokens and trimmed:
            break
        if total + item_tokens > max_tokens and not trimmed:
            continue
        trimmed.append(item)
        total += item_tokens
    return list(reversed(trimmed))


def _trim_history_for_models(
    history: List[dict],
    model_ids: List[str],
    prompt: str,
    base_instruction: str,
    summary_text: Optional[str]
) -> List[dict]:
    context_window, max_output = _get_min_context_window(model_ids)
    if context_window <= 0:
        return history[-HISTORY_LIMIT:]

    base_tokens = token_service.estimate_tokens(prompt) + token_service.estimate_tokens(base_instruction)
    summary_tokens = token_service.estimate_tokens(summary_text or "")
    available = context_window - max_output - HISTORY_BUFFER_TOKENS - base_tokens - summary_tokens
    return _trim_history_to_budget(history, max(0, available))

def normalize_page_range(min_pages: Optional[int], max_pages: Optional[int]) -> tuple[int, int]:
    min_value = int(min_pages or 0)
    max_value = int(max_pages or 0)
    if min_value < 0:
        min_value = 0
    if max_value < 0:
        max_value = 0
    if min_value and max_value and max_value < min_value:
        max_value = min_value
    if max_value and not min_value:
        min_value = 1
    if min_value and not max_value:
        max_value = min_value
    return min_value, max_value


def normalize_rag_sources(raw_sources: Optional[List[str]]) -> List[str]:
    if not raw_sources:
        return []
    normalized = []
    for item in raw_sources:
        value = str(item).strip().lower()
        if value:
            normalized.append(value)
    return list(dict.fromkeys(normalized))


def build_rag_context(
    query: str,
    rag_sources: Optional[List[str]],
    rag_top_k: Optional[int],
    attachment_mode: str,
    adaptive_routing: bool,
    crag_gate: bool,
    crag_min_best_score: float,
    crag_min_avg_score: float,
    hyde_enabled: bool,
    graph_rag_enabled: bool,
    graph_hops: int,
    dense_research: bool,
    tenant_id: str,
    user_id: Optional[str] = None,
) -> tuple[str, str, List[dict]]:
    sources = normalize_rag_sources(rag_sources)
    if adaptive_routing and not sources:
        sources = ["lei", "juris", "pecas_modelo"]
    if not sources:
        return "", "", []

    rag_manager = get_rag_manager()
    if not rag_manager:
        return "", "", []

    top_k = int(rag_top_k or 8)
    if dense_research:
        top_k = max(top_k, 12)
    top_k = max(1, min(top_k, 50))

    results: List[dict] = []
    try:
        if hyde_enabled:
            results = rag_manager.hyde_search(
                query=query,
                sources=sources,
                top_k=top_k,
                user_id=user_id,
                tenant_id=tenant_id,
            )
        else:
            results = rag_manager.hybrid_search(
                query=query,
                sources=sources,
                top_k=top_k,
                user_id=user_id,
                tenant_id=tenant_id,
            )
    except Exception as exc:
        logger.warning(f"⚠️ RAG search falhou: {exc}")
        return "", "", []

    if crag_gate and results:
        scores = [
            float(r.get("final_score") or r.get("score") or 0.0)
            for r in results
        ]
        best_score = max(scores) if scores else 0.0
        avg_score = (sum(scores) / len(scores)) if scores else 0.0
        if best_score < crag_min_best_score or avg_score < crag_min_avg_score:
            return "", "", []

    max_chars = 8000 if attachment_mode == "prompt_injection" else 4000
    rag_context = rag_manager.format_sources_for_prompt(results, max_chars=max_chars)

    graph_context = ""
    if graph_rag_enabled and results:
        graph = get_knowledge_graph()
        if graph:
            graph_context = graph.enrich_context(results, hops=max(1, min(int(graph_hops or 1), 5)))

    return rag_context, graph_context, results


@router.get("/", response_model=List[ChatResponse])
async def list_chats(
    skip: int = 0,
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Listar chats do usuário
    """
    query = select(Chat).where(
        Chat.user_id == current_user.id,
        Chat.is_active == True
    ).order_by(desc(Chat.updated_at)).offset(skip).limit(limit)
    
    result = await db.execute(query)
    chats = result.scalars().all()
    return chats


@router.post("/", response_model=ChatResponse)
async def create_chat(
    chat_in: ChatCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Criar novo chat
    """
    chat = Chat(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        title=chat_in.title,
        mode=chat_in.mode,
        context=chat_in.context,
        created_at=utcnow(),
        updated_at=utcnow()
    )
    
    db.add(chat)
    await db.commit()
    await db.refresh(chat)
    return chat


@router.get("/{chat_id}", response_model=ChatResponse)
async def get_chat(
    chat_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Obter detalhes do chat
    """
    result = await db.execute(select(Chat).where(Chat.id == chat_id, Chat.user_id == current_user.id))
    chat = result.scalars().first()
    
    if not chat:
        raise HTTPException(status_code=404, detail="Chat não encontrado")
        
    return chat


@router.post("/{chat_id}/duplicate", response_model=ChatResponse, status_code=status.HTTP_201_CREATED)
async def duplicate_chat(
    chat_id: str,
    payload: ChatDuplicate = Body(default=ChatDuplicate()),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Duplicar chat com todas as mensagens
    """
    result = await db.execute(
        select(Chat).where(
            Chat.id == chat_id,
            Chat.user_id == current_user.id,
            Chat.is_active == True
        )
    )
    chat = result.scalars().first()

    if not chat:
        raise HTTPException(status_code=404, detail="Chat não encontrado")

    base_title = (chat.title or "Chat").strip()
    requested_title = (payload.title or "").strip()
    new_title = requested_title or f"Cópia de {base_title}"

    new_chat = Chat(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        title=new_title,
        mode=chat.mode,
        context=dict(chat.context or {}),
        is_active=True,
        created_at=utcnow(),
        updated_at=utcnow()
    )

    db.add(new_chat)

    messages_result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.chat_id == chat.id)
        .order_by(ChatMessage.created_at)
    )
    messages = messages_result.scalars().all()

    for msg in messages:
        db.add(ChatMessage(
            id=str(uuid.uuid4()),
            chat_id=new_chat.id,
            role=msg.role,
            content=msg.content,
            attachments=list(msg.attachments or []),
            thinking=msg.thinking,
            msg_metadata=dict(msg.msg_metadata or {}),
            created_at=msg.created_at
        ))

    await db.commit()
    await db.refresh(new_chat)
    return new_chat


@router.delete("/{chat_id}")
async def delete_chat(
    chat_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Deletar chat (soft delete)
    """
    result = await db.execute(select(Chat).where(Chat.id == chat_id, Chat.user_id == current_user.id))
    chat = result.scalars().first()
    
    if not chat:
        raise HTTPException(status_code=404, detail="Chat não encontrado")
        
    chat.is_active = False
    await db.commit()
    
    return {"message": "Chat deletado com sucesso"}


@router.get("/{chat_id}/messages", response_model=List[MessageResponse])
async def list_messages(
    chat_id: str,
    skip: int = 0,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Listar mensagens do chat
    """
    # Verificar acesso ao chat
    chat_result = await db.execute(select(Chat).where(Chat.id == chat_id, Chat.user_id == current_user.id))
    if not chat_result.scalars().first():
        raise HTTPException(status_code=404, detail="Chat não encontrado")
        
    query = select(ChatMessage).where(
        ChatMessage.chat_id == chat_id
    ).order_by(ChatMessage.created_at).offset(skip).limit(limit)
    
    result = await db.execute(query)
    messages = result.scalars().all()
    return messages


@router.post("/{chat_id}/messages", response_model=MessageResponse)
async def send_message(
    chat_id: str,
    message_in: MessageCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Enviar mensagem para o chat e obter resposta simples (Claude)
    """
    # Verificar chat
    result = await db.execute(select(Chat).where(Chat.id == chat_id, Chat.user_id == current_user.id))
    chat = result.scalars().first()
    
    if not chat:
        raise HTTPException(status_code=404, detail="Chat não encontrado")

    history_messages = await _get_recent_messages(db, chat_id, HISTORY_MAX_FETCH)
    conversation_history_full = _serialize_history(history_messages)
    history_model_ids = _infer_history_model_ids(message_in.content, message_in.model, chat.context)
    base_instruction = build_system_instruction(message_in.chat_personality)
    conversation_history = _trim_history_for_models(
        conversation_history_full,
        history_model_ids,
        message_in.content,
        base_instruction,
        chat.context.get("conversation_summary")
    )
    turn_id = str(uuid.uuid4())

    # Salvar mensagem do usuário
    user_msg = ChatMessage(
        id=str(uuid.uuid4()),
        chat_id=chat_id,
        role="user",
        content=message_in.content,
        attachments=message_in.attachments,
        msg_metadata={"turn_id": turn_id},
        created_at=utcnow()
    )
    db.add(user_msg)
    
    # 1. Verificar Slash Commands
    cmd_response, cmd_error = await command_service.parse_command(
        message_in.content, db, current_user.id, chat.context
    )
    
    if cmd_response or cmd_error:
        # É comando - responder imediatamente sem chamar LLM
        ai_content = cmd_response if cmd_response else f"⚠️ Erro ao processar comando: {cmd_error}"
        token_usage = _estimate_token_usage(message_in.content, ai_content, DEFAULT_JUDGE_MODEL, "command")
        ai_msg = ChatMessage(
            id=str(uuid.uuid4()),
            chat_id=chat_id,
            role="assistant",
            content=ai_content,
            thinking=None, # Comandos não pensam
            msg_metadata={"turn_id": turn_id, "token_usage": token_usage},
            created_at=utcnow()
        )
        
        # Persistir chat (caso o comando tenha alterado contexto)
        flag_modified(chat, "context")
        db.add(chat) # Garantir que o chat está na sessão

        history_payload = conversation_history_full + [
            {"role": "user", "content": message_in.content},
            {"role": "assistant", "content": ai_content},
        ]
        if _maybe_update_conversation_summary(chat, history_payload):
            flag_modified(chat, "context")
        
        db.add(ai_msg)
        await db.commit()
        await db.refresh(ai_msg)
        return ai_msg

    # 2. Processar menções (Parser) + Sticky Context
    sticky_docs = chat.context.get("sticky_docs", [])
    clean_content, system_context, mentions_meta = await mention_service.parse_mentions(
        message_in.content, db, current_user.id, sticky_docs=sticky_docs
    )
    
    current_context = chat.context.copy()
    if system_context:
        current_context["referenced_content"] = system_context

    current_context["chat_personality"] = message_in.chat_personality
    current_context["conversation_history"] = conversation_history

    # Persistir sticky docs se houver mudança
    if chat.context.get("sticky_docs") != sticky_docs:
        chat.context["sticky_docs"] = sticky_docs
        # Force update
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(chat, "context")
        await db.commit()
    
    # 3. Pré-checagem de Orçamento de Tokens
    # Usa contagem precisa se houver menções (documentos grandes)
    target_model = "gemini-2.5-pro-preview-06-05" # Default do sistema
    
    if mentions_meta: # Documentos grandes - usar contagem real
        budget = await token_service.check_budget_precise(clean_content, current_context, target_model)
    else:
        budget = token_service.check_budget(clean_content, current_context, target_model)
    
    if budget["status"] == "error":
        # Bloquear envio
        raise HTTPException(
            status_code=400, 
            detail=budget["message"]
        )
    
    # Se warning, logar mas prosseguir
    if budget["status"] == "warning":
        print(f"⚠️ {budget['message']}")

    # Obter resposta da IA (Simples)
    try:
        # Usar conteúdo limpo + contexto enriquecido
        ai_response = await get_chat_orchestrator().simple_chat(
            message=clean_content,
            context=current_context,
            conversation_history=conversation_history
        )
        ai_content = ai_response.content
        thinking = _build_safe_thinking_summary(
            dense_research=bool(message_in.dense_research),
            web_search=bool(message_in.web_search),
            used_context=bool(system_context or mentions_meta),
            used_outline=False
        )
        
        # 4. Telemetria Pós-execução
        item_telemetry = token_service.get_telemetry(ai_response.usage_metadata or {}, target_model)
        
    except Exception as e:
        # Fallback em caso de erro (ex: falta de API Key)
        print(f"Erro na IA: {e}")
        ai_content = f"Desculpe, estou operando em modo offline no momento. Recebi sua mensagem: '{message_in.content}'"
        thinking = "Erro de conexão com LLM"
        item_telemetry = {}
        item_telemetry = {}
    
    # Montar metadados finais
    final_metadata = {"turn_id": turn_id}
    if mentions_meta: final_metadata["mentions"] = mentions_meta
    if item_telemetry: final_metadata["token_usage"] = item_telemetry
    
    # Salvar resposta da IA
    ai_msg = ChatMessage(
        id=str(uuid.uuid4()),
        chat_id=chat_id,
        role="assistant",
        content=ai_content,
        thinking=thinking,
        msg_metadata=final_metadata if final_metadata else {},
        created_at=utcnow()
    )
    db.add(ai_msg)
    
    # Atualizar chat
    chat.updated_at = utcnow()

    history_payload = conversation_history_full + [
        {"role": "user", "content": message_in.content},
        {"role": "assistant", "content": ai_content},
    ]
    if _maybe_update_conversation_summary(chat, history_payload):
        flag_modified(chat, "context")
    
    await db.commit()
    await db.refresh(ai_msg)
    
    return ai_msg


@router.post("/{chat_id}/messages/stream")
async def send_message_stream(
    chat_id: str,
    message_in: MessageCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Enviar mensagem para o chat com streaming SSE
    """
    result = await db.execute(select(Chat).where(Chat.id == chat_id, Chat.user_id == current_user.id))
    chat = result.scalars().first()

    if not chat:
        raise HTTPException(status_code=404, detail="Chat não encontrado")

    history_messages = await _get_recent_messages(db, chat_id, HISTORY_MAX_FETCH)
    conversation_history_full = _serialize_history(history_messages)
    history_model_ids = _infer_history_model_ids(message_in.content, message_in.model, chat.context)
    base_instruction = build_system_instruction(message_in.chat_personality)
    conversation_history = _trim_history_for_models(
        conversation_history_full,
        history_model_ids,
        message_in.content,
        base_instruction,
        chat.context.get("conversation_summary")
    )
    turn_id = str(uuid.uuid4())

    user_msg = ChatMessage(
        id=str(uuid.uuid4()),
        chat_id=chat_id,
        role="user",
        content=message_in.content,
        attachments=message_in.attachments,
        msg_metadata={"turn_id": turn_id},
        created_at=utcnow()
    )
    db.add(user_msg)
    await db.commit()

    # 1. Verificar Slash Commands
    cmd_response, cmd_error = await command_service.parse_command(
        message_in.content, db, current_user.id, chat.context
    )

    if cmd_response or cmd_error:
        ai_content = cmd_response if cmd_response else f"⚠️ Erro ao processar comando: {cmd_error}"
        token_usage = _estimate_token_usage(message_in.content, ai_content, DEFAULT_JUDGE_MODEL, "command")
        ai_msg = ChatMessage(
            id=str(uuid.uuid4()),
            chat_id=chat_id,
            role="assistant",
            content=ai_content,
            thinking=None,
            msg_metadata={"turn_id": turn_id, "token_usage": token_usage},
            created_at=utcnow()
        )
        flag_modified(chat, "context")
        db.add(chat)
        history_payload = conversation_history_full + [
            {"role": "user", "content": message_in.content},
            {"role": "assistant", "content": ai_content},
        ]
        if _maybe_update_conversation_summary(chat, history_payload):
            flag_modified(chat, "context")
        db.add(ai_msg)
        chat.updated_at = utcnow()
        await db.commit()

        async def stream_command():
            for chunk in chunk_text(ai_content):
                yield sse_event({"type": "token", "delta": chunk, "turn_id": turn_id})
                await asyncio.sleep(0)
            yield sse_event({
                "type": "done",
                "full_text": ai_content,
                "message_id": ai_msg.id,
                "turn_id": turn_id,
                "token_usage": token_usage,
            })

        return StreamingResponse(stream_command(), media_type="text/event-stream")

    # 2. Processar menções + contexto
    sticky_docs = chat.context.get("sticky_docs", [])
    clean_content, system_context, mentions_meta = await mention_service.parse_mentions(
        message_in.content, db, current_user.id, sticky_docs=sticky_docs
    )

    current_context = chat.context.copy()
    if system_context:
        current_context["referenced_content"] = system_context
    current_context["chat_personality"] = message_in.chat_personality
    current_context["conversation_history"] = conversation_history
    current_context["web_search"] = message_in.web_search
    current_context["search_mode"] = message_in.search_mode
    current_context["rag_sources"] = message_in.rag_sources
    current_context["rag_top_k"] = message_in.rag_top_k
    current_context["attachment_mode"] = message_in.attachment_mode
    current_context["context_mode"] = message_in.context_mode
    current_context["context_files"] = message_in.context_files
    current_context["cache_ttl"] = message_in.cache_ttl
    current_context["adaptive_routing"] = message_in.adaptive_routing
    current_context["crag_gate"] = message_in.crag_gate
    current_context["crag_min_best_score"] = message_in.crag_min_best_score
    current_context["crag_min_avg_score"] = message_in.crag_min_avg_score
    current_context["hyde_enabled"] = message_in.hyde_enabled
    current_context["graph_rag_enabled"] = message_in.graph_rag_enabled
    current_context["graph_hops"] = message_in.graph_hops
    current_context["dense_research"] = message_in.dense_research
    current_context["reasoning_level"] = message_in.reasoning_level  # NEW: Sync thinking level

    context_updated = False
    if chat.context.get("sticky_docs") != sticky_docs:
        chat.context["sticky_docs"] = sticky_docs
        flag_modified(chat, "context")
        context_updated = True
    if chat.context.get("web_search") != message_in.web_search:
        chat.context["web_search"] = message_in.web_search
        flag_modified(chat, "context")
        context_updated = True
    if chat.context.get("search_mode") != message_in.search_mode:
        chat.context["search_mode"] = message_in.search_mode
        flag_modified(chat, "context")
        context_updated = True
    if chat.context.get("rag_sources") != message_in.rag_sources:
        chat.context["rag_sources"] = message_in.rag_sources
        flag_modified(chat, "context")
        context_updated = True
    if chat.context.get("rag_top_k") != message_in.rag_top_k:
        chat.context["rag_top_k"] = message_in.rag_top_k
        flag_modified(chat, "context")
        context_updated = True
    if chat.context.get("attachment_mode") != message_in.attachment_mode:
        chat.context["attachment_mode"] = message_in.attachment_mode
        flag_modified(chat, "context")
        context_updated = True
    if chat.context.get("context_mode") != message_in.context_mode:
        chat.context["context_mode"] = message_in.context_mode
        flag_modified(chat, "context")
        context_updated = True
    if chat.context.get("context_files") != message_in.context_files:
        chat.context["context_files"] = message_in.context_files
        flag_modified(chat, "context")
        context_updated = True
    if chat.context.get("cache_ttl") != message_in.cache_ttl:
        chat.context["cache_ttl"] = message_in.cache_ttl
        flag_modified(chat, "context")
        context_updated = True
    if chat.context.get("adaptive_routing") != message_in.adaptive_routing:
        chat.context["adaptive_routing"] = message_in.adaptive_routing
        flag_modified(chat, "context")
        context_updated = True
    if chat.context.get("crag_gate") != message_in.crag_gate:
        chat.context["crag_gate"] = message_in.crag_gate
        flag_modified(chat, "context")
        context_updated = True
    if chat.context.get("crag_min_best_score") != message_in.crag_min_best_score:
        chat.context["crag_min_best_score"] = message_in.crag_min_best_score
        flag_modified(chat, "context")
        context_updated = True
    if chat.context.get("crag_min_avg_score") != message_in.crag_min_avg_score:
        chat.context["crag_min_avg_score"] = message_in.crag_min_avg_score
        flag_modified(chat, "context")
        context_updated = True
    if chat.context.get("hyde_enabled") != message_in.hyde_enabled:
        chat.context["hyde_enabled"] = message_in.hyde_enabled
        flag_modified(chat, "context")
        context_updated = True
    if chat.context.get("graph_rag_enabled") != message_in.graph_rag_enabled:
        chat.context["graph_rag_enabled"] = message_in.graph_rag_enabled
        flag_modified(chat, "context")
        context_updated = True
    if chat.context.get("graph_hops") != message_in.graph_hops:
        chat.context["graph_hops"] = message_in.graph_hops
        flag_modified(chat, "context")
        context_updated = True
    if chat.context.get("dense_research") != message_in.dense_research:
        chat.context["dense_research"] = message_in.dense_research
        flag_modified(chat, "context")
        context_updated = True
    if context_updated:
        await db.commit()
        context_updated = False

    rag_context, graph_context, _ = build_rag_context(
        query=clean_content,
        rag_sources=message_in.rag_sources,
        rag_top_k=message_in.rag_top_k,
        attachment_mode=message_in.attachment_mode,
        adaptive_routing=message_in.adaptive_routing,
        crag_gate=message_in.crag_gate,
        crag_min_best_score=message_in.crag_min_best_score,
        crag_min_avg_score=message_in.crag_min_avg_score,
        hyde_enabled=message_in.hyde_enabled,
        graph_rag_enabled=message_in.graph_rag_enabled,
        graph_hops=message_in.graph_hops,
        dense_research=message_in.dense_research,
        tenant_id=current_user.id,
        user_id=current_user.id,
    )
    if rag_context:
        current_context["rag_context"] = rag_context
    if graph_context:
        current_context["graph_context"] = graph_context

    # 3. Orçamento de tokens
    target_model = "gemini-2.5-pro-preview-06-05"
    if mentions_meta:
        budget = await token_service.check_budget_precise(clean_content, current_context, target_model)
    else:
        budget = token_service.check_budget(clean_content, current_context, target_model)

    if budget["status"] == "error":
        raise HTTPException(status_code=400, detail=budget["message"])
    if budget["status"] == "warning":
        print(f"⚠️ {budget['message']}")

    # 4. Resposta da IA (streaming real)
    message_lower = clean_content.lower()
    target_models: List[str] = []

    if "@todos" in message_lower or "@all" in message_lower:
        target_models = ["gpt", "claude", "gemini"]
    else:
        if "@gpt" in message_lower:
            target_models.append("gpt")
        if "@claude" in message_lower:
            target_models.append("claude")
        if "@gemini" in message_lower:
            target_models.append("gemini")

    explicit_mentions = bool(target_models)

    chat_personality = (current_context.get("chat_personality") or "juridico").lower()
    reasoning_level = current_context.get("reasoning_level", "medium")
    logger.info(f"🧠 [Stream] reasoning_level={reasoning_level}")  # DEBUG
    web_search = current_context.get("web_search", False)
    search_mode = (current_context.get("search_mode") or "hybrid").lower()
    if search_mode not in ("shared", "native", "hybrid"):
        search_mode = "hybrid"

    requested_model = (message_in.model or current_context.get("model") or "").strip()
    model_overrides: dict = {}
    gpt_override_provider: Optional[str] = None
    if requested_model and not explicit_mentions:
        try:
            requested_model = validate_model_id(
                requested_model,
                for_juridico=(chat_personality == "juridico"),
                field_name="model"
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        model_cfg = get_model_config(requested_model)
        provider = model_cfg.provider if model_cfg else None
        model_key = None
        if provider in ("openai", "xai", "openrouter", "deepseek", "meta"):
            model_key = "gpt"
            gpt_override_provider = provider
        elif provider == "anthropic":
            model_key = "claude"
        elif provider == "google":
            model_key = "gemini"
        if not model_key:
            raise HTTPException(status_code=400, detail=f"Modelo '{requested_model}' não suportado no chat.")

        model_overrides[model_key] = requested_model
        if not target_models:
            target_models = [model_key]

        current_context["model"] = requested_model
        if chat.context.get("model") != requested_model:
            chat.context["model"] = requested_model
            flag_modified(chat, "context")
            context_updated = True

    if context_updated:
        await db.commit()

    gpt_client = get_gpt_client()
    claude_client = get_async_claude_client()
    gemini_client = get_gemini_client()
    xai_client = get_xai_client()
    openrouter_client = get_openrouter_client()
    xai_async_client = get_async_xai_client()
    openrouter_async_client = get_async_openrouter_client()

    gpt_call_client = gpt_client
    gpt_stream_client = gpt_client
    if gpt_override_provider == "xai":
        gpt_call_client = xai_client
        gpt_stream_client = xai_async_client
    elif gpt_override_provider in ("openrouter", "deepseek", "meta"):
        gpt_call_client = openrouter_client
        gpt_stream_client = openrouter_async_client

    if not target_models:
        if chat_personality == "geral":
            if gpt_client:
                target_models = ["gpt"]
            elif claude_client:
                target_models = ["claude"]
            else:
                target_models = ["gemini"]
        else:
            if claude_client:
                target_models = ["claude"]
            elif gpt_client:
                target_models = ["gpt"]
            else:
                target_models = ["gemini"]

    available = {
        "gpt": gpt_call_client is not None,
        "claude": claude_client is not None,
        "gemini": gemini_client is not None,
    }
    target_models = [m for m in target_models if available.get(m)]
    if not target_models:
        fallback_text = (
            "Desculpe, estou operando em modo offline no momento. "
            f"Recebi sua mensagem: '{message_in.content}'"
        )
        offline_usage = _estimate_token_usage(message_in.content, fallback_text, DEFAULT_JUDGE_MODEL, "offline")
        ai_msg = ChatMessage(
            id=str(uuid.uuid4()),
            chat_id=chat_id,
            role="assistant",
            content=fallback_text,
            thinking="Erro de conexão com LLM",
            msg_metadata={"model": "offline", "turn_id": turn_id, "token_usage": offline_usage},
            created_at=utcnow()
        )
        history_payload = conversation_history_full + [
            {"role": "user", "content": message_in.content},
            {"role": "assistant", "content": fallback_text},
        ]
        if _maybe_update_conversation_summary(chat, history_payload):
            flag_modified(chat, "context")
        db.add(ai_msg)
        chat.updated_at = utcnow()
        await db.commit()

        async def stream_offline():
            for chunk in chunk_text(fallback_text):
                yield sse_event({"type": "token", "delta": chunk, "model": "offline", "turn_id": turn_id})
                await asyncio.sleep(0)
            yield sse_event({
                "type": "done",
                "full_text": fallback_text,
                "model": "offline",
                "message_id": ai_msg.id,
                "turn_id": turn_id,
                "token_usage": offline_usage,
            })

        return StreamingResponse(stream_offline(), media_type="text/event-stream")

    base_instruction = build_system_instruction(chat_personality)
    if reasoning_level == "high":
        base_instruction += "\n- Aprofunde a análise e considere nuances importantes."
    elif reasoning_level == "low":
        base_instruction += "\n- Seja direto e conciso."

    history_block = _build_history_block(chat.context.get("conversation_summary"), conversation_history)

    multi_query = bool(message_in.multi_query)
    breadth_first = bool(message_in.breadth_first) or (web_search and is_breadth_first(clean_content))
    if message_in.dense_research:
        multi_query = True
        breadth_first = True

    max_tokens = 700 if chat_personality == "geral" else 1800
    temperature = 0.6 if chat_personality == "geral" else 0.3

    gpt_model_id = model_overrides.get("gpt", "gpt-5.2")
    claude_model_id = model_overrides.get("claude", "claude-4.5-sonnet")
    gemini_model_id = model_overrides.get("gemini", "gemini-3-flash")

    model_label = "+".join(
        [model_overrides.get(model_key, model_key) for model_key in target_models]
    )
    native_search_by_model = {
        "gpt": bool(gpt_client and hasattr(gpt_client, "responses") and gpt_override_provider in (None, "openai")),
        "claude": bool(claude_client),
        "gemini": bool(gemini_client),
    }
    allow_native_search = web_search and search_mode in ("native", "hybrid")
    allow_shared_search = web_search and search_mode in ("shared", "hybrid")
    use_shared_search = allow_shared_search and (
        search_mode == "shared"
        or any(not native_search_by_model.get(model_key, False) for model_key in target_models)
    )

    async def stream_response():
        full_text_parts: List[str] = []
        full_thinking_parts: List[str] = []  # NEW: Accumulate real thinking from models
        system_instruction = base_instruction
        if history_block:
            system_instruction += "\n\n## CONTEXTO DA CONVERSA\n" + history_block
        sources = []

        outline_items = []
        if isinstance(message_in.outline, list):
            outline_items = [str(item).strip() for item in message_in.outline if str(item).strip()]
        if outline_items:
            outline_block = "\n".join(f"- {item}" for item in outline_items[:20])
            system_instruction += (
                "\n\n### ESTRUTURA SUGERIDA (OUTLINE)\n"
                "Siga o sumário abaixo para organizar sua resposta, ajustando o nível de detalhe conforme necessário.\n"
                f"{outline_block}\n"
            )

        if rag_context:
            system_instruction += f"\n\n{rag_context}"
        if graph_context:
            system_instruction += f"\n\n{graph_context}"
        if message_in.dense_research:
            system_instruction += "\n- Pesquisa profunda solicitada; aumente a cobertura e valide com mais cuidado."

        if message_in.context_mode == "upload_cache" and message_in.context_files:
            try:
                from app.services.ai.juridico_adapter import get_juridico_adapter

                adapter = get_juridico_adapter()
                if adapter and adapter.is_available():
                    custom_prompt = system_instruction
                    if system_context:
                        custom_prompt += f"\n\n{system_context}"
                    rag_config = {
                        "rag_sources": message_in.rag_sources,
                        "rag_top_k": message_in.rag_top_k,
                        "adaptive_routing": message_in.adaptive_routing,
                        "crag_gate": message_in.crag_gate,
                        "crag_min_best_score": message_in.crag_min_best_score,
                        "crag_min_avg_score": message_in.crag_min_avg_score,
                        "hyde_enabled": message_in.hyde_enabled,
                        "graph_rag_enabled": message_in.graph_rag_enabled,
                        "graph_hops": message_in.graph_hops,
                        "dense_research": message_in.dense_research,
                    }
                    result = await adapter.chat(
                        message=clean_content,
                        history=[],
                        context_files=message_in.context_files,
                        cache_ttl=message_in.cache_ttl,
                        model=message_in.model or None,
                        tenant_id=current_user.id,
                        custom_prompt=custom_prompt,
                        rag_config=rag_config,
                    )
                    reply_text = (result or {}).get("reply", "") or "Não foi possível gerar resposta."
                    for chunk in chunk_text(reply_text):
                        yield sse_event({
                            "type": "token",
                            "delta": chunk,
                            "model": message_in.model or "juridico",
                            "turn_id": turn_id,
                        })
                        await asyncio.sleep(0)

                    usage_model = message_in.model or DEFAULT_JUDGE_MODEL
                    usage_label = message_in.model or "juridico"
                    token_usage = _estimate_token_usage(
                        f"{system_instruction}\n\n{clean_content}",
                        reply_text,
                        usage_model,
                        usage_label
                    )
                    final_metadata = {"turn_id": turn_id, "token_usage": token_usage}
                    if mentions_meta:
                        final_metadata["mentions"] = mentions_meta
                    if message_in.model:
                        final_metadata["model"] = message_in.model

                    thinking_summary = _build_safe_thinking_summary(
                        dense_research=bool(message_in.dense_research),
                        web_search=bool(web_search),
                        used_context=bool(system_context or mentions_meta or rag_context or graph_context),
                        used_outline=bool(outline_items)
                    )

                    history_payload = conversation_history_full + [
                        {"role": "user", "content": message_in.content},
                        {"role": "assistant", "content": reply_text},
                    ]
                    if _maybe_update_conversation_summary(chat, history_payload):
                        flag_modified(chat, "context")

                    ai_msg = ChatMessage(
                        id=str(uuid.uuid4()),
                        chat_id=chat_id,
                        role="assistant",
                        content=reply_text,
                        thinking=thinking_summary,
                        msg_metadata=final_metadata if final_metadata else {},
                        created_at=utcnow()
                    )
                    db.add(ai_msg)
                    chat.updated_at = utcnow()
                    await db.commit()

                    yield sse_event({
                        "type": "done",
                        "full_text": reply_text,
                        "model": message_in.model or "juridico",
                        "message_id": ai_msg.id,
                        "turn_id": turn_id,
                        "token_usage": token_usage,
                        "thinking": thinking_summary,
                    })
                    return
            except Exception as exc:
                logger.warning(f"⚠️ Chat com upload_cache falhou, seguindo fluxo padrão: {exc}")

        if use_shared_search and web_search:
            search_query = re.sub(
                r'@(?:gpt|claude|gemini|all|todos)\\b',
                '',
                clean_content,
                flags=re.IGNORECASE
            ).strip()
            if search_query:
                yield sse_event({"type": "search_started", "query": search_query})
                if multi_query:
                    search_payload = await web_search_service.search_multi(search_query, num_results=8)
                else:
                    search_payload = await web_search_service.search(search_query, num_results=8)
                results = search_payload.get("results") or []
                yield sse_event({
                    "type": "search_done",
                    "query": search_query,
                    "count": len(results),
                    "cached": bool(search_payload.get("cached")),
                    "source": search_payload.get("source"),
                    "queries": search_payload.get("queries") if multi_query else None
                })
                if search_payload.get("success") and results:
                    web_context = build_web_context(search_payload, max_items=8)
                    url_title_stream = [
                        (res.get("url", ""), res.get("title", ""))
                        for res in results
                    ]
                    _, sources = stable_numbering(url_title_stream)
                    system_instruction += (
                        "\n- Use as fontes numeradas abaixo quando relevante."
                        "\n- Cite no texto com [n] e finalize com uma seção 'Fontes:' apenas com as URLs citadas."
                        f"\n\n{web_context}"
                    )
        try:
            async def _call_native_search(model_key: str, prompt: str) -> Optional[str]:
                if model_key == "gpt":
                    if not gpt_client or not hasattr(gpt_client, "responses"):
                        return None
                    def _sync_call():
                        return gpt_client.responses.create(
                            model=get_api_model_name(gpt_model_id),
                            input=[
                                {"role": "system", "content": base_instruction},
                                {"role": "user", "content": prompt},
                            ],
                            tools=[{"type": "web_search"}],
                            temperature=temperature,
                            max_output_tokens=max_tokens,
                        )
                    resp = await asyncio.to_thread(_sync_call)
                    text = to_perplexity("openai", resp)
                    return text or getattr(resp, "output_text", "") or None

                if model_key == "claude":
                    if not claude_client:
                        return None
                    kwargs = {
                        "model": get_api_model_name(claude_model_id),
                        "max_tokens": max_tokens,
                        "system": base_instruction,
                        "messages": [{"role": "user", "content": prompt}],
                        "tools": [{"type": "web_search_20250305", "name": "web_search"}],
                    }
                    beta_header = os.getenv("ANTHROPIC_WEB_SEARCH_BETA", "web-search-2025-03-05").strip()
                    if beta_header:
                        kwargs["extra_headers"] = {"anthropic-beta": beta_header}
                    if _is_anthropic_vertex_client(claude_client):
                        kwargs["anthropic_version"] = os.getenv("ANTHROPIC_VERTEX_VERSION", "vertex-2023-10-16")
                    resp = await claude_client.messages.create(**kwargs)
                    return to_perplexity("claude", resp) or None

                if model_key == "gemini":
                    if not gemini_client:
                        return None
                    from google.genai import types as genai_types
                    tool = genai_types.Tool(google_search=genai_types.GoogleSearch())
                    config = genai_types.GenerateContentConfig(
                        system_instruction=base_instruction,
                        tools=[tool],
                        max_output_tokens=max_tokens,
                        temperature=temperature,
                    )
                    def _sync_call():
                        return gemini_client.models.generate_content(
                            model=get_api_model_name(gemini_model_id),
                            contents=prompt,
                            config=config,
                        )
                    resp = await asyncio.to_thread(_sync_call)
                    text = to_perplexity("gemini", resp)
                    return text or extract_genai_text(resp) or None

                return None

            if breadth_first and len(target_models) == 1:
                model_key = target_models[0]
                worker_tasks = [
                    ("Fontes", "Liste fatos centrais e evidências relevantes para responder à pergunta."),
                    ("Contrapontos", "Apresente controvérsias ou nuances importantes relacionadas ao tema."),
                    ("Contexto", "Explique conceitos-chave e termos técnicos necessários para entender a resposta."),
                ]

                async def call_model(prompt: str, tokens: int) -> Optional[str]:
                    if allow_native_search and not use_shared_search and native_search_by_model.get(model_key):
                        return await _call_native_search(model_key, prompt)
                    if model_key == "gpt":
                        return await call_openai_async(
                            gpt_call_client,
                            prompt,
                            model=get_api_model_name(gpt_model_id),
                            max_tokens=tokens,
                            temperature=temperature,
                            system_instruction=system_instruction,
                        )
                    if model_key == "claude":
                        return await call_anthropic_async(
                            claude_client,
                            prompt,
                            model=get_api_model_name(claude_model_id),
                            max_tokens=tokens,
                            temperature=temperature,
                            system_instruction=system_instruction,
                        )
                    return await call_vertex_gemini_async(
                        gemini_client,
                        prompt,
                        model=get_api_model_name(gemini_model_id),
                        max_tokens=tokens,
                        temperature=temperature,
                        system_instruction=system_instruction,
                    )

                worker_prompts = [
                    f"{clean_content}\n\nTarefa do agente ({title}):\n{task}"
                    for title, task in worker_tasks
                ]
                worker_results = await asyncio.gather(
                    *[call_model(p, 700) for p in worker_prompts],
                    return_exceptions=True
                )
                worker_notes = []
                for (title, _), result in zip(worker_tasks, worker_results):
                    if isinstance(result, Exception) or not result:
                        continue
                    worker_notes.append(f"### {title}\n{result}")

                lead_prompt = (
                    f"{clean_content}\n\n"
                    "Você é o agente líder. Use as notas abaixo para responder de forma objetiva.\n\n"
                    + "\n\n".join(worker_notes)
                )

                lead_text = await call_model(lead_prompt, max_tokens)
                if not lead_text:
                    lead_text = "Não foi possível gerar resposta no momento."
                if sources and "fontes:" not in lead_text.lower():
                    lead_text = render_perplexity(lead_text, sources)

                for chunk in chunk_text(lead_text):
                    yield sse_event({"type": "token", "delta": chunk, "model": model_key, "turn_id": turn_id})
                    await asyncio.sleep(0)

                usage_model_id = gpt_model_id if model_key == "gpt" else claude_model_id if model_key == "claude" else gemini_model_id
                token_usage = _estimate_token_usage(
                    f"{system_instruction}\n\n{lead_prompt}",
                    lead_text,
                    usage_model_id,
                    model_key
                )
                history_payload = conversation_history_full + [
                    {"role": "user", "content": message_in.content},
                    {"role": "assistant", "content": lead_text},
                ]
                if _maybe_update_conversation_summary(chat, history_payload):
                    flag_modified(chat, "context")
                ai_msg = ChatMessage(
                    id=str(uuid.uuid4()),
                    chat_id=chat_id,
                    role="assistant",
                    content=lead_text,
                    thinking=None,
                    msg_metadata={"model": model_key, "breadth_first": True, "turn_id": turn_id, "token_usage": token_usage},
                    created_at=utcnow()
                )
                db.add(ai_msg)
                chat.updated_at = utcnow()
                await db.commit()

                yield sse_event({
                    "type": "done",
                    "full_text": lead_text,
                    "model": model_key,
                    "message_id": ai_msg.id,
                    "turn_id": turn_id,
                    "token_usage": token_usage,
                })
                return

            for idx, model_key in enumerate(target_models):
                model_id = None
                if model_key == "gpt":
                    model_id = gpt_model_id
                elif model_key == "claude":
                    model_id = claude_model_id
                elif model_key == "gemini":
                    model_id = gemini_model_id

                model_cfg = get_model_config(model_id) if model_id else None
                label = model_cfg.label if model_cfg else ""
                if not label:
                    if model_key == "gpt":
                        label = "GPT"
                    elif model_key == "claude":
                        label = "Claude"
                    elif model_key == "gemini":
                        label = "Gemini"

                if len(target_models) > 1:
                    header = f"🤖 **{label}**:\n"
                    full_text_parts.append(header)
                    yield sse_event({"type": "token", "delta": header, "model": model_key})

                if allow_native_search and not use_shared_search and native_search_by_model.get(model_key):
                    native_text = await _call_native_search(model_key, clean_content)
                    if native_text:
                        for chunk in chunk_text(native_text):
                            full_text_parts.append(chunk)
                            yield sse_event({"type": "token", "delta": chunk, "model": model_key})
                        if len(target_models) > 1 and idx < len(target_models) - 1:
                            separator = "\n\n---\n\n"
                            full_text_parts.append(separator)
                            yield sse_event({"type": "token", "delta": separator})
                        continue

                if model_key == "gpt":
                    gpt_api_model = get_api_model_name(gpt_model_id)
                    thinking_cat = get_thinking_category(gpt_model_id)
                    
                    # Determine if we need reasoning_effort (o1/o3) or XML parsing (GPT-5.2)
                    reasoning_effort_param = None
                    effective_instruction = system_instruction
                    xml_parser = None
                    
                    if gpt_api_model.startswith(("o1-", "o3-")):
                        # Native reasoning models
                        reasoning_effort_param = reasoning_level
                        logger.info(f"🧠 [GPT Native] model={gpt_api_model}, reasoning_effort={reasoning_level}")
                    elif thinking_cat == "xml" and reasoning_level in ("high", "medium"):
                        # Standard models: use XML parsing
                        effective_instruction = inject_thinking_prompt(system_instruction, brief=(reasoning_level == "medium"))
                        xml_parser = ThinkingStreamParser()
                        logger.info(f"🧠 [GPT XML] model={gpt_api_model}, using XML parsing")
                    
                    if gpt_stream_client:
                        async for chunk_data in stream_openai_async(
                            gpt_stream_client,
                            clean_content,
                            model=gpt_api_model,
                            max_tokens=max_tokens,
                            temperature=temperature,
                            system_instruction=effective_instruction,
                            reasoning_effort=reasoning_effort_param,
                        ):
                            # Handle tuples from native reasoning
                            if isinstance(chunk_data, tuple):
                                chunk_type, delta = chunk_data
                                if chunk_type == "thinking":
                                    full_thinking_parts.append(delta)
                                    yield sse_event({"type": "thinking", "delta": delta, "model": model_key})
                                else:
                                    full_text_parts.append(delta)
                                    yield sse_event({"type": "token", "delta": delta, "model": model_key})
                            elif xml_parser:
                                # Use XML parser for standard models
                                thinking, content = xml_parser.process_token(chunk_data)
                                if thinking:
                                    full_thinking_parts.append(thinking)
                                    yield sse_event({"type": "thinking", "delta": thinking, "model": model_key})
                                if content:
                                    full_text_parts.append(content)
                                    yield sse_event({"type": "token", "delta": content, "model": model_key})
                            else:
                                # No thinking extraction
                                full_text_parts.append(chunk_data)
                                yield sse_event({"type": "token", "delta": chunk_data, "model": model_key})
                        
                        # Flush XML parser if used
                        if xml_parser:
                            thinking, content = xml_parser.flush()
                            if thinking:
                                full_thinking_parts.append(thinking)
                                yield sse_event({"type": "thinking", "delta": thinking, "model": model_key})
                            if content:
                                full_text_parts.append(content)
                                yield sse_event({"type": "token", "delta": content, "model": model_key})
                    else:
                        fallback_text = await call_openai_async(
                            gpt_call_client,
                            clean_content,
                            model=gpt_api_model,
                            max_tokens=max_tokens,
                            temperature=temperature,
                            system_instruction=effective_instruction,
                        )
                        for chunk in chunk_text(fallback_text or ""):
                            full_text_parts.append(chunk)
                            yield sse_event({"type": "token", "delta": chunk, "model": model_key})
                
                elif model_key == "claude":
                    claude_api_model = get_api_model_name(claude_model_id)
                    thinking_cat = get_thinking_category(claude_model_id)
                    
                    # Determine thinking approach based on category
                    extended_thinking_param = False
                    effective_instruction = system_instruction
                    xml_parser = None
                    
                    if thinking_cat == "native" and reasoning_level in ("high", "medium"):
                        # Sonnet: use native extended_thinking API
                        extended_thinking_param = True
                        logger.info(f"🧠 [Claude Native] model={claude_api_model}, extended_thinking=True")
                    elif thinking_cat == "xml" and reasoning_level in ("high", "medium"):
                        # Opus: use XML parsing
                        effective_instruction = inject_thinking_prompt(system_instruction, brief=(reasoning_level == "medium"))
                        xml_parser = ThinkingStreamParser()
                        logger.info(f"🧠 [Claude XML] model={claude_api_model}, using XML parsing")
                    else:
                        logger.info(f"🧠 [Claude] model={claude_api_model}, thinking_cat={thinking_cat}, no thinking extraction")
                    
                    async for chunk_data in stream_anthropic_async(
                        claude_client,
                        clean_content,
                        model=claude_api_model,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        system_instruction=effective_instruction,
                        extended_thinking=extended_thinking_param,
                    ):
                        # Handle tuples from native thinking API
                        if isinstance(chunk_data, tuple):
                            chunk_type, delta = chunk_data
                            if chunk_type == "thinking":
                                full_thinking_parts.append(delta)
                                yield sse_event({"type": "thinking", "delta": delta, "model": model_key})
                            else:
                                full_text_parts.append(delta)
                                yield sse_event({"type": "token", "delta": delta, "model": model_key})
                        elif xml_parser:
                            # Use XML parser for Opus
                            thinking, content = xml_parser.process_token(chunk_data)
                            if thinking:
                                full_thinking_parts.append(thinking)
                                yield sse_event({"type": "thinking", "delta": thinking, "model": model_key})
                            if content:
                                full_text_parts.append(content)
                                yield sse_event({"type": "token", "delta": content, "model": model_key})
                        else:
                            full_text_parts.append(chunk_data)
                            yield sse_event({"type": "token", "delta": chunk_data, "model": model_key})
                    
                    # Flush XML parser if used
                    if xml_parser:
                        thinking, content = xml_parser.flush()
                        if thinking:
                            full_thinking_parts.append(thinking)
                            yield sse_event({"type": "thinking", "delta": thinking, "model": model_key})
                        if content:
                            full_text_parts.append(content)
                            yield sse_event({"type": "token", "delta": content, "model": model_key})
                
                elif model_key == "gemini":
                    gemini_api_model = get_api_model_name(gemini_model_id)
                    
                    # NEW: Enable extended thinking for Gemini 2.x Pro/Flash and 3.x models
                    thinking_mode_param = None
                    # Check if model supports thinking - use BOTH canonical id and api model name
                    model_str = f"{gemini_model_id} {gemini_api_model}".lower()
                    supports_thinking = (
                        "2.5" in model_str or  # Gemini 2.5 Pro/Flash
                        "2.0" in model_str or  # Gemini 2.0 Flash
                        "gemini-3" in model_str or  # Gemini 3.x canonical
                        ("3-" in model_str and ("flash" in model_str or "pro" in model_str))
                    )
                    
                    if supports_thinking:
                        if reasoning_level == "high":
                            thinking_mode_param = "extended"
                        elif reasoning_level == "medium":
                            thinking_mode_param = "standard"
                        elif reasoning_level == "low":
                            thinking_mode_param = "low"
                        else:
                            # Default to standard thinking if any reasoning level is set
                            thinking_mode_param = "standard"
                    
                    logger.info(f"🧠 [Gemini] model={gemini_api_model}, id={gemini_model_id}, supports={supports_thinking}, mode={thinking_mode_param}")
                    
                    async for chunk_data in stream_vertex_gemini_async(
                        gemini_client,
                        clean_content,
                        model=gemini_api_model,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        system_instruction=system_instruction,
                        thinking_mode=thinking_mode_param,  # NEW
                    ):
                        # NEW: Handle tuples (type, content)
                        if isinstance(chunk_data, tuple):
                            chunk_type, delta = chunk_data
                            if chunk_type == "thinking":
                                full_thinking_parts.append(delta)  # Accumulate real thinking
                                yield sse_event({
                                    "type": "thinking",
                                    "delta": delta,
                                    "model": model_key
                                })
                            else:  # text
                                full_text_parts.append(delta)
                                yield sse_event({"type": "token", "delta": delta, "model": model_key})
                        else:
                            # Retrocompatibilidade: string simples
                            full_text_parts.append(chunk_data)
                            yield sse_event({"type": "token", "delta": chunk_data, "model": model_key})

                if len(target_models) > 1 and idx < len(target_models) - 1:
                    separator = "\n\n---\n\n"
                    full_text_parts.append(separator)
                    yield sse_event({"type": "token", "delta": separator})

            full_text = "".join(full_text_parts)
            if sources and use_shared_search and "fontes:" not in full_text.lower():
                full_text = render_perplexity(full_text, sources)

            usage_model_id = DEFAULT_JUDGE_MODEL
            if len(target_models) == 1:
                if target_models[0] == "gpt":
                    usage_model_id = gpt_model_id
                elif target_models[0] == "claude":
                    usage_model_id = claude_model_id
                elif target_models[0] == "gemini":
                    usage_model_id = gemini_model_id
            usage_label = model_label or usage_model_id
            token_usage = _estimate_token_usage(
                f"{system_instruction}\n\n{clean_content}",
                full_text,
                usage_model_id,
                usage_label
            )

            final_metadata = {"turn_id": turn_id, "token_usage": token_usage}
            if mentions_meta:
                final_metadata["mentions"] = mentions_meta
            if model_label:
                final_metadata["model"] = model_label

            # NEW: Use real accumulated thinking if available, otherwise fallback to static summary
            full_thinking = "".join(full_thinking_parts).strip() if full_thinking_parts else ""
            
            if not full_thinking:
                # Fallback to static summary if no real thinking was captured
                thinking_summary = _build_safe_thinking_summary(
                    dense_research=bool(message_in.dense_research),
                    web_search=bool(web_search),
                    used_context=bool(system_context or mentions_meta or rag_context or graph_context),
                    used_outline=bool(outline_items)
                )
            else:
                thinking_summary = full_thinking

            history_payload = conversation_history_full + [
                {"role": "user", "content": message_in.content},
                {"role": "assistant", "content": full_text},
            ]
            if _maybe_update_conversation_summary(chat, history_payload):
                flag_modified(chat, "context")

            ai_msg = ChatMessage(
                id=str(uuid.uuid4()),
                chat_id=chat_id,
                role="assistant",
                content=full_text,
                thinking=thinking_summary,
                msg_metadata=final_metadata if final_metadata else {},
                created_at=utcnow()
            )
            db.add(ai_msg)
            chat.updated_at = utcnow()
            await db.commit()

            yield sse_event({
                "type": "done",
                "full_text": full_text,
                "model": model_label,
                "message_id": ai_msg.id,
                "turn_id": turn_id,
                "token_usage": token_usage,
                "thinking": thinking_summary,
            })
        except Exception as e:
            logger.error(f"Erro na IA (stream): {e}")
            fallback_text = (
                "Desculpe, estou operando em modo offline no momento. "
                f"Recebi sua mensagem: '{message_in.content}'"
            )
            offline_usage = _estimate_token_usage(message_in.content, fallback_text, DEFAULT_JUDGE_MODEL, "offline")
            ai_msg = ChatMessage(
                id=str(uuid.uuid4()),
                chat_id=chat_id,
                role="assistant",
                content=fallback_text,
                thinking="Erro de conexão com LLM",
                msg_metadata={"model": "offline", "turn_id": turn_id, "token_usage": offline_usage},
                created_at=utcnow()
            )
            history_payload = conversation_history_full + [
                {"role": "user", "content": message_in.content},
                {"role": "assistant", "content": fallback_text},
            ]
            if _maybe_update_conversation_summary(chat, history_payload):
                flag_modified(chat, "context")
            db.add(ai_msg)
            chat.updated_at = utcnow()
            await db.commit()
            for chunk in chunk_text(fallback_text):
                yield sse_event({"type": "token", "delta": chunk, "model": "offline", "turn_id": turn_id})
                await asyncio.sleep(0)
            yield sse_event({
                "type": "done",
                "full_text": fallback_text,
                "model": "offline",
                "message_id": ai_msg.id,
                "turn_id": turn_id,
                "token_usage": offline_usage,
            })

    return StreamingResponse(stream_response(), media_type="text/event-stream")


@router.post("/{chat_id}/outline", response_model=OutlineResponse)
async def generate_chat_outline(
    chat_id: str,
    request: OutlineRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Gerar outline leve para modo chat (single-model).
    """
    result = await db.execute(select(Chat).where(Chat.id == chat_id, Chat.user_id == current_user.id))
    chat = result.scalars().first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat não encontrado")

    prompt = (request.prompt or "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt vazio para outline.")

    model_id = (request.model or chat.context.get("model") or DEFAULT_JUDGE_MODEL).strip()
    try:
        model_id = validate_model_id(model_id, for_juridico=True, field_name="model")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    min_pages, max_pages = normalize_page_range(request.min_pages, request.max_pages)
    document_type = request.document_type or chat.context.get("document_type") or "PETICAO"
    thesis = request.thesis or chat.context.get("thesis") or ""

    outline_state = await outline_node({
        "mode": document_type,
        "input_text": prompt,
        "tese": thesis,
        "strategist_model": model_id,
        "judge_model": model_id,
        "min_pages": min_pages,
        "max_pages": max_pages,
    })
    outline = outline_state.get("outline", []) if isinstance(outline_state, dict) else []
    outline = [str(item).strip() for item in outline if str(item).strip()]

    return OutlineResponse(outline=outline, model=model_id)


@router.post("/{chat_id}/generate", response_model=GenerateDocumentResponse)
async def generate_document(
    chat_id: str,
    request: GenerateDocumentRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Gerar documento completo com múltiplos agentes
    """
    # Verificar chat
    result = await db.execute(select(Chat).where(Chat.id == chat_id, Chat.user_id == current_user.id))
    chat = result.scalars().first()
    
    if not chat:
        raise HTTPException(status_code=404, detail="Chat não encontrado")
        
    # Buscar perfil do usuário para contexto
    if request.use_profile == "full":
        user_result = await db.execute(select(User).where(User.id == current_user.id))
        user = user_result.scalars().first()
        if user:
            # Adicionar dados do perfil ao contexto
            chat.context.update(user.full_signature_data)
            
    # Executar Gerador de Documentos (Motor juridico_gemini)
    try:
        # Converter GenerateDocumentRequest do Chat para DocumentGenerationRequest do DocumentGenerator
        # (Eles são compatíveis nos campos principais)
        from app.schemas.document import DocumentGenerationRequest as DocGenRequest
        from app.services.ai.model_registry import validate_model_id, validate_model_list

        # Validate models early (clear 400 errors)
        try:
            judge_model = validate_model_id(request.model, for_juridico=True, field_name="model")
            gpt_model = validate_model_id(getattr(request, "model_gpt", None) or "gpt-5.2", for_agents=True, field_name="model_gpt")
            claude_model = validate_model_id(getattr(request, "model_claude", None) or "claude-4.5-sonnet", for_agents=True, field_name="model_claude")
            strategist_model = getattr(request, "strategist_model", None)
            if strategist_model:
                strategist_model = validate_model_id(strategist_model, for_agents=True, field_name="strategist_model")
            drafter_models = validate_model_list(getattr(request, "drafter_models", None), for_agents=True, field_name="drafter_models")
            reviewer_models = validate_model_list(getattr(request, "reviewer_models", None), for_agents=True, field_name="reviewer_models")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        rag_config = request.rag_config or {}
        use_templates = request.use_templates or bool(rag_config.get("use_templates"))
        context_use_templates = chat.context.get("use_templates")
        if not use_templates and context_use_templates:
            use_templates = True
        template_filters = request.template_filters or rag_config.get("template_filters") or chat.context.get("template_filters") or {}
        prompt_extra = request.prompt_extra or rag_config.get("prompt_extra")
        formatting_options = request.formatting_options or rag_config.get("formatting_options") or {}
        template_id = request.template_id or rag_config.get("template_id") or chat.context.get("template_id")
        template_document_id = request.template_document_id or rag_config.get("template_document_id") or chat.context.get("template_document_id")
        variables = request.variables or rag_config.get("variables") or {}
        thesis = request.thesis or chat.context.get("thesis") or request.prompt[:100]
        rag_sources = request.rag_sources or rag_config.get("rag_sources") or rag_config.get("sources")
        rag_top_k = request.rag_top_k or rag_config.get("rag_top_k") or rag_config.get("top_k")
        
        doc_request = DocGenRequest(
            prompt=request.prompt,
            document_type=request.document_type,
            effort_level=request.effort_level,
            min_pages=request.min_pages,
            max_pages=request.max_pages,
            attachment_mode=request.attachment_mode,
            use_multi_agent=request.use_multi_agent,
            model_selection=judge_model,
            model_gpt=gpt_model,
            model_claude=claude_model,
            strategist_model=strategist_model,
            drafter_models=drafter_models,
            reviewer_models=reviewer_models,
            chat_personality=request.chat_personality,
            reasoning_level=request.thinking_level,
            web_search=request.web_search,
            search_mode=request.search_mode,
            multi_query=request.multi_query,
            breadth_first=request.breadth_first,
            research_policy=request.research_policy,
            dense_research=request.dense_research,
            thesis=thesis,
            citation_style=getattr(request, "citation_style", "forense") or "forense",
            formatting_options=formatting_options,
            use_templates=use_templates,
            template_filters=template_filters,
            prompt_extra=prompt_extra,
            template_id=template_id,
            template_document_id=template_document_id,
            variables=variables,
            rag_sources=rag_sources,
            rag_top_k=rag_top_k,
            context_documents=request.context_documents,
            audit=True, # Default para jurídico_gemini
            use_langgraph=request.use_langgraph,
            adaptive_routing=request.adaptive_routing,
            crag_gate=request.crag_gate,
            crag_min_best_score=request.crag_min_best_score,
            crag_min_avg_score=request.crag_min_avg_score,
            hyde_enabled=request.hyde_enabled,
            graph_rag_enabled=request.graph_rag_enabled,
            graph_hops=request.graph_hops,
            destino=request.destino,
            risco=request.risco,
            hil_outline_enabled=request.hil_outline_enabled,
            hil_target_sections=request.hil_target_sections
        )

        result = await get_document_generator().generate_document(
            request=doc_request,
            user=current_user,
            db=db,
            context_data={**chat.context, **request.context}
        )
        
        return GenerateDocumentResponse(
            content=result.content,
            metrics=result.cost_info
        )
        
    except Exception as e:
        # Simulação de Fallback Robusta
        print(f"Erro no DocumentGenerator (juridico_gemini): {e}. Usando Fallback.")
        
        final_content = f"""# DEBUG ERROR INFO
{str(e)}

# PETIÇÃO INICIAL (GERADO EM MODO OFFLINE)

EXCELENTÍSSIMO SENHOR DOUTOR JUIZ DE DIREITO DA ___ VARA CÍVEL DA COMARCA DE SÃO PAULO/SP

**{current_user.name}**, brasileiro, solteiro, portador do CPF nº ..., residente e domiciliado em ..., vem, respeitosamente, perante Vossa Excelência, propor a presente

**AÇÃO INDENIZATÓRIA**

em face de **EMPRESA RÉ**, pessoa jurídica de direito privado, pelos fatos e fundamentos a seguir expostos:

**I - DOS FATOS**

{request.prompt}

**II - DO DIREITO**

Conforme dispõe o Código Civil... (Fundamentação gerada offline)

**III - DOS PEDIDOS**

Diante do exposto, requer a procedência total da ação...

Nestes termos,
Pede deferimento.

São Paulo, {datetime.now().strftime('%d/%m/%Y')}

ADVOGADO
OAB/UF ...
"""
        reviews = [
            {
                "agent_name": "Gemini (Revisor Legal)",
                "score": 8.5,
                "approved": True,
                "comments": ["Fundamentação adequada (Simulada)."]
            },
            {
                "agent_name": "GPT (Revisor Textual)",
                "score": 9.0,
                "approved": True,
                "comments": ["Texto claro e objetivo (Simulado)."]
            }
        ]
        consensus = True
        conflicts = []
        total_tokens = 1500
        total_cost = 0.05
        processing_time = 2.5
        metadata = {"mode": "fallback"}

    # Persistência do fallback não pode derrubar a rota (senão o front só vê "Erro ao enviar mensagem").
    try:
        # Salvar como mensagem no chat
        ai_msg = ChatMessage(
            id=str(uuid.uuid4()),
            chat_id=chat_id,
            role="assistant",
            content=final_content,
            thinking=f"Gerado por Multi-Agent Orchestrator (Esforço {request.effort_level})",
            msg_metadata={
                "reviews": reviews,
                "cost": total_cost,
                "tokens": total_tokens,
                "metadata": metadata,
                "fallback_error": str(e),
            },
            created_at=utcnow()
        )
        db.add(ai_msg)

        # Salvar documento gerado no banco (best-effort)
        generated_document = Document(
            id=str(uuid.uuid4()),
            user_id=current_user.id,
            name=f"Minuta - {chat.title or 'Documento'}",
            original_name=f"{chat.title or 'documento'}.md",
            type=DocumentType.TXT,
            status=DocumentStatus.READY,
            size=len(final_content.encode("utf-8")),
            url="",
            content=final_content,
            extracted_text=final_content,
            doc_metadata={
                "source_chat_id": chat_id,
                "generation": metadata or {},
            },
            tags=[],
            folder_id=None,
            is_shared=False,
            is_archived=False,
        )
        db.add(generated_document)

        await db.commit()
    except Exception as persist_err:
        # Não falhar a resposta: devolve conteúdo mesmo que não tenha conseguido salvar
        print(f"Falha ao persistir fallback do /generate: {persist_err}")
        await db.rollback()

    return GenerateDocumentResponse(
        content=final_content,
        metrics={
            "mode": "fallback",
            "reviews": reviews,
            "consensus": consensus,
            "conflicts": conflicts,
            "total_tokens": total_tokens,
            "total_cost": total_cost,
            "processing_time": processing_time,
            "metadata": metadata,
            "fallback_error": str(e),
        }
    )


@router.post("/{chat_id}/edit")
async def edit_document(
    chat_id: str,
    message: str = Body(..., description="Edit command"),
    document: str = Body(..., description="Full document"),
    selection: str = Body(None, description="Selected text"),
    selection_start: int = Body(None),
    selection_end: int = Body(None),
    selection_context_before: str = Body(None),
    selection_context_after: str = Body(None),
    models: List[str] = Body(None),
    use_debate: bool = Body(False, description="Enable 4-round deep debate"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    v5.4: Edit document via agent committee or single model.
    """
    # Verify chat
    result = await db.execute(select(Chat).where(Chat.id == chat_id, Chat.user_id == current_user.id))
    chat = result.scalars().first()
    
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
        
    # Save user message
    user_msg = ChatMessage(
        id=str(uuid.uuid4()),
        chat_id=chat_id,
        role="user",
        content=f"[EDIÇÃO] {message}",
        created_at=utcnow()
    )
    db.add(user_msg)
    await db.commit()
    
    async def event_generator():
        final_text = None
        try:
            async for event in chat_service.dispatch_document_edit(
                chat_id,
                message,
                document,
                selection,
                models,
                selection_start,
                selection_end,
                selection_context_before,
                selection_context_after,
                log_thread=False,
                use_debate=use_debate
            ):
                if event.get("type") == "edit_complete":
                    final_text = event.get("edited")
                yield sse_event(event)
                
            if final_text:
                # Persist result
                ai_msg = ChatMessage(
                    id=str(uuid.uuid4()),
                    chat_id=chat_id,
                    role="assistant",
                    content="Edição concluída.",
                    msg_metadata={"edited_text": final_text, "type": "edit_result"},
                    created_at=utcnow()
                )
                db.add(ai_msg)
                await db.commit()
                
        except Exception as e:
            logger.error(f"Edit stream error: {e}")
            yield sse_event({"type": "error", "error": str(e)})
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive"
        }
    )
