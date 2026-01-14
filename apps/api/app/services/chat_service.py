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
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Literal, Generator, AsyncGenerator
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
from app.services.ai.agent_clients import (
    call_openai_async,
    call_anthropic_async,
    call_vertex_gemini_async,
)
from app.services.ai.citations import to_perplexity
from app.services.ai.citations.base import render_perplexity, stable_numbering
from app.services.ai.agent_clients import _is_anthropic_vertex_client
from app.services.ai.genai_utils import extract_genai_text
from app.services.model_registry import get_model_config as get_budget_model_config

logger = logging.getLogger("ChatService")

from app.services.ai.engineering_pipeline import run_engineering_pipeline


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
    preferred = os.getenv("JUDGE_MODEL_ID", "gemini-3-pro").strip() or "gemini-3-pro"
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
            cursor.execute("SELECT * FROM messages WHERE thread_id = ? ORDER BY created_at ASC", (thread_id,))
            msg_rows = cursor.fetchall()
            
            messages = []
            for row in msg_rows:
                messages.append(ChatMessage(
                    id=row["id"],
                    role=row["role"],
                    content=row["content"],
                    model=row["model"],
                    created_at=row["created_at"]
                ))
            
            return ChatThread(
                id=thread_row["id"],
                title=thread_row["title"],
                messages=messages,
                created_at=thread_row["created_at"],
                updated_at=thread_row["updated_at"]
            )
        except Exception as e:
            logger.error(f"❌ Error getting thread {thread_id}: {e}")
            return None

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
                except Exception as e:
                    logger.error(f"Consolidate via {model_id} failed: {e}")
            elif provider == "anthropic":
                try:
                    client = get_claude_client()
                    if not client:
                        continue
                    api_model = get_api_model_name(model_id) or model_id
                    resp = client.messages.create(
                        model=api_model,
                        max_tokens=2048,
                        system=system,
                        messages=[*history, {"role": "user", "content": judge_user}],
                    )
                    if hasattr(resp, "content") and resp.content:
                        merged_text = "".join([getattr(b, "text", "") for b in resp.content]).strip()
                except Exception as e:
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
                except Exception as e:
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
                    drafter=drafter
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
                        resp = client.chat.completions.create(
                            model=api_model,
                            messages=[{"role": "user", "content": edit_prompt}],
                            max_tokens=4096
                        )
                        final_text = resp.choices[0].message.content

                elif provider == "anthropic" or "claude" in model_id.lower():
                    client = get_claude_client()
                    if client:
                        api_model = get_api_model_name(model_id)
                        resp = client.messages.create(
                            model=api_model,
                            max_tokens=4096,
                            messages=[{"role": "user", "content": edit_prompt}]
                        )
                        final_text = "".join([getattr(b, "text", "") for b in resp.content]).strip()

                elif provider == "google" or "gemini" in model_id.lower():
                    client = get_gemini_client()
                    if client:
                        api_model = get_api_model_name(model_id)
                        resp = client.models.generate_content(
                            model=api_model,
                            contents=edit_prompt
                        )
                        final_text = extract_genai_text(resp)

                elif provider == "xai" or "grok" in model_id.lower():
                    client = get_xai_client()
                    if client:
                        api_model = get_api_model_name(model_id)
                        resp = client.chat.completions.create(
                            model=api_model,
                            messages=[{"role": "user", "content": edit_prompt}],
                            max_tokens=4096
                        )
                        final_text = resp.choices[0].message.content

                elif provider in ("openrouter", "deepseek", "meta") or "llama" in model_id.lower():
                    client = get_openrouter_client()
                    if client:
                        api_model = get_api_model_name(model_id)
                        resp = client.chat.completions.create(
                            model=api_model,
                            messages=[{"role": "user", "content": edit_prompt}],
                            max_tokens=4096
                        )
                        final_text = resp.choices[0].message.content

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
                    resp = client.chat.completions.create(
                        model=api_model,
                        messages=[{"role": "user", "content": edit_prompt}],
                        max_tokens=4096
                    )
                    return {"agent": "GPT", "response": resp.choices[0].message.content}
            except Exception as e:
                logger.error(f"GPT edit failed: {e}")
            return {"agent": "GPT", "response": None}
        
        async def eval_claude():
            try:
                client = get_claude_client()
                if client:
                    from app.services.ai.model_registry import get_api_model_name
                    api_model = get_api_model_name("claude-4.5-sonnet")
                    resp = client.messages.create(
                        model=api_model,
                        max_tokens=4096,
                        messages=[{"role": "user", "content": edit_prompt}]
                    )
                    text = "".join([getattr(b, "text", "") for b in resp.content]).strip()
                    return {"agent": "Claude", "response": text}
            except Exception as e:
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
                final_text = extract_genai_text(resp)
        except Exception as e:
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
        chat_personality: str = "juridico",
        web_search: bool = False,
        multi_query: bool = True,
        breadth_first: bool = False,
        search_mode: str = "hybrid"
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        1. Save User Message
        2. Stream back responses from selected models in parallel
        3. Save Assistant Messages
        """
        
        # 1. Save User Message
        self.thread_manager.add_message(thread_id, "user", user_message)
        
        # 2. Get history for context
        thread = self.thread_manager.get_thread(thread_id)
        if not thread:
            yield {"error": "Thread not found"}
            return
            
        history = [
            {"role": m.role, "content": m.content} 
            for m in thread.messages
            # Filter out potentially confusing multi-model context if needed, 
            # for now we send everything (shared history view)
        ]
        base_instruction = build_system_instruction(chat_personality)
        system_instruction = base_instruction

        history = _trim_history_for_models(history, selected_models, base_instruction, user_message)

        sources = []
        breadth_first = bool(breadth_first) or (web_search and is_breadth_first(user_message))
        search_mode = (search_mode or "hybrid").lower()
        if search_mode not in ("shared", "native", "hybrid"):
            search_mode = "hybrid"

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
            mid = (model_id or "").lower()
            if "gemini" in mid:
                return bool(gemini_client)
            if "claude" in mid:
                return bool(claude_client)
            if "gpt" in mid:
                return bool(gpt_client and hasattr(gpt_client, "responses"))
            return False

        allow_native_search = web_search and search_mode in ("native", "hybrid")
        allow_shared_search = web_search and search_mode in ("shared", "hybrid")
        use_shared_search = allow_shared_search and (
            search_mode == "shared"
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
                if multi_query:
                    search_payload = await web_search_service.search_multi(search_query, num_results=8)
                else:
                    search_payload = await web_search_service.search(search_query, num_results=8)
                results = search_payload.get("results") or []
                yield {
                    "type": "search_done",
                    "query": search_query,
                    "count": len(results),
                    "cached": bool(search_payload.get("cached")),
                    "source": search_payload.get("source"),
                    "queries": search_payload.get("queries") if multi_query else None
                }
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

        async def _call_native_search(
            model_id: str,
            messages: List[Dict[str, str]],
            prompt: str,
            max_tokens: int = 4096,
            temperature: float = 0.3
        ) -> Optional[str]:
            from app.services.ai.model_registry import get_api_model_name, get_model_config

            cfg = get_model_config(model_id)
            provider = cfg.provider if cfg else ""
            api_model = get_api_model_name(model_id) or model_id

            if provider == "openai":
                if not gpt_client or not hasattr(gpt_client, "responses"):
                    return None
                try:
                    resp = gpt_client.responses.create(
                        model=api_model,
                        input=messages,
                        tools=[{"type": "web_search"}],
                        temperature=temperature,
                        max_output_tokens=max_tokens,
                    )
                    text = to_perplexity("openai", resp)
                    return text or getattr(resp, "output_text", "") or None
                except Exception as e:
                    logger.error(f"OpenAI web search failed ({model_id}): {e}")
                    return None

            if provider == "anthropic":
                if not claude_client:
                    return None
                try:
                    kwargs: Dict[str, Any] = {
                        "model": api_model,
                        "max_tokens": max_tokens,
                        "messages": messages,
                        "system": base_instruction,
                        "tools": [{"type": "web_search_20250305", "name": "web_search"}],
                    }
                    beta_header = os.getenv("ANTHROPIC_WEB_SEARCH_BETA", "web-search-2025-03-05").strip()
                    if beta_header:
                        kwargs["extra_headers"] = {"anthropic-beta": beta_header}
                    if _is_anthropic_vertex_client(claude_client):
                        kwargs["anthropic_version"] = os.getenv("ANTHROPIC_VERTEX_VERSION", "vertex-2023-10-16")
                    resp = claude_client.messages.create(**kwargs)
                    text = to_perplexity("claude", resp)
                    return text or None
                except Exception as e:
                    logger.error(f"Claude web search failed ({model_id}): {e}")
                    return None

            if provider == "google":
                if not gemini_client:
                    return None
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
                    text = to_perplexity("gemini", resp)
                    return text or (resp.text or "").strip() or None
                except Exception as e:
                    logger.error(f"Gemini web search failed ({model_id}): {e}")
                    return None

            return None
        
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
                    return await _call_native_search(
                        model_id,
                        messages=messages,
                        prompt=prompt,
                        max_tokens=tokens,
                        temperature=0.4,
                    )

                if provider == "openai":
                    return await call_openai_async(
                        gpt_client,
                        prompt,
                        model=api_model,
                        max_tokens=tokens,
                        temperature=0.4,
                        system_instruction=system_instruction,
                    )
                if provider == "anthropic":
                    return await call_anthropic_async(
                        claude_client,
                        prompt,
                        model=api_model,
                        max_tokens=tokens,
                        temperature=0.4,
                        system_instruction=system_instruction,
                    )
                if provider == "google":
                    return await call_vertex_gemini_async(
                        gemini_client,
                        prompt,
                        model=api_model,
                        max_tokens=tokens,
                        temperature=0.4,
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
                if sources and "fontes:" not in lead_text.lower():
                    lead_text = render_perplexity(lead_text, sources)

                # Save final message
                self.thread_manager.add_message(thread_id, "assistant", lead_text, model=model_id)

                for i in range(0, len(lead_text), 64):
                    yield {"type": "token", "model": model_id, "delta": lead_text[i:i + 64]}
                yield {"type": "done", "model": model_id, "full_text": lead_text}
                return

        # 3. Parallel Execution Logic
        # We will yield chunks as { "model": "gpt-4o", "delta": "..." }
        
        async def stream_model(model_id: str):
            """Stream wrapper for a single model"""
            full_response = ""
            used_native_search = False
            
            try:
                from app.services.ai.model_registry import get_api_model_name, get_model_config

                model_cfg = get_model_config(model_id)
                provider = model_cfg.provider if model_cfg else None
                stream_instruction = system_instruction

                if allow_native_search and not use_shared_search and _supports_native_search(model_id):
                    native_messages = []
                    if provider == "openai":
                        native_messages = [{"role": "system", "content": base_instruction}] + history
                    elif provider == "anthropic":
                        native_messages = history

                    native_text = await _call_native_search(
                        model_id,
                        messages=native_messages,
                        prompt=user_message,
                        max_tokens=4096,
                        temperature=0.3,
                    )
                    if native_text:
                        full_response = native_text
                        used_native_search = True
                        for i in range(0, len(full_response), 64):
                            yield {
                                "type": "token",
                                "model": model_id,
                                "delta": full_response[i:i + 64],
                            }
                            await asyncio.sleep(0)

                if not used_native_search and model_id == "internal-rag":
                    # Internal RAG (Gemini + Docs)
                    from app.services.ai.gemini_drafter import GeminiDrafterWrapper
                    drafter = GeminiDrafterWrapper()
                    # Use programmatic chat interface
                    # TODO: Implement proper streaming for programmatic chat
                    # For now, non-streaming fallback
                    response = drafter._generate_with_retry(user_message)
                    full_response = response.text if response else "Erro ao gerar resposta."

                    yield {
                        "type": "token",
                        "model": model_id,
                        "delta": full_response
                    }

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
                        stream = client.chat.completions.create(
                            model=api_model,
                            messages=messages,
                            stream=True
                        )
                        for chunk in stream:
                            content = chunk.choices[0].delta.content or ""
                            if content:
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
                        stream = client.messages.create(
                            model=api_model,
                            max_tokens=4096,
                            messages=history,
                            system=stream_instruction,
                            stream=True
                        )
                        for event in stream:
                            if event.type == "content_block_delta":
                                content = event.delta.text
                                full_response += content
                                yield {
                                    "type": "token",
                                    "model": model_id,
                                    "delta": content
                                }
                                await asyncio.sleep(0)
                    else:
                        yield {"type": "error", "model": model_id, "error": "Claude Client unavailable"}

                elif not used_native_search and ("gemini" in model_id or model_id.startswith("gemini")):
                    from app.services.ai.model_registry import get_api_model_name
                    client = gemini_client
                    if client:
                        api_model = get_api_model_name(model_id)
                        try:
                            from google.genai import types as genai_types
                            config = genai_types.GenerateContentConfig(system_instruction=stream_instruction)
                        except Exception:
                            config = {"system_instruction": stream_instruction}
                        response = client.models.generate_content(
                            model=api_model,
                            contents=user_message,
                            config=config
                        )
                        full_response = extract_genai_text(response)
                        yield {
                            "type": "token",
                            "model": model_id,
                            "delta": full_response
                        }
                    else:
                         yield {"type": "error", "model": model_id, "error": "Gemini Client unavailable"}
                
                else:
                    yield {"type": "error", "model": model_id, "error": f"Unknown model: {model_id}"}
                
                if sources and not used_native_search and "fontes:" not in full_response.lower():
                    full_response = render_perplexity(full_response, sources)

                # Save final message
                self.thread_manager.add_message(thread_id, "assistant", full_response, model=model_id)
                
                yield {
                    "type": "done",
                    "model": model_id,
                    "full_text": full_response
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
