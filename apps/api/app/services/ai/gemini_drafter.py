"""
Gemini Drafter Wrapper for API
Provides the 'Judge' capability for the MultiAgentOrchestrator.
Adapts the interface expected by agent_clients.py
"""

import os
import time
import logging
from typing import Optional, Any
from dataclasses import dataclass

logger = logging.getLogger("GeminiDrafter")

@dataclass
class GenerationResponse:
    text: str

class GeminiDrafterWrapper:
    """
    Wrapper minimalista para simular o LegalDrafter do juridico_gemini.py
    usado pelo agent_clients.py para o Juiz.
    """
    
    def __init__(self, model_name: str = "gemini-1.5-pro-002"):
        self.model_name = model_name
        self.client_initialized = self._init_client()
        
    def _init_client(self):
        try:
            from app.services.ai.agent_clients import init_vertex_client
            return init_vertex_client()
        except ImportError:
            logger.error("❌ Erro ao importar init_vertex_client de agent_clients.")
            return None
            
    def _generate_with_retry(
        self,
        prompt: str,
        max_retries: int = 3,
        model_name: Optional[str] = None,
        cached_content: Optional[Any] = None,
        temperature: float = 0.1
    ) -> Optional[GenerationResponse]:
        """
        Gera texto com retry e backoff exponencial usando agent_clients (Unified).
        Supports Context Caching via cached_content.
        """
        try:
            from app.services.ai.agent_clients import call_vertex_gemini
            from app.services.ai.agent_clients import get_gemini_client
        except ImportError:
            logger.error("❌ Erro ao importar agent_clients.")
            return None
            
        client = get_gemini_client()
        target_model = model_name or self.model_name
        try:
            temperature = float(temperature)
        except (TypeError, ValueError):
            temperature = 0.1
        temperature = max(0.0, min(1.0, temperature))
        
        for attempt in range(max_retries):
            try:
                # Use unified client call which supports caching
                response_text = call_vertex_gemini(
                    client=client,
                    prompt=prompt,
                    model=target_model,
                    cached_content=cached_content,
                    # Allow caller to override temperature for creativity control.
                    temperature=temperature
                )
                
                if response_text:
                    return GenerationResponse(text=response_text)
                    
            except Exception as e:
                wait_time = 2 ** attempt
                logger.warning(f"⚠️ Erro Gemini Drafter (Tentativa {attempt+1}/{max_retries}): {e}. Aguardando {wait_time}s...")
                time.sleep(wait_time)
                
        logger.error("❌ Falha final na geração do Gemini Drafter após retries.")
    def generate_section(
        self,
        titulo: str,
        contexto_rag: str,
        tipo_peca: str,
        resumo_caso: str,
        tese_usuario: str,
        cached_content: Optional[Any] = None,
        temperature: float = 0.1
    ) -> str:
        """
        Gera uma seção individual com robustez (simula o LegalDrafter original).
        Supports Context Caching.
        """
        # Se tiver cache, o prompt pode ser mais enxuto pois o contexto factual já está no cache
        prompt = f"""
## TAREFA: REDIGIR SEÇÃO "{titulo}"
## TIPO: {tipo_peca}
## TESE: {tese_usuario}

{'## CONTEXTO (RAG): ' + contexto_rag[:3000] if not cached_content else '[CONTEXTO FACTUAL JÁ FORNECIDO NO CACHE]'}

{'## RESUMO DO CASO: ' + resumo_caso[:2000] if not cached_content else ''}

## INSTRUÇÕES:
1. Escreva em parágrafos claros e jurídicos.
2. Use citações [TIPO - Doc. X] se houver fatos.
3. Não invente informações.
"""
        resp = self._generate_with_retry(
            prompt,
            model_name=self.model_name,
            cached_content=cached_content,
            temperature=temperature
        )
        return resp.text if resp else ""
