"""
Chat API Endpoints - Multi-Model Support

Exposes:
- POST /chat/threads: Create new conversation
- GET /chat/threads: List conversations
- POST /chat/threads/{id}/messages: Send message (SSE streaming)
- POST /chat/threads/{id}/consolidate: Consolidate multi-model candidates into a single answer
"""

from fastapi import APIRouter, HTTPException, Body
from fastapi.responses import StreamingResponse
from loguru import logger
import json
from typing import List, Dict, Any

from app.services.chat_service import chat_service

router = APIRouter()

# --- SSE HELPER ---
def sse_event(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"

@router.post("/threads")
async def create_thread(
    title: str = Body("Nova Conversa", embed=True)
):
    """Create a new chat thread"""
    try:
        thread = chat_service.thread_manager.create_thread(title)
        return thread
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/threads")
async def list_threads(limit: int = 20):
    """List recent threads"""
    return chat_service.thread_manager.list_threads(limit)

@router.get("/threads/{thread_id}")
async def get_thread(thread_id: str):
    """Get full thread history"""
    thread = chat_service.thread_manager.get_thread(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    return thread

@router.post("/threads/{thread_id}/messages")
async def send_message(
    thread_id: str,
    message: str = Body(...),
    models: List[str] = Body(...),
    chat_personality: str = Body("juridico")
):
    """
    Send message to one or more models.
    Returns: SSE Stream
    """
    logger.info(f"💬 Chat request in {thread_id} for models: {models}")
    
    async def event_generator():
        try:
            async for event in chat_service.dispatch_turn(thread_id, message, models, chat_personality=chat_personality):
                yield sse_event(event)
        except Exception as e:
            logger.error(f"Stream error: {e}")
            yield sse_event({"type": "error", "error": str(e)})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive"
        }
    )


@router.post("/threads/{thread_id}/consolidate")
async def consolidate_turn(
    thread_id: str,
    message: str = Body(...),
    candidates: List[Dict[str, Any]] = Body(...)
):
    """
    Consolidate multiple model answers into a single "judge/merge" response.
    candidates: [{ "model": "gpt-4o", "text": "..." }, ...]
    """
    try:
        merged = await chat_service.consolidate_turn(thread_id, message, candidates)
        return {"content": merged}
    except Exception as e:
        logger.error(f"Consolidate error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
