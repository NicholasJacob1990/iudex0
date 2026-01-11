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
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Literal, Generator, AsyncGenerator
from pydantic import BaseModel

from app.services.ai.agent_clients import (
    get_gpt_client,
    get_claude_client,
    get_gemini_client,
    build_system_instruction
)

logger = logging.getLogger("ChatService")

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

        # Preferência: GPT -> Claude -> Gemini (dependendo de chaves disponíveis)
        try:
            client = get_gpt_client()
            if client:
                from app.services.ai.model_registry import get_api_model_name
                api_model = get_api_model_name("gpt-5-mini") or "gpt-5-mini"
                resp = client.chat.completions.create(
                    model=api_model,
                    messages=history + [
                        {"role": "system", "content": system},
                        {"role": "user", "content": judge_user},
                    ],
                )
                merged_text = (resp.choices[0].message.content or "").strip()
        except Exception as e:
            logger.error(f"Consolidate via GPT failed: {e}")

        if not merged_text:
            try:
                client = get_claude_client()
                if client:
                    from app.services.ai.model_registry import get_api_model_name
                    api_model = get_api_model_name("claude-4.5-sonnet") or "claude-4.5-sonnet"
                    resp = client.messages.create(
                        model=api_model,
                        max_tokens=2048,
                        system=system,
                        messages=history + [{"role": "user", "content": judge_user}],
                    )
                    # Anthropic SDK response content can be list of blocks
                    if hasattr(resp, "content") and resp.content:
                        merged_text = "".join([getattr(b, "text", "") for b in resp.content]).strip()
            except Exception as e:
                logger.error(f"Consolidate via Claude failed: {e}")

        if not merged_text:
            try:
                client = get_gemini_client()
                if client:
                    from app.services.ai.model_registry import get_api_model_name
                    api_model = get_api_model_name("gemini-3-flash") or "gemini-3-flash"
                    resp = client.models.generate_content(
                        model=api_model,
                        contents=f"{system}\n\n{judge_user}",
                    )
                    merged_text = (resp.text or "").strip()
            except Exception as e:
                logger.error(f"Consolidate via Gemini failed: {e}")

        if not merged_text:
            raise RuntimeError("No LLM client available to consolidate")

        self.thread_manager.add_message(thread_id, "assistant", merged_text, model="consolidado")
        return merged_text
        
    async def dispatch_turn(
        self, 
        thread_id: str, 
        user_message: str, 
        selected_models: List[str],
        chat_personality: str = "juridico"
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
        system_instruction = build_system_instruction(chat_personality)
        
        # 3. Parallel Execution Logic
        # We will yield chunks as { "model": "gpt-4o", "delta": "..." }
        
        async def stream_model(model_id: str):
            """Stream wrapper for a single model"""
            full_response = ""
            
            try:
                if model_id == "internal-rag":
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
                    
                elif "gpt" in model_id or model_id.startswith("gpt"):
                    from app.services.ai.model_registry import get_api_model_name
                    client = get_gpt_client()
                    if client:
                        api_model = get_api_model_name(model_id)
                        messages = [{"role": "system", "content": system_instruction}] + history
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
                        yield {"type": "error", "model": model_id, "error": "GPT Client unavailable"}

                elif "claude" in model_id or model_id.startswith("claude"):
                    from app.services.ai.model_registry import get_api_model_name
                    client = get_claude_client()
                    if client:
                        api_model = get_api_model_name(model_id)
                        stream = client.messages.create(
                            model=api_model,
                            max_tokens=4096,
                            messages=history,
                            system=system_instruction,
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

                elif "gemini" in model_id or model_id.startswith("gemini"):
                    from app.services.ai.model_registry import get_api_model_name
                    client = get_gemini_client()
                    if client:
                        api_model = get_api_model_name(model_id)
                        try:
                            from google.genai import types as genai_types
                            config = genai_types.GenerateContentConfig(system_instruction=system_instruction)
                        except Exception:
                            config = {"system_instruction": system_instruction}
                        response = client.models.generate_content(
                            model=api_model,
                            contents=user_message,
                            config=config
                        )
                        full_response = response.text
                        yield {
                            "type": "token",
                            "model": model_id,
                            "delta": full_response
                        }
                    else:
                         yield {"type": "error", "model": model_id, "error": "Gemini Client unavailable"}
                
                else:
                    yield {"type": "error", "model": model_id, "error": f"Unknown model: {model_id}"}
                
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

# Global instance
chat_service = ChatOrchestrator()
