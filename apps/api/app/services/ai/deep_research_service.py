import os
import time
import logging
from typing import Optional, Dict, Any, Generator
from dataclasses import dataclass

from app.services.job_manager import job_manager

logger = logging.getLogger("DeepResearchService")

# Tentar importar SDK Google GenAI (v1.53+)
try:
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False
    logger.error("❌ google-genai não instalado. Deep Research indisponível.")

@dataclass
class DeepResearchResult:
    text: str
    log: str = ""
    success: bool = False
    error: Optional[str] = None
    sources: Optional[list] = None
    thinking_steps: Optional[list] = None
    from_cache: bool = False

class DeepResearchService:
    """
    Service wrapper for Google's Deep Research Agent (deep-research-pro-preview-12-2025).
    Provides methods for background execution and polling/streaming of research tasks.
    """
    
    def __init__(self):
        self.client = None
        if GENAI_AVAILABLE:
            api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
            if api_key:
                self.client = genai.Client(api_key=api_key)
            else:
                logger.warning("⚠️ GOOGLE_API_KEY não configurada. Deep Research não funcionará.")

    async def run_research_task(self, query: str, config: Optional[Dict[str, Any]] = None) -> DeepResearchResult:
        """
        Executes Deep Research with caching strategy.
        1. Check Cache
        2. If miss, run agent
        3. Cache result
        """
        if not self.client:
            return DeepResearchResult(text="", error="Client GenAI não inicializado", success=False)

        # 1. Try Cache
        cached = job_manager.get_cached_deep_research(query)
        if cached:
            logger.info(f"⚡ Deep Research Cache Hit: {cached['cache_key']}")
            return DeepResearchResult(
                text=cached['report'],
                log="\n".join([t['text'] for t in cached['thinking_steps']]),
                success=True,
                sources=cached['sources'],
                thinking_steps=cached['thinking_steps'],
                from_cache=True
            )

        # 2. Run Live Research
        agent_model = "deep-research-pro-preview-12-2025" 
        logger.info(f"🚀 Iniciando Deep Research (Live): '{query}'")
        
        try:
            interaction = self.client.interactions.create(
                input=query,
                agent=agent_model,
                background=True,
                stream=True,
                agent_config={
                    "type": "deep-research",
                    "thinking_summaries": "auto"
                }
            )
            
            final_report = ""
            full_thinking = []
            
            for event in interaction:
                if event.type == "thinking":
                    logger.debug(f"💭 Thinking: {event.text[:50]}...")
                    full_thinking.append({"text": event.text, "timestamp": time.time()})
                elif event.type == "content":
                    logger.info(f"📄 Content received ({len(event.text)} chars)")
                    final_report += event.text
                elif event.type == "interaction.end":
                    logger.info("✅ Deep Research concluído.")
                    break
                elif event.type == "error":
                    logger.error(f"❌ Erro no stream: {event.text}")
                    return DeepResearchResult(text="", error=event.text, success=False)
            
            # Extract basic sources if possible (placeholder logic as real extraction depends on format)
            # For now assume sources are embedded or we need a helper. 
            # We'll save empty list or basic extraction for now.
            sources = [] 
            
            # 3. Cache Result
            if final_report:
                job_manager.cache_deep_research(
                    query=query,
                    report=final_report,
                    sources=sources,
                    thinking_steps=full_thinking
                )
                
            return DeepResearchResult(
                text=final_report,
                log="\n".join([t['text'] for t in full_thinking]),
                success=True,
                sources=sources,
                thinking_steps=full_thinking,
                from_cache=False
            )

        except Exception as e:
            logger.error(f"❌ Falha crítica no Deep Research: {e}")
            return DeepResearchResult(text="", error=str(e), success=False)

    async def stream_research_task(self, query: str) -> Generator[Dict[str, Any], None, None]:
        """
        Async generator that yields events: 
        - type: 'thinking', 'content', 'cache_hit', 'done'
        """
        if not self.client:
            yield {"type": "error", "message": "Client GenAI não inicializado"}
            return

        # 1. Try Cache
        cached = job_manager.get_cached_deep_research(query)
        if cached:
            yield {"type": "cache_hit", "key": cached['cache_key']}
            # Replay thinking
            for step in cached['thinking_steps']:
                yield {"type": "thinking", "text": step['text'], "from_cache": True}
                # Artificial delay for UI pacing if needed, but skipped for speed
            
            yield {"type": "content", "text": cached['report'], "from_cache": True}
            yield {"type": "done", "sources": cached['sources']}
            return

        # 2. Run Live
        try:
            interaction = self.client.interactions.create(
                input=query,
                agent="deep-research-pro-preview-12-2025",
                background=True,
                stream=True,
                agent_config={"type": "deep-research", "thinking_summaries": "auto"}
            )
            
            final_report = ""
            full_thinking = []
            
            for event in interaction:
                if event.type == "thinking":
                    full_thinking.append({"text": event.text, "timestamp": time.time()})
                    yield {"type": "thinking", "text": event.text, "from_cache": False}
                
                elif event.type == "content":
                    final_report += event.text
                    yield {"type": "content", "text": event.text, "from_cache": False}
                
                elif event.type == "interaction.end":
                    break
                    
            # 3. Cache
            if final_report:
                job_manager.cache_deep_research(
                    query=query,
                    report=final_report,
                    sources=[],
                    thinking_steps=full_thinking
                )
            
            yield {"type": "done", "sources": []}
            
        except Exception as e:
            logger.error(f"❌ Stream Deep Research Error: {e}")
            yield {"type": "error", "message": str(e)}

deep_research_service = DeepResearchService()

deep_research_service = DeepResearchService()
