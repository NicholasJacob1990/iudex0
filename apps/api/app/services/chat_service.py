"""
Chat Service for Multi-Model Chat (Sider/Poe Style)

Manages:
1. Thread persistence (SQLite)
2. Message history
3. Model orchestration (dispatching to GPT, Claude, etc.)
"""

import sqlite3
import json
import logging
import uuid
import asyncio
import html as html_lib
import re
import os
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Literal, Generator, AsyncGenerator
from functools import lru_cache
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from app.services.ai.agent_clients import (
    get_gpt_client,
    get_claude_client,
    get_gemini_client,
    get_xai_client,
    get_openrouter_client,
    build_system_instruction
)
from app.services.ai.gemini_drafter import GeminiDrafterWrapper
from app.services.ai.debate_subgraph import run_debate_for_section
from app.services.web_search_service import web_search_service, build_web_context, is_breadth_first
from app.services.rag.pipeline_adapter import build_rag_context_unified as build_rag_context
from app.services.rag_trace import trace_event
from app.services.ai.internal_rag_agent import (
    build_internal_rag_system_instruction,
    build_internal_rag_prompt,
)
from app.services.ai.agent_clients import (
    call_openai_async,
    call_anthropic_async,
    call_vertex_gemini_async,
    stream_vertex_gemini_async,
)
from app.services.ai.citations import extract_perplexity
from app.services.ai.perplexity_config import (
    build_perplexity_chat_kwargs,
    normalize_perplexity_search_mode,
    normalize_perplexity_recency,
    normalize_perplexity_date,
    parse_csv_list,
    normalize_float,
)
from app.services.ai.citations.base import render_perplexity, stable_numbering, sources_to_citations
from app.services.ai.research_policy import decide_research_flags
from app.services.ai.deep_research_service import deep_research_service
from app.services.web_rag_service import web_rag_service
from app.services.ai.agent_clients import _is_anthropic_vertex_client
from app.services.ai.genai_utils import extract_genai_text
from app.services.ai.prompt_flags import apply_verbosity_instruction, clamp_thinking_budget
from app.services.model_registry import get_model_config as get_budget_model_config
from app.services.token_budget_service import TokenBudgetService
from app.services.api_call_tracker import record_api_call, billing_context

logger = logging.getLogger("ChatService")

from app.services.ai.engineering_pipeline import run_engineering_pipeline

token_budget_service = TokenBudgetService()


@lru_cache(maxsize=1)
def get_document_generator():
    from app.services.document_generator import DocumentGenerator
    return DocumentGenerator()


def _normalize_text(value: Optional[str]) -> str:
    if not value:
        return ""
    text = str(value)
    text = re.sub(r"<\s*br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</\s*(p|div|li|tr|h[1-6])\s*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = html_lib.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _find_all_occurrences(haystack: str, needle: str) -> List[int]:
    if not haystack or not needle:
        return []
    indices = []
    start = 0
    while True:
        idx = haystack.find(needle, start)
        if idx == -1:
            break
        indices.append(idx)
        start = idx + 1
    return indices


def _common_suffix_len(a: str, b: str) -> int:
    i = 0
    max_len = min(len(a), len(b))
    while i < max_len and a[-(i + 1)] == b[-(i + 1)]:
        i += 1
    return i


HISTORY_BUFFER_TOKENS = 1000
HISTORY_DEFAULT_MAX_OUTPUT = 4096


def _estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, int(len(text) / 3.5))


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


def _pick_smallest_context_model(model_ids: List[str]) -> str:
    selected = model_ids[0]
    min_ctx = get_budget_model_config(selected).get("context_window", 0)
    for model_id in model_ids[1:]:
        ctx = get_budget_model_config(model_id).get("context_window", 0)
        if min_ctx <= 0 or (ctx > 0 and ctx < min_ctx):
            selected = model_id
            min_ctx = ctx
    return selected


def _should_use_precise_budget(model_id: str) -> bool:
    provider = (get_budget_model_config(model_id) or {}).get("provider") or ""
    return provider in ("vertex", "google")


def _join_context_parts(*parts: Optional[str]) -> str:
    filtered = [part for part in parts if part]
    return "\n\n".join(filtered).strip()


def _redact_prompt(text: str, max_len: int = 2000) -> str:
    if not text:
        return ""
    redacted = re.sub(r"(?i)(api[_-]?key|secret|token)\s*[:=]\s*\S+", r"\1=[REDACTED]", text)
    return redacted if len(redacted) <= max_len else redacted[: max_len - 3] + "..."


def _estimate_attachment_stats(docs: List[Any]) -> tuple[int, int]:
    total_tokens = 0
    total_chars = 0
    for doc in docs:
        text = (getattr(doc, "extracted_text", "") or "").strip()
        if not text:
            continue
        total_chars += len(text)
        total_tokens += token_budget_service.estimate_tokens(text)
    return total_tokens, total_chars


def _estimate_available_tokens(model_id: str, prompt: str, base_context: str) -> int:
    config = get_budget_model_config(model_id) or {}
    limit = config.get("context_window", 0)
    max_output = config.get("max_output", HISTORY_DEFAULT_MAX_OUTPUT)
    if limit <= 0:
        return 0
    buffer = 1000
    base_tokens = token_budget_service.estimate_tokens(base_context)
    prompt_tokens = token_budget_service.estimate_tokens(prompt)
    return limit - base_tokens - prompt_tokens - max_output - buffer


def _format_history_block(history: List[Dict[str, str]]) -> str:
    lines: List[str] = []
    for item in history[-12:]:
        role = str(item.get("role") or "").strip().lower() or "user"
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        label = "Usuário" if role == "user" else "Assistente"
        lines.append(f"{label}: {content}")
    return "\n".join(lines).strip()


def _trim_history_to_budget(history: List[Dict[str, str]], max_tokens: int) -> List[Dict[str, str]]:
    if max_tokens <= 0 or not history:
        return []
    total = 0
    trimmed: List[Dict[str, str]] = []
    for item in reversed(history):
        role = str(item.get("role") or "").strip().lower() or "user"
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        item_tokens = _estimate_tokens(f"{role}: {content}")
        if total + item_tokens > max_tokens and trimmed:
            break
        if total + item_tokens > max_tokens and not trimmed:
            continue
        trimmed.append(item)
        total += item_tokens
    return list(reversed(trimmed))


def _trim_history_for_models(
    history: List[Dict[str, str]],
    model_ids: List[str],
    system_instruction: str,
    user_message: str
) -> List[Dict[str, str]]:
    context_window, max_output = _get_min_context_window(model_ids)
    if context_window <= 0:
        return history[-12:]

    base_tokens = _estimate_tokens(system_instruction) + _estimate_tokens(user_message)
    available = context_window - max_output - HISTORY_BUFFER_TOKENS - base_tokens
    return _trim_history_to_budget(history, max(0, available))


def _common_prefix_len(a: str, b: str) -> int:
    i = 0
    max_len = min(len(a), len(b))
    while i < max_len and a[i] == b[i]:
        i += 1
    return i


def _should_use_fast_judge(user_message: str, candidates: List[Dict[str, Any]]) -> bool:
    total_chars = len(user_message or "")
    for c in candidates:
        total_chars += len((c or {}).get("text") or "")
    if len(candidates) <= 2 and total_chars < 1800:
        return True
    if len(user_message.split()) < 40 and total_chars < 2800:
        return True
    return False


def _judge_model_priority(user_message: str, candidates: List[Dict[str, Any]]) -> List[str]:
    preferred = os.getenv("JUDGE_MODEL_ID", "gemini-3-flash").strip() or "gemini-3-flash"
    fast = os.getenv("JUDGE_FAST_MODEL_ID", "gemini-3-flash").strip() or "gemini-3-flash"
    primary = fast if _should_use_fast_judge(user_message, candidates) else preferred

    fallback_env = os.getenv(
        "JUDGE_FALLBACK_MODELS",
        "gpt-5-mini,claude-4.5-sonnet,gemini-3-flash"
    )
    fallbacks = [m.strip() for m in fallback_env.split(",") if m.strip()]

    order = [primary]
    if preferred not in order:
        order.append(preferred)
    for model_id in fallbacks:
        if model_id not in order:
            order.append(model_id)
    return order

# --- DATA MODELS ---

class ChatMessage(BaseModel):
    id: str
    role: Literal["user", "assistant", "system"]
    content: str
    model: Optional[str] = None  # "gpt-4o", "claude-3.5", etc.
    created_at: str

class ChatThread(BaseModel):
    id: str
    title: str
    messages: List[ChatMessage]
    created_at: str
    updated_at: str

# --- THREAD MANAGER ---

class ThreadManager:
    def __init__(self, db_path: str = "chat.db"):
        base_dir = Path(__file__).parent.parent.parent / "data"
        base_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = str(base_dir / db_path)
        self._init_db()

    def _init_db(self):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Threads Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS threads (
                    id TEXT PRIMARY KEY,
                    title TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
            """)
            
            # Messages Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    thread_id TEXT,
                    role TEXT,
                    content TEXT,
                    model TEXT,
                    created_at TEXT,
                    FOREIGN KEY(thread_id) REFERENCES threads(id)
                )
            """)
            
            conn.commit()
            conn.close()
            logger.info(f"✅ ChatService DB initialized at {self.db_path}")
        except Exception as e:
            logger.error(f"❌ Failed to init ChatService DB: {e}")

    def create_thread(self, title: str = "Nova Conversa") -> ChatThread:
        thread_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO threads (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (thread_id, title, now, now)
            )
            conn.commit()
            conn.close()
            
            return ChatThread(id=thread_id, title=title, messages=[], created_at=now, updated_at=now)
        except Exception as e:
            logger.error(f"❌ Error creating thread: {e}")
            raise e

    def get_thread(self, thread_id: str) -> Optional[ChatThread]:
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Get Thread
            cursor.execute("SELECT * FROM threads WHERE id = ?", (thread_id,))
            thread_row = cursor.fetchone()
            if not thread_row:
                return None

            # Get Messages
            cursor.execute(
                "SELECT * FROM messages WHERE thread_id = ? ORDER BY created_at ASC",
                (thread_id,),
            )
            msg_rows = cursor.fetchall()

            messages = []
            for row in msg_rows:
                messages.append(
                    ChatMessage(
                        id=row["id"],
                        role=row["role"],
                        content=row["content"],
                        model=row["model"],
                        created_at=row["created_at"],
                    )
                )

            return ChatThread(
                id=thread_row["id"],
                title=thread_row["title"],
                messages=messages,
                created_at=thread_row["created_at"],
                updated_at=thread_row["updated_at"],
            )
        except Exception as e:
            logger.error(f"❌ Error getting thread {thread_id}: {e}")
            return None
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    def add_message(self, thread_id: str, role: str, content: str, model: Optional[str] = None) -> ChatMessage:
        msg_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Insert Message
            cursor.execute(
                "INSERT INTO messages (id, thread_id, role, content, model, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (msg_id, thread_id, role, content, model, now)
            )
            
            # Update Thread Timestamp
            cursor.execute("UPDATE threads SET updated_at = ? WHERE id = ?", (now, thread_id))
            
            conn.commit()
            conn.close()
            
            return ChatMessage(id=msg_id, role=role, content=content, model=model, created_at=now)
        except Exception as e:
            logger.error(f"❌ Error adding message to thread {thread_id}: {e}")
            raise e

    def list_threads(self, limit: int = 50) -> List[Dict[str, Any]]:
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("SELECT * FROM threads ORDER BY updated_at DESC LIMIT ?", (limit,))
            rows = cursor.fetchall()
            conn.close()
            
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"❌ Error listing threads: {e}")
            return []


# --- CHAT ORCHESTRATOR ---

class ChatOrchestrator:
    def __init__(self):
        self.thread_manager = ThreadManager()

    async def consolidate_turn(
        self,
        thread_id: str,
        user_message: str,
        candidates: List[Dict[str, Any]],
        mode: str = "merge",
    ) -> str:
        """
        Produz uma resposta única a partir de múltiplas respostas (multi-modelo).

        - Usa o histórico do thread para contexto.
        - Salva a resposta consolidada no thread com model="consolidado".
        """
        thread = self.thread_manager.get_thread(thread_id)
        if not thread:
            raise ValueError("Thread not found")

        # Normaliza candidatos
        cleaned = []
        for c in (candidates or []):
            model = (c or {}).get("model") or "modelo"
            text = (c or {}).get("text") or ""
            text = str(text).strip()
            if text:
                cleaned.append({"model": str(model), "text": text})

        if not cleaned:
            raise ValueError("No candidates to consolidate")

        mode_norm = (mode or "merge").strip().lower()
        if mode_norm == "debate":
            try:
                gpt_client = get_gpt_client()
                claude_client = get_claude_client()
                drafter = GeminiDrafterWrapper()

                candidates_block = "\n\n".join([f"### {c['model']}\n{c['text']}" for c in cleaned])
                prompt_base = (
                    "Você é um comitê de juristas. Sua tarefa é produzir UMA resposta final em português, "
                    "clara e correta, consolidando o melhor conteúdo das respostas candidatas.\n\n"
                    "Regras:\n"
                    "- Não invente fatos.\n"
                    "- Se houver divergência, explique e escolha a opção mais segura.\n"
                    "- Preserve definições, requisitos e fundamentos, e organize a resposta.\n"
                    "- Se houver lacunas, sinalize como pendente.\n\n"
                    f"Pergunta do usuário:\n{user_message}\n\n"
                    f"Respostas candidatas:\n{candidates_block}\n"
                )

                result = await run_debate_for_section(
                    section_title="Consolidação (Chat)",
                    section_index=0,
                    prompt_base=prompt_base,
                    rag_context="",
                    thesis=user_message,
                    mode="chat_consolidate",
                    gpt_client=gpt_client,
                    claude_client=claude_client,
                    drafter=drafter,
                    temperature=0.2,
                )
                merged_text = (result or {}).get("merged_content") or (result or {}).get("merged") or ""
                merged_text = str(merged_text or "").strip()
                if merged_text:
                    self.thread_manager.add_message(thread_id, "assistant", merged_text, model="consolidado")
                    return merged_text
            except Exception as e:
                logger.error(f"Deep debate consolidate failed: {e}")
                # Fall back to standard merge path below.

        # Histórico compartilhado (como no dispatch_turn), mas sem tags de modelo
        history = [{"role": m.role, "content": m.content} for m in thread.messages]

        system = (
            "Você é um JUIZ/CONSOLIDADOR. Sua tarefa é produzir UMA resposta final em português, "
            "clara e correta, combinando o melhor das respostas fornecidas por diferentes modelos.\n\n"
            "Regras:\n"
            "- Não invente fatos. Se houver divergência, explique e escolha a opção mais segura.\n"
            "- Evite contradições com o contexto do chat.\n"
            "- Mantenha concisão. Use Markdown quando útil.\n"
            "- Se houver lacunas de informação, sinalize como pendente.\n"
        )

        candidates_block = "\n\n".join(
            [f"### {c['model']}\n{c['text']}" for c in cleaned]
        )

        judge_user = (
            f"Pergunta do usuário:\n{user_message}\n\n"
            f"Respostas dos modelos (para consolidar):\n{candidates_block}\n\n"
            "Entregue apenas a resposta final consolidada (sem prefácio)."
        )

        merged_text: Optional[str] = None

        from app.services.ai.model_registry import get_api_model_name, get_model_config

        def _infer_provider(model_id: str) -> str:
            cfg = get_model_config(model_id)
            if cfg:
                return cfg.provider
            mid = (model_id or "").lower()
            if "claude" in mid:
                return "anthropic"
            if "gemini" in mid:
                return "google"
            if "gpt" in mid:
                return "openai"
            return ""

        judge_order = _judge_model_priority(user_message, cleaned)
        for model_id in judge_order:
            provider = _infer_provider(model_id)
            if provider == "openai":
                try:
                    client = get_gpt_client()
                    if not client:
                        continue
                    provider_name = "vertex-openai" if hasattr(getattr(client, "models", None), "generate_content") else "openai"
                    api_model = get_api_model_name(model_id) or model_id
                    resp = client.chat.completions.create(
                        model=api_model,
                        messages=[
                            {"role": "system", "content": system},
                            *history,
                            {"role": "user", "content": judge_user},
                        ],
                    )
                    merged_text = (resp.choices[0].message.content or "").strip()
                    record_api_call(
                        kind="llm",
                        provider=provider_name,
                        model=api_model,
                        success=True,
                    )
                except Exception as e:
                    record_api_call(
                        kind="llm",
                        provider="vertex-openai" if "provider_name" in locals() and provider_name == "vertex-openai" else "openai",
                        model=get_api_model_name(model_id) or model_id,
                        success=False,
                    )
                    logger.error(f"Consolidate via {model_id} failed: {e}")
            elif provider == "anthropic":
                try:
                    client = get_claude_client()
                    if not client:
                        continue
                    provider_name = "vertex-anthropic" if _is_anthropic_vertex_client(client) else "anthropic"
                    api_model = get_api_model_name(model_id) or model_id
                    resp = client.messages.create(
                        model=api_model,
                        max_tokens=2048,
                        system=system,
                        messages=[*history, {"role": "user", "content": judge_user}],
                    )
                    if hasattr(resp, "content") and resp.content:
                        merged_text = "".join([getattr(b, "text", "") for b in resp.content]).strip()
                    record_api_call(
                        kind="llm",
                        provider=provider_name,
                        model=api_model,
                        success=True,
                    )
                except Exception as e:
                    record_api_call(
                        kind="llm",
                        provider=provider_name if "provider_name" in locals() else "anthropic",
                        model=get_api_model_name(model_id) or model_id,
                        success=False,
                    )
                    logger.error(f"Consolidate via {model_id} failed: {e}")
            elif provider == "google":
                try:
                    client = get_gemini_client()
                    if not client:
                        continue
                    api_model = get_api_model_name(model_id) or model_id
                    resp = client.models.generate_content(
                        model=api_model,
                        contents=f"{system}\n\n{judge_user}",
                    )
                    merged_text = extract_genai_text(resp)
                    record_api_call(
                        kind="llm",
                        provider="vertex-gemini",
                        model=api_model,
                        success=True,
                    )
                except Exception as e:
                    record_api_call(
                        kind="llm",
                        provider="vertex-gemini",
                        model=get_api_model_name(model_id) or model_id,
                        success=False,
                    )
                    logger.error(f"Consolidate via {model_id} failed: {e}")

            if merged_text:
                break

        if not merged_text:
            raise RuntimeError("No LLM client available to consolidate")

        self.thread_manager.add_message(thread_id, "assistant", merged_text, model="consolidado")
        return merged_text

    async def dispatch_document_edit(
        self,
        thread_id: str,
        user_message: str,
        document_context: str,
        selection: Optional[str] = None,
        models: Optional[List[str]] = None,
        selection_start: Optional[int] = None,
        selection_end: Optional[int] = None,
        selection_context_before: Optional[str] = None,
        selection_context_after: Optional[str] = None,
        log_thread: bool = True,
        use_debate: bool = False,
        mode: str = "committee" # New parameter
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        v5.4: Document-aware editing.
        Supports modes: "committee", "fast", "debate", "engineering".
        """
        is_fast_mode = models and len(models) == 1
        
        # Determine effective mode
        if mode == "engineering":
            mode_label = "Engineering Pipeline (Agentic)"
        elif use_debate:
            mode_label = "Deep Debate (4-Round)"
        elif is_fast_mode:
            mode_label = f"Fast ({models[0]})"
        else:
            mode_label = "Comitê (1-Round)"

        logger.info(f"📝 Document edit [{mode_label}]: {user_message[:50]}...")
        
        # Save user message (multi-chat threads only)
        if log_thread:
            self.thread_manager.add_message(thread_id, "user", f"[EDIÇÃO] {user_message}")
        
        # Prepare context (with surrounding text if possible)
        target_text = selection if selection else document_context[:5000]
        context_window = ""

        if selection and document_context:
            try:
                plain_doc = _normalize_text(document_context)
                plain_selection = _normalize_text(selection)
                plain_before = _normalize_text(selection_context_before)
                plain_after = _normalize_text(selection_context_after)

                start_idx = None
                if (
                    selection_start is not None
                    and selection_end is not None
                    and 0 <= selection_start < selection_end <= len(plain_doc)
                    and plain_doc[selection_start:selection_end] == plain_selection
                ):
                    start_idx = selection_start

                if start_idx is None and plain_doc and plain_selection:
                    candidates = _find_all_occurrences(plain_doc, plain_selection)
                    if candidates:
                        if plain_before or plain_after:
                            selection_len = len(plain_selection)
                            best_score = -1
                            best_idx = candidates[0]
                            for idx in candidates:
                                before_slice = plain_doc[max(0, idx - len(plain_before)):idx]
                                after_slice = plain_doc[
                                    idx + selection_len: idx + selection_len + len(plain_after)
                                ]
                                score = 0
                                if plain_before:
                                    score += _common_suffix_len(before_slice.lower(), plain_before.lower())
                                if plain_after:
                                    score += _common_prefix_len(after_slice.lower(), plain_after.lower())
                                if score > best_score:
                                    best_score = score
                                    best_idx = idx
                            start_idx = best_idx
                        else:
                            start_idx = candidates[0]

                if start_idx is not None:
                    selection_len = len(plain_selection)
                    pre_ctx = plain_doc[max(0, start_idx - 500):start_idx]
                    post_ctx = plain_doc[
                        start_idx + selection_len: min(len(plain_doc), start_idx + selection_len + 500)
                    ]
                    context_window = (
                        "\n## CONTEXTO (Para referência, NÃO EDITE):\n"
                        f"...{pre_ctx} [[TRECHO ALVO]] {post_ctx}..."
                    )
            except Exception as e:
                logger.warning(f"Context extraction failed: {e}")

        
        edit_prompt = f"""## COMANDO DE EDIÇÃO DO USUÁRIO
{user_message}

## TEXTO A EDITAR (ALVO):
{target_text}
{context_window}

## INSTRUÇÕES:
1. Aplique a edição solicitada APENAS no 'TEXTO A EDITAR'.
2. Use o CONTEXTO apenas para garantir coerência (tom, terminologia).
3. Preserve formatação Markdown.
4. Retorne APENAS o texto editado final, sem explicações.
"""
        
        # === ENGINEERING MODE (New) ===
        if mode == "engineering":
            yield {"type": "status", "message": "Iniciando Engineering Pipeline (Planner -> Executor -> Reviewer)..."}
            
            try:
                gpt_client = get_gpt_client()
                claude_client = get_claude_client()
                gemini_client = get_gemini_client() # Used as client, not drafter wrapper
                
                # Context combining target + window
                file_context = f"Target Text:\n{target_text}\n\nContext:\n{context_window}"
                
                result = await run_engineering_pipeline(
                    user_message,
                    file_context,
                    gemini_client,
                    gpt_client,
                    claude_client
                )
                
                final_text = result.get("final_output") or target_text
                plan = result.get("plan")
                
                yield {"type": "agent_response", "agent": "Planner (Gemini)", "text": f"Plan:\n{plan}"[:500]}
                yield {"type": "agent_response", "agent": "Executor (GPT)", "text": "Code generated."}
                
                if result.get("decision") == "APPROVE":
                    yield {"type": "status", "message": "Reviewer (Claude) aprovou o código."}
                else:
                     yield {"type": "status", "message": f"Reviewer final: {result.get('decision')} (Feedback: {result.get('feedback', '')[:100]}...)"}

                yield {
                    "type": "edit_complete",
                    "original": target_text,
                    "edited": final_text,
                    "agents_used": ["Gemini-Planner", "GPT-Executor", "Claude-Reviewer"]
                }
                return

            except Exception as e:
                logger.error(f"Engineering pipeline failed: {e}")
                yield {"type": "error", "error": f"Engineering fail: {e}"}
                return

        
        # === MULTI-ROUND DEBATE MODE ===
        if not is_fast_mode and use_debate:
            yield {"type": "status", "message": "Iniciando debate profundo (4 rodadas)..."}

            try:
                # Clients
                gpt_client = get_gpt_client()
                claude_client = get_claude_client()
                drafter = GeminiDrafterWrapper()

                result = await run_debate_for_section(
                    section_title="Solicitação de Edição",
                    section_index=0,
                    prompt_base=edit_prompt,
                    rag_context=context_window,  # Use context window as RAG context equivalent
                    thesis=user_message,
                    mode="edicao_especifica",  # Custom mode
                    gpt_client=gpt_client,
                    claude_client=claude_client,
                    drafter=drafter,
                    temperature=0.3
                )

                final_text = result.get("merged_content") or target_text
                drafts = result.get("drafts", {})

                # Emit drafts as progress
                if drafts.get("gpt_v1"):
                    yield {"type": "agent_response", "agent": "GPT (Rascunho)", "text": drafts["gpt_v1"][:500]}
                if drafts.get("claude_v1"):
                    yield {"type": "agent_response", "agent": "Claude (Rascunho)", "text": drafts["claude_v1"][:500]}
                if drafts.get("critique_gpt"):
                    yield {"type": "agent_response", "agent": "GPT (Crítica)", "text": drafts["critique_gpt"][:500]}

                # Final result
                yield {
                    "type": "edit_complete",
                    "original": target_text,
                    "edited": final_text,
                    "agents_used": ["GPT-4o", "Claude-3.5", "Gemini-Judge", "DeepDebate"]
                }
                return

            except Exception as e:
                logger.error(f"Deep debate failed: {e}")
                yield {"type": "error", "error": "Falha no debate profundo, revertendo para modo simples."}
                # Fallthrough to normal committee logic
                pass

        # === FAST MODE: Single model ===
        if is_fast_mode:
            model_id = models[0]
            final_text = None
            
            try:
                from app.services.ai.model_registry import get_api_model_name, get_model_config

                model_cfg = get_model_config(model_id)
                provider = model_cfg.provider if model_cfg else None

                if provider == "openai" or "gpt" in model_id.lower():
                    client = get_gpt_client()
                    if client:
                        api_model = get_api_model_name(model_id)
                        provider_name = "vertex-openai" if hasattr(getattr(client, "models", None), "generate_content") else "openai"
                        try:
                            resp = client.chat.completions.create(
                                model=api_model,
                                messages=[{"role": "user", "content": edit_prompt}],
                                max_tokens=4096
                            )
                            record_api_call(
                                kind="llm",
                                provider=provider_name,
                                model=api_model,
                                success=True,
                            )
                            final_text = resp.choices[0].message.content
                        except Exception:
                            record_api_call(
                                kind="llm",
                                provider=provider_name,
                                model=api_model,
                                success=False,
                            )
                            raise

                elif provider == "anthropic" or "claude" in model_id.lower():
                    client = get_claude_client()
                    if client:
                        api_model = get_api_model_name(model_id)
                        provider_name = "vertex-anthropic" if _is_anthropic_vertex_client(client) else "anthropic"
                        try:
                            resp = client.messages.create(
                                model=api_model,
                                max_tokens=4096,
                                messages=[{"role": "user", "content": edit_prompt}]
                            )
                            record_api_call(
                                kind="llm",
                                provider=provider_name,
                                model=api_model,
                                success=True,
                            )
                            final_text = "".join([getattr(b, "text", "") for b in resp.content]).strip()
                        except Exception:
                            record_api_call(
                                kind="llm",
                                provider=provider_name,
                                model=api_model,
                                success=False,
                            )
                            raise

                elif provider == "google" or "gemini" in model_id.lower():
                    client = get_gemini_client()
                    if client:
                        api_model = get_api_model_name(model_id)
                        try:
                            resp = client.models.generate_content(
                                model=api_model,
                                contents=edit_prompt
                            )
                            record_api_call(
                                kind="llm",
                                provider="vertex-gemini",
                                model=api_model,
                                success=True,
                            )
                            final_text = extract_genai_text(resp)
                        except Exception:
                            record_api_call(
                                kind="llm",
                                provider="vertex-gemini",
                                model=api_model,
                                success=False,
                            )
                            raise

                elif provider == "xai" or "grok" in model_id.lower():
                    client = get_xai_client()
                    if client:
                        api_model = get_api_model_name(model_id)
                        try:
                            resp = client.chat.completions.create(
                                model=api_model,
                                messages=[{"role": "user", "content": edit_prompt}],
                                max_tokens=4096
                            )
                            record_api_call(
                                kind="llm",
                                provider="xai",
                                model=api_model,
                                success=True,
                            )
                            final_text = resp.choices[0].message.content
                        except Exception:
                            record_api_call(
                                kind="llm",
                                provider="xai",
                                model=api_model,
                                success=False,
                            )
                            raise

                elif provider in ("openrouter", "deepseek", "meta") or "llama" in model_id.lower():
                    client = get_openrouter_client()
                    if client:
                        api_model = get_api_model_name(model_id)
                        try:
                            resp = client.chat.completions.create(
                                model=api_model,
                                messages=[{"role": "user", "content": edit_prompt}],
                                max_tokens=4096
                            )
                            record_api_call(
                                kind="llm",
                                provider="openrouter",
                                model=api_model,
                                success=True,
                            )
                            final_text = resp.choices[0].message.content
                        except Exception:
                            record_api_call(
                                kind="llm",
                                provider="openrouter",
                                model=api_model,
                                success=False,
                            )
                            raise

            except Exception as e:
                logger.error(f"Fast mode edit failed: {e}")
            
            if not final_text:
                final_text = target_text
            
            if log_thread:
                self.thread_manager.add_message(thread_id, "assistant", final_text, model=model_id)
            
            yield {
                "type": "edit_complete",
                "original": target_text,
                "edited": final_text,
                "agents_used": [model_id]
            }
            return
        
        # === COMMITTEE MODE: GPT + Claude + Gemini Judge ===
        evaluations = {}
        
        async def eval_gpt():
            try:
                client = get_gpt_client()
                if client:
                    from app.services.ai.model_registry import get_api_model_name
                    api_model = get_api_model_name("gpt-5-mini")
                    provider_name = "vertex-openai" if hasattr(getattr(client, "models", None), "generate_content") else "openai"
                    resp = client.chat.completions.create(
                        model=api_model,
                        messages=[{"role": "user", "content": edit_prompt}],
                        max_tokens=4096
                    )
                    record_api_call(
                        kind="llm",
                        provider=provider_name,
                        model=api_model,
                        success=True,
                    )
                    return {"agent": "GPT", "response": resp.choices[0].message.content}
            except Exception as e:
                record_api_call(
                    kind="llm",
                    provider="vertex-openai" if "provider_name" in locals() and provider_name == "vertex-openai" else "openai",
                    model="gpt-5-mini",
                    success=False,
                )
                logger.error(f"GPT edit failed: {e}")
            return {"agent": "GPT", "response": None}
        
        async def eval_claude():
            try:
                client = get_claude_client()
                if client:
                    from app.services.ai.model_registry import get_api_model_name
                    api_model = get_api_model_name("claude-4.5-sonnet")
                    provider_name = "vertex-anthropic" if _is_anthropic_vertex_client(client) else "anthropic"
                    resp = client.messages.create(
                        model=api_model,
                        max_tokens=4096,
                        messages=[{"role": "user", "content": edit_prompt}]
                    )
                    record_api_call(
                        kind="llm",
                        provider=provider_name,
                        model=api_model,
                        success=True,
                    )
                    text = "".join([getattr(b, "text", "") for b in resp.content]).strip()
                    return {"agent": "Claude", "response": text}
            except Exception as e:
                record_api_call(
                    kind="llm",
                    provider=provider_name if "provider_name" in locals() else "anthropic",
                    model="claude-4.5-sonnet",
                    success=False,
                )
                logger.error(f"Claude edit failed: {e}")
            return {"agent": "Claude", "response": None}
        
        # Run in parallel
        import asyncio
        results = await asyncio.gather(eval_gpt(), eval_claude(), return_exceptions=True)
        
        for r in results:
            if r and not isinstance(r, Exception) and r.get("response"):
                evaluations[r["agent"]] = r["response"]
                yield {"type": "agent_response", "agent": r["agent"], "text": r["response"][:500]}
        
        # Gemini Judge consolidates
        judge_prompt = f"""## CONSOLIDAÇÃO DE EDIÇÃO

O usuário pediu: {user_message}

### TEXTO ORIGINAL:
{target_text[:2000]}

### VERSÃO GPT:
{evaluations.get("GPT", "[não disponível]")[:1500]}

### VERSÃO CLAUDE:
{evaluations.get("Claude", "[não disponível]")[:1500]}

## INSTRUÇÕES:
Produza a versão final editada, combinando o melhor de cada versão.
Retorne APENAS o texto final, sem explicações.
"""
        
        final_text = None
        try:
            client = get_gemini_client()
            if client:
                from app.services.ai.model_registry import get_api_model_name
                api_model = get_api_model_name("gemini-3-flash")
                resp = client.models.generate_content(
                    model=api_model,
                    contents=judge_prompt
                )
                record_api_call(
                    kind="llm",
                    provider="vertex-gemini",
                    model=api_model,
                    success=True,
                )
                final_text = extract_genai_text(resp)
        except Exception as e:
            record_api_call(
                kind="llm",
                provider="vertex-gemini",
                model="gemini-3-flash",
                success=False,
            )
            logger.error(f"Gemini judge failed: {e}")
            final_text = evaluations.get("GPT") or evaluations.get("Claude") or target_text
        
        if not final_text:
            final_text = target_text
        
        if log_thread:
            self.thread_manager.add_message(thread_id, "assistant", final_text, model="comitê-edit")
        
        yield {
            "type": "edit_complete",
            "original": target_text,
            "edited": final_text,
            "agents_used": list(evaluations.keys()) + ["Gemini-Judge"]
        }
        


    async def dispatch_turn(
        self,
        thread_id: str,
        user_message: str,
        selected_models: List[str],
        attachment_docs: Optional[List[Any]] = None,
        attachment_mode: str = "auto",
        tenant_id: str = "default",
        chat_personality: str = "juridico",
        reasoning_level: str = "medium",
        verbosity: Optional[str] = None,
        thinking_budget: Optional[int] = None,
        temperature: Optional[float] = None,
        mcp_tool_calling: Optional[bool] = None,
        mcp_server_labels: Optional[List[str]] = None,
        web_search: bool = False,
        multi_query: bool = True,
        breadth_first: bool = False,
        search_mode: str = "hybrid",
        perplexity_search_mode: Optional[str] = None,
        perplexity_search_type: Optional[str] = None,
        perplexity_search_context_size: Optional[str] = None,
        perplexity_search_classifier: bool = False,
        perplexity_disable_search: bool = False,
        perplexity_stream_mode: Optional[str] = None,
        perplexity_search_domain_filter: Optional[object] = None,
        perplexity_search_language_filter: Optional[object] = None,
        perplexity_search_recency_filter: Optional[str] = None,
        perplexity_search_after_date: Optional[str] = None,
        perplexity_search_before_date: Optional[str] = None,
        perplexity_last_updated_after: Optional[str] = None,
        perplexity_last_updated_before: Optional[str] = None,
        perplexity_search_max_results: Optional[int] = None,
        perplexity_search_max_tokens: Optional[int] = None,
        perplexity_search_max_tokens_per_page: Optional[int] = None,
        perplexity_search_country: Optional[str] = None,
        perplexity_search_region: Optional[str] = None,
        perplexity_search_city: Optional[str] = None,
        perplexity_search_latitude: Optional[object] = None,
        perplexity_search_longitude: Optional[object] = None,
        perplexity_return_images: bool = False,
        perplexity_return_videos: bool = False,
        rag_sources: Optional[List[str]] = None,
        rag_top_k: Optional[int] = None,
        adaptive_routing: bool = False,
        crag_gate: bool = False,
        crag_min_best_score: float = 0.45,
        crag_min_avg_score: float = 0.35,
        hyde_enabled: bool = False,
        graph_rag_enabled: bool = False,
        argument_graph_enabled: Optional[bool] = None,
        graph_hops: int = 1,
        dense_research: bool = False,
        rag_scope: str = "case_and_global",  # case_only, case_and_global, global_only
        scope_groups: Optional[List[str]] = None,
        allow_global_scope: Optional[bool] = None,
        allow_group_scope: Optional[bool] = None,
        deep_research_effort: Optional[str] = None,
        deep_research_provider: Optional[str] = None,
        deep_research_model: Optional[str] = None,
        deep_research_search_focus: Optional[str] = None,
        deep_research_domain_filter: Optional[object] = None,
        deep_research_search_after_date: Optional[str] = None,
        deep_research_search_before_date: Optional[str] = None,
        deep_research_last_updated_after: Optional[str] = None,
        deep_research_last_updated_before: Optional[str] = None,
        deep_research_country: Optional[str] = None,
        deep_research_latitude: Optional[object] = None,
        deep_research_longitude: Optional[object] = None,
        deep_research_points_multiplier: Optional[float] = None,
        max_web_search_requests: Optional[int] = None,
        research_policy: str = "auto",
        per_model_overrides: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        1. Save User Message
        2. Stream back responses from selected models in parallel
        3. Save Assistant Messages
        """
        dispatch_t0 = time.perf_counter()
        request_id = f"{thread_id}:{uuid.uuid4().hex}"

        # MCP tool-calling is gated globally by env AND optionally per-request.
        # - If mcp_tool_calling is False: disable even if env is enabled.
        # - If mcp_tool_calling is True/None: enable only when env is enabled.
        try:
            env_mcp_enabled = os.getenv("IUDEX_MCP_TOOL_CALLING", "false").lower() in (
                "1",
                "true",
                "yes",
                "on",
            )
        except Exception:
            env_mcp_enabled = False
        mcp_enabled_for_turn = env_mcp_enabled and (mcp_tool_calling is not False)
        if mcp_enabled_for_turn:
            try:
                from app.services.mcp_hub import mcp_hub

                configured = mcp_hub.list_servers() or []
                configured_labels = {
                    str(s.get("label") or "").strip()
                    for s in configured
                    if isinstance(s, dict)
                }
                configured_labels = {lbl for lbl in configured_labels if lbl}

                requested_labels = [
                    str(x).strip()
                    for x in (mcp_server_labels or [])
                    if str(x).strip()
                ]
                if requested_labels:
                    allowed_server_labels = [lbl for lbl in requested_labels if lbl in configured_labels]
                    mcp_enabled_for_turn = bool(allowed_server_labels)
                else:
                    allowed_server_labels = sorted(configured_labels) if configured_labels else []
                    mcp_enabled_for_turn = bool(allowed_server_labels)
            except Exception:
                allowed_server_labels = []
                mcp_enabled_for_turn = False
        else:
            allowed_server_labels = []
        
        # 1. Save User Message
        self.thread_manager.add_message(thread_id, "user", user_message)
        
        # 2. Get history for context
        thread = self.thread_manager.get_thread(thread_id)
        if not thread:
            yield {"error": "Thread not found"}
            return

        try:
            temperature = float(temperature) if temperature is not None else (
                0.6 if chat_personality == "geral" else 0.3
            )
        except (TypeError, ValueError):
            temperature = 0.6 if chat_personality == "geral" else 0.3
        temperature = max(0.0, min(1.0, temperature))
            
        history = [
            {"role": m.role, "content": m.content} 
            for m in thread.messages
            # Filter out potentially confusing multi-model context if needed, 
            # for now we send everything (shared history view)
        ]
        base_instruction = build_system_instruction(chat_personality)
        system_instruction = base_instruction

        history = _trim_history_for_models(history, selected_models, base_instruction, user_message)
        history_block = _format_history_block(history)

        async def _persist_rag_history_to_redis() -> None:
            """Best-effort: persist compact chat history for RAG memory features (Redis + TTL)."""
            try:
                from app.services.ai.rag_memory_store import RAGMemoryStore
            except Exception:
                return
            try:
                thread_now = self.thread_manager.get_thread(thread_id)
                if not thread_now:
                    return
                payload = [{"role": m.role, "content": m.content} for m in thread_now.messages]
                try:
                    max_items = int(os.getenv("RAG_MEMORY_MAX_ITEMS", "30") or 30)
                except Exception:
                    max_items = 30
                if max_items > 0:
                    payload = payload[-max_items:]
                try:
                    max_chars = int(os.getenv("RAG_MEMORY_MAX_CHARS_PER_MESSAGE", "2000") or 2000)
                except Exception:
                    max_chars = 2000
                if max_chars > 0:
                    for item in payload:
                        content = item.get("content")
                        if isinstance(content, str) and len(content) > max_chars:
                            item["content"] = content[:max_chars]
                await RAGMemoryStore().set_history(thread_id, payload)
            except Exception as exc:
                logger.debug(f"RAG memory persist skipped: {exc}")

        # Fire-and-forget: cache history after receiving the user message.
        asyncio.create_task(_persist_rag_history_to_redis())

        attachment_docs = attachment_docs or []
        attachment_mode = (attachment_mode or "auto").lower()
        if attachment_mode not in ("auto", "rag_local", "prompt_injection"):
            attachment_mode = "auto"

        budget_model_id = _pick_smallest_context_model(selected_models)
        attachment_injection_context = ""
        if attachment_docs:
            if attachment_mode == "prompt_injection":
                attachment_injection_context = get_document_generator()._build_attachment_prompt_context(attachment_docs)
            elif attachment_mode == "auto":
                base_context = _join_context_parts(base_instruction, history_block)
                attachment_tokens, attachment_chars = _estimate_attachment_stats(attachment_docs)
                if attachment_tokens > 0:
                    available_tokens = _estimate_available_tokens(budget_model_id, user_message, base_context)
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
                    attachment_injection_context,
                )
                if _should_use_precise_budget(budget_model_id):
                    budget = await token_budget_service.check_budget_precise(
                        user_message,
                        {"system": budget_context},
                        budget_model_id,
                    )
                else:
                    budget = token_budget_service.check_budget(
                        user_message,
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

        # =====================================================================
        # RAG SCOPE CONTROL
        # rag_scope: case_only | case_and_global | global_only
        # =====================================================================
        rag_scope = (rag_scope or "case_and_global").lower()
        if rag_scope not in ("case_only", "case_and_global", "global_only"):
            rag_scope = "case_and_global"

        # Build local RAG context (case attachments) - skip if global_only
        local_rag_context = ""
        if rag_scope != "global_only" and attachment_mode == "rag_local" and attachment_docs:
            local_query_override: Optional[str] = None
            local_queries: Optional[List[str]] = None
            try:
                from app.services.ai.rag_helpers import (
                    generate_hypothetical_document,
                    generate_multi_queries,
                )
            except Exception:
                generate_hypothetical_document = None
                generate_multi_queries = None

            if hyde_enabled and generate_hypothetical_document:
                try:
                    local_query_override = await generate_hypothetical_document(
                        query=user_message,
                        history=history,
                        summary_text=None,
                    )
                except Exception as exc:
                    logger.warning(f"HyDE local falhou: {exc}")

            if multi_query and generate_multi_queries:
                try:
                    max_q = int(os.getenv("RAG_MULTI_QUERY_MAX", "3") or 3)
                except Exception:
                    max_q = 3
                try:
                    local_queries = await generate_multi_queries(
                        user_message,
                        history=history,
                        summary_text=None,
                        max_queries=max(2, max_q),
                    )
                except Exception as exc:
                    logger.warning(f"Multi-query local falhou: {exc}")

            local_rag_context = get_document_generator()._build_local_rag_context(
                attachment_docs,
                user_message,
                tenant_id=tenant_id,
                queries=local_queries,
                query_override=local_query_override,
                multi_query=bool(multi_query),
                crag_gate=bool(crag_gate),
                graph_rag_enabled=bool(graph_rag_enabled),
                argument_graph_enabled=bool(argument_graph_enabled),
                graph_hops=int(graph_hops or 2),
            )

        effective_sources = rag_sources if rag_sources is not None else ["lei", "juris", "pecas_modelo"]
        research_decision = decide_research_flags(
            user_message,
            bool(web_search),
            bool(dense_research),
            research_policy,
        )
        effective_web_search = bool(research_decision.get("web_search"))
        effective_dense_research = bool(research_decision.get("deep_research")) and bool(deep_research_effort)
        planned_queries = research_decision.get("planned_queries") or []

        # Normalize deep research web-search controls early (used by the deep research branch below).
        deep_search_focus = normalize_perplexity_search_mode(deep_research_search_focus)
        deep_domain_filter = parse_csv_list(deep_research_domain_filter, max_items=20)
        deep_search_after = normalize_perplexity_date(deep_research_search_after_date)
        deep_search_before = normalize_perplexity_date(deep_research_search_before_date)
        deep_updated_after = normalize_perplexity_date(deep_research_last_updated_after)
        deep_updated_before = normalize_perplexity_date(deep_research_last_updated_before)
        deep_country = (deep_research_country or "").strip() or None
        deep_latitude = normalize_float(deep_research_latitude)
        deep_longitude = normalize_float(deep_research_longitude)
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

        # Build global RAG context - skip if case_only
        rag_context = ""
        graph_context = ""
        if rag_scope != "case_only":
            resolved_scope_groups = scope_groups
            if resolved_scope_groups is None:
                raw_groups = os.getenv("RAG_SCOPE_GROUPS", "")
                resolved_scope_groups = [g.strip() for g in raw_groups.split(",") if g.strip()]
            resolved_allow_global_scope = allow_global_scope
            if resolved_allow_global_scope is None:
                resolved_allow_global_scope = os.getenv("RAG_ALLOW_GLOBAL", "false").lower() in ("1", "true", "yes", "on")
            resolved_allow_group_scope = allow_group_scope
            if resolved_allow_group_scope is None:
                resolved_allow_group_scope = True if resolved_scope_groups else False
            rag_context, graph_context, _ = await build_rag_context(
                query=user_message,
                rag_sources=effective_sources,
                rag_top_k=rag_top_k,
                attachment_mode="prompt_injection",
                adaptive_routing=adaptive_routing,
                crag_gate=crag_gate,
                crag_min_best_score=crag_min_best_score,
                crag_min_avg_score=crag_min_avg_score,
                hyde_enabled=hyde_enabled,
                multi_query=bool(multi_query),
                graph_rag_enabled=graph_rag_enabled,
                graph_hops=graph_hops,
                argument_graph_enabled=argument_graph_enabled,
                dense_research=effective_dense_research,
                tenant_id=tenant_id,
                user_id=None,
                scope_groups=resolved_scope_groups,
                allow_global_scope=bool(resolved_allow_global_scope),
                allow_group_scope=bool(resolved_allow_group_scope),
                history=history,
                summary_text=None,
                rewrite_query=len(history) > 1,
                request_id=request_id,
            )

        # Combine contexts based on rag_scope
        if rag_context:
            base_instruction += f"\n\n{rag_context}"
        if graph_context:
            base_instruction += f"\n\n{graph_context}"
        if local_rag_context:
            base_instruction += f"\n\n{local_rag_context}"
        if attachment_injection_context:
            base_instruction += f"\n\n{attachment_injection_context}"
        system_instruction = base_instruction
        if os.getenv("RAG_TRACE_ENABLED", "false").lower() in ("1", "true", "yes", "on"):
            preview = _redact_prompt(system_instruction)
            trace_event(
                "prompt_final",
                {
                    "preview": preview,
                    "length": len(system_instruction),
                    "graph_rag_enabled": graph_rag_enabled,
                    "argument_graph_enabled": argument_graph_enabled,
                },
                request_id=request_id,
                tenant_id=tenant_id,
                conversation_id=thread_id,
            )

        # Collect citations across all research steps/providers for this turn.
        # NOTE: This must be defined before the deep-research branch, since we merge deep research
        # sources into the same final citations payload.
        citations_by_url: Dict[str, Dict[str, Any]] = {}

        def _merge_citations(items: List[Dict[str, Any]]):
            for item in items or []:
                url = str(item.get("url") or "").strip()
                # Use URL as the primary key. Source numbers are not globally unique across providers,
                # so keying by "number" can silently drop citations when merging streams.
                key = url
                if not key:
                    number = item.get("number")
                    key = str(number).strip() if number is not None else ""
                if not key:
                    continue
                if key not in citations_by_url:
                    citations_by_url[key] = item

        if effective_dense_research:
            deep_report = ""
            yield {"type": "research_start", "researchmode": "deep"}
            try:
                deep_sources: List[Dict[str, Any]] = []
                deep_config: Dict[str, Any] = {"effort": deep_research_effort}
                if deep_research_points_multiplier is not None:
                    deep_config["points_multiplier"] = deep_research_points_multiplier
                deep_provider_raw = (deep_research_provider or "").strip().lower()
                if deep_provider_raw in ("pplx", "sonar"):
                    deep_provider_raw = "perplexity"
                if deep_provider_raw in ("gemini",):
                    deep_provider_raw = "google"
                if deep_provider_raw and deep_provider_raw != "auto":
                    deep_config["provider"] = deep_provider_raw
                if deep_research_model:
                    deep_config["model"] = deep_research_model
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

                async for event in deep_research_service.stream_research_task(
                    user_message,
                    config=deep_config,
                ):
                    etype = (event or {}).get("type")
                    if etype == "cache_hit":
                        yield {"type": "cache_hit", "key": event.get("key")}
                    elif etype == "thinking":
                        text = event.get("text") or ""
                        if text:
                            yield {"type": "deepresearch_step", "text": text}
                    elif etype == "content":
                        deep_report += event.get("text") or ""
                    elif etype in ("step.start", "step.add_query", "step.add_source", "step.done"):
                        # Propagate granular step events directly to SSE stream
                        yield event
                    elif etype == "done":
                        sources_raw = event.get("sources") or []
                        if isinstance(sources_raw, list):
                            deep_sources = [s for s in sources_raw if isinstance(s, dict)]
                            if deep_sources:
                                _merge_citations(deep_sources)
                    elif etype == "error":
                        message = event.get("message") or event.get("error") or "Deep research falhou."
                        yield {"type": "research_error", "message": str(message)}
                        # Stop deep research; continue the chat answer with whatever we have.
                        break
            except Exception as exc:
                logger.warning(f"Deep research falhou: {exc}")
                yield {"type": "research_error", "message": str(exc)}

            if deep_report:
                trimmed = deep_report.strip()[:5000]
                system_instruction += "\n\n## PESQUISA PROFUNDA (resumo)\n" + trimmed
            yield {"type": "research_done", "researchmode": "deep"}

        sources = []
        web_search = bool(effective_web_search)
        dense_research = bool(effective_dense_research)
        breadth_first = bool(breadth_first) or (web_search and is_breadth_first(user_message))
        if dense_research:
            multi_query = True
            breadth_first = True
        search_mode = (search_mode or "hybrid").lower()
        if search_mode not in ("shared", "native", "hybrid", "perplexity"):
            search_mode = "hybrid"
        perplexity_search_mode = normalize_perplexity_search_mode(perplexity_search_mode)
        search_domain_filter = parse_csv_list(perplexity_search_domain_filter, max_items=20)
        search_language_filter = parse_csv_list(perplexity_search_language_filter, max_items=10)
        search_recency_filter = normalize_perplexity_recency(perplexity_search_recency_filter)
        search_after_date = normalize_perplexity_date(perplexity_search_after_date)
        search_before_date = normalize_perplexity_date(perplexity_search_before_date)
        last_updated_after = normalize_perplexity_date(perplexity_last_updated_after)
        last_updated_before = normalize_perplexity_date(perplexity_last_updated_before)
        search_country = (perplexity_search_country or "").strip() or None
        search_region = (perplexity_search_region or "").strip() or None
        search_city = (perplexity_search_city or "").strip() or None
        search_latitude = normalize_float(perplexity_search_latitude)
        search_longitude = normalize_float(perplexity_search_longitude)
        return_images = bool(perplexity_return_images)
        return_videos = bool(perplexity_return_videos)
        try:
            search_max_results = int(perplexity_search_max_results) if perplexity_search_max_results else None
        except (TypeError, ValueError):
            search_max_results = None
        if search_max_results is not None and search_max_results <= 0:
            search_max_results = None
        if search_max_results is not None and search_max_results > 20:
            search_max_results = 20
        try:
            search_max_tokens = int(perplexity_search_max_tokens) if perplexity_search_max_tokens else None
        except (TypeError, ValueError):
            search_max_tokens = None
        if search_max_tokens is not None and search_max_tokens <= 0:
            search_max_tokens = None
        if search_max_tokens is not None and search_max_tokens > 1_000_000:
            search_max_tokens = 1_000_000
        try:
            search_max_tokens_per_page = (
                int(perplexity_search_max_tokens_per_page)
                if perplexity_search_max_tokens_per_page
                else None
            )
        except (TypeError, ValueError):
            search_max_tokens_per_page = None
        if search_max_tokens_per_page is not None and search_max_tokens_per_page <= 0:
            search_max_tokens_per_page = None
        if search_max_tokens_per_page is not None and search_max_tokens_per_page > 1_000_000:
            search_max_tokens_per_page = 1_000_000
        deep_search_focus = normalize_perplexity_search_mode(deep_research_search_focus)
        deep_domain_filter = parse_csv_list(deep_research_domain_filter, max_items=20)
        deep_search_after = normalize_perplexity_date(deep_research_search_after_date)
        deep_search_before = normalize_perplexity_date(deep_research_search_before_date)
        deep_updated_after = normalize_perplexity_date(deep_research_last_updated_after)
        deep_updated_before = normalize_perplexity_date(deep_research_last_updated_before)
        deep_country = (deep_research_country or "").strip() or None
        deep_latitude = normalize_float(deep_research_latitude)
        deep_longitude = normalize_float(deep_research_longitude)
        max_sources = search_max_results or 20

        from app.services.ai.model_registry import get_model_config
        gpt_client = get_gpt_client()
        claude_client = get_claude_client()
        gemini_client = get_gemini_client()

        def _supports_native_search(model_id: str) -> bool:
            cfg = get_model_config(model_id)
            provider = cfg.provider if cfg else ""
            if provider == "openai":
                return bool(gpt_client and hasattr(gpt_client, "responses"))
            if provider == "anthropic":
                return bool(claude_client)
            if provider == "google":
                return bool(gemini_client)
            if provider == "perplexity":
                return bool(os.getenv("PERPLEXITY_API_KEY"))
            mid = (model_id or "").lower()
            if "gemini" in mid:
                return bool(gemini_client)
            if "claude" in mid:
                return bool(claude_client)
            if "gpt" in mid:
                return bool(gpt_client and hasattr(gpt_client, "responses"))
            return False

        allow_native_search = web_search and search_mode in ("native", "hybrid")
        allow_shared_search = web_search and search_mode in ("shared", "hybrid", "perplexity")
        use_shared_search = allow_shared_search and (
            search_mode in ("shared", "perplexity")
            or any(not _supports_native_search(model_id) for model_id in selected_models)
        )

        if use_shared_search and web_search:
            search_query = re.sub(
                r'@(?:gpt|claude|gemini|all|todos)\\b',
                '',
                user_message,
                flags=re.IGNORECASE
            ).strip()
            if search_query:
                yield {"type": "search_started", "query": search_query}

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
                    combined: list[dict] = []
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
                yield {
                    "type": "search_done",
                    "query": search_query,
                    "count": len(results),
                    "cached": bool(search_payload.get("cached")),
                    "source": search_payload.get("source"),
                    "queries": search_payload.get("queries") if multi_query else None,
                }
                if search_payload.get("success") and results:
                    url_title_stream = [
                        (res.get("url", ""), res.get("title", ""))
                        for res in results
                    ]
                    url_to_number, sources = stable_numbering(url_title_stream)
                    web_context = build_web_context(search_payload, max_items=max_sources)
                    web_rag_context, web_citations = await web_rag_service.build_web_rag_context(
                        user_message,
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
                        "\n- Cite no texto com [n] e finalize com uma seção 'Fontes:' apenas com as URLs citadas."
                        f"\n\n{web_rag_context or web_context}"
                    )

        async def _call_native_search(
            model_id: str,
            messages: List[Dict[str, str]],
            prompt: str,
            max_tokens: int = 4096,
            temperature: float = 0.3,
            system_instruction_override: Optional[str] = None,
        ) -> tuple[Optional[str], List[dict]]:
            from app.services.ai.model_registry import get_api_model_name, get_model_config

            cfg = get_model_config(model_id)
            provider = cfg.provider if cfg else ""
            api_model = get_api_model_name(model_id) or model_id

            if provider == "openai":
                if not gpt_client or not hasattr(gpt_client, "responses"):
                    return None, []
                try:
                    resp = gpt_client.responses.create(
                        model=api_model,
                        input=messages,
                        tools=[{"type": "web_search"}],
                        temperature=temperature,
                        max_output_tokens=max_tokens,
                    )
                    record_api_call(
                        kind="llm",
                        provider="openai",
                        model=api_model,
                        success=True,
                        meta={"tool": "web_search"},
                    )
                    text, sources = extract_perplexity("openai", resp)
                    citations = sources_to_citations(sources)
                    return text or getattr(resp, "output_text", "") or None, citations
                except Exception as e:
                    record_api_call(
                        kind="llm",
                        provider="openai",
                        model=api_model,
                        success=False,
                        meta={"tool": "web_search"},
                    )
                    logger.error(f"OpenAI web search failed ({model_id}): {e}")
                    return None, []

            if provider == "anthropic":
                if not claude_client:
                    return None, []
                try:
                    kwargs: Dict[str, Any] = {
                        "model": api_model,
                        "max_tokens": max_tokens,
                        "messages": messages,
                        "system": system_instruction_override or base_instruction,
                        "tools": [{"type": "web_search_20250305", "name": "web_search"}],
                    }
                    beta_header = os.getenv("ANTHROPIC_WEB_SEARCH_BETA", "web-search-2025-03-05").strip()
                    if beta_header:
                        kwargs["extra_headers"] = {"anthropic-beta": beta_header}
                    provider_name = "anthropic"
                    if _is_anthropic_vertex_client(claude_client):
                        kwargs["anthropic_version"] = os.getenv("ANTHROPIC_VERTEX_VERSION", "vertex-2023-10-16")
                        provider_name = "vertex-anthropic"
                    resp = claude_client.messages.create(**kwargs)
                    record_api_call(
                        kind="llm",
                        provider=provider_name,
                        model=api_model,
                        success=True,
                        meta={"tool": "web_search"},
                    )
                    text, sources = extract_perplexity("claude", resp)
                    return text or None, sources_to_citations(sources)
                except Exception as e:
                    record_api_call(
                        kind="llm",
                        provider=provider_name if "provider_name" in locals() else "anthropic",
                        model=api_model,
                        success=False,
                        meta={"tool": "web_search"},
                    )
                    logger.error(f"Claude web search failed ({model_id}): {e}")
                    return None, []

            if provider == "google":
                if not gemini_client:
                    return None, []
                try:
                    from google.genai import types as genai_types
                    tool = genai_types.Tool(google_search=genai_types.GoogleSearch())
                    config = genai_types.GenerateContentConfig(
                        system_instruction=base_instruction,
                        tools=[tool],
                        max_output_tokens=max_tokens,
                        temperature=temperature,
                    )
                    resp = gemini_client.models.generate_content(
                        model=api_model,
                        contents=prompt,
                        config=config,
                    )
                    record_api_call(
                        kind="llm",
                        provider="vertex-gemini",
                        model=api_model,
                        success=True,
                        meta={"tool": "web_search"},
                    )
                    text, sources = extract_perplexity("gemini", resp)
                    if not text:
                        text = (resp.text or "").strip() or None
                    return text or None, sources_to_citations(sources)
                except Exception as e:
                    record_api_call(
                        kind="llm",
                        provider="vertex-gemini",
                        model=api_model,
                        success=False,
                        meta={"tool": "web_search"},
                    )
                    logger.error(f"Gemini web search failed ({model_id}): {e}")
                    return None, []

            return None, []
        
        if breadth_first and len(selected_models) == 1:
            from app.services.ai.model_registry import get_api_model_name, get_model_config

            model_id = selected_models[0]
            cfg = get_model_config(model_id)
            provider = cfg.provider if cfg else ""

            async def call_model(prompt: str, tokens: int) -> Optional[str]:
                api_model = get_api_model_name(model_id)
                if allow_native_search and not use_shared_search and _supports_native_search(model_id):
                    if provider == "openai":
                        messages = [
                            {"role": "system", "content": base_instruction},
                            {"role": "user", "content": prompt},
                        ]
                    else:
                        messages = [{"role": "user", "content": prompt}]
                    text, native_citations = await _call_native_search(
                        model_id,
                        messages=messages,
                        prompt=prompt,
                        max_tokens=tokens,
                        temperature=temperature,
                    )
                    if native_citations:
                        _merge_citations(native_citations)
                    return text

                if provider == "openai":
                    # Optional MCP tool-calling (model-driven) via lightweight helper tools.
                    # Enabled only when IUDEX_MCP_SERVERS is configured and IUDEX_MCP_TOOL_CALLING is truthy.
                    if mcp_enabled_for_turn:
                        try:
                            from app.services.ai.mcp_tools import run_openai_tool_loop
                            from app.services.ai.agent_clients import get_async_openai_client

                            async_client = get_async_openai_client()
                            if async_client:
                                text, _tool_trace = await run_openai_tool_loop(
                                    client=async_client,
                                    model=api_model,
                                    system_instruction=system_instruction,
                                    user_prompt=prompt,
                                    max_tokens=tokens,
                                    temperature=temperature,
                                    allowed_server_labels=allowed_server_labels,
                                )
                                return text
                        except Exception as e:
                            logger.warning(f"MCP tool-calling fallback to normal OpenAI call: {e}")
                    return await call_openai_async(
                        gpt_client,
                        prompt,
                        model=api_model,
                        max_tokens=tokens,
                        temperature=temperature,
                        system_instruction=system_instruction,
                    )
                if provider == "anthropic":
                    return await call_anthropic_async(
                        claude_client,
                        prompt,
                        model=api_model,
                        max_tokens=tokens,
                        temperature=temperature,
                        system_instruction=system_instruction,
                    )
                if provider == "google":
                    if mcp_enabled_for_turn:
                        try:
                            from app.services.ai.mcp_tools import run_gemini_tool_loop

                            text, _tool_trace = await run_gemini_tool_loop(
                                client=gemini_client,
                                model=api_model,
                                system_instruction=system_instruction,
                                user_prompt=prompt,
                                max_tokens=tokens,
                                temperature=temperature,
                                allowed_server_labels=allowed_server_labels,
                            )
                            return text
                        except Exception as e:
                            logger.warning(f"MCP tool-calling fallback to normal Gemini call: {e}")
                    return await call_vertex_gemini_async(
                        gemini_client,
                        prompt,
                        model=api_model,
                        max_tokens=tokens,
                        temperature=temperature,
                        system_instruction=system_instruction,
                    )
                return None

            if provider in ("openai", "anthropic", "google"):
                worker_tasks = [
                    ("Fontes", "Liste fatos centrais e evidências relevantes para responder à pergunta."),
                    ("Contrapontos", "Apresente controvérsias ou nuances importantes relacionadas ao tema."),
                    ("Contexto", "Explique conceitos-chave e termos técnicos necessários para entender a resposta."),
                ]
                worker_prompts = [
                    f"{user_message}\n\nTarefa do agente ({title}):\n{task}"
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
                    f"{user_message}\n\n"
                    "Você é o agente líder. Use as notas abaixo para responder de forma objetiva.\n\n"
                    + "\n\n".join(worker_notes)
                )
                lead_text = await call_model(lead_prompt, 1800)
                if not lead_text:
                    lead_text = "Não foi possível gerar resposta no momento."
                if sources and "fontes:" not in lead_text.lower() and not citations_by_url:
                    lead_text = render_perplexity(lead_text, sources)
                if sources and not citations_by_url:
                    _merge_citations(sources_to_citations(sources))

                # Save final message
                self.thread_manager.add_message(thread_id, "assistant", lead_text, model=model_id)

                start_ms = int(time.time() * 1000)
                yield {"type": "meta", "phase": "start", "t": start_ms, "model": model_id}
                yield {"type": "meta", "phase": "answer_start", "t": start_ms, "model": model_id}
                for i in range(0, len(lead_text), 64):
                    yield {"type": "token", "model": model_id, "delta": lead_text[i:i + 64]}
                yield {
                    "type": "done",
                    "model": model_id,
                    "full_text": lead_text,
                    "citations": list(citations_by_url.values()),
                }
                return

        # 3. Parallel Execution Logic
        # We will yield chunks as { "model": "gpt-4o", "delta": "..." }
        dispatch_preprocess_done_t = time.perf_counter()
        ttft_logged: Dict[str, float] = {}

        def _log_model_ttft(model_id: str, event_type: str) -> None:
            if model_id in ttft_logged:
                return
            now = time.perf_counter()
            pre_ms = int((dispatch_preprocess_done_t - dispatch_t0) * 1000)
            ttft_ms = int((now - dispatch_preprocess_done_t) * 1000)
            total_ms = int((now - dispatch_t0) * 1000)
            ttft_logged[model_id] = now
            logger.info(
                "TTFT multi_chat thread_id=%s model=%s pre_ms=%d ttft_ms=%d total_ms=%d event=%s",
                thread_id,
                model_id,
                pre_ms,
                ttft_ms,
                total_ms,
                event_type,
            )

        async def stream_model(model_id: str):
            """Stream wrapper for a single model"""
            full_response = ""
            full_thinking = ""
            used_native_search = False
            answer_started = False

            def _mark_answer_started() -> bool:
                nonlocal answer_started
                if answer_started:
                    return False
                answer_started = True
                _log_model_ttft(model_id, "token")
                return True
            
            try:
                from app.services.ai.model_registry import get_api_model_name, get_model_config, get_thinking_category

                model_cfg = get_model_config(model_id)
                provider = model_cfg.provider if model_cfg else None
                thinking_category = get_thinking_category(model_id)
                model_override = (per_model_overrides or {}).get(model_id) or {}
                override_reasoning = (
                    model_override.get("reasoning_level")
                    if isinstance(model_override, dict)
                    else None
                )
                raw_reasoning = override_reasoning or (reasoning_level or "medium")
                normalized_reasoning = str(raw_reasoning).strip().lower()
                if normalized_reasoning in ("standard",):
                    normalized_reasoning = "medium"
                elif normalized_reasoning in ("extended",):
                    normalized_reasoning = "high"
                elif normalized_reasoning in ("x-high", "x_high", "xh"):
                    normalized_reasoning = "xhigh"
                if normalized_reasoning not in ("none", "minimal", "low", "medium", "high", "xhigh"):
                    normalized_reasoning = "medium"
                override_verbosity = model_override.get("verbosity") if isinstance(model_override, dict) else None
                stream_instruction = apply_verbosity_instruction(
                    system_instruction,
                    override_verbosity or verbosity,
                )
                model_thinking_budget = thinking_budget
                if isinstance(model_override, dict) and "thinking_budget" in model_override:
                    model_thinking_budget = model_override.get("thinking_budget")

                yield {"type": "meta", "phase": "start", "t": int(time.time() * 1000), "model": model_id}

                if allow_native_search and not use_shared_search and _supports_native_search(model_id):
                    native_messages = []
                    if provider == "openai":
                        native_messages = [{"role": "system", "content": stream_instruction}] + history
                    elif provider == "anthropic":
                        native_messages = history

                    native_text, native_citations = await _call_native_search(
                        model_id,
                        messages=native_messages,
                        prompt=user_message,
                        max_tokens=4096,
                        temperature=temperature,
                        system_instruction_override=stream_instruction,
                    )
                    if native_citations:
                        _merge_citations(native_citations)
                    if native_text:
                        full_response = native_text
                        used_native_search = True
                        for i in range(0, len(full_response), 64):
                            if _mark_answer_started():
                                yield {"type": "meta", "phase": "answer_start", "t": int(time.time() * 1000), "model": model_id}
                            yield {
                                "type": "token",
                                "model": model_id,
                                "delta": full_response[i:i + 64],
                            }
                            await asyncio.sleep(0)

                if not used_native_search and model_id == "internal-rag":
                    # Internal RAG Agent (NotebookLM-like) powered by Gemini 3 Flash (Vertex).
                    if not gemini_client:
                        yield {"type": "error", "model": model_id, "error": "Gemini Client unavailable"}
                    else:
                        internal_system = build_internal_rag_system_instruction(stream_instruction)
                        internal_prompt = build_internal_rag_prompt(user_message, history_block=history_block)
                        thinking_mode = None
                        if normalized_reasoning in ("high", "xhigh"):
                            thinking_mode = "high"
                        elif normalized_reasoning == "medium":
                            thinking_mode = "high"
                        elif normalized_reasoning == "low":
                            thinking_mode = "low"
                        elif normalized_reasoning == "minimal":
                            thinking_mode = "minimal"
                        # "none" -> thinking_mode stays None (completely disabled)

                        api_model = get_api_model_name(model_id)
                        with billing_context(node="internal_rag_agent", size="M"):
                            async for chunk_data in stream_vertex_gemini_async(
                                gemini_client,
                                internal_prompt,
                                model=api_model,
                                max_tokens=4096,
                                temperature=temperature,
                                system_instruction=internal_system,
                                thinking_mode=thinking_mode,
                            ):
                                if isinstance(chunk_data, tuple):
                                    chunk_type, delta = chunk_data
                                    if chunk_type in ("thinking", "thinking_summary") and delta:
                                        full_thinking += str(delta)
                                        payload: Dict[str, Any] = {
                                            "type": "thinking",
                                            "model": model_id,
                                            "delta": str(delta),
                                        }
                                        if chunk_type == "thinking_summary":
                                            payload["thinking_type"] = "summary"
                                        yield payload
                                        await asyncio.sleep(0)
                                    elif chunk_type == "text" and delta:
                                        if _mark_answer_started():
                                            yield {
                                                "type": "meta",
                                                "phase": "answer_start",
                                                "t": int(time.time() * 1000),
                                                "model": model_id,
                                            }
                                        full_response += str(delta)
                                        yield {"type": "token", "model": model_id, "delta": str(delta)}
                                        await asyncio.sleep(0)
                                elif chunk_data:
                                    if _mark_answer_started():
                                        yield {
                                            "type": "meta",
                                            "phase": "answer_start",
                                            "t": int(time.time() * 1000),
                                            "model": model_id,
                                        }
                                    full_response += str(chunk_data)
                                    yield {"type": "token", "model": model_id, "delta": str(chunk_data)}
                                    await asyncio.sleep(0)

                elif not used_native_search and provider == "perplexity":
                    perplexity_key = os.getenv("PERPLEXITY_API_KEY")
                    if not perplexity_key:
                        yield {"type": "error", "model": model_id, "error": "PERPLEXITY_API_KEY não configurada"}
                    else:
                        try:
                            from perplexity import AsyncPerplexity
                        except Exception:
                            yield {"type": "error", "model": model_id, "error": "Pacote perplexityai não instalado (pip install perplexityai)"}
                            AsyncPerplexity = None  # type: ignore

                        if AsyncPerplexity:
                            import inspect

                            def _get(obj: Any, key: str, default=None):
                                if isinstance(obj, dict):
                                    return obj.get(key, default)
                                return getattr(obj, key, default)

                            api_model = get_api_model_name(model_id) or model_id
                            messages = [{"role": "system", "content": stream_instruction}] + history
                            client = AsyncPerplexity(api_key=perplexity_key)
                            disable_search_effective = bool(perplexity_disable_search) or bool(use_shared_search)
                            pplx_meta = {
                                "size": "M",
                                "stream": True,
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
                                api_model=api_model,
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
                            seen_citation_keys: set = set()
                            pplx_step_id: str | None = None

                            def _ensure_pplx_step_started():
                                nonlocal pplx_step_id
                                if not pplx_step_id and not disable_search_effective:
                                    pplx_step_id = str(uuid.uuid4())[:8]
                                    return {"type": "step.start", "step_name": "Pesquisando", "step_id": pplx_step_id}
                                return None

                            def _emit_citation(url: str, title: str):
                                nonlocal pplx_step_id
                                citation_key = url or title
                                if citation_key and citation_key not in seen_citation_keys:
                                    seen_citation_keys.add(citation_key)
                                    return {"type": "step.add_source", "step_id": pplx_step_id or "pplx_search", "source": {"url": url, "title": title or url}}
                                return None

                            try:
                                stream_obj = client.chat.completions.create(
                                    model=api_model,
                                    messages=messages,
                                    temperature=temperature,
                                    max_tokens=4096,
                                    stream=True,
                                    **perplexity_kwargs,
                                )
                                record_api_call(
                                    kind="llm",
                                    provider="perplexity",
                                    model=api_model,
                                    success=True,
                                    meta=pplx_meta,
                                )
                            except Exception:
                                record_api_call(
                                    kind="llm",
                                    provider="perplexity",
                                    model=api_model,
                                    success=False,
                                    meta=pplx_meta,
                                )
                                raise
                            if inspect.isawaitable(stream_obj):
                                stream_obj = await stream_obj

                            if hasattr(stream_obj, "__aiter__"):
                                async for chunk in stream_obj:
                                    choices = _get(chunk, "choices", []) or []
                                    if choices:
                                        delta = _get(choices[0], "delta", None) or {}
                                        content = _get(delta, "content", None) or ""
                                        if content:
                                            if _mark_answer_started():
                                                yield {"type": "meta", "phase": "answer_start", "t": int(time.time() * 1000), "model": model_id}
                                            full_response += str(content)
                                            yield {"type": "token", "model": model_id, "delta": str(content)}
                                            await asyncio.sleep(0)

                                    chunk_results = _get(chunk, "search_results", None) or _get(chunk, "searchResults", None)
                                    if isinstance(chunk_results, list) and chunk_results:
                                        # Emit step.start on first citation
                                        start_evt = _ensure_pplx_step_started()
                                        if start_evt:
                                            yield start_evt
                                            await asyncio.sleep(0)
                                        for result in chunk_results:
                                            url = str(_get(result, "url", "") or _get(result, "uri", "") or "").strip()
                                            title = str(_get(result, "title", "") or _get(result, "name", "") or "").strip()
                                            evt = _emit_citation(url, title)
                                            if evt:
                                                yield evt
                                                await asyncio.sleep(0)
                                        search_results.extend(chunk_results)

                                    chunk_citations = _get(chunk, "citations", None)
                                    if isinstance(chunk_citations, list) and chunk_citations:
                                        start_evt = _ensure_pplx_step_started()
                                        if start_evt:
                                            yield start_evt
                                            await asyncio.sleep(0)
                                        for cit in chunk_citations:
                                            if isinstance(cit, str):
                                                evt = _emit_citation(cit.strip(), cit.strip())
                                            else:
                                                url = str(_get(cit, "url", "") or _get(cit, "uri", "") or "").strip()
                                                title = str(_get(cit, "title", "") or _get(cit, "name", "") or "").strip()
                                                evt = _emit_citation(url, title)
                                            if evt:
                                                yield evt
                                                await asyncio.sleep(0)
                                        citation_items.extend(chunk_citations)
                            else:
                                for chunk in stream_obj:
                                    choices = _get(chunk, "choices", []) or []
                                    if choices:
                                        delta = _get(choices[0], "delta", None) or {}
                                        content = _get(delta, "content", None) or ""
                                        if content:
                                            if _mark_answer_started():
                                                yield {"type": "meta", "phase": "answer_start", "t": int(time.time() * 1000), "model": model_id}
                                            full_response += str(content)
                                            yield {"type": "token", "model": model_id, "delta": str(content)}
                                            await asyncio.sleep(0)

                                    chunk_results = _get(chunk, "search_results", None) or _get(chunk, "searchResults", None)
                                    if isinstance(chunk_results, list) and chunk_results:
                                        # Emit step.start on first citation
                                        start_evt = _ensure_pplx_step_started()
                                        if start_evt:
                                            yield start_evt
                                        for result in chunk_results:
                                            url = str(_get(result, "url", "") or _get(result, "uri", "") or "").strip()
                                            title = str(_get(result, "title", "") or _get(result, "name", "") or "").strip()
                                            evt = _emit_citation(url, title)
                                            if evt:
                                                yield evt
                                        search_results.extend(chunk_results)

                                    chunk_citations = _get(chunk, "citations", None)
                                    if isinstance(chunk_citations, list) and chunk_citations:
                                        start_evt = _ensure_pplx_step_started()
                                        if start_evt:
                                            yield start_evt
                                        for cit in chunk_citations:
                                            if isinstance(cit, str):
                                                evt = _emit_citation(cit.strip(), cit.strip())
                                            else:
                                                url = str(_get(cit, "url", "") or _get(cit, "uri", "") or "").strip()
                                                title = str(_get(cit, "title", "") or _get(cit, "name", "") or "").strip()
                                                evt = _emit_citation(url, title)
                                            if evt:
                                                yield evt
                                        citation_items.extend(chunk_citations)

                            # Emit step.done if we started a search step
                            if pplx_step_id:
                                yield {"type": "step.done", "step_id": pplx_step_id}

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

                elif not used_native_search and (
                    provider in ("openai", "xai", "openrouter", "deepseek", "meta")
                    or any(token in model_id.lower() for token in ("gpt", "grok", "llama"))
                ):
                    client = None
                    if provider == "xai" or "grok" in model_id.lower():
                        client = get_xai_client()
                    elif provider in ("openrouter", "deepseek", "meta") or "llama" in model_id.lower():
                        client = get_openrouter_client()
                    else:
                        client = gpt_client

                    if client:
                        api_model = get_api_model_name(model_id)
                        messages = [{"role": "system", "content": stream_instruction}] + history

                        # Optional MCP tool-calling (OpenAI only for now): execute tool loop (non-stream)
                        # and stream the final text as SSE tokens.
                        # This gives *any* OpenAI model access to configured MCP servers via:
                        #   - mcp_tool_search(query, server_labels?, limit?)
                        #   - mcp_tool_call(server_label, tool_name, arguments)
                        if mcp_enabled_for_turn:
                            try:
                                from app.services.ai.agent_clients import (
                                    get_async_openai_client,
                                    get_async_openrouter_client,
                                    get_async_xai_client,
                                )
                                from app.services.ai.mcp_tools import run_openai_tool_loop

                                async_client = None
                                if provider == "xai" or "grok" in model_id.lower():
                                    async_client = get_async_xai_client()
                                elif provider in ("openrouter", "deepseek", "meta") or "llama" in model_id.lower():
                                    async_client = get_async_openrouter_client()
                                else:
                                    async_client = get_async_openai_client()

                                if async_client:
                                    tool_step_id = f"mcp_{model_id}"
                                    yield {
                                        "type": "step.start",
                                        "step_name": "MCP tools",
                                        "step_id": tool_step_id,
                                        "model": model_id,
                                    }
                                    await asyncio.sleep(0)
                                    text, tool_trace = await run_openai_tool_loop(
                                        client=async_client,
                                        model=api_model,
                                        system_instruction=stream_instruction,
                                        user_prompt=user_message,
                                        max_tokens=4096,
                                        temperature=temperature,
                                        allowed_server_labels=allowed_server_labels,
                                    )
                                    for item in tool_trace:
                                        yield {
                                            "type": "tool_call",
                                            "model": model_id,
                                            "step_id": tool_step_id,
                                            "name": item.get("name"),
                                            "arguments": item.get("arguments"),
                                            "result_preview": item.get("result_preview"),
                                        }
                                        await asyncio.sleep(0)
                                    yield {
                                        "type": "step.done",
                                        "step_id": tool_step_id,
                                        "model": model_id,
                                    }
                                    await asyncio.sleep(0)

                                    if _mark_answer_started():
                                        yield {
                                            "type": "meta",
                                            "phase": "answer_start",
                                            "t": int(time.time() * 1000),
                                            "model": model_id,
                                        }
                                    full_response += text
                                    chunk_size = 64
                                    for i in range(0, len(text), chunk_size):
                                        yield {
                                            "type": "token",
                                            "model": model_id,
                                            "delta": text[i : i + chunk_size],
                                        }
                                        await asyncio.sleep(0)
                                    # Save final message and finish this model stream.
                                    self.thread_manager.add_message(
                                        thread_id, "assistant", full_response, model=model_id
                                    )
                                    yield {
                                        "type": "done",
                                        "model": model_id,
                                        "full_text": full_response,
                                        "thinking": full_thinking or None,
                                        "citations": list(citations_by_url.values()),
                                    }
                                    return
                            except Exception as e:
                                logger.warning(f"MCP tool-calling disabled for {model_id}: {e}")

                        # Prefer Responses API for OpenAI provider so we can stream reasoning summaries when available.
                        used_responses_stream = False
                        if provider == "openai" and hasattr(client, "responses"):
                            try:
                                reasoning_arg = None
                                effort = normalized_reasoning
                                if effort and effort != "none":
                                    if effort == "minimal":
                                        effort = "low"
                                    if effort == "xhigh":
                                        effort = "high"
                                    reasoning_arg = {"effort": effort, "summary": "auto"}

                                req_kwargs = {
                                    "model": api_model,
                                    "input": messages,
                                    "max_output_tokens": 4096,
                                    "temperature": temperature,
                                    "stream": True,
                                }
                                if reasoning_arg is not None:
                                    req_kwargs["reasoning"] = reasoning_arg

                                stream = client.responses.create(**req_kwargs)
                                record_api_call(
                                    kind="llm",
                                    provider="openai",
                                    model=api_model,
                                    success=True,
                                    meta={"stream": True, "api": "responses"},
                                )
                                used_responses_stream = True
                                openai_search_step_active = False
                                for ev in stream:
                                    ev_type = getattr(ev, "type", "") or ""
                                    if ev_type == "response.reasoning_summary_text.delta":
                                        delta = getattr(ev, "delta", None)
                                        if delta:
                                            full_thinking += str(delta)
                                            yield {"type": "thinking", "model": model_id, "delta": str(delta)}
                                            await asyncio.sleep(0)
                                    elif ev_type == "response.output_text.delta":
                                        delta = getattr(ev, "delta", None)
                                        if delta:
                                            if _mark_answer_started():
                                                yield {"type": "meta", "phase": "answer_start", "t": int(time.time() * 1000), "model": model_id}
                                            full_response += str(delta)
                                            yield {"type": "token", "model": model_id, "delta": str(delta)}
                                            await asyncio.sleep(0)
                                    # Handle web search progress events
                                    elif ev_type == "response.web_search_call.in_progress":
                                        if not openai_search_step_active:
                                            openai_search_step_active = True
                                            yield {"type": "step.start", "step_name": "Pesquisando na web", "step_id": "openai_web_search"}
                                            await asyncio.sleep(0)
                                    elif ev_type == "response.web_search_call.completed":
                                        if openai_search_step_active:
                                            yield {"type": "step.done", "step_id": "openai_web_search"}
                                            openai_search_step_active = False
                                            await asyncio.sleep(0)
                                    # Handle file search progress events
                                    elif ev_type == "response.file_search_call.in_progress":
                                        yield {"type": "step.start", "step_name": "Buscando em arquivos", "step_id": "openai_file_search"}
                                        await asyncio.sleep(0)
                                    elif ev_type == "response.file_search_call.completed":
                                        yield {"type": "step.done", "step_id": "openai_file_search"}
                                        await asyncio.sleep(0)
                            except Exception as e:
                                record_api_call(
                                    kind="llm",
                                    provider="openai",
                                    model=api_model,
                                    success=False,
                                    meta={"stream": True, "api": "responses"},
                                )
                                used_responses_stream = False
                                logger.warning(f"OpenAI Responses streaming failed for {api_model}: {e}")

                        if not used_responses_stream:
                            provider_name = "openai"
                            if provider == "xai" or "grok" in model_id.lower():
                                provider_name = "xai"
                            elif provider in ("openrouter", "deepseek", "meta") or "llama" in model_id.lower():
                                provider_name = "openrouter"
                            try:
                                stream = client.chat.completions.create(
                                    model=api_model,
                                    messages=messages,
                                    temperature=temperature,
                                    stream=True
                                )
                                record_api_call(
                                    kind="llm",
                                    provider=provider_name,
                                    model=api_model,
                                    success=True,
                                    meta={"stream": True},
                                )
                            except Exception:
                                record_api_call(
                                    kind="llm",
                                    provider=provider_name,
                                    model=api_model,
                                    success=False,
                                    meta={"stream": True},
                                )
                                raise
                            for chunk in stream:
                                delta = getattr(chunk.choices[0], "delta", None)
                                if delta is None:
                                    continue

                                reasoning_delta = getattr(delta, "reasoning_content", None)
                                if reasoning_delta:
                                    full_thinking += str(reasoning_delta)
                                    yield {
                                        "type": "thinking",
                                        "model": model_id,
                                        "delta": str(reasoning_delta),
                                    }
                                    await asyncio.sleep(0)

                                content = getattr(delta, "content", None) or ""
                                if content:
                                    if _mark_answer_started():
                                        yield {"type": "meta", "phase": "answer_start", "t": int(time.time() * 1000), "model": model_id}
                                    full_response += content
                                    yield {
                                        "type": "token",
                                        "model": model_id,
                                        "delta": content
                                    }
                                    await asyncio.sleep(0) # Yield for event loop
                    else:
                        yield {"type": "error", "model": model_id, "error": "OpenAI-compatible client unavailable"}
                
                elif not used_native_search and ("claude" in model_id or model_id.startswith("claude")):
                    from app.services.ai.model_registry import get_api_model_name
                    client = claude_client
                    if client:
                        api_model = get_api_model_name(model_id)
                        max_tokens = 4096
                        create_kwargs: Dict[str, Any] = {
                            "model": api_model,
                            "max_tokens": max_tokens,
                            "messages": history,
                            "system": stream_instruction,
                            "stream": True,
                        }

                        # Optional MCP tool-calling (Anthropic): run non-stream tool loop and emit SSE tokens.
                        if mcp_enabled_for_turn:
                            try:
                                from app.services.ai.agent_clients import get_async_claude_client
                                from app.services.ai.mcp_tools import run_anthropic_tool_loop

                                async_client = get_async_claude_client()
                                if async_client:
                                    tool_step_id = f"mcp_{model_id}"
                                    yield {
                                        "type": "step.start",
                                        "step_name": "MCP tools",
                                        "step_id": tool_step_id,
                                        "model": model_id,
                                    }
                                    await asyncio.sleep(0)
                                    text, tool_trace = await run_anthropic_tool_loop(
                                        client=async_client,
                                        model=api_model,
                                        system_instruction=stream_instruction,
                                        user_prompt=user_message,
                                        max_tokens=4096,
                                        temperature=temperature,
                                        allowed_server_labels=allowed_server_labels,
                                    )
                                    for item in tool_trace:
                                        yield {
                                            "type": "tool_call",
                                            "model": model_id,
                                            "step_id": tool_step_id,
                                            "name": item.get("name"),
                                            "arguments": item.get("arguments"),
                                            "result_preview": item.get("result_preview"),
                                        }
                                        await asyncio.sleep(0)
                                    yield {"type": "step.done", "step_id": tool_step_id, "model": model_id}
                                    await asyncio.sleep(0)

                                    if _mark_answer_started():
                                        yield {
                                            "type": "meta",
                                            "phase": "answer_start",
                                            "t": int(time.time() * 1000),
                                            "model": model_id,
                                        }
                                    full_response += text
                                    chunk_size = 64
                                    for i in range(0, len(text), chunk_size):
                                        yield {"type": "token", "model": model_id, "delta": text[i : i + chunk_size]}
                                        await asyncio.sleep(0)
                                    self.thread_manager.add_message(
                                        thread_id, "assistant", full_response, model=model_id
                                    )
                                    yield {
                                        "type": "done",
                                        "model": model_id,
                                        "full_text": full_response,
                                        "thinking": full_thinking or None,
                                        "citations": list(citations_by_url.values()),
                                    }
                                    return
                            except Exception as e:
                                logger.warning(f"MCP tool-calling disabled for {model_id}: {e}")

                        # Enable native thinking for Claude Sonnet (extended thinking API)
                        budget_tokens = None
                        if thinking_category == "native":
                            if model_thinking_budget is not None:
                                budget_tokens = clamp_thinking_budget(model_thinking_budget, model_id)
                            elif normalized_reasoning in ("medium", "high", "xhigh"):
                                budget_tokens = 1024 if normalized_reasoning == "medium" else 2048
                        if budget_tokens is not None and budget_tokens > 0:
                            if max_tokens <= budget_tokens:
                                max_tokens = budget_tokens + 1024
                                create_kwargs["max_tokens"] = max_tokens
                            create_kwargs["thinking"] = {"type": "enabled", "budget_tokens": budget_tokens}
                            create_kwargs["temperature"] = 1.0
                        else:
                            create_kwargs["temperature"] = temperature
                        provider_name = "vertex-anthropic" if _is_anthropic_vertex_client(client) else "anthropic"
                        try:
                            stream = client.messages.create(**create_kwargs)
                            record_api_call(
                                kind="llm",
                                provider=provider_name,
                                model=api_model,
                                success=True,
                                meta={"stream": True},
                            )
                        except Exception:
                            record_api_call(
                                kind="llm",
                                provider=provider_name,
                                model=api_model,
                                success=False,
                                meta={"stream": True},
                            )
                            raise
                        for event in stream:
                            if event.type == "content_block_delta":
                                delta = getattr(event, "delta", None)
                                if not delta:
                                    continue
                                delta_type = getattr(delta, "type", None)

                                if delta_type == "thinking_delta":
                                    thinking_text = getattr(delta, "thinking", "") or ""
                                    if thinking_text:
                                        full_thinking += thinking_text
                                        yield {
                                            "type": "thinking",
                                            "model": model_id,
                                            "delta": thinking_text,
                                        }
                                        await asyncio.sleep(0)
                                    continue

                                # text_delta (Anthropic SDK) or older delta.text fallback
                                text = getattr(delta, "text", None) or ""
                                if text:
                                    if _mark_answer_started():
                                        yield {"type": "meta", "phase": "answer_start", "t": int(time.time() * 1000), "model": model_id}
                                    full_response += text
                                    yield {
                                        "type": "token",
                                        "model": model_id,
                                        "delta": text,
                                    }
                                    await asyncio.sleep(0)
                    else:
                        yield {"type": "error", "model": model_id, "error": "Claude Client unavailable"}

                elif not used_native_search and ("gemini" in model_id or model_id.startswith("gemini")):
                    from app.services.ai.model_registry import get_api_model_name

                    client = gemini_client
                    if client:
                        api_model = get_api_model_name(model_id)

                        # Optional MCP tool-calling (Gemini): run non-stream tool loop and emit SSE tokens.
                        if mcp_enabled_for_turn:
                            try:
                                from app.services.ai.mcp_tools import run_gemini_tool_loop

                                tool_step_id = f"mcp_{model_id}"
                                yield {
                                    "type": "step.start",
                                    "step_name": "MCP tools",
                                    "step_id": tool_step_id,
                                    "model": model_id,
                                }
                                await asyncio.sleep(0)
                                text, tool_trace = await run_gemini_tool_loop(
                                    client=client,
                                    model=api_model,
                                    system_instruction=stream_instruction,
                                    user_prompt=user_message,
                                    max_tokens=4096,
                                    temperature=temperature,
                                    allowed_server_labels=allowed_server_labels,
                                )
                                for item in tool_trace:
                                    yield {
                                        "type": "tool_call",
                                        "model": model_id,
                                        "step_id": tool_step_id,
                                        "name": item.get("name"),
                                        "arguments": item.get("arguments"),
                                        "result_preview": item.get("result_preview"),
                                    }
                                    await asyncio.sleep(0)
                                yield {"type": "step.done", "step_id": tool_step_id, "model": model_id}
                                await asyncio.sleep(0)

                                if _mark_answer_started():
                                    yield {
                                        "type": "meta",
                                        "phase": "answer_start",
                                        "t": int(time.time() * 1000),
                                        "model": model_id,
                                    }
                                full_response += text
                                chunk_size = 64
                                for i in range(0, len(text), chunk_size):
                                    yield {"type": "token", "model": model_id, "delta": text[i : i + chunk_size]}
                                    await asyncio.sleep(0)
                                self.thread_manager.add_message(thread_id, "assistant", full_response, model=model_id)
                                yield {
                                    "type": "done",
                                    "model": model_id,
                                    "full_text": full_response,
                                    "thinking": full_thinking or None,
                                    "citations": list(citations_by_url.values()),
                                }
                                return
                            except Exception as e:
                                logger.warning(f"MCP tool-calling disabled for {model_id}: {e}")

                        thinking_mode = None
                        if normalized_reasoning in ("high", "xhigh"):
                            thinking_mode = "high"
                        elif normalized_reasoning == "medium":
                            thinking_mode = "medium"
                        elif normalized_reasoning == "low":
                            thinking_mode = "low"
                        elif normalized_reasoning == "minimal":
                            thinking_mode = "minimal"
                        # "none" -> thinking_mode stays None (completely disabled)

                        gemini_grounding_step_id = None
                        gemini_seen_source_urls: set = set()
                        async for chunk_data in stream_vertex_gemini_async(
                            client,
                            user_message,
                            model=api_model,
                            max_tokens=4096,
                            temperature=temperature,
                            system_instruction=stream_instruction,
                            thinking_mode=thinking_mode,
                        ):
                            if isinstance(chunk_data, tuple):
                                chunk_type, delta = chunk_data
                                if chunk_type in ("thinking", "thinking_summary") and delta:
                                    full_thinking += str(delta)
                                    payload: Dict[str, Any] = {
                                        "type": "thinking",
                                        "model": model_id,
                                        "delta": str(delta),
                                    }
                                    if chunk_type == "thinking_summary":
                                        payload["thinking_type"] = "summary"
                                    yield payload
                                    await asyncio.sleep(0)
                                elif chunk_type == "grounding_query" and delta:
                                    # Emit step.start on first grounding event
                                    if not gemini_grounding_step_id:
                                        import uuid
                                        gemini_grounding_step_id = str(uuid.uuid4())[:8]
                                        yield {"type": "step.start", "step_name": "Pesquisando", "step_id": gemini_grounding_step_id}
                                    yield {"type": "step.add_query", "step_id": gemini_grounding_step_id, "query": str(delta)[:200]}
                                    await asyncio.sleep(0)
                                elif chunk_type == "grounding_source" and delta:
                                    # Emit step.start on first grounding event
                                    if not gemini_grounding_step_id:
                                        import uuid
                                        gemini_grounding_step_id = str(uuid.uuid4())[:8]
                                        yield {"type": "step.start", "step_name": "Pesquisando", "step_id": gemini_grounding_step_id}
                                    yield {"type": "step.add_source", "step_id": gemini_grounding_step_id, "source": delta}
                                    # Also include grounding sources in the final `done.citations`.
                                    try:
                                        if isinstance(delta, dict):
                                            url = str(delta.get("url") or "").strip()
                                            title = str(delta.get("title") or url).strip()
                                        else:
                                            url = str(getattr(delta, "url", "") or "").strip()
                                            title = str(getattr(delta, "title", "") or url).strip()
                                        if url and url not in gemini_seen_source_urls:
                                            gemini_seen_source_urls.add(url)
                                            _merge_citations([{"title": title or url, "url": url}])
                                    except Exception:
                                        pass
                                    await asyncio.sleep(0)
                                elif chunk_type == "text" and delta:
                                    # Close grounding step when text starts
                                    if gemini_grounding_step_id:
                                        yield {"type": "step.done", "step_id": gemini_grounding_step_id}
                                        gemini_grounding_step_id = None
                                    if _mark_answer_started():
                                        yield {
                                            "type": "meta",
                                            "phase": "answer_start",
                                            "t": int(time.time() * 1000),
                                            "model": model_id,
                                        }
                                    full_response += str(delta)
                                    yield {"type": "token", "model": model_id, "delta": str(delta)}
                                    await asyncio.sleep(0)
                            elif chunk_data:
                                if _mark_answer_started():
                                    yield {
                                        "type": "meta",
                                        "phase": "answer_start",
                                        "t": int(time.time() * 1000),
                                        "model": model_id,
                                    }
                                full_response += str(chunk_data)
                                yield {"type": "token", "model": model_id, "delta": str(chunk_data)}
                                await asyncio.sleep(0)
                        # Ensure grounding step is closed
                        if gemini_grounding_step_id:
                            yield {"type": "step.done", "step_id": gemini_grounding_step_id}
                    else:
                        yield {"type": "error", "model": model_id, "error": "Gemini Client unavailable"}
                
                else:
                    yield {"type": "error", "model": model_id, "error": f"Unknown model: {model_id}"}
                
                if sources and not used_native_search and "fontes:" not in full_response.lower() and not citations_by_url:
                    full_response = render_perplexity(full_response, sources)
                if sources and not citations_by_url:
                    _merge_citations(sources_to_citations(sources))

                # Save final message
                self.thread_manager.add_message(thread_id, "assistant", full_response, model=model_id)
                asyncio.create_task(_persist_rag_history_to_redis())
                
                yield {
                    "type": "done",
                    "model": model_id,
                    "full_text": full_response,
                    "thinking": full_thinking or None,
                    "citations": list(citations_by_url.values()),
                }
                
            except Exception as e:
                logger.error(f"Error streaming {model_id}: {e}")
                yield {"type": "error", "model": model_id, "error": str(e)}

        # Run all model streams concurrently and merge results
        # Using a simple gather pattern is tricky for merged streaming generator.
        # We'll use an asyncio Queue to merge streams.
        
        queue = asyncio.Queue()
        active_streams = len(selected_models)
        
        async def producer(model_id):
            async for event in stream_model(model_id):
                await queue.put(event)
            await queue.put(None) # Signal done for this model
            
        # Start producers
        producers = [asyncio.create_task(producer(m)) for m in selected_models]
        
        # Consume queue
        completed_streams = 0
        while completed_streams < active_streams:
            item = await queue.get()
            if item is None:
                completed_streams += 1
            else:
                yield item


# Backwards-compatible alias for imports expecting ChatService.
class ChatService(ChatOrchestrator):
    pass

# Global instance
chat_service = ChatOrchestrator()
