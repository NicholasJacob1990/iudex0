"""
Gemini Drafter Wrapper for API
Provides the 'Judge' capability for the MultiAgentOrchestrator.
Adapts the interface expected by agent_clients.py
"""

import os
import time
import logging
from typing import Optional
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
            
    def _generate_with_retry(self, prompt: str, max_retries: int = 3, model_name: Optional[str] = None) -> Optional[GenerationResponse]:
        """
        Gera texto com retry e backoff exponencial usando Vertex AI.
        """
        if not self.client_initialized:
            logger.error("Client Vertex AI não inicializado.")
            return None
            
        # Vertex AI imports
        try:
            from vertexai.generative_models import GenerativeModel, GenerationConfig
        except ImportError:
            try:
                from vertexai.preview.generative_models import GenerativeModel, GenerationConfig
            except ImportError:
                logger.error("❌ Vertex AI SDK não encontrado.")
                return None
        
        target_model = model_name or self.model_name
        
        for attempt in range(max_retries):
            try:
                # Instanciar modelo Vertex (stateless/global init)
                model = GenerativeModel(target_model)
                
                # Configuração conservadora para o Juiz
                response = model.generate_content(
                    prompt,
                    generation_config=GenerationConfig(
                        temperature=0.1,
                        max_output_tokens=8192
                    )
                )
                
                if response.text:
                    return GenerationResponse(text=response.text)
                    
            except Exception as e:
                wait_time = 2 ** attempt
                logger.warning(f"⚠️ Erro Vertex Gemini (Tentativa {attempt+1}/{max_retries}): {e}. Aguardando {wait_time}s...")
                time.sleep(wait_time)
                
        logger.error("❌ Falha final na geração do Gemini (Vertex) após retries.")
        return None
