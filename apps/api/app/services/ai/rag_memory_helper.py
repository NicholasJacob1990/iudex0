
import logging
from typing import Dict, Any, List, Optional
logger = logging.getLogger(__name__)

async def _rewrite_query_with_memory(
    state: "DocumentState",
    query: str,
    section_title: str
) -> str:
    """
    RAG Memory: Rewrites the search query based on chat history.
    """
    messages = state.get("messages") or []
    if not messages and state.get("conversation_id"):
        try:
            from app.services.ai.rag_memory_store import RAGMemoryStore
            messages = await RAGMemoryStore().get_history(state.get("conversation_id"))
        except Exception as e:
            logger.warning(f"⚠️ RAG Memory redis load failed: {e}")
    if not messages:
        return query
        
    last_user_msg = None
    # Find last user message
    for msg in reversed(messages):
        role = msg.get("role") or msg.get("type")
        if role == "user":
            last_user_msg = msg.get("content")
            break
            
    if not last_user_msg:
        return query
        
    try:
        from app.services.ai.agent_clients import init_openai_client, call_openai_async, get_api_model_name
        client = init_openai_client()
        if not client:
             return query

        prompt = f"""
        Você é um especialista em busca jurídica. Rescreva a query de busca abaixo considerando o histórico da conversa e a seção atual.
        
        Seção: {section_title}
        Query Original: {query}
        Última mensagem do usuário: {last_user_msg}
        
        Sua tarefa: Retorne APENAS a query reescrita, otimizada para busca semântica (RAG). Se a query original já for adequada, retorne-a inalterada.
        """
        
        rewritten = await call_openai_async(
            client,
            prompt,
            model=get_api_model_name(state.get("judge_model") or "gpt-5.2"),
            temperature=0.1,
            max_tokens=200
        )
        
        if rewritten and len(rewritten) > 5:
             logger.info(f"🧠 RAG Memory: Query rewritten | Original: '{query}' | New: '{rewritten.strip()}'")
             return rewritten.strip()
             
    except Exception as e:
        logger.warning(f"⚠️ RAG Memory rewrite failed: {e}")
        
    return query
