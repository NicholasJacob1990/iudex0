"""
Endpoints de Chat e Geração de Documentos
"""

import asyncio
import json
import os
import re
import time
import uuid
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status, Body
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import desc
from sqlalchemy.orm.attributes import flag_modified

from app.core.database import get_db
from app.core.config import settings
from app.core.security import get_current_user
from app.core.time_utils import utcnow
from app.models.chat import Chat, ChatMessage, ChatMode
from app.models.user import User, UserRole
from app.models.library import LibraryItem, LibraryItemType
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
from app.services.ai.prompt_flags import (
    parse_prompt_flags,
    apply_verbosity_instruction,
    clamp_thinking_budget,
)
from app.services.model_registry import get_model_config as get_budget_model_config
from app.services.ai.langgraph_legal_workflow import outline_node, build_length_guidance
from app.schemas.smart_template import UserTemplateV1
from app.services.rag_trace import trace_event
from app.services.ai.nodes.catalogo_documentos import (
    TemplateSpec,
    get_template,
    merge_user_template,
    build_default_outline,
    get_numbering_instruction,
)
from app.services.chat_service import ChatService
from app.services.web_search_service import web_search_service, build_web_context, is_breadth_first
from app.services.rag_context import build_rag_context
from app.services.api_call_tracker import (
    usage_context,
    record_api_call,
    billing_context,
    points_counter_context,
    get_points_total,
)
from app.services.ai.internal_rag_agent import (
    build_internal_rag_system_instruction,
    build_internal_rag_prompt,
)
from app.services.billing_service import (
    resolve_plan_key,
    resolve_deep_research_billing,
    get_plan_cap,
    get_deep_research_monthly_status,
    get_points_summary,
    resolve_chat_max_points_per_message,
    get_usd_per_point,
)
from app.services.billing_quote_service import (
    estimate_chat_turn_points,
    estimate_langgraph_job_points,
    FixedPointsEstimator,
)
from app.services.poe_like_billing import quote_message as poe_quote_message
from app.services.context_strategy import decide_context_mode_from_paths, supports_upload_cache
from app.utils.validators import InputValidator
from app.services.rag_policy import resolve_rag_scope
from app.services.document_processor import (
    extract_text_from_pdf,
    extract_text_from_pdf_with_ocr,
    extract_text_from_docx,
    extract_text_from_odt,
    extract_text_from_image,
    extract_text_from_zip,
)
from app.services.ai.citations import extract_perplexity
from app.services.ai.citations.base import (
    render_perplexity,
    stable_numbering,
    sources_to_citations,
    append_references_section,
    append_autos_references_section,
)
from app.services.ai.perplexity_config import (
    build_perplexity_chat_kwargs,
    normalize_perplexity_search_mode,
    normalize_perplexity_recency,
    normalize_perplexity_date,
    parse_csv_list,
    normalize_float,
)
from app.services.ai.research_policy import decide_research_flags
from app.services.ai.deep_research_service import deep_research_service
from app.services.web_rag_service import web_rag_service
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

mention_service = MentionService()
token_service = TokenBudgetService()
command_service = CommandService()


def sse_event(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


def sse_keepalive() -> str:
    """SSE comment for keepalive (prevents proxy buffering/timeout)."""
    return ":\n\n"


def sse_activity_event(
    turn_id: str,
    op: str,  # "add", "update", "done", "error"
    step_id: str,
    title: str = "",
    status: str = "running",
    detail: str = "",
    tags: list = None,
) -> str:
    """
    Helper to emit activity step events for the Activity Panel.
    
    The frontend expects:
    - op: "add" | "update" | "done" | "error"
    - id: step identifier
    - title: display title
    - status: "running" | "done" | "error"
    - detail: optional detail text
    - tags: optional list of domain/chip tags
    """
    payload = {
        "type": "activity",
        "turn_id": turn_id,
        "op": op,
        "step": {
            "id": step_id,
            "title": title,
            "status": status,
            "detail": detail,
            "tags": tags or [],
            "t": int(time.time() * 1000),
        }
    }
    return sse_event(payload)

def _cursor_debug_log(payload: dict) -> None:
    """
    Debug-mode NDJSON logger (Cursor).
    IMPORTANT: never log secrets/PII. Keep payloads minimal.
    """
    try:
        with open("/Users/nicholasjacob/Documents/Aplicativos/Iudex/.cursor/debug.log", "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        return

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


def _is_thinking_enabled(reasoning_level: Optional[str], thinking_budget: Optional[int]) -> bool:
    level = (reasoning_level or "").strip().lower()
    if level in ("none", "off", "disabled"):
        return False
    if thinking_budget is not None and thinking_budget <= 0:
        return False
    return True


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


def _collect_attachment_ids(attachments: Optional[List[Any]]) -> List[str]:
    ids: List[str] = []
    for item in attachments or []:
        if isinstance(item, str):
            ids.append(item)
            continue
        if isinstance(item, dict):
            raw = item.get("id") or item.get("document_id") or item.get("doc_id")
            if raw:
                ids.append(str(raw))
    return list(dict.fromkeys(ids))


async def _load_attachment_docs(
    db: AsyncSession,
    user_id: str,
    attachments: Optional[List[Any]],
) -> List[Document]:
    ids = _collect_attachment_ids(attachments)
    if not ids:
        return []
    result = await db.execute(
        select(Document).where(
            Document.user_id == user_id,
            Document.id.in_(ids),
        )
    )
    docs = result.scalars().all()
    by_id = {doc.id: doc for doc in docs}
    return [by_id[doc_id] for doc_id in ids if doc_id in by_id]


def _pick_smallest_context_model(model_ids: List[str]) -> str:
    selected = model_ids[0]
    min_ctx = get_budget_model_config(selected).get("context_window", 0)
    for model_id in model_ids[1:]:
        ctx = get_budget_model_config(model_id).get("context_window", 0)
        if min_ctx <= 0 or (ctx > 0 and ctx < min_ctx):
            selected = model_id
            min_ctx = ctx
    return selected


def _resolve_budget_model_id(
    message_text: str,
    requested_model: Optional[str],
    fallback_model: str,
) -> str:
    if requested_model:
        return requested_model
    lowered = (message_text or "").lower()
    targets: List[str] = []
    if "@todos" in lowered or "@all" in lowered:
        targets = ["gpt-5.2", "claude-4.5-sonnet", "gemini-3-flash"]
    else:
        if "@gpt" in lowered:
            targets.append("gpt-5.2")
        if "@claude" in lowered:
            targets.append("claude-4.5-sonnet")
        if "@gemini" in lowered:
            targets.append("gemini-3-flash")
    if targets:
        return _pick_smallest_context_model(targets)
    return fallback_model


def _should_use_precise_budget(model_id: str) -> bool:
    provider = (get_budget_model_config(model_id) or {}).get("provider") or ""
    return provider in ("vertex", "google")


def _join_context_parts(*parts: Optional[str]) -> str:
    filtered = [part for part in parts if part]
    return "\n\n".join(filtered).strip()


def _estimate_attachment_stats(docs: List[Document]) -> tuple[int, int]:
    total_tokens = 0
    total_chars = 0
    for doc in docs:
        text = (getattr(doc, "extracted_text", "") or "").strip()
        if not text:
            continue
        total_chars += len(text)
        total_tokens += token_service.estimate_tokens(text)
    return total_tokens, total_chars


def _estimate_available_tokens(model_id: str, prompt: str, base_context: str) -> int:
    config = get_budget_model_config(model_id) or {}
    limit = config.get("context_window", 0)
    max_output = config.get("max_output", 4096)
    if limit <= 0:
        return 0
    buffer = 1000
    base_tokens = token_service.estimate_tokens(base_context)
    prompt_tokens = token_service.estimate_tokens(prompt)
    return limit - base_tokens - prompt_tokens - max_output - buffer


def _resolve_provider_for_model(model_id: Optional[str]) -> str:
    if not model_id:
        return ""
    cfg = get_model_config(model_id)
    return cfg.provider if cfg else ""


def _find_oversized_upload_cache_files(
    context_files: List[str],
    attachment_docs: List[Document],
    provider: Optional[str],
) -> tuple[List[str], int]:
    limit_mb = InputValidator.get_provider_upload_limit_mb(provider)
    limit_bytes = limit_mb * 1024 * 1024
    oversized: List[str] = []
    for doc in attachment_docs:
        size = int(getattr(doc, "size", 0) or 0)
        if size > limit_bytes:
            oversized.append(doc.name or doc.id)
    for raw_path in context_files:
        path = str(raw_path or "").strip()
        if not path or not os.path.isfile(path):
            continue
        try:
            size = os.path.getsize(path)
        except OSError:
            continue
        if size > limit_bytes:
            oversized.append(path)
    return oversized, limit_mb


_CONTEXT_FILE_EXTS = {
    ".pdf",
    ".txt",
    ".md",
    ".docx",
    ".odt",
    ".rtf",
    ".html",
    ".htm",
    ".zip",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".bmp",
    ".tiff",
    ".tif",
}


def _expand_context_file_paths(paths: List[str], max_files: int) -> List[str]:
    expanded: List[str] = []
    seen: set[str] = set()
    for raw_path in paths:
        if len(expanded) >= max_files:
            break
        path = Path(str(raw_path or "").strip())
        if not path.exists():
            continue
        if path.is_dir():
            for candidate in path.rglob("*"):
                if len(expanded) >= max_files:
                    break
                if not candidate.is_file():
                    continue
                if candidate.suffix.lower() not in _CONTEXT_FILE_EXTS:
                    continue
                candidate_str = str(candidate)
                if candidate_str in seen:
                    continue
                seen.add(candidate_str)
                expanded.append(candidate_str)
        else:
            if path.suffix.lower() not in _CONTEXT_FILE_EXTS:
                continue
            path_str = str(path)
            if path_str in seen:
                continue
            seen.add(path_str)
            expanded.append(path_str)
    return expanded


async def _extract_text_for_context_file(path: str) -> str:
    ext = Path(path).suffix.lower()
    if ext == ".pdf":
        text = await extract_text_from_pdf(path)
        if text and len(text.strip()) >= 50:
            return text
        if settings.ENABLE_OCR:
            return await extract_text_from_pdf_with_ocr(path)
        return text
    if ext == ".docx":
        return await extract_text_from_docx(path)
    if ext == ".odt":
        return await extract_text_from_odt(path)
    if ext in {".txt", ".md", ".rtf"}:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
        except OSError:
            return ""
    if ext in {".html", ".htm"}:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                return InputValidator.sanitize_html(f.read())
        except OSError:
            return ""
    if ext == ".zip":
        zip_result = await extract_text_from_zip(path)
        return (zip_result or {}).get("extracted_text", "")
    if ext in {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".tif"}:
        if settings.ENABLE_OCR:
            return await extract_text_from_image(path)
        return ""
    return ""


async def _build_local_rag_context_from_paths(
    context_files: List[str],
    query: str,
    tenant_id: str = "default",
    top_k: Optional[int] = None,
    max_files: Optional[int] = None,
    *,
    queries: Optional[List[str]] = None,
    query_override: Optional[str] = None,
    multi_query: bool = False,
    crag_gate: bool = False,
    graph_rag_enabled: bool = False,
    argument_graph_enabled: bool = False,
    graph_hops: int = 2,
) -> str:
    try:
        from rag_local import LocalProcessIndex
    except Exception as e:
        logger.warning(f"RAG Local indisponível: {e}")
        return ""

    if top_k is None:
        top_k = settings.ATTACHMENT_RAG_LOCAL_TOP_K
    if max_files is None:
        max_files = settings.ATTACHMENT_RAG_LOCAL_MAX_FILES
    max_files = max(1, int(max_files))

    expanded_paths = _expand_context_file_paths(context_files, max_files)
    if not expanded_paths:
        return ""

    try:
        index = LocalProcessIndex(
            processo_id=f"context-{uuid.uuid4()}",
            sistema="UPLOAD",
            tenant_id=tenant_id,
        )
        index.enable_graph(
            graph_rag_enabled=bool(graph_rag_enabled),
            argument_graph_enabled=bool(argument_graph_enabled),
        )
        remaining = max_files
        for path in expanded_paths:
            if remaining <= 0:
                break
            ext = Path(path).suffix.lower()
            if ext in {".pdf", ".txt", ".md"}:
                chunks = index.index_documento(path)
                remaining -= 1
                if chunks <= 0 and ext == ".pdf" and settings.ENABLE_OCR:
                    text = await extract_text_from_pdf_with_ocr(path)
                    if text and text.strip():
                        index.index_text(
                            text,
                            filename=Path(path).name,
                            source_path=path,
                        )
                continue
            text = await _extract_text_for_context_file(path)
            if text and text.strip():
                index.index_text(
                    text,
                    filename=Path(path).name,
                    source_path=path,
                )
                remaining -= 1
        search_query = (query_override or query or "").strip()
        unlock_all_raw = os.getenv("RAG_UNLOCK_ALL")
        if unlock_all_raw is None:
            unlock_all = not settings.is_production
        else:
            unlock_all = str(unlock_all_raw).lower() in ("1", "true", "yes", "on")
        results, graph_ctx = index.search_advanced(
            search_query,
            top_k=top_k,
            multi_query=bool(multi_query),
            queries=queries,
            compression_enabled=bool(crag_gate) or unlock_all,
            neighbor_expand=bool(crag_gate) or unlock_all,
            corrective_rag=bool(crag_gate) or unlock_all,
            rerank=True if unlock_all else None,
            graph_rag_enabled=bool(graph_rag_enabled),
            graph_hops=int(graph_hops or 2),
            argument_graph_enabled=bool(argument_graph_enabled),
        )
    except Exception as e:
        logger.warning(f"Falha ao indexar context_files no RAG Local: {e}")
        return ""

    if not results:
        return ""

    lines = ["### 📁 FATOS DO PROCESSO (CONTEXT_FILES)"]
    for r in results:
        snippet = (r.get("text") or "")[:300].strip()
        citation = r.get("citacao") or "Documento"
        if snippet:
            lines.append(f"- {citation}: \"{snippet}...\"")
    if graph_ctx:
        lines.append("")
        lines.append("### 🔗 CONTEXTO RELACIONAL (GRAPH)")
        lines.append((graph_ctx or "").strip()[:2000])
    return "\n".join(lines)


def _parse_template_frontmatter(text: str) -> tuple[Optional[Dict[str, Any]], str]:
    """Extrai frontmatter JSON e retorna (meta, corpo)."""
    if not text:
        return None, ""

    match = re.match(
        r"\s*<!--\s*IUDX_TEMPLATE_V1(?P<json>.*?)-->\s*(?P<body>.*)",
        text,
        flags=re.S
    )
    if not match:
        return None, text

    raw_json = (match.group("json") or "").strip()
    body = match.group("body") or ""

    if not raw_json:
        return None, body

    if raw_json.startswith("{") and raw_json.endswith("}"):
        try:
            meta = json.loads(raw_json)
            if isinstance(meta, dict):
                return meta, body
        except Exception as e:
            logger.warning(f"Frontmatter invalido (ignorado): {e}")
            return None, text

    return None, text


def _strip_template_placeholders(text: str) -> str:
    if not text:
        return text
    stripped = re.sub(r"{{\s*BLOCK:[^}]+}}", "", text)
    stripped = stripped.replace("{{CONTENT}}", "")
    stripped = stripped.replace("{{minuta}}", "")
    stripped = stripped.replace("(minuta)", "")
    return stripped


def _build_template_instruction(meta: Optional[Dict[str, Any]], body: str) -> str:
    if not meta:
        return ""

    parts: List[str] = []
    system_instructions = meta.get("system_instructions") or meta.get("instructions") or ""
    output_format = meta.get("output_format") or meta.get("structure") or ""
    user_template_v1 = meta.get("user_template_v1") or meta.get("user_template") or None

    if system_instructions:
        parts.append(str(system_instructions).strip())
    if output_format:
        parts.append("FORMATO DE SAIDA:\n" + str(output_format).strip())

    if user_template_v1:
        try:
            parsed = UserTemplateV1.model_validate(user_template_v1)
            base_spec = get_template(parsed.doc_kind, parsed.doc_subtype)
            user_dict = parsed.model_dump()
            if base_spec:
                merged = merge_user_template(base_spec, user_dict)
            else:
                merged = TemplateSpec(
                    name=parsed.name,
                    doc_kind=parsed.doc_kind,
                    doc_subtype=parsed.doc_subtype,
                    numbering=parsed.format.numbering,
                    style={
                        "tone": parsed.format.tone,
                        "verbosity": parsed.format.verbosity,
                        "voice": parsed.format.voice,
                    },
                    sections=[s.title for s in parsed.sections],
                    required_fields=[f.name for f in parsed.required_fields],
                    checklist_base=[],
                    forbidden_sections=[],
                )
            outline = build_default_outline(merged)
            if outline:
                parts.append("ESTRUTURA BASE:\n" + "\n".join(f"- {s}" for s in outline))
            if merged.required_fields:
                parts.append("CAMPOS OBRIGATORIOS:\n" + "\n".join(f"- {f}" for f in merged.required_fields))
            if merged.style:
                parts.append(
                    "REGRAS DE ESTILO:\n"
                    + f"- tom: {merged.style.get('tone')}\n"
                    + f"- voz: {merged.style.get('voice')}\n"
                    + f"- extensao: {merged.style.get('verbosity')}\n"
                    + f"- numeracao: {get_numbering_instruction(merged.numbering)}"
                )
        except Exception as e:
            logger.warning(f"Falha ao interpretar user_template_v1: {e}")

    clean_body = _strip_template_placeholders(body or "")
    if clean_body:
        snippet = clean_body.strip()
        if len(snippet) > 2000:
            snippet = snippet[:2000].rstrip()
        parts.append("TEXTO BASE (EXCERTO):\n" + snippet)

    return "\n\n".join([p for p in parts if p]).strip()


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


async def _store_rag_memory(chat_id: str, history_payload: List[dict]) -> None:
    if not chat_id:
        return
    try:
        from app.services.ai.rag_memory_store import RAGMemoryStore
        await RAGMemoryStore().set_history(str(chat_id), history_payload)
    except Exception as exc:
        logger.warning(f"RAG memory persist failed: {exc}")


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


DEFAULT_OUTLINE_SECTIONS = 8


def _sections_for_pages(pages: int) -> int:
    pages = int(pages or 0)
    if pages <= 0:
        return 0
    sections = round(pages * 0.5) + 2
    return max(3, min(sections, 14))


def _estimate_outline_sections(
    outline: Optional[List[str]],
    min_pages: Optional[int],
    max_pages: Optional[int],
) -> int:
    if isinstance(outline, list):
        cleaned = [str(item).strip() for item in outline if str(item).strip()]
        if cleaned:
            return len(cleaned)

    min_value, max_value = normalize_page_range(min_pages, max_pages)
    if min_value or max_value:
        min_sections = _sections_for_pages(min_value) if min_value else 0
        max_sections = _sections_for_pages(max_value) if max_value else 0
        if min_sections and max_sections:
            return max(3, int(round((min_sections + max_sections) / 2)))
        return max(min_sections, max_sections, DEFAULT_OUTLINE_SECTIONS)

    return DEFAULT_OUTLINE_SECTIONS


def _estimate_outline_pipeline_calls(
    outline_sections: int,
    has_outline: bool,
) -> int:
    sections = int(outline_sections or 0)
    if sections <= 0:
        sections = DEFAULT_OUTLINE_SECTIONS
    calls = sections if has_outline else sections + 1
    return max(1, calls)


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
    _cursor_debug_log({
        "sessionId": "debug-session",
        "runId": "pre",
        "hypothesisId": "H2",
        "location": "apps/api/app/api/endpoints/chats.py:list_chats",
        "message": "GET /api/chats list_chats",
        "data": {"skip": int(skip), "limit": int(limit), "count": len(chats)},
        "timestamp": int(datetime.utcnow().timestamp() * 1000),
    })
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
    _cursor_debug_log({
        "sessionId": "debug-session",
        "runId": "pre2",
        "hypothesisId": "H1",
        "location": "apps/api/app/api/endpoints/chats.py:create_chat",
        "message": "POST /api/chats create_chat",
        "data": {"chatIdSuffix": str(chat.id or "")[-6:], "mode": str(getattr(chat, "mode", "") or "")},
        "timestamp": int(datetime.utcnow().timestamp() * 1000),
    })
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
    _cursor_debug_log({
        "sessionId": "debug-session",
        "runId": "pre2",
        "hypothesisId": "H3",
        "location": "apps/api/app/api/endpoints/chats.py:duplicate_chat",
        "message": "POST /api/chats/{chat_id}/duplicate duplicate_chat",
        "data": {"sourceChatIdSuffix": str(chat_id or "")[-6:], "newChatIdSuffix": str(new_chat.id or "")[-6:], "copiedMessages": len(messages)},
        "timestamp": int(datetime.utcnow().timestamp() * 1000),
    })
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

    logger.info(
        "💬 Chat request (simple) chat_id=%s graph_rag=%s argument_graph=%s",
        chat_id,
        message_in.graph_rag_enabled,
        message_in.argument_graph_enabled,
    )

    parsed_flags = parse_prompt_flags(message_in.content)
    if parsed_flags.clean_text != message_in.content:
        message_in.content = parsed_flags.clean_text
    if parsed_flags.web_search is not None:
        message_in.web_search = parsed_flags.web_search
    if parsed_flags.reasoning_level:
        message_in.reasoning_level = parsed_flags.reasoning_level
    verbosity_override = parsed_flags.verbosity
    thinking_budget_override = parsed_flags.thinking_budget
    if getattr(message_in, "verbosity", None):
        verbosity_override = str(message_in.verbosity).strip().lower()
    if getattr(message_in, "thinking_budget", None) is not None:
        thinking_budget_override = message_in.thinking_budget
    if getattr(message_in, "verbosity", None):
        verbosity_override = str(message_in.verbosity).strip().lower()
    if getattr(message_in, "thinking_budget", None) is not None:
        thinking_budget_override = message_in.thinking_budget

    history_messages = await _get_recent_messages(db, chat_id, HISTORY_MAX_FETCH)
    conversation_history_full = _serialize_history(history_messages)
    history_model_ids = _infer_history_model_ids(message_in.content, message_in.model, chat.context)
    base_instruction = apply_verbosity_instruction(
        build_system_instruction(message_in.chat_personality),
        verbosity_override,
    )
    conversation_history = _trim_history_for_models(
        conversation_history_full,
        history_model_ids,
        message_in.content,
        base_instruction,
        chat.context.get("conversation_summary")
    )
    turn_id = str(uuid.uuid4())
    request_id = f"{chat_id}:{turn_id}"
    request_id = f"{chat_id}:{turn_id}"
    plan_key = resolve_plan_key(getattr(current_user, "plan", None))
    max_web_search_requests = get_plan_cap(plan_key, "max_web_search_requests", default=5)
    web_search_flag = bool(message_in.web_search)
    if max_web_search_requests is not None and max_web_search_requests <= 0:
        web_search_flag = False

    deep_effort, deep_multiplier = resolve_deep_research_billing(plan_key, getattr(message_in, "deep_research_effort", None))
    if bool(getattr(message_in, "dense_research", False)) and deep_effort:
        status = await get_deep_research_monthly_status(
            db,
            user_id=str(current_user.id),
            plan_key=plan_key,
        )
        if not status.get("allowed", True):
            deep_effort = None
            deep_multiplier = 1.0

    # --- Poe-like billing: quote + gates (wallet + per-message budget) ---
    requested_model = (message_in.model or chat.context.get("model") or DEFAULT_JUDGE_MODEL).strip()
    try:
        requested_model = validate_model_id(requested_model, for_juridico=True, field_name="model")
    except ValueError:
        requested_model = DEFAULT_JUDGE_MODEL

    history_text = "\n".join(
        str(item.get("content") or "")
        for item in (conversation_history or [])
        if isinstance(item, dict)
    )
    context_tokens_est = token_service.estimate_tokens(
        "\n\n".join([base_instruction or "", history_text, str(message_in.content or "")]).strip()
    )

    points_base, billing_breakdown = estimate_chat_turn_points(
        model_id=requested_model,
        context_tokens=context_tokens_est,
        web_search=bool(web_search_flag),
        max_web_search_requests=max_web_search_requests,
        multi_query=bool(getattr(message_in, "multi_query", True)),
        dense_research=bool(getattr(message_in, "dense_research", False)) and bool(deep_effort),
        deep_research_effort=deep_effort,
        deep_research_points_multiplier=float(deep_multiplier),
        perplexity_search_type=getattr(message_in, "perplexity_search_type", None),
        perplexity_search_context_size=getattr(message_in, "perplexity_search_context_size", None),
        perplexity_disable_search=bool(getattr(message_in, "perplexity_disable_search", False)),
    )
    if bool(getattr(message_in, "outline_pipeline", False)):
        has_outline = isinstance(message_in.outline, list) and any(
            str(item).strip() for item in message_in.outline
        )
        sections_est = _estimate_outline_sections(
            message_in.outline,
            getattr(message_in, "min_pages", None),
            getattr(message_in, "max_pages", None),
        )
        call_count = _estimate_outline_pipeline_calls(sections_est, has_outline)
        base_points = int(points_base)
        points_base = int(base_points * call_count)
        if isinstance(billing_breakdown, dict):
            billing_breakdown["outline_pipeline_calls"] = int(call_count)
            billing_breakdown["outline_pipeline_sections_est"] = int(sections_est)
            billing_breakdown["outline_pipeline_has_outline"] = bool(has_outline)
            billing_breakdown["points_total_scaled"] = int(points_base)
            extra_points = max(0, int(points_base) - int(base_points))
            components = billing_breakdown.get("components")
            if isinstance(components, list):
                components.append({
                    "kind": "outline_pipeline",
                    "calls": int(call_count),
                    "points": int(extra_points),
                })
    points_summary = await get_points_summary(
        db,
        user_id=str(current_user.id),
        plan_key=plan_key,
    )
    points_available = points_summary.get("available_points")
    wallet_points_balance = int(points_available) if isinstance(points_available, int) else 10**12

    budget_override = getattr(message_in, "budget_override_points", None)
    try:
        budget_override = int(budget_override) if budget_override is not None else None
    except (TypeError, ValueError):
        budget_override = None
    message_budget = budget_override or resolve_chat_max_points_per_message(chat.context)

    usd_per_point = get_usd_per_point()
    quote = poe_quote_message(
        estimator=FixedPointsEstimator(usd_per_point=usd_per_point, breakdown=billing_breakdown),
        req={"points_estimate": int(points_base)},
        wallet_points_balance=int(wallet_points_balance),
        chat_max_points_per_message=int(message_budget),
        usd_per_point=usd_per_point,
    )
    if not quote.ok:
        status_code = 400
        if quote.error == "insufficient_balance":
            status_code = 402
        elif quote.error == "message_budget_exceeded":
            status_code = 409
        raise HTTPException(status_code=status_code, detail=asdict(quote))
    # Salvar mensagem do usuário
    user_msg = ChatMessage(
        id=str(uuid.uuid4()),
        chat_id=chat_id,
        role="user",
        content=message_in.content,
        attachments=message_in.attachments,
        msg_metadata={
            "turn_id": turn_id,
            "request_id": request_id,
            "billing_quote": {
                "estimated_points": int(quote.estimated_points),
                "estimated_usd": float(quote.estimated_usd),
            },
        },
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
            msg_metadata={"turn_id": turn_id, "request_id": request_id, "token_usage": token_usage},
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
        await _store_rag_memory(chat_id, history_payload)
        
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
    current_context["attachment_mode"] = message_in.attachment_mode
    raw_temperature = getattr(message_in, "temperature", None)
    if raw_temperature is None:
        raw_temperature = chat.context.get("temperature")
    try:
        temperature = float(raw_temperature) if raw_temperature is not None else (
            0.6 if message_in.chat_personality == "geral" else 0.3
        )
    except (TypeError, ValueError):
        temperature = 0.6 if message_in.chat_personality == "geral" else 0.3
    temperature = max(0.0, min(1.0, temperature))
    current_context["temperature"] = temperature

    attachment_mode = (message_in.attachment_mode or "auto").lower()
    if attachment_mode not in ("auto", "rag_local", "prompt_injection"):
        attachment_mode = "auto"

    history_block = _build_history_block(chat.context.get("conversation_summary"), conversation_history)
    fallback_model = "claude-4.5-sonnet" if message_in.chat_personality == "juridico" else "gpt-5.2"
    requested_model = (message_in.model or chat.context.get("model") or "").strip() or None
    budget_model_id = _resolve_budget_model_id(clean_content, requested_model, fallback_model)

    attachment_docs = await _load_attachment_docs(db, current_user.id, message_in.attachments)
    attachment_injection_context = ""
    if attachment_docs:
        if attachment_mode == "prompt_injection":
            attachment_injection_context = get_document_generator()._build_attachment_prompt_context(attachment_docs)
        elif attachment_mode == "auto":
            base_context = _join_context_parts(base_instruction, history_block, system_context)
            attachment_tokens, attachment_chars = _estimate_attachment_stats(attachment_docs)
            if attachment_tokens > 0:
                available_tokens = _estimate_available_tokens(budget_model_id, clean_content, base_context)
                available_chars = max(0, int(available_tokens * 3.5))
                if available_tokens > 0 and attachment_chars > 0 and attachment_chars <= available_chars:
                    max_chars = min(attachment_chars, available_chars)
                    attachment_injection_context = get_document_generator()._build_attachment_prompt_context(
                        attachment_docs,
                        max_chars=max_chars,
                        per_doc_chars=max_chars,
                    )

    if attachment_mode == "auto":
        if not attachment_injection_context:
            attachment_mode = "rag_local"
        else:
            budget_context = _join_context_parts(
                base_instruction,
                history_block,
                system_context,
                attachment_injection_context,
            )
            if _should_use_precise_budget(budget_model_id):
                budget = await token_service.check_budget_precise(
                    clean_content,
                    {"system": budget_context},
                    budget_model_id,
                )
            else:
                budget = token_service.check_budget(
                    clean_content,
                    {"system": budget_context},
                    budget_model_id,
                )
            if budget["status"] == "error":
                attachment_mode = "rag_local"
                attachment_injection_context = ""
            else:
                attachment_mode = "prompt_injection"
    if attachment_mode == "prompt_injection" and not attachment_injection_context:
        attachment_mode = "rag_local"

    current_context["attachment_mode"] = attachment_mode
    if attachment_mode == "prompt_injection" and attachment_injection_context:
        current_context["extra_agent_instructions"] = _join_context_parts(
            system_context,
            attachment_injection_context,
        )
    elif attachment_mode == "rag_local" and attachment_docs:
        local_rag_context = get_document_generator()._build_local_rag_context(
            attachment_docs,
            clean_content,
            tenant_id=current_user.id,
        )
        if local_rag_context:
            current_context["rag_context"] = _join_context_parts(
                current_context.get("rag_context"),
                local_rag_context,
            )
    if context_mode == "rag_local" and context_files:
        context_rag = await _build_local_rag_context_from_paths(
            context_files,
            clean_content,
            tenant_id=current_user.id,
        )
        if context_rag:
            current_context["rag_context"] = _join_context_parts(
                current_context.get("rag_context"),
                context_rag,
            )

    # Persistir sticky docs se houver mudança
    if chat.context.get("sticky_docs") != sticky_docs:
        chat.context["sticky_docs"] = sticky_docs
        # Force update
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(chat, "context")
        await db.commit()
    
    # 3. Pré-checagem de Orçamento de Tokens
    if mentions_meta and _should_use_precise_budget(budget_model_id):
        budget = await token_service.check_budget_precise(clean_content, current_context, budget_model_id)
    else:
        budget = token_service.check_budget(clean_content, current_context, budget_model_id)
    
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
    thinking_enabled_simple = _is_thinking_enabled(
        message_in.reasoning_level,
        message_in.thinking_budget
    )
    rag_mode = getattr(message_in, "rag_mode", None) or chat.context.get("rag_mode") or "manual"
    rag_mode = str(rag_mode).strip().lower()
    if rag_mode not in ("auto", "manual"):
        rag_mode = "manual"

    argument_graph_enabled = message_in.argument_graph_enabled
    if argument_graph_enabled is None:
        argument_graph_enabled = chat.context.get("argument_graph_enabled")
    effective_graph_rag_enabled = bool(message_in.graph_rag_enabled)
    effective_argument_graph_enabled = argument_graph_enabled
    effective_graph_hops = int(getattr(message_in, "graph_hops", 1) or 1)
    if rag_mode == "auto":
        try:
            from app.services.ai.rag_router import decide_rag_route_hybrid
            allow_argument = os.getenv("ARGUMENT_RAG_ENABLED", "true").lower() in ("1", "true", "yes", "on")
            router_roles = [str(getattr(current_user, "role", "") or "")] if getattr(current_user, "role", None) else []
            router_groups = chat.context.get("rag_groups") if isinstance(chat.context, dict) else None
            if isinstance(router_groups, str):
                router_groups = [g.strip() for g in router_groups.split(",") if g.strip()]
            if not isinstance(router_groups, list):
                router_groups = []
            decision = await decide_rag_route_hybrid(
                clean_content,
                rag_mode="auto",
                graph_hops=effective_graph_hops,
                allow_graph=True,
                allow_argument=allow_argument,
                risk_mode="high",
                roles=router_roles,
                groups=router_groups,
            )
            effective_graph_rag_enabled = decision.graph_rag_enabled
            effective_argument_graph_enabled = decision.argument_graph_enabled
            effective_graph_hops = decision.graph_hops
            trace_event(
                "rag_router_decision",
                {
                    "mode": "chat_simple",
                    "rag_mode": rag_mode,
                    "used_llm": bool(getattr(decision, "used_llm", False)),
                    "llm_confidence": getattr(decision, "llm_confidence", None),
                    "llm_provider": getattr(decision, "llm_provider", None),
                    "llm_model": getattr(decision, "llm_model", None),
                    "llm_thinking_level": getattr(decision, "llm_thinking_level", None),
                    "llm_schema_enforced": getattr(decision, "llm_schema_enforced", None),
                    "ambiguous": getattr(decision, "ambiguous", None),
                    "ambiguous_reason": getattr(decision, "ambiguous_reason", None),
                    "signals": getattr(decision, "signals", None),
                    "reasons": list(getattr(decision, "reasons", []) or []),
                    "graph_rag_requested": bool(getattr(message_in, "graph_rag_enabled", False)),
                    "argument_graph_requested": getattr(message_in, "argument_graph_enabled", None),
                    "graph_rag_enabled": bool(effective_graph_rag_enabled),
                    "argument_graph_enabled": effective_argument_graph_enabled,
                    "graph_hops": int(effective_graph_hops),
                    "query": clean_content[:180],
                },
                request_id=request_id,
                user_id=str(current_user.id),
                tenant_id=str(current_user.id),
                conversation_id=chat_id,
            )
        except Exception as exc:
            logger.warning(f"RAG router failed (ignored): {exc}")
    with usage_context("chat", chat_id, user_id=current_user.id, turn_id=turn_id):
        with billing_context(
            graph_rag_enabled=bool(effective_graph_rag_enabled),
            argument_graph_enabled=effective_argument_graph_enabled,
        ):
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
                    web_search=bool(web_search_flag),
                    used_context=bool(system_context or mentions_meta),
                    used_outline=False
                ) if thinking_enabled_simple else None

                # 4. Telemetria Pós-execução
                item_telemetry = token_service.get_telemetry(ai_response.usage_metadata or {}, budget_model_id)

            except Exception as e:
                # Fallback em caso de erro (ex: falta de API Key)
                print(f"Erro na IA: {e}")
            ai_content = None
            
            # Gemini failsafe: try direct Gemini call as last resort
            try:
                from app.services.ai.agent_clients import call_vertex_gemini_async
                from app.services.ai.model_registry import get_api_model_name
                print("⚠️ Tentando Gemini como fallback...")
                ai_content = await call_vertex_gemini_async(
                    None,
                    clean_content,
                    model=get_api_model_name("gemini-3-flash"),
                    max_tokens=1000,
                    temperature=temperature
                )
                if ai_content:
                    print("✅ Gemini failsafe successful")
            except Exception as gemini_err:
                print(f"❌ Gemini failsafe also failed: {gemini_err}")
            
            if not ai_content:
                ai_content = f"Desculpe, estou operando em modo offline no momento. Recebi sua mensagem: '{message_in.content}'"
            thinking = "Fallback ativado" if thinking_enabled_simple else None
            item_telemetry = {}
    
    # Montar metadados finais
    final_metadata = {"turn_id": turn_id, "request_id": request_id}
    if mentions_meta: final_metadata["mentions"] = mentions_meta
    if item_telemetry: final_metadata["token_usage"] = item_telemetry
    final_metadata["thinking_enabled"] = thinking_enabled_simple
    
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
    await _store_rag_memory(chat_id, history_payload)
    
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
    request_t0 = time.perf_counter()
    preprocess_done_t: Optional[float] = None
    first_token_t: Optional[float] = None
    result = await db.execute(select(Chat).where(Chat.id == chat_id, Chat.user_id == current_user.id))
    chat = result.scalars().first()

    if not chat:
        raise HTTPException(status_code=404, detail="Chat não encontrado")

    parsed_flags = parse_prompt_flags(message_in.content)
    if parsed_flags.clean_text != message_in.content:
        message_in.content = parsed_flags.clean_text
    if parsed_flags.web_search is not None:
        message_in.web_search = parsed_flags.web_search
    if parsed_flags.reasoning_level:
        message_in.reasoning_level = parsed_flags.reasoning_level
    verbosity_override = parsed_flags.verbosity
    thinking_budget_override = parsed_flags.thinking_budget

    _cursor_debug_log({
        "sessionId": "debug-session",
        "runId": "pre",
        "hypothesisId": "H4",
        "location": "apps/api/app/api/endpoints/chats.py:send_message_stream",
        "message": "POST /api/chats/{chat_id}/messages/stream entry",
        "data": {
            "chatIdSuffix": str(chat_id or "")[-6:],
            "web_search": bool(getattr(message_in, "web_search", False)),
            "dense_research": bool(getattr(message_in, "dense_research", False)),
            "has_outline": bool(getattr(message_in, "outline", None)),
            "attachment_mode": getattr(message_in, "attachment_mode", None),
            "graph_rag_enabled": bool(getattr(message_in, "graph_rag_enabled", False)),
            "argument_graph_enabled": getattr(message_in, "argument_graph_enabled", None),
        },
        "timestamp": int(datetime.utcnow().timestamp() * 1000),
    })

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
    plan_key = resolve_plan_key(getattr(current_user, "plan", None))
    deep_effort, deep_multiplier = resolve_deep_research_billing(plan_key, message_in.deep_research_effort)
    if bool(getattr(message_in, "dense_research", False)) and deep_effort:
        status = await get_deep_research_monthly_status(
            db,
            user_id=str(current_user.id),
            plan_key=plan_key,
        )
        if not status.get("allowed", True):
            deep_effort = None
            deep_multiplier = 1.0
    max_web_search_requests = get_plan_cap(plan_key, "max_web_search_requests", default=5)
    web_search_flag = bool(message_in.web_search)
    if max_web_search_requests is not None and max_web_search_requests <= 0:
        web_search_flag = False

    # --- Poe-like billing: quote + gates (wallet + per-message budget) ---
    requested_model = (message_in.model or chat.context.get("model") or DEFAULT_JUDGE_MODEL).strip()
    try:
        requested_model = validate_model_id(requested_model, for_juridico=True, field_name="model")
    except ValueError:
        requested_model = DEFAULT_JUDGE_MODEL

    history_text = "\n".join(
        str(item.get("content") or "")
        for item in (conversation_history or [])
        if isinstance(item, dict)
    )
    context_tokens_est = token_service.estimate_tokens(
        "\n\n".join([base_instruction or "", history_text, str(message_in.content or "")]).strip()
    )

    points_base, billing_breakdown = estimate_chat_turn_points(
        model_id=requested_model,
        context_tokens=context_tokens_est,
        web_search=bool(web_search_flag),
        max_web_search_requests=max_web_search_requests,
        multi_query=bool(message_in.multi_query),
        dense_research=bool(getattr(message_in, "dense_research", False)),
        deep_research_effort=deep_effort,
        deep_research_points_multiplier=float(deep_multiplier),
        perplexity_search_type=getattr(message_in, "perplexity_search_type", None),
        perplexity_search_context_size=getattr(message_in, "perplexity_search_context_size", None),
        perplexity_disable_search=bool(getattr(message_in, "perplexity_disable_search", False)),
    )
    use_outline_pipeline = bool(getattr(message_in, "outline_pipeline", False))
    if use_outline_pipeline:
        billing_context_model = (message_in.model or chat.context.get("model") or "").strip()
        billing_context_mode = (message_in.context_mode or "auto").lower()
        billing_context_files = message_in.context_files or []
        if billing_context_mode == "auto":
            billing_context_mode = decide_context_mode_from_paths(
                billing_context_files,
                billing_context_model,
            )
        if billing_context_mode == "upload_cache" and not supports_upload_cache(billing_context_model):
            billing_context_mode = "rag_local"
        if billing_context_mode == "upload_cache" and not billing_context_files:
            billing_context_mode = "rag_local"
        if billing_context_mode == "upload_cache":
            lowered = str(message_in.content or "").lower()
            if any(tag in lowered for tag in ("@gpt", "@claude", "@all", "@todos")):
                billing_context_mode = "rag_local"
        has_outline = isinstance(message_in.outline, list) and any(
            str(item).strip() for item in message_in.outline
        )
        sections_est = _estimate_outline_sections(
            message_in.outline,
            getattr(message_in, "min_pages", None),
            getattr(message_in, "max_pages", None),
        )
        base_call_count = _estimate_outline_pipeline_calls(sections_est, has_outline)
        summary_calls = 1 if billing_context_mode == "upload_cache" else 0
        call_count = base_call_count + summary_calls
        base_points = int(points_base)
        points_base = int(base_points * call_count)
        if isinstance(billing_breakdown, dict):
            billing_breakdown["outline_pipeline_calls"] = int(call_count)
            billing_breakdown["outline_pipeline_sections_est"] = int(sections_est)
            billing_breakdown["outline_pipeline_has_outline"] = bool(has_outline)
            billing_breakdown["outline_pipeline_summary_calls"] = int(summary_calls)
            billing_breakdown["points_total_scaled"] = int(points_base)
            extra_points = max(0, int(points_base) - int(base_points))
            components = billing_breakdown.get("components")
            if isinstance(components, list):
                components.append({
                    "kind": "outline_pipeline",
                    "calls": int(call_count),
                    "points": int(extra_points),
                })

    points_summary = await get_points_summary(
        db,
        user_id=str(current_user.id),
        plan_key=plan_key,
    )
    points_available = points_summary.get("available_points")
    wallet_points_balance = int(points_available) if isinstance(points_available, int) else 10**12

    budget_override = getattr(message_in, "budget_override_points", None)
    try:
        budget_override = int(budget_override) if budget_override is not None else None
    except (TypeError, ValueError):
        budget_override = None

    message_budget = budget_override or resolve_chat_max_points_per_message(chat.context)
    usd_per_point = get_usd_per_point()
    quote = poe_quote_message(
        estimator=FixedPointsEstimator(usd_per_point=usd_per_point, breakdown=billing_breakdown),
        req={"points_estimate": int(points_base)},
        wallet_points_balance=wallet_points_balance,
        chat_max_points_per_message=int(message_budget),
        usd_per_point=usd_per_point,
    )
    if not quote.ok:
        status_code = 400
        if quote.error == "insufficient_balance":
            status_code = 402
        elif quote.error == "message_budget_exceeded":
            status_code = 409
        raise HTTPException(status_code=status_code, detail=asdict(quote))

    user_msg = ChatMessage(
        id=str(uuid.uuid4()),
        chat_id=chat_id,
        role="user",
        content=message_in.content,
        attachments=message_in.attachments,
        msg_metadata={
            "turn_id": turn_id,
            "request_id": request_id,
            "billing_quote": {
                "estimated_points": int(quote.estimated_points),
                "estimated_usd": float(quote.estimated_usd),
            },
        },
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
        await _store_rag_memory(chat_id, history_payload)
        db.add(ai_msg)
        chat.updated_at = utcnow()
        await db.commit()

        async def stream_command():
            start_ms = int(time.time() * 1000)
            yield sse_event({"type": "meta", "phase": "start", "t": start_ms, "turn_id": turn_id, "request_id": request_id})
            answer_started = False
            for chunk in chunk_text(ai_content):
                if not answer_started:
                    answer_started = True
                    yield sse_event({"type": "meta", "phase": "answer_start", "t": int(time.time() * 1000), "turn_id": turn_id})
                yield sse_event({"type": "token", "delta": chunk, "turn_id": turn_id})
                await asyncio.sleep(0)
            yield sse_event({
                "type": "done",
                "full_text": ai_content,
                "message_id": ai_msg.id,
                "turn_id": turn_id,
                "request_id": request_id,
                "token_usage": token_usage,
            })

        return StreamingResponse(stream_command(), media_type="text/event-stream")

    # 2. Processar menções + contexto
    sticky_docs = chat.context.get("sticky_docs", [])
    clean_content, system_context, mentions_meta = await mention_service.parse_mentions(
        message_in.content, db, current_user.id, sticky_docs=sticky_docs
    )

    template_filters = message_in.template_filters or chat.context.get("template_filters") or {}
    use_templates = bool(message_in.use_templates) or bool(chat.context.get("use_templates"))
    effective_rag_sources = list(message_in.rag_sources or [])
    if use_templates and "pecas_modelo" not in effective_rag_sources:
        effective_rag_sources.append("pecas_modelo")

    raw_temperature = getattr(message_in, "temperature", None)
    if raw_temperature is None:
        raw_temperature = chat.context.get("temperature")
    try:
        temperature = float(raw_temperature) if raw_temperature is not None else (
            0.6 if message_in.chat_personality == "geral" else 0.3
        )
    except (TypeError, ValueError):
        temperature = 0.6 if message_in.chat_personality == "geral" else 0.3
    temperature = max(0.0, min(1.0, temperature))

    context_model = (message_in.model or chat.context.get("model") or "").strip()
    attachment_mode = (message_in.attachment_mode or "auto").lower()
    if attachment_mode not in ("auto", "rag_local", "prompt_injection"):
        attachment_mode = "auto"

    context_files = message_in.context_files or []
    context_mode = (message_in.context_mode or "auto").lower()
    if context_mode == "auto":
        context_mode = decide_context_mode_from_paths(context_files, context_model)
    if context_mode == "upload_cache" and not supports_upload_cache(context_model):
        context_mode = "rag_local"
    if context_mode == "upload_cache" and not context_files:
        context_mode = "rag_local"
    if context_mode == "upload_cache":
        lowered = clean_content.lower()
        if any(tag in lowered for tag in ("@gpt", "@claude", "@all", "@todos")):
            context_mode = "rag_local"

    attachment_docs = await _load_attachment_docs(db, current_user.id, message_in.attachments)
    if context_mode == "upload_cache" and attachment_docs:
        attachment_paths = [doc.url for doc in attachment_docs if getattr(doc, "url", None)]
        if attachment_paths:
            context_files = list(dict.fromkeys([*context_files, *attachment_paths]))
    if context_mode == "upload_cache" and attachment_docs and attachment_mode == "auto":
        attachment_mode = "rag_local"
    if context_mode == "upload_cache":
        provider = _resolve_provider_for_model(context_model) or "google"
        oversized, limit_mb = _find_oversized_upload_cache_files(context_files, attachment_docs, provider)
        if oversized:
            logger.warning(
                "Upload cache desativado: arquivo(s) acima do limite do provedor (%s MB): %s",
                limit_mb,
                ", ".join(oversized[:5]),
            )
            context_mode = "rag_local"
            context_files = []

    chat_personality = (message_in.chat_personality or "juridico").lower()
    reasoning_level = (message_in.reasoning_level or "medium").lower()
    thinking_enabled = _is_thinking_enabled(reasoning_level, thinking_budget_override)
    base_instruction = apply_verbosity_instruction(
        build_system_instruction(chat_personality),
        verbosity_override,
    )
    if reasoning_level == "high":
        base_instruction += "\n- Aprofunde a análise e considere nuances importantes."
    elif reasoning_level == "low":
        base_instruction += "\n- Seja direto e conciso."
    history_block = _build_history_block(chat.context.get("conversation_summary"), conversation_history)
    fallback_model = "claude-4.5-sonnet" if chat_personality == "juridico" else "gpt-5.2"
    budget_model_id = _resolve_budget_model_id(clean_content, context_model or None, fallback_model)

    attachment_injection_context = ""
    if attachment_docs:
        if attachment_mode == "prompt_injection":
            attachment_injection_context = get_document_generator()._build_attachment_prompt_context(attachment_docs)
        elif attachment_mode == "auto":
            base_context = _join_context_parts(base_instruction, history_block, system_context)
            attachment_tokens, attachment_chars = _estimate_attachment_stats(attachment_docs)
            if attachment_tokens > 0:
                available_tokens = _estimate_available_tokens(budget_model_id, clean_content, base_context)
                available_chars = max(0, int(available_tokens * 3.5))
                if available_tokens > 0 and attachment_chars > 0 and attachment_chars <= available_chars:
                    max_chars = min(attachment_chars, available_chars)
                    attachment_injection_context = get_document_generator()._build_attachment_prompt_context(
                        attachment_docs,
                        max_chars=max_chars,
                        per_doc_chars=max_chars,
                    )

    if attachment_mode == "auto":
        if not attachment_injection_context:
            attachment_mode = "rag_local"
        else:
            budget_context = _join_context_parts(
                base_instruction,
                history_block,
                system_context,
                attachment_injection_context,
            )
            if _should_use_precise_budget(budget_model_id):
                budget = await token_service.check_budget_precise(
                    clean_content,
                    {"system": budget_context},
                    budget_model_id,
                )
            else:
                budget = token_service.check_budget(
                    clean_content,
                    {"system": budget_context},
                    budget_model_id,
                )
            if budget["status"] == "error":
                attachment_mode = "rag_local"
                attachment_injection_context = ""
            else:
                attachment_mode = "prompt_injection"
    if attachment_mode == "prompt_injection" and not attachment_injection_context:
        attachment_mode = "rag_local"

    rag_mode = getattr(message_in, "rag_mode", None) or chat.context.get("rag_mode") or "manual"
    rag_mode = str(rag_mode).strip().lower()
    if rag_mode not in ("auto", "manual"):
        rag_mode = "manual"

    argument_graph_enabled = message_in.argument_graph_enabled
    if argument_graph_enabled is None:
        argument_graph_enabled = chat.context.get("argument_graph_enabled")

    effective_graph_rag_enabled = bool(message_in.graph_rag_enabled)
    effective_argument_graph_enabled = argument_graph_enabled
    effective_graph_hops = int(message_in.graph_hops or 1)
    router_reasons: List[str] = []
    if rag_mode == "auto":
        try:
            from app.services.ai.rag_router import decide_rag_route_hybrid
            allow_argument = os.getenv("ARGUMENT_RAG_ENABLED", "true").lower() in ("1", "true", "yes", "on")
            router_roles = [str(getattr(current_user, "role", "") or "")] if getattr(current_user, "role", None) else []
            router_groups = chat.context.get("rag_groups") if isinstance(chat.context, dict) else None
            if isinstance(router_groups, str):
                router_groups = [g.strip() for g in router_groups.split(",") if g.strip()]
            if not isinstance(router_groups, list):
                router_groups = []
            decision = await decide_rag_route_hybrid(
                clean_content,
                rag_mode="auto",
                graph_hops=effective_graph_hops,
                allow_graph=True,
                allow_argument=allow_argument,
                risk_mode="high",
                roles=router_roles,
                groups=router_groups,
            )
            effective_graph_rag_enabled = decision.graph_rag_enabled
            effective_argument_graph_enabled = decision.argument_graph_enabled
            effective_graph_hops = decision.graph_hops
            router_reasons = list(decision.reasons or [])
            trace_event(
                "rag_router_decision",
                {
                    "mode": "chat_stream",
                    "rag_mode": rag_mode,
                    "used_llm": bool(getattr(decision, "used_llm", False)),
                    "llm_confidence": getattr(decision, "llm_confidence", None),
                    "llm_provider": getattr(decision, "llm_provider", None),
                    "llm_model": getattr(decision, "llm_model", None),
                    "llm_thinking_level": getattr(decision, "llm_thinking_level", None),
                    "llm_schema_enforced": getattr(decision, "llm_schema_enforced", None),
                    "ambiguous": getattr(decision, "ambiguous", None),
                    "ambiguous_reason": getattr(decision, "ambiguous_reason", None),
                    "signals": getattr(decision, "signals", None),
                    "reasons": list(getattr(decision, "reasons", []) or []),
                    "graph_rag_requested": bool(getattr(message_in, "graph_rag_enabled", False)),
                    "argument_graph_requested": getattr(message_in, "argument_graph_enabled", None),
                    "graph_rag_enabled": bool(effective_graph_rag_enabled),
                    "argument_graph_enabled": effective_argument_graph_enabled,
                    "graph_hops": int(effective_graph_hops),
                    "query": clean_content[:180],
                },
                request_id=request_id,
                user_id=str(current_user.id),
                tenant_id=str(current_user.id),
                conversation_id=chat_id,
            )
        except Exception as exc:
            logger.warning(f"RAG router failed (ignored): {exc}")

    current_context = chat.context.copy()
    if system_context:
        current_context["referenced_content"] = system_context
    current_context["chat_personality"] = message_in.chat_personality
    current_context["conversation_history"] = conversation_history
    current_context["web_search"] = web_search_flag
    current_context["search_mode"] = message_in.search_mode
    current_context["perplexity_search_mode"] = message_in.perplexity_search_mode
    current_context["perplexity_search_type"] = message_in.perplexity_search_type
    current_context["perplexity_search_context_size"] = message_in.perplexity_search_context_size
    current_context["perplexity_search_classifier"] = message_in.perplexity_search_classifier
    current_context["perplexity_disable_search"] = message_in.perplexity_disable_search
    current_context["perplexity_stream_mode"] = message_in.perplexity_stream_mode
    current_context["perplexity_search_domain_filter"] = message_in.perplexity_search_domain_filter
    current_context["perplexity_search_language_filter"] = message_in.perplexity_search_language_filter
    current_context["perplexity_search_recency_filter"] = message_in.perplexity_search_recency_filter
    current_context["perplexity_search_after_date"] = message_in.perplexity_search_after_date
    current_context["perplexity_search_before_date"] = message_in.perplexity_search_before_date
    current_context["perplexity_last_updated_after"] = message_in.perplexity_last_updated_after
    current_context["perplexity_last_updated_before"] = message_in.perplexity_last_updated_before
    current_context["perplexity_search_max_results"] = message_in.perplexity_search_max_results
    current_context["perplexity_search_max_tokens"] = message_in.perplexity_search_max_tokens
    current_context["perplexity_search_max_tokens_per_page"] = (
        message_in.perplexity_search_max_tokens_per_page
    )
    current_context["perplexity_search_country"] = message_in.perplexity_search_country
    current_context["perplexity_search_region"] = message_in.perplexity_search_region
    current_context["perplexity_search_city"] = message_in.perplexity_search_city
    current_context["perplexity_search_latitude"] = message_in.perplexity_search_latitude
    current_context["perplexity_search_longitude"] = message_in.perplexity_search_longitude
    current_context["perplexity_return_images"] = message_in.perplexity_return_images
    current_context["perplexity_return_videos"] = message_in.perplexity_return_videos
    current_context["research_policy"] = message_in.research_policy
    current_context["rag_sources"] = effective_rag_sources
    current_context["rag_top_k"] = message_in.rag_top_k
    current_context["attachment_mode"] = attachment_mode
    current_context["context_mode"] = context_mode
    current_context["context_files"] = context_files
    current_context["cache_ttl"] = message_in.cache_ttl
    current_context["adaptive_routing"] = message_in.adaptive_routing
    current_context["rag_mode"] = rag_mode
    current_context["crag_gate"] = message_in.crag_gate
    current_context["crag_min_best_score"] = message_in.crag_min_best_score
    current_context["crag_min_avg_score"] = message_in.crag_min_avg_score
    current_context["hyde_enabled"] = message_in.hyde_enabled
    current_context["graph_rag_enabled"] = message_in.graph_rag_enabled
    current_context["argument_graph_enabled"] = argument_graph_enabled
    current_context["graph_hops"] = message_in.graph_hops
    current_context["dense_research"] = message_in.dense_research
    current_context["deep_research_effort"] = message_in.deep_research_effort
    current_context["deep_research_provider"] = message_in.deep_research_provider
    current_context["deep_research_model"] = message_in.deep_research_model
    current_context["deep_research_search_focus"] = message_in.deep_research_search_focus
    current_context["deep_research_domain_filter"] = message_in.deep_research_domain_filter
    current_context["deep_research_search_after_date"] = message_in.deep_research_search_after_date
    current_context["deep_research_search_before_date"] = message_in.deep_research_search_before_date
    current_context["deep_research_last_updated_after"] = message_in.deep_research_last_updated_after
    current_context["deep_research_last_updated_before"] = message_in.deep_research_last_updated_before
    current_context["deep_research_country"] = message_in.deep_research_country
    current_context["deep_research_latitude"] = message_in.deep_research_latitude
    current_context["deep_research_longitude"] = message_in.deep_research_longitude
    current_context["reasoning_level"] = message_in.reasoning_level  # NEW: Sync thinking level
    current_context["use_templates"] = use_templates
    current_context["template_filters"] = template_filters
    current_context["template_id"] = message_in.template_id
    current_context["template_document_id"] = message_in.template_document_id
    current_context["temperature"] = temperature

    context_updated = False
    if chat.context.get("sticky_docs") != sticky_docs:
        chat.context["sticky_docs"] = sticky_docs
        flag_modified(chat, "context")
        context_updated = True
    if chat.context.get("web_search") != web_search_flag:
        chat.context["web_search"] = web_search_flag
        flag_modified(chat, "context")
        context_updated = True
    if chat.context.get("search_mode") != message_in.search_mode:
        chat.context["search_mode"] = message_in.search_mode
        flag_modified(chat, "context")
        context_updated = True
    if chat.context.get("rag_mode") != rag_mode:
        chat.context["rag_mode"] = rag_mode
        flag_modified(chat, "context")
        context_updated = True
    if chat.context.get("perplexity_search_mode") != message_in.perplexity_search_mode:
        chat.context["perplexity_search_mode"] = message_in.perplexity_search_mode
        flag_modified(chat, "context")
        context_updated = True
    if chat.context.get("perplexity_search_type") != message_in.perplexity_search_type:
        chat.context["perplexity_search_type"] = message_in.perplexity_search_type
        flag_modified(chat, "context")
        context_updated = True
    if chat.context.get("perplexity_search_context_size") != message_in.perplexity_search_context_size:
        chat.context["perplexity_search_context_size"] = message_in.perplexity_search_context_size
        flag_modified(chat, "context")
        context_updated = True
    if chat.context.get("perplexity_search_classifier") != message_in.perplexity_search_classifier:
        chat.context["perplexity_search_classifier"] = message_in.perplexity_search_classifier
        flag_modified(chat, "context")
        context_updated = True
    if chat.context.get("perplexity_disable_search") != message_in.perplexity_disable_search:
        chat.context["perplexity_disable_search"] = message_in.perplexity_disable_search
        flag_modified(chat, "context")
        context_updated = True
    if chat.context.get("perplexity_stream_mode") != message_in.perplexity_stream_mode:
        chat.context["perplexity_stream_mode"] = message_in.perplexity_stream_mode
        flag_modified(chat, "context")
        context_updated = True
    if chat.context.get("perplexity_search_domain_filter") != message_in.perplexity_search_domain_filter:
        chat.context["perplexity_search_domain_filter"] = message_in.perplexity_search_domain_filter
        flag_modified(chat, "context")
        context_updated = True
    if chat.context.get("perplexity_search_language_filter") != message_in.perplexity_search_language_filter:
        chat.context["perplexity_search_language_filter"] = message_in.perplexity_search_language_filter
        flag_modified(chat, "context")
        context_updated = True
    if chat.context.get("perplexity_search_recency_filter") != message_in.perplexity_search_recency_filter:
        chat.context["perplexity_search_recency_filter"] = message_in.perplexity_search_recency_filter
        flag_modified(chat, "context")
        context_updated = True
    if chat.context.get("perplexity_search_after_date") != message_in.perplexity_search_after_date:
        chat.context["perplexity_search_after_date"] = message_in.perplexity_search_after_date
        flag_modified(chat, "context")
        context_updated = True
    if chat.context.get("perplexity_search_before_date") != message_in.perplexity_search_before_date:
        chat.context["perplexity_search_before_date"] = message_in.perplexity_search_before_date
        flag_modified(chat, "context")
        context_updated = True
    if chat.context.get("perplexity_last_updated_after") != message_in.perplexity_last_updated_after:
        chat.context["perplexity_last_updated_after"] = message_in.perplexity_last_updated_after
        flag_modified(chat, "context")
        context_updated = True
    if chat.context.get("perplexity_last_updated_before") != message_in.perplexity_last_updated_before:
        chat.context["perplexity_last_updated_before"] = message_in.perplexity_last_updated_before
        flag_modified(chat, "context")
        context_updated = True
    if chat.context.get("perplexity_search_max_results") != message_in.perplexity_search_max_results:
        chat.context["perplexity_search_max_results"] = message_in.perplexity_search_max_results
        flag_modified(chat, "context")
        context_updated = True
    if chat.context.get("perplexity_search_max_tokens") != message_in.perplexity_search_max_tokens:
        chat.context["perplexity_search_max_tokens"] = message_in.perplexity_search_max_tokens
        flag_modified(chat, "context")
        context_updated = True
    if (
        chat.context.get("perplexity_search_max_tokens_per_page")
        != message_in.perplexity_search_max_tokens_per_page
    ):
        chat.context["perplexity_search_max_tokens_per_page"] = (
            message_in.perplexity_search_max_tokens_per_page
        )
        flag_modified(chat, "context")
        context_updated = True
    if chat.context.get("perplexity_search_country") != message_in.perplexity_search_country:
        chat.context["perplexity_search_country"] = message_in.perplexity_search_country
        flag_modified(chat, "context")
        context_updated = True
    if chat.context.get("perplexity_search_region") != message_in.perplexity_search_region:
        chat.context["perplexity_search_region"] = message_in.perplexity_search_region
        flag_modified(chat, "context")
        context_updated = True
    if chat.context.get("perplexity_search_city") != message_in.perplexity_search_city:
        chat.context["perplexity_search_city"] = message_in.perplexity_search_city
        flag_modified(chat, "context")
        context_updated = True
    if chat.context.get("perplexity_search_latitude") != message_in.perplexity_search_latitude:
        chat.context["perplexity_search_latitude"] = message_in.perplexity_search_latitude
        flag_modified(chat, "context")
        context_updated = True
    if chat.context.get("perplexity_search_longitude") != message_in.perplexity_search_longitude:
        chat.context["perplexity_search_longitude"] = message_in.perplexity_search_longitude
        flag_modified(chat, "context")
        context_updated = True
    if chat.context.get("perplexity_return_images") != message_in.perplexity_return_images:
        chat.context["perplexity_return_images"] = message_in.perplexity_return_images
        flag_modified(chat, "context")
        context_updated = True
    if chat.context.get("perplexity_return_videos") != message_in.perplexity_return_videos:
        chat.context["perplexity_return_videos"] = message_in.perplexity_return_videos
        flag_modified(chat, "context")
        context_updated = True
    if chat.context.get("research_policy") != message_in.research_policy:
        chat.context["research_policy"] = message_in.research_policy
        flag_modified(chat, "context")
        context_updated = True
    if chat.context.get("rag_sources") != effective_rag_sources:
        chat.context["rag_sources"] = effective_rag_sources
        flag_modified(chat, "context")
        context_updated = True
    if chat.context.get("rag_top_k") != message_in.rag_top_k:
        chat.context["rag_top_k"] = message_in.rag_top_k
        flag_modified(chat, "context")
        context_updated = True
    if chat.context.get("attachment_mode") != attachment_mode:
        chat.context["attachment_mode"] = attachment_mode
        flag_modified(chat, "context")
        context_updated = True
    if chat.context.get("context_mode") != context_mode:
        chat.context["context_mode"] = context_mode
        flag_modified(chat, "context")
        context_updated = True
    if chat.context.get("context_files") != context_files:
        chat.context["context_files"] = context_files
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
    if chat.context.get("argument_graph_enabled") != argument_graph_enabled:
        chat.context["argument_graph_enabled"] = argument_graph_enabled
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
    if chat.context.get("deep_research_effort") != message_in.deep_research_effort:
        chat.context["deep_research_effort"] = message_in.deep_research_effort
        flag_modified(chat, "context")
        context_updated = True
    if chat.context.get("deep_research_provider") != message_in.deep_research_provider:
        chat.context["deep_research_provider"] = message_in.deep_research_provider
        flag_modified(chat, "context")
        context_updated = True
    if chat.context.get("deep_research_model") != message_in.deep_research_model:
        chat.context["deep_research_model"] = message_in.deep_research_model
        flag_modified(chat, "context")
        context_updated = True
    if chat.context.get("deep_research_search_focus") != message_in.deep_research_search_focus:
        chat.context["deep_research_search_focus"] = message_in.deep_research_search_focus
        flag_modified(chat, "context")
        context_updated = True
    if chat.context.get("deep_research_domain_filter") != message_in.deep_research_domain_filter:
        chat.context["deep_research_domain_filter"] = message_in.deep_research_domain_filter
        flag_modified(chat, "context")
        context_updated = True
    if chat.context.get("deep_research_search_after_date") != message_in.deep_research_search_after_date:
        chat.context["deep_research_search_after_date"] = message_in.deep_research_search_after_date
        flag_modified(chat, "context")
        context_updated = True
    if chat.context.get("deep_research_search_before_date") != message_in.deep_research_search_before_date:
        chat.context["deep_research_search_before_date"] = message_in.deep_research_search_before_date
        flag_modified(chat, "context")
        context_updated = True
    if chat.context.get("deep_research_last_updated_after") != message_in.deep_research_last_updated_after:
        chat.context["deep_research_last_updated_after"] = message_in.deep_research_last_updated_after
        flag_modified(chat, "context")
        context_updated = True
    if chat.context.get("deep_research_last_updated_before") != message_in.deep_research_last_updated_before:
        chat.context["deep_research_last_updated_before"] = message_in.deep_research_last_updated_before
        flag_modified(chat, "context")
        context_updated = True
    if chat.context.get("deep_research_country") != message_in.deep_research_country:
        chat.context["deep_research_country"] = message_in.deep_research_country
        flag_modified(chat, "context")
        context_updated = True
    if chat.context.get("deep_research_latitude") != message_in.deep_research_latitude:
        chat.context["deep_research_latitude"] = message_in.deep_research_latitude
        flag_modified(chat, "context")
        context_updated = True
    if chat.context.get("deep_research_longitude") != message_in.deep_research_longitude:
        chat.context["deep_research_longitude"] = message_in.deep_research_longitude
        flag_modified(chat, "context")
        context_updated = True
    if message_in.temperature is not None and chat.context.get("temperature") != temperature:
        chat.context["temperature"] = temperature
        flag_modified(chat, "context")
        context_updated = True
    if chat.context.get("use_templates") != use_templates:
        chat.context["use_templates"] = use_templates
        flag_modified(chat, "context")
        context_updated = True
    if chat.context.get("template_filters") != template_filters:
        chat.context["template_filters"] = template_filters
        flag_modified(chat, "context")
        context_updated = True
    if chat.context.get("template_id") != message_in.template_id:
        chat.context["template_id"] = message_in.template_id
        flag_modified(chat, "context")
        context_updated = True
    if chat.context.get("template_document_id") != message_in.template_document_id:
        chat.context["template_document_id"] = message_in.template_document_id
        flag_modified(chat, "context")
        context_updated = True
    if context_updated:
        await db.commit()
        context_updated = False

    rag_filters = None
    tipo_peca_filter = None
    if isinstance(template_filters, dict) and template_filters:
        tipo_peca_filter = template_filters.get("tipo_peca")
        raw_filters = {}
        for key, value in template_filters.items():
            if key == "tipo_peca":
                continue
            if value in (None, "", False):
                continue
            raw_filters[key] = value
        if raw_filters:
            rag_filters = {"pecas_modelo": raw_filters}

    template_instruction = ""
    template_id = message_in.template_id or chat.context.get("template_id")
    if template_id:
        try:
            result = await db.execute(
                select(LibraryItem).where(
                    LibraryItem.id == template_id,
                    LibraryItem.user_id == current_user.id,
                    LibraryItem.type == LibraryItemType.MODEL,
                )
            )
            template_item = result.scalars().first()
            if template_item and template_item.description:
                meta, body = _parse_template_frontmatter(template_item.description)
                template_instruction = _build_template_instruction(meta, body)
        except Exception as e:
            logger.warning(f"Falha ao carregar template {template_id}: {e}")

    research_policy = message_in.research_policy
    research_decision = decide_research_flags(
        clean_content,
        bool(web_search_flag),
        bool(message_in.dense_research) and bool(deep_effort),
        research_policy,
    )
    effective_web_search = bool(research_decision.get("web_search"))
    effective_dense_research = bool(research_decision.get("deep_research")) and bool(deep_effort)
    planned_queries = research_decision.get("planned_queries") or []
    max_query_cap = None
    if max_web_search_requests is not None:
        try:
            max_query_cap = int(max_web_search_requests)
        except (TypeError, ValueError):
            max_query_cap = None
    if max_query_cap is not None and max_query_cap <= 0:
        effective_web_search = False
        planned_queries = []
    elif max_query_cap is not None:
        planned_queries = planned_queries[:max_query_cap]

    scope_groups, allow_global_scope, allow_group_scope = await resolve_rag_scope(
        db,
        tenant_id=str(current_user.id),
        user_id=str(current_user.id),
        user_role=current_user.role,
        chat_context=chat.context or {},
    )

    rag_context, graph_context, _ = await build_rag_context(
        query=clean_content,
        rag_sources=effective_rag_sources,
        rag_top_k=message_in.rag_top_k,
        attachment_mode=attachment_mode,
        adaptive_routing=message_in.adaptive_routing,
        # Router (rag_mode=auto) pode sobrescrever Graph/Argument no nível do request.
        crag_gate=message_in.crag_gate,
        crag_min_best_score=message_in.crag_min_best_score,
        crag_min_avg_score=message_in.crag_min_avg_score,
        hyde_enabled=message_in.hyde_enabled,
        multi_query=bool(message_in.multi_query),
        graph_rag_enabled=bool(effective_graph_rag_enabled),
        graph_hops=int(effective_graph_hops or message_in.graph_hops or 1),
        argument_graph_enabled=effective_argument_graph_enabled,
        dense_research=effective_dense_research,
        tenant_id=current_user.id,
        user_id=current_user.id,
        scope_groups=scope_groups,
        allow_global_scope=allow_global_scope,
        allow_group_scope=allow_group_scope,
        history=conversation_history,
        summary_text=chat.context.get("conversation_summary"),
        conversation_id=chat_id,
        rewrite_query=bool(conversation_history),
        request_id=request_id,
        filters=rag_filters,
        tipo_peca_filter=tipo_peca_filter,
    )

    local_query_override: Optional[str] = None
    local_queries: Optional[List[str]] = None
    if (attachment_mode == "rag_local" and attachment_docs) or (context_mode == "rag_local" and context_files):
        try:
            from app.services.ai.rag_helpers import generate_hypothetical_document, generate_multi_queries
        except Exception:
            generate_hypothetical_document = None
            generate_multi_queries = None
        if message_in.hyde_enabled and generate_hypothetical_document:
            try:
                local_query_override = await generate_hypothetical_document(
                    query=clean_content,
                    history=conversation_history,
                    summary_text=chat.context.get("conversation_summary"),
                )
            except Exception:
                local_query_override = None
        if message_in.multi_query and generate_multi_queries:
            try:
                local_queries = await generate_multi_queries(
                    clean_content,
                    history=conversation_history,
                    summary_text=chat.context.get("conversation_summary"),
                    max_queries=int(os.getenv("RAG_LOCAL_MULTI_QUERY_MAX", "3")),
                )
            except Exception:
                local_queries = None

    if attachment_mode == "rag_local" and attachment_docs:
        local_rag_context = get_document_generator()._build_local_rag_context(
            attachment_docs,
            clean_content,
            tenant_id=current_user.id,
            queries=local_queries,
            query_override=local_query_override,
            multi_query=bool(message_in.multi_query),
            crag_gate=bool(message_in.crag_gate),
            graph_rag_enabled=bool(effective_graph_rag_enabled),
            argument_graph_enabled=bool(effective_argument_graph_enabled),
            graph_hops=int(effective_graph_hops or message_in.graph_hops or 2),
        )
        if local_rag_context:
            rag_context = _join_context_parts(rag_context, local_rag_context)
    if context_mode == "rag_local" and context_files:
        context_rag = await _build_local_rag_context_from_paths(
            context_files,
            clean_content,
            tenant_id=current_user.id,
            queries=local_queries,
            query_override=local_query_override,
            multi_query=bool(message_in.multi_query),
            crag_gate=bool(message_in.crag_gate),
            graph_rag_enabled=bool(effective_graph_rag_enabled),
            argument_graph_enabled=bool(effective_argument_graph_enabled),
            graph_hops=int(effective_graph_hops or message_in.graph_hops or 2),
        )
        if context_rag:
            rag_context = _join_context_parts(rag_context, context_rag)
    if rag_context:
        current_context["rag_context"] = rag_context
    if graph_context:
        current_context["graph_context"] = graph_context
    if attachment_injection_context:
        current_context["attachment_context"] = attachment_injection_context
    upload_cache_rag_config = {
        "rag_sources": effective_rag_sources,
        "rag_top_k": message_in.rag_top_k,
        "adaptive_routing": message_in.adaptive_routing,
        "rag_mode": rag_mode,
        "crag_gate": message_in.crag_gate,
        "crag_min_best_score": message_in.crag_min_best_score,
        "crag_min_avg_score": message_in.crag_min_avg_score,
        "hyde_enabled": message_in.hyde_enabled,
        "graph_rag_enabled": bool(effective_graph_rag_enabled),
        "argument_graph_enabled": effective_argument_graph_enabled,
        "graph_hops": int(effective_graph_hops or message_in.graph_hops or 1),
        "dense_research": effective_dense_research,
        "filters": rag_filters,
        "tipo_peca_filter": tipo_peca_filter,
    }

    # 3. Orçamento de tokens
    if mentions_meta and _should_use_precise_budget(budget_model_id):
        budget = await token_service.check_budget_precise(clean_content, current_context, budget_model_id)
    else:
        budget = token_service.check_budget(clean_content, current_context, budget_model_id)

    if budget["status"] == "error":
        raise HTTPException(status_code=400, detail=budget["message"])
    if budget["status"] == "warning":
        print(f"⚠️ {budget['message']}")

    use_outline_pipeline = bool(getattr(message_in, "outline_pipeline", False))
    upload_cache_summary = ""
    if use_outline_pipeline and context_mode == "upload_cache":
        try:
            from app.services.ai.juridico_adapter import get_juridico_adapter

            adapter = get_juridico_adapter()
            if adapter and adapter.is_available() and context_files:
                summary_prompt = "\n".join([
                    "Gere um resumo factual detalhado dos documentos anexados para redacao de uma peca juridica.",
                    "Inclua: partes, fatos e cronologia (datas/valores), pedidos/pretensoes,",
                    "provas/documentos relevantes, pontos controvertidos e lacunas.",
                    "Formato: Markdown com secoes curtas e bullets quando cabivel.",
                    "Limite: ~4000 caracteres.",
                    "",
                    "Solicitacao do usuario:",
                    clean_content.strip(),
                ]).strip()
                summary_system_instruction = base_instruction
                if system_context:
                    summary_system_instruction += f"\n\n{system_context}"
                result = await adapter.chat(
                    message=summary_prompt,
                    history=[],
                    context_files=context_files,
                    cache_ttl=message_in.cache_ttl,
                    model=message_in.model or None,
                    tenant_id=current_user.id,
                    custom_prompt=summary_system_instruction,
                    rag_config=upload_cache_rag_config,
                )
                upload_cache_summary = str((result or {}).get("reply") or "").strip()
                if upload_cache_summary and len(upload_cache_summary) > 6000:
                    upload_cache_summary = upload_cache_summary[:6000].rstrip() + "..."
        except Exception as exc:
            logger.warning(f"Outline pipeline desativado: resumo upload_cache falhou ({exc})")
            upload_cache_summary = ""

        if not upload_cache_summary:
            logger.info("Outline pipeline desativado: resumo upload_cache indisponivel.")
            use_outline_pipeline = False

    if use_outline_pipeline:
        requested_model_id = requested_model
        model_cfg = get_model_config(requested_model_id)
        provider = (model_cfg.provider if model_cfg else "openai")
        if provider == "internal":
            provider = "google"
        api_model = get_api_model_name(requested_model_id)
        max_tokens = getattr(model_cfg, "max_output_tokens", None) if model_cfg else None
        if not max_tokens:
            max_tokens = 4096

        min_pages, max_pages = normalize_page_range(message_in.min_pages, message_in.max_pages)
        doc_kind = message_in.doc_kind or chat.context.get("doc_kind")
        doc_subtype = message_in.doc_subtype or chat.context.get("doc_subtype")
        document_type = (
            message_in.document_type
            or doc_subtype
            or chat.context.get("document_type")
            or "PETICAO"
        )
        doc_subtype = doc_subtype or document_type
        if not doc_kind and doc_subtype:
            try:
                from app.services.ai.nodes.catalogo_documentos import infer_doc_kind_subtype
                doc_kind, _ = infer_doc_kind_subtype(doc_subtype)
            except Exception:
                doc_kind = None

        thesis = message_in.thesis or chat.context.get("thesis") or ""
        outline_seed: List[str] = []
        if isinstance(message_in.outline, list):
            outline_seed = [str(item).strip() for item in message_in.outline if str(item).strip()]
        pipeline_case_summary = (
            f"{upload_cache_summary}\n\nSolicitacao do usuario:\n{clean_content}".strip()
            if upload_cache_summary
            else clean_content.strip()
        )

        system_instruction = base_instruction
        if history_block:
            system_instruction += "\n\n## CONTEXTO DA CONVERSA\n" + history_block
        if template_instruction:
            system_instruction += "\n\n### TEMPLATE DE ESTRUTURA\n" + template_instruction
        if rag_context:
            system_instruction += f"\n\n{rag_context}"
        if graph_context:
            system_instruction += f"\n\n{graph_context}"
        if system_context:
            system_instruction += f"\n\n{system_context}"
        if attachment_injection_context:
            system_instruction += f"\n\n{attachment_injection_context}"
        if effective_dense_research:
            system_instruction += "\n- Pesquisa profunda solicitada; aumente a cobertura e valide com mais cuidado."
        system_instruction += (
            "\n- Quando emitir raciocinio interno (thinking) ou resumo de raciocinio, escreva em portugues."
        )

        async def _stream_single_model(prompt: str):
            if provider == "anthropic":
                client = get_async_claude_client()
                extended_thinking = reasoning_level in ("high", "xhigh")
                thinking_budget = clamp_thinking_budget(thinking_budget_override, api_model)
                async for kind, delta in stream_anthropic_async(
                    client,
                    prompt,
                    model=api_model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system_instruction=system_instruction,
                    extended_thinking=extended_thinking,
                    thinking_budget=thinking_budget,
                ):
                    yield kind, delta
                return

            if provider == "google":
                client = get_gemini_client()
                gemini_thinking = None
                if reasoning_level in ("minimal", "low", "medium", "high", "xhigh"):
                    gemini_thinking = "high" if reasoning_level in ("high", "xhigh") else reasoning_level
                async for kind, delta in stream_vertex_gemini_async(
                    client,
                    prompt,
                    model=api_model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system_instruction=system_instruction,
                    thinking_mode=gemini_thinking,
                ):
                    yield kind, delta
                return

            if provider in ("openrouter", "deepseek"):
                client = get_async_openrouter_client() or get_openrouter_client()
            elif provider == "xai":
                client = get_async_xai_client() or get_xai_client()
            else:
                client = get_gpt_client()

            async for kind, delta in stream_openai_async(
                client,
                prompt,
                model=api_model,
                max_tokens=max_tokens,
                temperature=temperature,
                system_instruction=system_instruction,
                reasoning_effort=reasoning_level,
            ):
                yield kind, delta

        async def stream_outline_pipeline():
            start_ms = int(time.time() * 1000)
            yield sse_keepalive()
            yield sse_event({"type": "meta", "phase": "start", "t": start_ms, "turn_id": turn_id, "request_id": request_id})

            outline_items = list(outline_seed)
            if not outline_items:
                try:
                    outline_state = await outline_node({
                        "mode": document_type,
                        "doc_kind": doc_kind,
                        "doc_subtype": doc_subtype,
                        "input_text": pipeline_case_summary,
                        "tese": thesis,
                        "strategist_model": requested_model_id,
                        "judge_model": requested_model_id,
                        "min_pages": min_pages,
                        "max_pages": max_pages,
                    })
                    outline_items = outline_state.get("outline", []) if isinstance(outline_state, dict) else []
                    outline_items = [str(item).strip() for item in outline_items if str(item).strip()]
                except Exception as exc:
                    yield sse_event({"type": "error", "error": f"Falha ao gerar outline: {exc}", "turn_id": turn_id})
                    return

            if not outline_items:
                yield sse_event({"type": "error", "error": "Outline vazio.", "turn_id": turn_id})
                return

            yield sse_event({"type": "outline", "outline": outline_items, "turn_id": turn_id})

            outline_block = "\n".join(f"- {item}" for item in outline_items)
            length_guidance = build_length_guidance(
                {"min_pages": min_pages, "max_pages": max_pages, "target_pages": 0},
                len(outline_items),
            )
            case_summary = pipeline_case_summary
            if len(case_summary) > 6000:
                case_summary = case_summary[:6000].rstrip() + "..."

            full_text = ""
            previous_context = ""
            answer_started = False

            for idx, title in enumerate(outline_items):
                if not answer_started:
                    answer_started = True
                    yield sse_event({
                        "type": "meta",
                        "phase": "answer_start",
                        "t": int(time.time() * 1000),
                        "turn_id": turn_id,
                    })

                section_header = f"\n\n# {title}\n\n"
                full_text += section_header
                yield sse_event({
                    "type": "token",
                    "delta": section_header,
                    "model": requested_model_id,
                    "turn_id": turn_id,
                })

                prompt_parts = [
                    f"# CONTEXTO DO CASO\n{case_summary}",
                ]
                if thesis:
                    prompt_parts.append(f"# TESE/OBJETIVO\n{thesis}")
                prompt_parts.append(f"# OUTLINE COMPLETO\n{outline_block}")
                prompt_parts.append(f"# SECAO ATUAL ({idx + 1}/{len(outline_items)})\n{title}")
                if length_guidance:
                    prompt_parts.append(length_guidance.strip())
                if previous_context:
                    trimmed_prev = previous_context[-1500:]
                    prompt_parts.append(
                        "# CONTEXTO ANTERIOR (NAO REPETIR)\n" + trimmed_prev
                    )
                prompt_parts.append(
                    "\n".join([
                        "INSTRUCOES:",
                        "- Escreva apenas o corpo da secao atual em Markdown.",
                        "- Nao repita o titulo da secao.",
                        "- Mantenha coesao com as secoes anteriores.",
                        "- Evite duplicar trechos ja escritos.",
                    ])
                )
                section_prompt = "\n\n".join(prompt_parts).strip()

                try:
                    async for kind, delta in _stream_single_model(section_prompt):
                        if not delta:
                            continue
                        if kind == "thinking":
                            if thinking_enabled:
                                yield sse_event({
                                    "type": "thinking",
                                    "delta": str(delta),
                                    "model": requested_model_id,
                                    "turn_id": turn_id,
                                })
                        else:
                            text = str(delta)
                            if not text:
                                continue
                            full_text += text
                            yield sse_event({
                                "type": "token",
                                "delta": text,
                                "model": requested_model_id,
                                "turn_id": turn_id,
                            })
                        await asyncio.sleep(0)
                except Exception as exc:
                    logger.error(f"Erro no pipeline de outline: {exc}")
                    yield sse_event({
                        "type": "error",
                        "error": f"Erro ao gerar a secao '{title}': {exc}",
                        "turn_id": turn_id,
                    })
                    return

                previous_context = full_text

            token_usage = _estimate_token_usage(
                f"{system_instruction}\n\n{clean_content}",
                full_text,
                requested_model_id,
            )
            final_metadata = {
                "turn_id": turn_id,
                "request_id": request_id,
                "token_usage": token_usage,
                "model": requested_model_id,
                "outline_pipeline": True,
                "outline": outline_items,
            }
            if upload_cache_summary:
                final_metadata["outline_pipeline_hybrid"] = True
                final_metadata["outline_pipeline_summary_chars"] = len(upload_cache_summary)
            if mentions_meta:
                final_metadata["mentions"] = mentions_meta
            final_metadata["thinking_enabled"] = thinking_enabled

            thinking_summary = _build_safe_thinking_summary(
                dense_research=bool(effective_dense_research),
                web_search=bool(effective_web_search),
                used_context=bool(system_context or mentions_meta or rag_context or graph_context),
                used_outline=True,
            ) if thinking_enabled else None

            history_payload = conversation_history_full + [
                {"role": "user", "content": message_in.content},
                {"role": "assistant", "content": full_text},
            ]
            if _maybe_update_conversation_summary(chat, history_payload):
                flag_modified(chat, "context")
            await _store_rag_memory(chat_id, history_payload)

            ai_msg = ChatMessage(
                id=str(uuid.uuid4()),
                chat_id=chat_id,
                role="assistant",
                content=full_text,
                thinking=thinking_summary or None,
                msg_metadata=final_metadata,
                created_at=utcnow()
            )
            db.add(ai_msg)
            chat.updated_at = utcnow()
            await db.commit()

            yield sse_event({
                "type": "done",
                "full_text": full_text,
                "model": requested_model_id,
                "message_id": ai_msg.id,
                "turn_id": turn_id,
                "request_id": request_id,
                "token_usage": token_usage,
                "thinking": thinking_summary if thinking_enabled else None,
                "thinking_enabled": thinking_enabled,
            })

        return StreamingResponse(
            stream_outline_pipeline(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

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
    web_search = bool(effective_web_search)
    search_mode = (current_context.get("search_mode") or "hybrid").lower()
    if search_mode not in ("shared", "native", "hybrid", "perplexity"):
        search_mode = "hybrid"
    perplexity_search_mode = normalize_perplexity_search_mode(
        current_context.get("perplexity_search_mode")
    )
    perplexity_search_type = current_context.get("perplexity_search_type")
    perplexity_search_context_size = current_context.get("perplexity_search_context_size")
    perplexity_search_classifier = bool(current_context.get("perplexity_search_classifier"))
    perplexity_disable_search = bool(current_context.get("perplexity_disable_search"))
    perplexity_stream_mode = current_context.get("perplexity_stream_mode")
    search_domain_filter = parse_csv_list(
        current_context.get("perplexity_search_domain_filter"),
        max_items=20,
    )
    search_language_filter = parse_csv_list(
        current_context.get("perplexity_search_language_filter"),
        max_items=10,
    )
    search_recency_filter = normalize_perplexity_recency(
        current_context.get("perplexity_search_recency_filter")
    )
    search_after_date = normalize_perplexity_date(
        current_context.get("perplexity_search_after_date")
    )
    search_before_date = normalize_perplexity_date(
        current_context.get("perplexity_search_before_date")
    )
    last_updated_after = normalize_perplexity_date(
        current_context.get("perplexity_last_updated_after")
    )
    last_updated_before = normalize_perplexity_date(
        current_context.get("perplexity_last_updated_before")
    )
    try:
        search_max_results = int(current_context.get("perplexity_search_max_results"))
    except (TypeError, ValueError):
        search_max_results = None
    if search_max_results is not None and search_max_results <= 0:
        search_max_results = None
    if search_max_results is not None and search_max_results > 20:
        search_max_results = 20
    try:
        search_max_tokens = int(current_context.get("perplexity_search_max_tokens"))
    except (TypeError, ValueError):
        search_max_tokens = None
    if search_max_tokens is not None and search_max_tokens <= 0:
        search_max_tokens = None
    if search_max_tokens is not None and search_max_tokens > 1_000_000:
        search_max_tokens = 1_000_000
    try:
        search_max_tokens_per_page = int(
            current_context.get("perplexity_search_max_tokens_per_page")
        )
    except (TypeError, ValueError):
        search_max_tokens_per_page = None
    if search_max_tokens_per_page is not None and search_max_tokens_per_page <= 0:
        search_max_tokens_per_page = None
    if search_max_tokens_per_page is not None and search_max_tokens_per_page > 1_000_000:
        search_max_tokens_per_page = 1_000_000
    search_country = (current_context.get("perplexity_search_country") or "").strip() or None
    search_region = (current_context.get("perplexity_search_region") or "").strip() or None
    search_city = (current_context.get("perplexity_search_city") or "").strip() or None
    search_latitude = normalize_float(current_context.get("perplexity_search_latitude"))
    search_longitude = normalize_float(current_context.get("perplexity_search_longitude"))
    return_images = bool(current_context.get("perplexity_return_images"))
    return_videos = bool(current_context.get("perplexity_return_videos"))
    deep_search_focus = normalize_perplexity_search_mode(
        current_context.get("deep_research_search_focus")
    )
    deep_domain_filter = parse_csv_list(
        current_context.get("deep_research_domain_filter"),
        max_items=20,
    )
    deep_search_after = normalize_perplexity_date(
        current_context.get("deep_research_search_after_date")
    )
    deep_search_before = normalize_perplexity_date(
        current_context.get("deep_research_search_before_date")
    )
    deep_updated_after = normalize_perplexity_date(
        current_context.get("deep_research_last_updated_after")
    )
    deep_updated_before = normalize_perplexity_date(
        current_context.get("deep_research_last_updated_before")
    )
    deep_country = (current_context.get("deep_research_country") or "").strip() or None
    deep_latitude = normalize_float(current_context.get("deep_research_latitude"))
    deep_longitude = normalize_float(current_context.get("deep_research_longitude"))
    deep_provider_raw = (current_context.get("deep_research_provider") or "").strip().lower()
    if deep_provider_raw in ("pplx", "sonar"):
        deep_provider_raw = "perplexity"
    if deep_provider_raw in ("gemini",):
        deep_provider_raw = "google"
    deep_provider = deep_provider_raw or None
    deep_model = (current_context.get("deep_research_model") or "").strip() or None

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
        elif provider == "perplexity":
            model_key = "perplexity"
        elif provider == "internal":
            model_key = "internal"
        if not model_key:
            raise HTTPException(status_code=400, detail=f"Modelo '{requested_model}' não suportado no chat.")

        if model_key == "perplexity":
            if not os.getenv("PERPLEXITY_API_KEY"):
                raise HTTPException(
                    status_code=400,
                    detail="PERPLEXITY_API_KEY não configurada no backend (necessária para usar modelos Sonar).",
                )
            try:
                import perplexity  # noqa: F401
            except Exception:
                raise HTTPException(
                    status_code=500,
                    detail="Pacote perplexityai não instalado no backend (pip install perplexityai).",
                )

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
        "perplexity": bool(os.getenv("PERPLEXITY_API_KEY")),
        "internal": gemini_client is not None,
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
            msg_metadata={"model": "offline", "turn_id": turn_id, "request_id": request_id, "token_usage": offline_usage},
            created_at=utcnow()
        )
        history_payload = conversation_history_full + [
            {"role": "user", "content": message_in.content},
            {"role": "assistant", "content": fallback_text},
        ]
        if _maybe_update_conversation_summary(chat, history_payload):
            flag_modified(chat, "context")
        await _store_rag_memory(chat_id, history_payload)
        db.add(ai_msg)
        chat.updated_at = utcnow()
        await db.commit()

        async def stream_offline():
            start_ms = int(time.time() * 1000)
            yield sse_event({"type": "meta", "phase": "start", "t": start_ms, "turn_id": turn_id, "request_id": request_id})
            answer_started = False
            for chunk in chunk_text(fallback_text):
                if not answer_started:
                    answer_started = True
                    yield sse_event({"type": "meta", "phase": "answer_start", "t": int(time.time() * 1000), "turn_id": turn_id})
                yield sse_event({"type": "token", "delta": chunk, "model": "offline", "turn_id": turn_id})
                await asyncio.sleep(0)
            yield sse_event({
                "type": "done",
                "full_text": fallback_text,
                "model": "offline",
                "message_id": ai_msg.id,
                "turn_id": turn_id,
                "request_id": request_id,
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
    if effective_dense_research:
        multi_query = True
        breadth_first = True

    gpt_model_id = model_overrides.get("gpt", "gpt-5.2")
    claude_model_id = model_overrides.get("claude", "claude-4.5-sonnet")
    gemini_model_id = model_overrides.get("gemini", "gemini-3-flash")
    perplexity_model_id = model_overrides.get("perplexity", "sonar-pro")
    internal_model_id = model_overrides.get("internal", "internal-rag")

    def _get_max_tokens_for_key(k: str) -> int:
        mid = None
        if k == "gpt": mid = gpt_model_id
        elif k == "claude": mid = claude_model_id
        elif k == "gemini": mid = gemini_model_id
        elif k == "perplexity": mid = perplexity_model_id
        elif k == "internal": mid = internal_model_id
        
        if not mid: return 8192
        cfg = get_model_config(mid)
        # Use declared capability or fallback to generous default
        return cfg.max_output_tokens if cfg and cfg.max_output_tokens else 8192

    # Set default max_tokens based on the primary target model to maximize window
    primary_key = target_models[0] if target_models else "gpt"
    max_tokens = _get_max_tokens_for_key(primary_key)
    if thinking_budget_override is None:
        level = (reasoning_level or "").strip().lower()
        if level in ("none", "off", "disabled"):
            thinking_budget_override = 0
        elif level == "low":
            thinking_budget_override = 2000
        elif level == "medium":
            thinking_budget_override = 8000
        elif level == "xhigh":
            thinking_budget_override = 24000
        elif level == "high":
            thinking_budget_override = 16000
    claude_thinking_budget = clamp_thinking_budget(thinking_budget_override, claude_model_id)

    model_label = "+".join(
        [model_overrides.get(model_key, model_key) for model_key in target_models]
    )
    native_search_by_model = {
        "gpt": bool(gpt_client and hasattr(gpt_client, "responses") and gpt_override_provider in (None, "openai")),
        "claude": bool(claude_client),
        "gemini": bool(gemini_client),
        "perplexity": bool(os.getenv("PERPLEXITY_API_KEY")),
        # internal-rag é um agente RAG (Gemini Flash) e não usa native web_search tools.
        "internal": False,
    }
    allow_native_search = web_search and search_mode in ("native", "hybrid")
    allow_shared_search = web_search and search_mode in ("shared", "hybrid", "perplexity")
    use_shared_search = allow_shared_search and (
        search_mode in ("shared", "perplexity")
        or any(not native_search_by_model.get(model_key, False) for model_key in target_models)
    )
    max_sources = search_max_results or 20
    preprocess_done_t = time.perf_counter()

    async def stream_response():
        full_text_parts: List[str] = []
        full_thinking_parts: List[str] = []  # NEW: Accumulate real thinking from models
        system_instruction = base_instruction
        if history_block:
            system_instruction += "\n\n## CONTEXTO DA CONVERSA\n" + history_block
        sources = []
        citations_payload: List[Dict[str, Any]] = []
        citations_by_url: Dict[str, Dict[str, Any]] = {}
        start_ms = int(time.time() * 1000)
        last_keepalive = time.time()
        
        # Keepalive inicial (anti-buffering em proxies)
        yield sse_keepalive()
        
        yield sse_event({"type": "meta", "phase": "start", "t": start_ms, "turn_id": turn_id, "request_id": request_id})
        
        # Activity: Chamando modelo(s)
        model_label_display = model_label if model_label else "modelo"
        yield sse_activity_event(
            turn_id=turn_id,
            op="add",
            step_id="call",
            title=f"Chamando {model_label_display}",
            status="running",
            tags=[m for m in target_models[:3]] if target_models else [],
        )
        
        # Activity: Processo de raciocínio (será atualizado quando chegar thinking)
        if thinking_enabled:
            yield sse_activity_event(
                turn_id=turn_id,
                op="add",
                step_id="thinking",
                title="Processo de raciocínio",
                status="running",
            )
        
        answer_started = False

        def _merge_citations(items: List[Dict[str, Any]]):
            for item in items or []:
                url = str(item.get("url") or "").strip()
                number = item.get("number")
                key = str(number).strip() if number is not None else ""
                if not key:
                    key = url
                if not key:
                    continue
                if key not in citations_by_url:
                    citations_by_url[key] = item

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

        if template_instruction:
            system_instruction += "\n\n### TEMPLATE DE ESTRUTURA\n" + template_instruction

        if rag_context:
            system_instruction += f"\n\n{rag_context}"
        if graph_context:
            system_instruction += f"\n\n{graph_context}"
        if system_context:
            system_instruction += f"\n\n{system_context}"
        if attachment_injection_context:
            system_instruction += f"\n\n{attachment_injection_context}"
        if effective_dense_research:
            system_instruction += "\n- Pesquisa profunda solicitada; aumente a cobertura e valide com mais cuidado."
        system_instruction += (
            "\n- Quando emitir raciocinio interno (thinking) ou resumo de raciocinio, escreva em portugues."
        )

        if effective_dense_research:
            deep_report = ""
            deep_sources: List[Dict[str, Any]] = []
            try:
                yield sse_event({
                    "type": "research_start",
                    "researchmode": "deep",
                    "turn_id": turn_id,
                })
                # Activity: Deep research
                yield sse_activity_event(
                    turn_id=turn_id,
                    op="add",
                    step_id="deep_research",
                    title="Pesquisa profunda",
                    status="running",
                    detail=f"Effort: {deep_effort}",
                )
                deep_config: Dict[str, Any] = {"effort": deep_effort}
                if deep_multiplier is not None:
                    deep_config["points_multiplier"] = deep_multiplier
                if deep_provider and deep_provider != "auto":
                    deep_config["provider"] = deep_provider
                if deep_model:
                    deep_config["model"] = deep_model
                if deep_search_focus:
                    deep_config["search_focus"] = deep_search_focus
                if deep_domain_filter:
                    deep_config["search_domain_filter"] = deep_domain_filter
                if deep_search_after:
                    deep_config["search_after_date"] = deep_search_after
                if deep_search_before:
                    deep_config["search_before_date"] = deep_search_before
                if deep_updated_after:
                    deep_config["last_updated_after"] = deep_updated_after
                if deep_updated_before:
                    deep_config["last_updated_before"] = deep_updated_before
                if deep_country:
                    deep_config["search_country"] = deep_country
                if deep_latitude is not None:
                    deep_config["search_latitude"] = deep_latitude
                if deep_longitude is not None:
                    deep_config["search_longitude"] = deep_longitude

                async for event in deep_research_service.stream_research_task(clean_content, config=deep_config):
                    etype = (event or {}).get("type")
                    if etype == "cache_hit":
                        yield sse_event({
                            "type": "cache_hit",
                            "key": event.get("key"),
                            "turn_id": turn_id,
                        })
                    elif etype == "thinking":
                        text = event.get("text") or ""
                        if text:
                            yield sse_event({
                                "type": "deepresearch_step",
                                "text": text,
                                "turn_id": turn_id,
                            })
                    elif etype == "content":
                        deep_report += event.get("text") or ""
                    elif etype == "done":
                        sources_raw = event.get("sources") or []
                        if isinstance(sources_raw, list):
                            deep_sources = [s for s in sources_raw if isinstance(s, dict)]
                            if deep_sources:
                                _merge_citations(deep_sources)
                    elif etype == "error":
                        message = event.get("message") or event.get("error") or "Deep research falhou."
                        yield sse_event({
                            "type": "research_error",
                            "message": str(message),
                            "turn_id": turn_id,
                        })
            except Exception as exc:
                logger.warning(f"Deep research falhou: {exc}")
                yield sse_event({
                    "type": "research_error",
                    "message": str(exc),
                    "turn_id": turn_id,
                })

            if deep_report:
                trimmed = deep_report.strip()[:5000]
                system_instruction += "\n\n## PESQUISA PROFUNDA (resumo)\n" + trimmed
            yield sse_event({
                "type": "research_done",
                "researchmode": "deep",
                "turn_id": turn_id,
            })
            # Activity: Deep research done
            yield sse_activity_event(
                turn_id=turn_id,
                op="done",
                step_id="deep_research",
                title="Pesquisa profunda",
                status="done",
                detail=f"Fontes: {len(deep_sources)}",
            )

        if context_mode == "upload_cache" and context_files:
            try:
                from app.services.ai.juridico_adapter import get_juridico_adapter

                adapter = get_juridico_adapter()
                if adapter and adapter.is_available():
                    custom_prompt = system_instruction
                    if system_context:
                        custom_prompt += f"\n\n{system_context}"
                    result = await adapter.chat(
                        message=clean_content,
                        history=[],
                        context_files=context_files,
                        cache_ttl=message_in.cache_ttl,
                        model=message_in.model or None,
                        tenant_id=current_user.id,
                        custom_prompt=custom_prompt,
                        rag_config=upload_cache_rag_config,
                    )
                    reply_text = (result or {}).get("reply", "") or "Não foi possível gerar resposta."
                    for chunk in chunk_text(reply_text):
                        if not answer_started:
                            answer_started = True
                            yield sse_event({"type": "meta", "phase": "answer_start", "t": int(time.time() * 1000), "turn_id": turn_id})
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
                    final_metadata = {"turn_id": turn_id, "request_id": request_id, "token_usage": token_usage}
                    if mentions_meta:
                        final_metadata["mentions"] = mentions_meta
                    if message_in.model:
                        final_metadata["model"] = message_in.model
                    final_metadata["thinking_enabled"] = thinking_enabled

                    thinking_summary = _build_safe_thinking_summary(
                        dense_research=bool(effective_dense_research),
                        web_search=bool(web_search),
                        used_context=bool(system_context or mentions_meta or rag_context or graph_context),
                        used_outline=bool(outline_items)
                    ) if thinking_enabled else None

                    history_payload = conversation_history_full + [
                        {"role": "user", "content": message_in.content},
                        {"role": "assistant", "content": reply_text},
                    ]
                    if _maybe_update_conversation_summary(chat, history_payload):
                        flag_modified(chat, "context")
                    await _store_rag_memory(chat_id, history_payload)

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
                        "request_id": request_id,
                        "token_usage": token_usage,
                        "thinking": thinking_summary if thinking_enabled else None,
                        "thinking_enabled": thinking_enabled,
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
                # Activity: Web search
                yield sse_activity_event(
                    turn_id=turn_id,
                    op="add",
                    step_id="web_search",
                    title="Pesquisando na web",
                    status="running",
                    detail=f"Consulta: {search_query[:100]}",
                    tags=["google.com"],
                )
                if planned_queries and multi_query:
                    per_query = max(2, int(max_sources / max(1, len(planned_queries))))
                    tasks = [
                        web_search_service.search(
                            q,
                            num_results=per_query,
                            search_mode=perplexity_search_mode,
                            country=search_country,
                            domain_filter=search_domain_filter,
                            language_filter=search_language_filter,
                            recency_filter=search_recency_filter,
                            search_after_date=search_after_date,
                            search_before_date=search_before_date,
                            last_updated_after=last_updated_after,
                            last_updated_before=last_updated_before,
                            max_tokens=search_max_tokens,
                            max_tokens_per_page=search_max_tokens_per_page,
                            return_images=return_images,
                            return_videos=return_videos,
                        )
                        for q in planned_queries
                    ]
                    results_list = await asyncio.gather(*tasks, return_exceptions=True)
                    combined = []
                    cached_all = True
                    for payload in results_list:
                        if isinstance(payload, Exception):
                            cached_all = False
                            continue
                        if not payload.get("cached"):
                            cached_all = False
                        combined.extend(payload.get("results") or [])
                    deduped = []
                    seen = set()
                    for item in combined:
                        url = (item.get("url") or "").strip()
                        if not url or url in seen:
                            continue
                        seen.add(url)
                        deduped.append(item)
                    search_payload = {
                        "success": True,
                        "query": search_query,
                        "queries": planned_queries,
                        "results": deduped[:max_sources],
                        "source": "multi-planned",
                        "cached": cached_all,
                    }
                elif multi_query:
                    if max_query_cap is not None:
                        search_payload = await web_search_service.search_multi(
                            search_query,
                            num_results=max_sources,
                            max_queries=max_query_cap,
                            search_mode=perplexity_search_mode,
                            country=search_country,
                            domain_filter=search_domain_filter,
                            language_filter=search_language_filter,
                            recency_filter=search_recency_filter,
                            search_after_date=search_after_date,
                            search_before_date=search_before_date,
                            last_updated_after=last_updated_after,
                            last_updated_before=last_updated_before,
                            max_tokens=search_max_tokens,
                            max_tokens_per_page=search_max_tokens_per_page,
                            return_images=return_images,
                            return_videos=return_videos,
                        )
                    else:
                        search_payload = await web_search_service.search_multi(
                            search_query,
                            num_results=max_sources,
                            search_mode=perplexity_search_mode,
                            country=search_country,
                            domain_filter=search_domain_filter,
                            language_filter=search_language_filter,
                            recency_filter=search_recency_filter,
                            search_after_date=search_after_date,
                            search_before_date=search_before_date,
                            last_updated_after=last_updated_after,
                            last_updated_before=last_updated_before,
                            max_tokens=search_max_tokens,
                            max_tokens_per_page=search_max_tokens_per_page,
                            return_images=return_images,
                            return_videos=return_videos,
                        )
                else:
                    search_payload = await web_search_service.search(
                        search_query,
                        num_results=max_sources,
                        search_mode=perplexity_search_mode,
                        country=search_country,
                        domain_filter=search_domain_filter,
                        language_filter=search_language_filter,
                        recency_filter=search_recency_filter,
                        search_after_date=search_after_date,
                        search_before_date=search_before_date,
                        last_updated_after=last_updated_after,
                        last_updated_before=last_updated_before,
                        max_tokens=search_max_tokens,
                        max_tokens_per_page=search_max_tokens_per_page,
                        return_images=return_images,
                        return_videos=return_videos,
                    )
                results = search_payload.get("results") or []
                # Extract domains from results for tags
                search_domains = []
                for res in results[:8]:
                    url = res.get("url", "")
                    if url:
                        try:
                            from urllib.parse import urlparse
                            domain = urlparse(url).netloc.replace("www.", "")
                            if domain and domain not in search_domains:
                                search_domains.append(domain)
                        except Exception:
                            pass
                
                yield sse_event({
                    "type": "search_done",
                    "query": search_query,
                    "count": len(results),
                    "cached": bool(search_payload.get("cached")),
                    "source": search_payload.get("source"),
                    "queries": search_payload.get("queries") if multi_query else None
                })
                # Activity: Web search done
                yield sse_activity_event(
                    turn_id=turn_id,
                    op="done",
                    step_id="web_search",
                    title="Pesquisando na web",
                    status="done",
                    detail=f"Fontes: {len(results)}",
                    tags=search_domains[:6],
                )
                if search_payload.get("success") and results:
                    url_title_stream = [
                        (res.get("url", ""), res.get("title", ""))
                        for res in results
                    ]
                    url_to_number, sources = stable_numbering(url_title_stream)
                    web_context = build_web_context(search_payload, max_items=max_sources)
                    web_rag_context, web_citations = await web_rag_service.build_web_rag_context(
                        clean_content,
                        results,
                        max_docs=3,
                        max_chunks=6,
                        max_chars=6000,
                        url_to_number=url_to_number,
                    )
                    if web_citations:
                        _merge_citations(web_citations)
                    system_instruction += (
                        "\n- Use as fontes numeradas abaixo quando relevante."
                        "\n- Cite no texto com [n]. Não inclua URLs no corpo; as referências serão anexadas automaticamente ao final."
                        f"\n\n{web_rag_context or web_context}"
                    )
        try:
            async def _call_native_search(model_key: str, prompt: str) -> tuple[Optional[str], List[dict]]:
                if model_key == "gpt":
                    if not gpt_client or not hasattr(gpt_client, "responses"):
                        return None, []
                    def _sync_call():
                        return gpt_client.responses.create(
                            model=get_api_model_name(gpt_model_id),
                            input=[
                                {"role": "system", "content": base_instruction},
                                {"role": "user", "content": prompt},
                            ],
                            tools=[{"type": "web_search"}],
                            temperature=temperature,
                            max_output_tokens=_get_max_tokens_for_key("gpt"),
                        )
                    try:
                        resp = await asyncio.to_thread(_sync_call)
                        record_api_call(
                            kind="llm",
                            provider="openai",
                            model=get_api_model_name(gpt_model_id),
                            success=True,
                            meta={"tool": "web_search"},
                        )
                    except Exception:
                        record_api_call(
                            kind="llm",
                            provider="openai",
                            model=get_api_model_name(gpt_model_id),
                            success=False,
                            meta={"tool": "web_search"},
                        )
                        raise
                    text, sources = extract_perplexity("openai", resp)
                    citations = sources_to_citations(sources)
                    return text or getattr(resp, "output_text", "") or None, citations

                if model_key == "claude":
                    if not claude_client:
                        return None, []
                    kwargs = {
                        "model": get_api_model_name(claude_model_id),
                        "max_tokens": _get_max_tokens_for_key("claude"),
                        "system": base_instruction,
                        "messages": [{"role": "user", "content": prompt}],
                        "tools": [{"type": "web_search_20250305", "name": "web_search"}],
                    }
                    beta_header = os.getenv("ANTHROPIC_WEB_SEARCH_BETA", "web-search-2025-03-05").strip()
                    if beta_header:
                        kwargs["extra_headers"] = {"anthropic-beta": beta_header}
                    if _is_anthropic_vertex_client(claude_client):
                        kwargs["anthropic_version"] = os.getenv("ANTHROPIC_VERTEX_VERSION", "vertex-2023-10-16")
                    provider_name = "vertex-anthropic" if _is_anthropic_vertex_client(claude_client) else "anthropic"
                    try:
                        resp = await claude_client.messages.create(**kwargs)
                        record_api_call(
                            kind="llm",
                            provider=provider_name,
                            model=get_api_model_name(claude_model_id),
                            success=True,
                            meta={"tool": "web_search"},
                        )
                    except Exception:
                        record_api_call(
                            kind="llm",
                            provider=provider_name,
                            model=get_api_model_name(claude_model_id),
                            success=False,
                            meta={"tool": "web_search"},
                        )
                        raise
                    text, sources = extract_perplexity("claude", resp)
                    return text or None, sources_to_citations(sources)

                if model_key == "gemini":
                    if not gemini_client:
                        return None, []
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
                    try:
                        resp = await asyncio.to_thread(_sync_call)
                        record_api_call(
                            kind="llm",
                            provider="vertex-gemini",
                            model=get_api_model_name(gemini_model_id),
                            success=True,
                            meta={"tool": "web_search"},
                        )
                    except Exception:
                        record_api_call(
                            kind="llm",
                            provider="vertex-gemini",
                            model=get_api_model_name(gemini_model_id),
                            success=False,
                            meta={"tool": "web_search"},
                        )
                        raise
                    text, sources = extract_perplexity("gemini", resp)
                    if not text:
                        text = extract_genai_text(resp) or None
                    return text or None, sources_to_citations(sources)

                return None, []

            if breadth_first and len(target_models) == 1:
                model_key = target_models[0]
                worker_tasks = [
                    ("Fontes", "Liste fatos centrais e evidências relevantes para responder à pergunta."),
                    ("Contrapontos", "Apresente controvérsias ou nuances importantes relacionadas ao tema."),
                    ("Contexto", "Explique conceitos-chave e termos técnicos necessários para entender a resposta."),
                ]

                async def call_model(prompt: str, tokens: int) -> Optional[str]:
                    if allow_native_search and not use_shared_search and native_search_by_model.get(model_key):
                        text, native_citations = await _call_native_search(model_key, prompt)
                        if native_citations:
                            _merge_citations(native_citations)
                        return text
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
                    if model_key == "internal":
                        internal_api_model = get_api_model_name(internal_model_id)
                        internal_system = build_internal_rag_system_instruction(system_instruction)
                        return await call_vertex_gemini_async(
                            gemini_client,
                            prompt,
                            model=internal_api_model,
                            max_tokens=tokens,
                            temperature=temperature,
                            system_instruction=internal_system,
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
                if sources and not citations_by_url:
                    # Fallback: se a resposta não inseriu [n], ainda assim anexamos a seção de referências.
                    lead_text = append_references_section(
                        lead_text,
                        sources_to_citations(sources),
                        heading="References",
                        include_all_if_uncited=True,
                    )
                lead_text = append_autos_references_section(lead_text, attachment_docs=attachment_docs)

                for chunk in chunk_text(lead_text):
                    if not answer_started:
                        answer_started = True
                        yield sse_event({"type": "meta", "phase": "answer_start", "t": int(time.time() * 1000), "turn_id": turn_id})
                    yield sse_event({"type": "token", "delta": chunk, "model": model_key, "turn_id": turn_id})
                    await asyncio.sleep(0)

                if model_key == "gpt":
                    usage_model_id = gpt_model_id
                elif model_key == "claude":
                    usage_model_id = claude_model_id
                elif model_key == "internal":
                    usage_model_id = internal_model_id
                else:
                    usage_model_id = gemini_model_id
                token_usage = _estimate_token_usage(
                    f"{system_instruction}\n\n{lead_prompt}",
                    lead_text,
                    usage_model_id,
                    internal_model_id if model_key == "internal" else model_key
                )
                history_payload = conversation_history_full + [
                    {"role": "user", "content": message_in.content},
                    {"role": "assistant", "content": lead_text},
                ]
                if _maybe_update_conversation_summary(chat, history_payload):
                    flag_modified(chat, "context")
                await _store_rag_memory(chat_id, history_payload)
                if sources and not citations_by_url:
                    _merge_citations(sources_to_citations(sources))
                citations_payload = list(citations_by_url.values())
                msg_metadata = {
                    "model": model_key,
                    "breadth_first": True,
                    "turn_id": turn_id,
                    "request_id": request_id,
                    "token_usage": token_usage,
                }
                if citations_payload:
                    msg_metadata["citations"] = citations_payload
                ai_msg = ChatMessage(
                    id=str(uuid.uuid4()),
                    chat_id=chat_id,
                    role="assistant",
                    content=lead_text,
                    thinking=None,
                    msg_metadata=msg_metadata,
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
                    "request_id": request_id,
                    "token_usage": token_usage,
                    "citations": citations_payload,
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
                elif model_key == "perplexity":
                    model_id = perplexity_model_id
                elif model_key == "internal":
                    model_id = internal_model_id

                model_cfg = get_model_config(model_id) if model_id else None
                label = model_cfg.label if model_cfg else ""
                if not label:
                    if model_key == "gpt":
                        label = "GPT"
                    elif model_key == "claude":
                        label = "Claude"
                    elif model_key == "gemini":
                        label = "Gemini"
                    elif model_key == "perplexity":
                        label = "Perplexity"
                    elif model_key == "internal":
                        label = "Iudex RAG"

                if len(target_models) > 1:
                    header = f"🤖 **{label}**:\n"
                    full_text_parts.append(header)
                    if not answer_started:
                        answer_started = True
                        yield sse_event({"type": "meta", "phase": "answer_start", "t": int(time.time() * 1000), "turn_id": turn_id})
                    yield sse_event({"type": "token", "delta": header, "model": model_key})

                if allow_native_search and not use_shared_search and model_key != "perplexity" and native_search_by_model.get(model_key):
                    native_text, native_citations = await _call_native_search(model_key, clean_content)
                    if native_citations:
                        _merge_citations(native_citations)
                    if native_text:
                        for chunk in chunk_text(native_text):
                            full_text_parts.append(chunk)
                            if not answer_started:
                                answer_started = True
                                yield sse_event({"type": "meta", "phase": "answer_start", "t": int(time.time() * 1000), "turn_id": turn_id})
                            yield sse_event({"type": "token", "delta": chunk, "model": model_key})
                        if len(target_models) > 1 and idx < len(target_models) - 1:
                            separator = "\n\n---\n\n"
                            full_text_parts.append(separator)
                            if not answer_started:
                                answer_started = True
                                yield sse_event({"type": "meta", "phase": "answer_start", "t": int(time.time() * 1000), "turn_id": turn_id})
                            yield sse_event({"type": "token", "delta": separator})
                        continue

                if model_key == "gpt":
                    gpt_api_model = get_api_model_name(gpt_model_id)
                    thinking_cat = get_thinking_category(gpt_model_id)
                    
                    # Determine if we need reasoning_effort (o1/o3) or XML parsing (GPT-5.2)
                    reasoning_effort_param = None
                    effective_instruction = system_instruction
                    xml_parser = None
                    
                    if gpt_api_model.startswith(("o1-", "o3-")) or "gpt-5.2" in gpt_api_model:
                        # Native reasoning models (o1/o3, GPT-5.2)
                        allowed_efforts = {"none", "low", "medium", "high", "xhigh"}
                        normalized_effort = (reasoning_level or "").strip().lower()
                        if normalized_effort in allowed_efforts:
                            reasoning_effort_param = normalized_effort
                        else:
                            reasoning_effort_param = "medium"
                        logger.info(
                            f"🧠 [GPT Native] model={gpt_api_model}, reasoning_effort={reasoning_effort_param}"
                        )
                    elif thinking_cat == "xml" and reasoning_level in ("high", "medium", "xhigh"):
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
                                if chunk_type in ("thinking", "thinking_summary"):
                                    full_thinking_parts.append(delta)
                                    payload = {"type": "thinking", "delta": delta, "model": model_key}
                                    if chunk_type == "thinking_summary":
                                        payload["thinking_type"] = "summary"
                                    yield sse_event(payload)
                                else:
                                    full_text_parts.append(delta)
                                    if not answer_started:
                                        answer_started = True
                                        yield sse_event({"type": "meta", "phase": "answer_start", "t": int(time.time() * 1000), "turn_id": turn_id})
                                    yield sse_event({"type": "token", "delta": delta, "model": model_key})
                            elif xml_parser:
                                # Use XML parser for standard models
                                thinking, content = xml_parser.process_token(chunk_data)
                                if thinking:
                                    full_thinking_parts.append(thinking)
                                    yield sse_event({"type": "thinking", "delta": thinking, "model": model_key})
                                if content:
                                    full_text_parts.append(content)
                                    if not answer_started:
                                        answer_started = True
                                        yield sse_event({"type": "meta", "phase": "answer_start", "t": int(time.time() * 1000), "turn_id": turn_id})
                                    yield sse_event({"type": "token", "delta": content, "model": model_key})
                            else:
                                # No thinking extraction
                                full_text_parts.append(chunk_data)
                                if not answer_started:
                                    answer_started = True
                                    yield sse_event({"type": "meta", "phase": "answer_start", "t": int(time.time() * 1000), "turn_id": turn_id})
                                yield sse_event({"type": "token", "delta": chunk_data, "model": model_key})
                        
                        # Flush XML parser if used
                        if xml_parser:
                            thinking, content = xml_parser.flush()
                            if thinking:
                                full_thinking_parts.append(thinking)
                                yield sse_event({"type": "thinking", "delta": thinking, "model": model_key})
                            if content:
                                full_text_parts.append(content)
                                if not answer_started:
                                    answer_started = True
                                    yield sse_event({"type": "meta", "phase": "answer_start", "t": int(time.time() * 1000), "turn_id": turn_id})
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
                            if not answer_started:
                                answer_started = True
                                yield sse_event({"type": "meta", "phase": "answer_start", "t": int(time.time() * 1000), "turn_id": turn_id})
                            yield sse_event({"type": "token", "delta": chunk, "model": model_key})
                
                elif model_key == "perplexity":
                    perplexity_key = os.getenv("PERPLEXITY_API_KEY")
                    if not perplexity_key:
                        error_text = "PERPLEXITY_API_KEY não configurada no backend."
                        for chunk in chunk_text(error_text):
                            full_text_parts.append(chunk)
                            if not answer_started:
                                answer_started = True
                                yield sse_event({"type": "meta", "phase": "answer_start", "t": int(time.time() * 1000), "turn_id": turn_id})
                            yield sse_event({"type": "token", "delta": chunk, "model": model_key})
                        await asyncio.sleep(0)
                    else:
                        try:
                            from perplexity import AsyncPerplexity
                        except Exception as exc:
                            logger.error(f"Perplexity SDK import failed: {exc}")
                            error_text = "Pacote perplexityai não instalado no backend (pip install perplexityai)."
                            for chunk in chunk_text(error_text):
                                full_text_parts.append(chunk)
                                if not answer_started:
                                    answer_started = True
                                    yield sse_event({"type": "meta", "phase": "answer_start", "t": int(time.time() * 1000), "turn_id": turn_id})
                                yield sse_event({"type": "token", "delta": chunk, "model": model_key})
                                await asyncio.sleep(0)
                        else:
                            import inspect

                            def _get(obj: Any, key: str, default=None):
                                if isinstance(obj, dict):
                                    return obj.get(key, default)
                                return getattr(obj, key, default)

                            def _to_url_title(item: Any) -> tuple[str, str]:
                                if isinstance(item, str):
                                    return item, item
                                if isinstance(item, dict):
                                    url = str(item.get("url") or item.get("uri") or "").strip()
                                    title = str(item.get("title") or item.get("name") or url).strip()
                                    return url, title
                                url = str(getattr(item, "url", "") or getattr(item, "uri", "") or "").strip()
                                title = str(getattr(item, "title", "") or getattr(item, "name", "") or url).strip()
                                return url, title

                            client = AsyncPerplexity(api_key=perplexity_key)
                            perplexity_api_model = get_api_model_name(perplexity_model_id) or perplexity_model_id
                            messages = [
                                {"role": "system", "content": system_instruction},
                                {"role": "user", "content": clean_content},
                            ]
                            disable_search_effective = bool(perplexity_disable_search) or bool(use_shared_search)
                            pplx_meta_base = {
                                "size": "M",
                                "search_type": perplexity_search_type,
                                "search_context_size": perplexity_search_context_size,
                                "disable_search": disable_search_effective,
                                "search_mode": perplexity_search_mode,
                                "search_domain_filter": search_domain_filter,
                                "search_language_filter": search_language_filter,
                                "search_recency_filter": search_recency_filter,
                                "search_after_date": search_after_date,
                                "search_before_date": search_before_date,
                                "last_updated_after": last_updated_after,
                                "last_updated_before": last_updated_before,
                                "search_country": search_country,
                                "search_region": search_region,
                                "search_city": search_city,
                                "search_latitude": search_latitude,
                                "search_longitude": search_longitude,
                                "return_images": return_images,
                                "return_videos": return_videos,
                            }
                            perplexity_kwargs = build_perplexity_chat_kwargs(
                                api_model=perplexity_api_model,
                                web_search_enabled=web_search,
                                search_mode=perplexity_search_mode,
                                search_type=perplexity_search_type,
                                search_context_size=perplexity_search_context_size,
                                search_domain_filter=search_domain_filter,
                                search_language_filter=search_language_filter,
                                search_recency_filter=search_recency_filter,
                                search_after_date=search_after_date,
                                search_before_date=search_before_date,
                                last_updated_after=last_updated_after,
                                last_updated_before=last_updated_before,
                                search_country=search_country,
                                search_region=search_region,
                                search_city=search_city,
                                search_latitude=search_latitude,
                                search_longitude=search_longitude,
                                return_images=return_images,
                                return_videos=return_videos,
                                enable_search_classifier=perplexity_search_classifier,
                                disable_search=disable_search_effective,
                                stream_mode=perplexity_stream_mode,
                            )
                            search_results: List[Any] = []
                            citation_items: List[Any] = []

                            try:
                                stream_obj = client.chat.completions.create(
                                    model=perplexity_api_model,
                                    messages=messages,
                                    temperature=temperature,
                                    max_tokens=max_tokens,
                                    stream=True,
                                    **perplexity_kwargs,
                                )
                                record_api_call(
                                    kind="llm",
                                    provider="perplexity",
                                    model=perplexity_api_model,
                                    success=True,
                                    meta={**pplx_meta_base, "stream": True},
                                )
                                if inspect.isawaitable(stream_obj):
                                    stream_obj = await stream_obj

                                if hasattr(stream_obj, "__aiter__"):
                                    async for chunk in stream_obj:
                                        choices = _get(chunk, "choices", []) or []
                                        if choices:
                                            delta = _get(choices[0], "delta", None) or {}
                                            content = _get(delta, "content", None) or ""
                                            if content:
                                                full_text_parts.append(str(content))
                                                if not answer_started:
                                                    answer_started = True
                                                    yield sse_event({"type": "meta", "phase": "answer_start", "t": int(time.time() * 1000), "turn_id": turn_id})
                                                yield sse_event({"type": "token", "delta": str(content), "model": model_key})
                                                await asyncio.sleep(0)

                                        chunk_results = _get(chunk, "search_results", None) or _get(chunk, "searchResults", None)
                                        if isinstance(chunk_results, list) and chunk_results:
                                            search_results.extend(chunk_results)

                                        chunk_citations = _get(chunk, "citations", None)
                                        if isinstance(chunk_citations, list) and chunk_citations:
                                            citation_items.extend(chunk_citations)
                                else:
                                    for chunk in stream_obj:
                                        choices = _get(chunk, "choices", []) or []
                                        if choices:
                                            delta = _get(choices[0], "delta", None) or {}
                                            content = _get(delta, "content", None) or ""
                                            if content:
                                                full_text_parts.append(str(content))
                                                if not answer_started:
                                                    answer_started = True
                                                    yield sse_event({"type": "meta", "phase": "answer_start", "t": int(time.time() * 1000), "turn_id": turn_id})
                                                yield sse_event({"type": "token", "delta": str(content), "model": model_key})
                                                await asyncio.sleep(0)

                                        chunk_results = _get(chunk, "search_results", None) or _get(chunk, "searchResults", None)
                                        if isinstance(chunk_results, list) and chunk_results:
                                            search_results.extend(chunk_results)

                                        chunk_citations = _get(chunk, "citations", None)
                                        if isinstance(chunk_citations, list) and chunk_citations:
                                            citation_items.extend(chunk_citations)
                            except Exception as exc:
                                record_api_call(
                                    kind="llm",
                                    provider="perplexity",
                                    model=perplexity_api_model,
                                    success=False,
                                    meta={**pplx_meta_base, "stream": True},
                                )
                                logger.warning(f"Perplexity streaming failed ({perplexity_api_model}): {exc}. Falling back to non-streaming.")
                                try:
                                    perplexity_sync_kwargs = build_perplexity_chat_kwargs(
                                        api_model=perplexity_api_model,
                                        web_search_enabled=web_search,
                                        search_mode=perplexity_search_mode,
                                        search_type=perplexity_search_type,
                                        search_context_size=perplexity_search_context_size,
                                        search_domain_filter=search_domain_filter,
                                        search_language_filter=search_language_filter,
                                        search_recency_filter=search_recency_filter,
                                        search_after_date=search_after_date,
                                        search_before_date=search_before_date,
                                        last_updated_after=last_updated_after,
                                        last_updated_before=last_updated_before,
                                        search_country=search_country,
                                        search_region=search_region,
                                        search_city=search_city,
                                        search_latitude=search_latitude,
                                        search_longitude=search_longitude,
	                                        return_images=return_images,
	                                        return_videos=return_videos,
	                                        enable_search_classifier=perplexity_search_classifier,
	                                        disable_search=disable_search_effective,
	                                        stream_mode=None,
	                                    )
                                    resp_obj = client.chat.completions.create(
                                        model=perplexity_api_model,
                                        messages=messages,
                                        temperature=temperature,
                                        max_tokens=max_tokens,
                                        **perplexity_sync_kwargs,
                                    )
                                    record_api_call(
                                        kind="llm",
                                        provider="perplexity",
                                        model=perplexity_api_model,
                                        success=True,
                                        meta={**pplx_meta_base, "stream": False},
                                    )
                                except Exception:
                                    record_api_call(
                                        kind="llm",
                                        provider="perplexity",
                                        model=perplexity_api_model,
                                        success=False,
                                        meta={**pplx_meta_base, "stream": False},
                                    )
                                    raise
                                if inspect.isawaitable(resp_obj):
                                    resp_obj = await resp_obj
                                choices = _get(resp_obj, "choices", []) or []
                                msg = _get(choices[0], "message", None) if choices else None
                                text = _get(msg, "content", "") if msg else ""
                                if text:
                                    for chunk in chunk_text(str(text)):
                                        full_text_parts.append(str(chunk))
                                        if not answer_started:
                                            answer_started = True
                                            yield sse_event({"type": "meta", "phase": "answer_start", "t": int(time.time() * 1000), "turn_id": turn_id})
                                        yield sse_event({"type": "token", "delta": str(chunk), "model": model_key})
                                        await asyncio.sleep(0)

                                chunk_results = _get(resp_obj, "search_results", None) or _get(resp_obj, "searchResults", None)
                                if isinstance(chunk_results, list) and chunk_results:
                                    search_results.extend(chunk_results)
                                chunk_citations = _get(resp_obj, "citations", None)
                                if isinstance(chunk_citations, list) and chunk_citations:
                                    citation_items.extend(chunk_citations)

                            url_title_stream: List[tuple[str, str]] = []
                            if citation_items:
                                for item in citation_items:
                                    url, title = _to_url_title(item)
                                    if url:
                                        url_title_stream.append((url, title or url))
                            elif search_results:
                                for item in search_results:
                                    url, title = _to_url_title(item)
                                    if url:
                                        url_title_stream.append((url, title or url))

                            if url_title_stream and not use_shared_search:
                                _, model_sources = stable_numbering(url_title_stream)
                                _merge_citations(sources_to_citations(model_sources))

                elif model_key == "claude":
                    claude_api_model = get_api_model_name(claude_model_id)
                    thinking_cat = get_thinking_category(claude_model_id)
                    
                    # Determine thinking approach based on category
                    extended_thinking_param = False
                    effective_instruction = system_instruction
                    xml_parser = None
                    
                    budget_active = (
                        claude_thinking_budget is not None and claude_thinking_budget > 0
                    )
                    if thinking_cat == "native":
                        # Sonnet: use native extended_thinking API
                        if claude_thinking_budget is not None:
                            extended_thinking_param = budget_active
                        elif reasoning_level in ("high", "medium"):
                            extended_thinking_param = True
                        if extended_thinking_param:
                            logger.info(f"🧠 [Claude Native] model={claude_api_model}, extended_thinking=True")
                    elif thinking_cat == "xml" and (reasoning_level in ("high", "medium") or budget_active):
                        # Opus: use XML parsing
                        effective_instruction = inject_thinking_prompt(
                            system_instruction,
                            brief=(reasoning_level == "medium"),
                            budget_tokens=claude_thinking_budget if budget_active else None,
                        )
                        xml_parser = ThinkingStreamParser()
                        logger.info(f"🧠 [Claude XML] model={claude_api_model}, using XML parsing")
                    else:
                        logger.info(f"🧠 [Claude] model={claude_api_model}, thinking_cat={thinking_cat}, no thinking extraction")
                    
                    # Claude extended_thinking requires temperature=1
                    effective_temperature = 1.0 if extended_thinking_param else temperature
                    async for chunk_data in stream_anthropic_async(
                        claude_client,
                        clean_content,
                        model=claude_api_model,
                        max_tokens=max_tokens,
                        temperature=effective_temperature,
                        system_instruction=effective_instruction,
                        extended_thinking=extended_thinking_param,
                        thinking_budget=claude_thinking_budget if extended_thinking_param else None,
                    ):
                        # Handle tuples from native thinking API
                        if isinstance(chunk_data, tuple):
                            chunk_type, delta = chunk_data
                            if chunk_type in ("thinking", "thinking_summary"):
                                full_thinking_parts.append(delta)
                                payload = {"type": "thinking", "delta": delta, "model": model_key}
                                if chunk_type == "thinking_summary":
                                    payload["thinking_type"] = "summary"
                                yield sse_event(payload)
                            else:
                                full_text_parts.append(delta)
                                if not answer_started:
                                    answer_started = True
                                    yield sse_event({"type": "meta", "phase": "answer_start", "t": int(time.time() * 1000), "turn_id": turn_id})
                                yield sse_event({"type": "token", "delta": delta, "model": model_key})
                        elif xml_parser:
                            # Use XML parser for Opus
                            thinking, content = xml_parser.process_token(chunk_data)
                            if thinking:
                                full_thinking_parts.append(thinking)
                                yield sse_event({"type": "thinking", "delta": thinking, "model": model_key})
                            if content:
                                full_text_parts.append(content)
                                if not answer_started:
                                    answer_started = True
                                    yield sse_event({"type": "meta", "phase": "answer_start", "t": int(time.time() * 1000), "turn_id": turn_id})
                                yield sse_event({"type": "token", "delta": content, "model": model_key})
                        else:
                            full_text_parts.append(chunk_data)
                            if not answer_started:
                                answer_started = True
                                yield sse_event({"type": "meta", "phase": "answer_start", "t": int(time.time() * 1000), "turn_id": turn_id})
                            yield sse_event({"type": "token", "delta": chunk_data, "model": model_key})
                    
                    # Flush XML parser if used
                    if xml_parser:
                        thinking, content = xml_parser.flush()
                        if thinking:
                            full_thinking_parts.append(thinking)
                            yield sse_event({"type": "thinking", "delta": thinking, "model": model_key})
                        if content:
                            full_text_parts.append(content)
                            if not answer_started:
                                answer_started = True
                                yield sse_event({"type": "meta", "phase": "answer_start", "t": int(time.time() * 1000), "turn_id": turn_id})
                            yield sse_event({"type": "token", "delta": content, "model": model_key})
                
                elif model_key == "gemini":
                    gemini_api_model = get_api_model_name(gemini_model_id)
                    
                    # NEW: Enable extended thinking for Gemini 2.x Pro/Flash and 3.x models
                    thinking_mode_param = None
                    # Check if model supports thinking - use BOTH canonical id and api model name
                    model_str = f"{gemini_model_id} {gemini_api_model}".lower()
                    supports_thinking = (
                        "2.5" in model_str or
                        "2.0" in model_str or
                        "gemini-3" in model_str or
                        ("3-" in model_str and ("flash" in model_str or "pro" in model_str))
                    )
                    is_flash = "flash" in model_str
                    is_pro = ("pro" in model_str) and not is_flash
                    normalized_level = (reasoning_level or "").strip().lower()

                    if supports_thinking:
                        if is_flash:
                            if normalized_level == "none":
                                thinking_mode_param = None  # Completely disabled
                            elif normalized_level == "minimal":
                                thinking_mode_param = "minimal"
                            elif normalized_level == "low":
                                thinking_mode_param = "low"
                            else:
                                # Flash tende a entregar "thoughts" apenas em níveis altos.
                                thinking_mode_param = "high"
                        elif is_pro:
                            thinking_mode_param = "low" if normalized_level == "low" else "high"
                        else:
                            thinking_mode_param = "high"
                    
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
                            if chunk_type in ("thinking", "thinking_summary"):
                                full_thinking_parts.append(delta)
                                payload = {"type": "thinking", "delta": delta, "model": model_key}
                                if chunk_type == "thinking_summary":
                                    payload["thinking_type"] = "summary"
                                yield sse_event(payload)
                            else:  # text
                                full_text_parts.append(delta)
                                if not answer_started:
                                    answer_started = True
                                    yield sse_event({"type": "meta", "phase": "answer_start", "t": int(time.time() * 1000), "turn_id": turn_id})
                                yield sse_event({"type": "token", "delta": delta, "model": model_key})
                        else:
                            # Retrocompatibilidade: string simples
                            full_text_parts.append(chunk_data)
                            if not answer_started:
                                answer_started = True
                                yield sse_event({"type": "meta", "phase": "answer_start", "t": int(time.time() * 1000), "turn_id": turn_id})
                            yield sse_event({"type": "token", "delta": chunk_data, "model": model_key})

                elif model_key == "internal":
                    internal_api_model = get_api_model_name(internal_model_id)
                    internal_system = build_internal_rag_system_instruction(system_instruction)
                    internal_prompt = build_internal_rag_prompt(clean_content)

                    thinking_mode_param = None
                    model_str = f"{internal_model_id} {internal_api_model}".lower()
                    supports_thinking = (
                        "2.5" in model_str
                        or "2.0" in model_str
                        or "gemini-3" in model_str
                        or ("3-" in model_str and ("flash" in model_str or "pro" in model_str))
                    )
                    if supports_thinking:
                        normalized_level = (reasoning_level or "").strip().lower()
                        if normalized_level == "none":
                            thinking_mode_param = None  # Completely disabled
                        elif normalized_level == "minimal":
                            thinking_mode_param = "minimal"
                        elif normalized_level == "low":
                            thinking_mode_param = "low"
                        else:
                            thinking_mode_param = "high"

                    logger.info(
                        f"🧠 [Internal RAG] model={internal_api_model}, id={internal_model_id}, "
                        f"supports={supports_thinking}, mode={thinking_mode_param}"
                    )

                    with billing_context(node="internal_rag_agent", size="M"):
                        async for chunk_data in stream_vertex_gemini_async(
                            gemini_client,
                            internal_prompt,
                            model=internal_api_model,
                            max_tokens=max_tokens,
                            temperature=temperature,
                            system_instruction=internal_system,
                            thinking_mode=thinking_mode_param,
                        ):
                            if isinstance(chunk_data, tuple):
                                chunk_type, delta = chunk_data
                                if chunk_type in ("thinking", "thinking_summary"):
                                    full_thinking_parts.append(delta)
                                    payload = {"type": "thinking", "delta": delta, "model": model_key}
                                    if chunk_type == "thinking_summary":
                                        payload["thinking_type"] = "summary"
                                    yield sse_event(payload)
                                else:
                                    full_text_parts.append(delta)
                                    if not answer_started:
                                        answer_started = True
                                        yield sse_event({"type": "meta", "phase": "answer_start", "t": int(time.time() * 1000), "turn_id": turn_id})
                                    yield sse_event({"type": "token", "delta": delta, "model": model_key})
                            else:
                                full_text_parts.append(chunk_data)
                                if not answer_started:
                                    answer_started = True
                                    yield sse_event({"type": "meta", "phase": "answer_start", "t": int(time.time() * 1000), "turn_id": turn_id})
                                yield sse_event({"type": "token", "delta": chunk_data, "model": model_key})

                if len(target_models) > 1 and idx < len(target_models) - 1:
                    separator = "\n\n---\n\n"
                    full_text_parts.append(separator)
                    if not answer_started:
                        answer_started = True
                        yield sse_event({"type": "meta", "phase": "answer_start", "t": int(time.time() * 1000), "turn_id": turn_id})
                    yield sse_event({"type": "token", "delta": separator})

            full_text = "".join(full_text_parts)
            # Padroniza: sempre preferir anexar referências no final usando o schema unificado de citações.
            # Não confiar no LLM para escrever a seção "Fontes:" corretamente.
            if sources and not citations_by_url:
                _merge_citations(sources_to_citations(sources))

            usage_model_id = DEFAULT_JUDGE_MODEL
            if len(target_models) == 1:
                if target_models[0] == "gpt":
                    usage_model_id = gpt_model_id
                elif target_models[0] == "claude":
                    usage_model_id = claude_model_id
                elif target_models[0] == "gemini":
                    usage_model_id = gemini_model_id
                elif target_models[0] == "perplexity":
                    usage_model_id = perplexity_model_id
                elif target_models[0] == "internal":
                    usage_model_id = internal_model_id
            usage_label = model_label or usage_model_id
            token_usage = _estimate_token_usage(
                f"{system_instruction}\n\n{clean_content}",
                full_text,
                usage_model_id,
                usage_label
            )

            final_metadata = {"turn_id": turn_id, "request_id": request_id, "token_usage": token_usage}
            if mentions_meta:
                final_metadata["mentions"] = mentions_meta
            if model_label:
                final_metadata["model"] = model_label
            citations_payload = list(citations_by_url.values())
            if citations_payload:
                final_metadata["citations"] = citations_payload

            if citations_payload:
                full_text = append_references_section(full_text, citations_payload, heading="References")
            # Referências dos autos/anexos (citações forenses) — seção separada no final.
            full_text = append_autos_references_section(full_text, attachment_docs=attachment_docs)
            actual_points = get_points_total()
            billing_snapshot = {
                "estimated_points": int(quote.estimated_points),
                "estimated_usd": float(quote.estimated_usd),
                "actual_points": int(actual_points),
                "actual_usd": float(actual_points) * float(usd_per_point),
                "usd_per_point": float(usd_per_point),
            }
            final_metadata["billing"] = billing_snapshot

            # NEW: Use real accumulated thinking if available, otherwise fallback to static summary
            full_thinking = "".join(full_thinking_parts).strip() if full_thinking_parts else ""

            thinking_summary = ""
            if thinking_enabled:
                if not full_thinking:
                    # Fallback to static summary if no real thinking was captured
                    thinking_summary = _build_safe_thinking_summary(
                        dense_research=bool(effective_dense_research),
                        web_search=bool(web_search),
                        used_context=bool(system_context or mentions_meta or rag_context or graph_context),
                        used_outline=bool(outline_items)
                    ) or ""
                else:
                    thinking_summary = full_thinking

                # NEW: If no thinking deltas were streamed, emit the summary as a streamed delta
                if not full_thinking_parts and thinking_summary:
                    for chunk in chunk_text(thinking_summary):
                        payload = {"type": "thinking", "delta": chunk, "thinking_type": "summary"}
                        if model_label:
                            payload["model"] = model_label
                        yield sse_event(payload)
                        await asyncio.sleep(0)

            history_payload = conversation_history_full + [
                {"role": "user", "content": message_in.content},
                {"role": "assistant", "content": full_text},
            ]
            if _maybe_update_conversation_summary(chat, history_payload):
                flag_modified(chat, "context")
            await _store_rag_memory(chat_id, history_payload)

            final_metadata["thinking_enabled"] = thinking_enabled

            ai_msg = ChatMessage(
                id=str(uuid.uuid4()),
                chat_id=chat_id,
                role="assistant",
                content=full_text,
                thinking=thinking_summary if thinking_enabled else None,
                msg_metadata=final_metadata if final_metadata else {},
                created_at=utcnow()
            )
            db.add(ai_msg)
            chat.updated_at = utcnow()
            await db.commit()

            # Activity: Mark thinking as done
            if thinking_enabled:
                yield sse_activity_event(
                    turn_id=turn_id,
                    op="done",
                    step_id="thinking",
                    title="Processo de raciocínio",
                    status="done",
                )
            # Activity: Mark call as done
            yield sse_activity_event(
                turn_id=turn_id,
                op="done",
                step_id="call",
                title=f"Chamando {model_label_display}",
                status="done",
            )
            
            yield sse_event({
                "type": "done",
                "full_text": full_text,
                "model": model_label,
                "message_id": ai_msg.id,
                "turn_id": turn_id,
                "request_id": request_id,
                "token_usage": token_usage,
                "thinking": thinking_summary if thinking_enabled else None,
                "thinking_enabled": thinking_enabled,
                "citations": citations_payload,
                "billing": billing_snapshot,
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
                thinking="Erro de conexão com LLM" if thinking_enabled else None,
                msg_metadata={
                    "model": "offline",
                    "turn_id": turn_id,
                    "request_id": request_id,
                    "token_usage": offline_usage,
                    "thinking_enabled": thinking_enabled,
                },
                created_at=utcnow()
            )
            history_payload = conversation_history_full + [
                {"role": "user", "content": message_in.content},
                {"role": "assistant", "content": fallback_text},
            ]
            if _maybe_update_conversation_summary(chat, history_payload):
                flag_modified(chat, "context")
            await _store_rag_memory(chat_id, history_payload)
            db.add(ai_msg)
            chat.updated_at = utcnow()
            await db.commit()
            for chunk in chunk_text(fallback_text):
                if not answer_started:
                    answer_started = True
                    yield sse_event({"type": "meta", "phase": "answer_start", "t": int(time.time() * 1000), "turn_id": turn_id})
                yield sse_event({"type": "token", "delta": chunk, "model": "offline", "turn_id": turn_id})
                await asyncio.sleep(0)
            yield sse_event({
                "type": "done",
                "full_text": fallback_text,
                "model": "offline",
                "message_id": ai_msg.id,
                "turn_id": turn_id,
                "request_id": request_id,
                "token_usage": offline_usage,
                "thinking_enabled": thinking_enabled,
            })

    async def event_generator():
        nonlocal first_token_t

        def _extract_payload(raw_event: Any) -> Optional[Dict[str, Any]]:
            if not isinstance(raw_event, str):
                return None
            if not raw_event.startswith("data:"):
                return None
            line = raw_event.split("\n", 1)[0]
            payload = line.replace("data:", "", 1).strip()
            if not payload or payload == "[DONE]":
                return None
            try:
                return json.loads(payload)
            except Exception:
                return None

        with usage_context("chat", chat_id, user_id=current_user.id, turn_id=turn_id):
            with billing_context(
                graph_rag_enabled=bool(effective_graph_rag_enabled),
                argument_graph_enabled=effective_argument_graph_enabled,
            ):
                with points_counter_context():
                    last_billing_emit = time.monotonic()
                    last_points_total = 0
                    async for event in stream_response():
                        if first_token_t is None and preprocess_done_t is not None:
                            payload = _extract_payload(event)
                            if payload and payload.get("type") in ("token", "thinking"):
                                first_token_t = time.perf_counter()
                                pre_ms = int((preprocess_done_t - request_t0) * 1000)
                                ttft_ms = int((first_token_t - preprocess_done_t) * 1000)
                                total_ms = int((first_token_t - request_t0) * 1000)
                                logger.info(
                                    "TTFT chat_stream chat_id={} turn_id={} model={} pre_ms={} ttft_ms={} total_ms={} event={}",
                                    chat_id,
                                    turn_id,
                                    payload.get("model") or "-",
                                    pre_ms,
                                    ttft_ms,
                                    total_ms,
                                    payload.get("type"),
                                )
                        yield event
                        now = time.monotonic()
                        if now - last_billing_emit >= 1.0:
                            current_points = get_points_total()
                            if current_points != last_points_total:
                                last_points_total = int(current_points)
                                yield sse_event(
                                    {
                                        "type": "billing_update",
                                        "billing": {
                                            "actual_points": int(current_points),
                                            "estimated_points": int(getattr(quote, "estimated_points", 0) or 0),
                                            "approved_points": int(message_budget or 0),
                                            "usd_per_point": float(usd_per_point),
                                        },
                                        "turn_id": turn_id,
                                    },
                                    event="billing",
                                )
                            last_billing_emit = now

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Nginx anti-buffering
        },
    )


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
    doc_kind = getattr(request, "doc_kind", None) or chat.context.get("doc_kind")
    doc_subtype = getattr(request, "doc_subtype", None) or chat.context.get("doc_subtype")
    document_type = request.document_type or doc_subtype or chat.context.get("document_type") or "PETICAO"
    doc_subtype = doc_subtype or document_type
    if not doc_kind and doc_subtype:
        try:
            from app.services.ai.nodes.catalogo_documentos import infer_doc_kind_subtype
            doc_kind, _ = infer_doc_kind_subtype(doc_subtype)
        except Exception:
            doc_kind = None
    thesis = request.thesis or chat.context.get("thesis") or ""
    turn_id = str(uuid.uuid4())
    graph_rag_enabled = bool(chat.context.get("graph_rag_enabled"))
    argument_graph_enabled = chat.context.get("argument_graph_enabled")

    with usage_context("chat", chat_id, user_id=current_user.id, turn_id=turn_id):
        with billing_context(
            graph_rag_enabled=graph_rag_enabled,
            argument_graph_enabled=argument_graph_enabled,
        ):
            outline_state = await outline_node({
                "mode": document_type,
                "doc_kind": doc_kind,
                "doc_subtype": doc_subtype,
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

    turn_id = str(uuid.uuid4())
    plan_key = resolve_plan_key(getattr(current_user, "plan", None))
        
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

        deep_effort, deep_multiplier = resolve_deep_research_billing(plan_key, getattr(request, "deep_research_effort", None))
        effective_dense_research = bool(getattr(request, "dense_research", False)) and bool(deep_effort)
        if effective_dense_research and deep_effort:
            status = await get_deep_research_monthly_status(
                db,
                user_id=str(current_user.id),
                plan_key=plan_key,
            )
            if not status.get("allowed", True):
                deep_effort = None
                deep_multiplier = 1.0
                effective_dense_research = False

        max_web_search_requests = get_plan_cap(plan_key, "max_web_search_requests", default=5)
        effective_web_search = bool(getattr(request, "web_search", False))
        if max_web_search_requests is not None and max_web_search_requests <= 0:
            effective_web_search = False

        # --- Poe-like billing: quote + gates (wallet + per-message/workflow budget) ---
        min_pages = int(getattr(request, "min_pages", 0) or 0)
        max_pages = int(getattr(request, "max_pages", 0) or 0)
        if min_pages < 0:
            min_pages = 0
        if max_pages < 0:
            max_pages = 0
        if min_pages and max_pages and max_pages < min_pages:
            max_pages = min_pages
        if min_pages or max_pages:
            target_pages = (min_pages + max_pages) // 2 if (min_pages and max_pages) else max(min_pages, max_pages)
        else:
            target_pages = int(getattr(request, "effort_level", 0) or 0) * 3

        billing_context_json = ""
        try:
            ctx_payload = getattr(request, "context", None)
            if isinstance(ctx_payload, dict) and ctx_payload:
                billing_context_json = json.dumps(ctx_payload, ensure_ascii=False, default=str)
                if len(billing_context_json) > 100_000:
                    billing_context_json = billing_context_json[:100_000]
        except Exception:
            billing_context_json = ""

        billing_context_text = "\n\n".join(
            part
            for part in [
                str(getattr(request, "prompt", "") or ""),
                str(getattr(request, "prompt_extra", "") or ""),
                str(getattr(request, "thesis", "") or ""),
                str(chat.context.get("conversation_summary") or ""),
                billing_context_json,
            ]
            if part
        ).strip()
        context_tokens_est = token_service.estimate_tokens(billing_context_text) if billing_context_text else 0

        points_base, billing_breakdown = estimate_langgraph_job_points(
            prompt=str(getattr(request, "prompt", "") or ""),
            context_tokens=int(context_tokens_est or 0),
            model_ids=[
                judge_model,
                gpt_model,
                claude_model,
                strategist_model or "",
                *(drafter_models or []),
                *(reviewer_models or []),
            ],
            use_multi_agent=bool(getattr(request, "use_multi_agent", False)),
            drafter_models=drafter_models or [],
            reviewer_models=reviewer_models or [],
            hyde_enabled=bool(getattr(request, "hyde_enabled", False)),
            web_search=bool(effective_web_search),
            multi_query=bool(getattr(request, "multi_query", True)),
            max_web_search_requests=max_web_search_requests,
            dense_research=bool(effective_dense_research),
            deep_research_effort=deep_effort,
            deep_research_points_multiplier=float(deep_multiplier),
            target_pages=int(target_pages or 0),
            max_style_loops=int(get_plan_cap(plan_key, "max_style_loops", default=2) or 0),
            max_final_review_loops=int(get_plan_cap(plan_key, "max_final_review_loops", default=2) or 0),
            max_granular_passes=int(get_plan_cap(plan_key, "max_granular_passes", default=2) or 0),
        )

        points_summary = await get_points_summary(
            db,
            user_id=str(current_user.id),
            plan_key=plan_key,
        )
        points_available = points_summary.get("available_points")
        wallet_points_balance = int(points_available) if isinstance(points_available, int) else 10**12
        budget_override = getattr(request, "budget_override_points", None)
        try:
            budget_override = int(budget_override) if budget_override is not None else None
        except (TypeError, ValueError):
            budget_override = None
        message_budget = budget_override or resolve_chat_max_points_per_message(chat.context)
        usd_per_point = get_usd_per_point()
        quote = poe_quote_message(
            estimator=FixedPointsEstimator(usd_per_point=usd_per_point, breakdown=billing_breakdown),
            req={"points_estimate": int(points_base)},
            wallet_points_balance=int(wallet_points_balance),
            chat_max_points_per_message=int(message_budget),
            usd_per_point=usd_per_point,
        )
        if not quote.ok:
            status_code = 400
            if quote.error == "insufficient_balance":
                status_code = 402
            elif quote.error == "message_budget_exceeded":
                status_code = 409
            raise HTTPException(status_code=status_code, detail=asdict(quote))

        approved_budget_points = int(message_budget)
        estimated_budget_points = int(quote.estimated_points)

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
        
        doc_kind = getattr(request, "doc_kind", None) or chat.context.get("doc_kind")
        doc_subtype = getattr(request, "doc_subtype", None) or chat.context.get("doc_subtype")
        if not doc_subtype:
            doc_subtype = request.document_type or chat.context.get("document_type")
        if not doc_kind and doc_subtype:
            try:
                from app.services.ai.nodes.catalogo_documentos import infer_doc_kind_subtype
                doc_kind, _ = infer_doc_kind_subtype(doc_subtype)
            except Exception:
                doc_kind = None

        citation_style = (getattr(request, "citation_style", "forense") or "forense").lower()
        if chat.mode == ChatMode.MINUTA:
            citation_style = "abnt"

        rag_mode = getattr(request, "rag_mode", None)
        if not rag_mode and isinstance(getattr(request, "context", None), dict):
            rag_mode = request.context.get("rag_mode")
        if not rag_mode:
            rag_mode = chat.context.get("rag_mode")
        rag_mode = str(rag_mode or "manual").strip().lower()
        if rag_mode not in ("auto", "manual"):
            rag_mode = "manual"

        argument_graph_enabled = getattr(request, "argument_graph_enabled", None)
        if argument_graph_enabled is None and isinstance(getattr(request, "context", None), dict):
            argument_graph_enabled = request.context.get("argument_graph_enabled")
        if argument_graph_enabled is None:
            argument_graph_enabled = chat.context.get("argument_graph_enabled")

        effective_graph_rag_enabled = bool(getattr(request, "graph_rag_enabled", False) or chat.context.get("graph_rag_enabled"))
        effective_argument_graph_enabled = argument_graph_enabled
        effective_graph_hops = int(getattr(request, "graph_hops", 1) or 1)
        if rag_mode == "auto":
            try:
                from app.services.ai.rag_router import decide_rag_route_hybrid
                allow_argument = os.getenv("ARGUMENT_RAG_ENABLED", "true").lower() in ("1", "true", "yes", "on")
                router_roles = [str(getattr(current_user, "role", "") or "")] if getattr(current_user, "role", None) else []
                router_groups = chat.context.get("rag_groups") if isinstance(chat.context, dict) else None
                if isinstance(router_groups, str):
                    router_groups = [g.strip() for g in router_groups.split(",") if g.strip()]
                if not isinstance(router_groups, list):
                    router_groups = []
                decision = await decide_rag_route_hybrid(
                    request.prompt,
                    rag_mode="auto",
                    graph_hops=effective_graph_hops,
                    allow_graph=True,
                    allow_argument=allow_argument,
                    risk_mode="high",
                    roles=router_roles,
                    groups=router_groups,
                )
                effective_graph_rag_enabled = decision.graph_rag_enabled
                effective_argument_graph_enabled = decision.argument_graph_enabled
                effective_graph_hops = decision.graph_hops
                trace_event(
                    "rag_router_decision",
                    {
                        "mode": "minuta_generate",
                        "rag_mode": rag_mode,
                        "used_llm": bool(getattr(decision, "used_llm", False)),
                        "llm_confidence": getattr(decision, "llm_confidence", None),
                        "llm_provider": getattr(decision, "llm_provider", None),
                        "llm_model": getattr(decision, "llm_model", None),
                        "llm_thinking_level": getattr(decision, "llm_thinking_level", None),
                        "llm_schema_enforced": getattr(decision, "llm_schema_enforced", None),
                        "ambiguous": getattr(decision, "ambiguous", None),
                        "ambiguous_reason": getattr(decision, "ambiguous_reason", None),
                        "signals": getattr(decision, "signals", None),
                        "reasons": list(getattr(decision, "reasons", []) or []),
                        "graph_rag_requested": bool(getattr(request, "graph_rag_enabled", False)),
                        "argument_graph_requested": getattr(request, "argument_graph_enabled", None),
                        "graph_rag_enabled": bool(effective_graph_rag_enabled),
                        "argument_graph_enabled": effective_argument_graph_enabled,
                        "graph_hops": int(effective_graph_hops),
                        "query": str(request.prompt or "")[:180],
                    },
                    request_id=f"{chat_id}:{turn_id}",
                    user_id=str(current_user.id),
                    tenant_id=str(current_user.id),
                    conversation_id=chat_id,
                )
            except Exception as exc:
                logger.warning(f"RAG router failed (ignored): {exc}")

        doc_request = DocGenRequest(
            prompt=request.prompt,
            document_type=doc_subtype or request.document_type,
            doc_kind=doc_kind,
            doc_subtype=doc_subtype,
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
            temperature=request.temperature,
            web_search=request.web_search,
            search_mode=request.search_mode,
            perplexity_search_mode=request.perplexity_search_mode,
            perplexity_search_type=request.perplexity_search_type,
            perplexity_search_context_size=request.perplexity_search_context_size,
            perplexity_search_classifier=request.perplexity_search_classifier,
            perplexity_disable_search=request.perplexity_disable_search,
            perplexity_stream_mode=request.perplexity_stream_mode,
            perplexity_search_domain_filter=request.perplexity_search_domain_filter,
            perplexity_search_language_filter=request.perplexity_search_language_filter,
            perplexity_search_recency_filter=request.perplexity_search_recency_filter,
            perplexity_search_after_date=request.perplexity_search_after_date,
            perplexity_search_before_date=request.perplexity_search_before_date,
            perplexity_last_updated_after=request.perplexity_last_updated_after,
            perplexity_last_updated_before=request.perplexity_last_updated_before,
            perplexity_search_max_results=request.perplexity_search_max_results,
            perplexity_search_max_tokens=request.perplexity_search_max_tokens,
            perplexity_search_max_tokens_per_page=request.perplexity_search_max_tokens_per_page,
            perplexity_search_country=request.perplexity_search_country,
            perplexity_search_region=request.perplexity_search_region,
            perplexity_search_city=request.perplexity_search_city,
            perplexity_search_latitude=request.perplexity_search_latitude,
            perplexity_search_longitude=request.perplexity_search_longitude,
            perplexity_return_images=request.perplexity_return_images,
            perplexity_return_videos=request.perplexity_return_videos,
            multi_query=request.multi_query,
            breadth_first=request.breadth_first,
            research_policy=request.research_policy,
            dense_research=request.dense_research,
            deep_research_effort=request.deep_research_effort,
            deep_research_search_focus=request.deep_research_search_focus,
            deep_research_domain_filter=request.deep_research_domain_filter,
            deep_research_search_after_date=request.deep_research_search_after_date,
            deep_research_search_before_date=request.deep_research_search_before_date,
            deep_research_last_updated_after=request.deep_research_last_updated_after,
            deep_research_last_updated_before=request.deep_research_last_updated_before,
            deep_research_country=request.deep_research_country,
            deep_research_latitude=request.deep_research_latitude,
            deep_research_longitude=request.deep_research_longitude,
            thesis=thesis,
            citation_style=citation_style,
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
            graph_rag_enabled=bool(effective_graph_rag_enabled),
            graph_hops=int(effective_graph_hops),
            destino=request.destino,
            risco=request.risco,
            hil_outline_enabled=request.hil_outline_enabled,
            hil_target_sections=request.hil_target_sections,
            outline_override=getattr(request, "outline_override", None) or [],
        )

        context_data = {}
        if isinstance(chat.context, dict):
            context_data.update(chat.context)
        if isinstance(getattr(request, "context", None), dict):
            context_data.update(request.context)
        context_data["rag_mode"] = rag_mode
        context_data["argument_graph_enabled"] = effective_argument_graph_enabled
        context_data["budget_approved_points"] = approved_budget_points
        context_data["budget_estimate_points"] = estimated_budget_points

        with usage_context("chat", chat_id, user_id=current_user.id, turn_id=turn_id):
            with billing_context(
                graph_rag_enabled=bool(effective_graph_rag_enabled),
                argument_graph_enabled=effective_argument_graph_enabled,
                budget_approved_points=approved_budget_points,
                budget_estimate_points=estimated_budget_points,
            ):
                result = await get_document_generator().generate_document(
                    request=doc_request,
                    user=current_user,
                    db=db,
                    context_data=context_data
                )
        
        return GenerateDocumentResponse(
            content=result.content,
            metrics=jsonable_encoder(getattr(result, "cost_info", {}) or {})
        )
        
    except HTTPException as http_exc:
        # Re-raise HTTP exceptions (like 400, 402, 409 from billing)
        # so frontend can handle them properly (e.g. show billing modal)
        raise http_exc
    except Exception as e:
        # Simulação de Fallback Robusta
        # OBS: em Python 3 o nome da exceção (`e`) é limpo ao sair do bloco `except`.
        # Então, qualquer uso posterior precisa copiar o erro para uma variável normal.
        fallback_error = str(e)
        print(f"Erro no DocumentGenerator (juridico_gemini): {fallback_error}. Usando Fallback.")
        
        final_content = f"""# DEBUG ERROR INFO
{fallback_error}

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
                "fallback_error": fallback_error,
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
            "fallback_error": fallback_error,
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
    turn_id = str(uuid.uuid4())
    
    async def event_generator():
        final_text = None
        try:
            with usage_context("chat", chat_id, user_id=current_user.id, turn_id=turn_id):
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
