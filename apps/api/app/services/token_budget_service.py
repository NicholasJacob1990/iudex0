import math
import os
from typing import Dict, Any, Optional
from loguru import logger
from app.services.model_registry import get_model_config, MODEL_REGISTRY

# Try to import genai for real token counting
try:
    from google import genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False
    logger.warning("google-genai not available, using token estimation")

class TokenBudgetService:
    """
    Serviço para gerenciar orçamento de tokens, pré-checagem e telemetria.
    Suporta contagem real via Gemini API e estimação como fallback.
    """
    
    def __init__(self):
        self._client = None
        if GENAI_AVAILABLE:
            try:
                # Vertex AI Config
                project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
                location = os.getenv("VERTEX_AI_LOCATION", "global")
                auth_mode = (os.getenv("IUDEX_GEMINI_AUTH") or "auto").strip().lower()
                
                use_vertex = False
                if auth_mode in ("vertex", "vertexai", "gcp"):
                    use_vertex = True
                elif auth_mode in ("apikey", "api_key"):
                    use_vertex = False
                else: 
                     # Auto: prefer Vertex if project is set
                     use_vertex = bool(project_id)

                if use_vertex and project_id:
                     self._client = genai.Client(
                        vertexai=True,
                        project=project_id,
                        location=location
                     )
                     logger.info(f"✅ TokenBudgetService: Connected via Vertex AI ({location})")
                else:
                     # Fallback to API Key (default)
                     api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
                     self._client = genai.Client(api_key=api_key)
                     logger.info("✅ TokenBudgetService: Connected via Google AI Studio (API Key)")

            except Exception as e:
                logger.warning(f"Could not initialize Gemini client: {e}")

    def estimate_tokens(self, text: str) -> int:
        """
        Estimativa rápida de tokens (fallback).
        ~3.5 chars/token para português jurídico.
        """
        if not text:
            return 0
        return math.ceil(len(text) / 3.5)

    async def count_tokens_real(self, text: str, model_name: str = "gemini-2.5-pro-preview-06-05") -> int:
        """
        Contagem REAL de tokens usando a API countTokens do Gemini.
        Retorna estimativa se API não estiver disponível.
        """
        if not self._client or not GENAI_AVAILABLE:
            logger.debug("Using estimation fallback for token count")
            return self.estimate_tokens(text)
        
        try:
            # Gemini countTokens API
            response = self._client.models.count_tokens(
                model=model_name,
                contents=text
            )
            return response.total_tokens
        except Exception as e:
            logger.warning(f"countTokens API failed, using estimation: {e}")
            return self.estimate_tokens(text)

    async def check_budget_precise(self, prompt: str, context: Optional[Dict[str, Any]], model_name: str) -> Dict[str, Any]:
        """
        Pré-checagem PRECISA usando countTokens real.
        Use esta versão quando precisão for crítica (documentos grandes).
        """
        config = get_model_config(model_name)
        limit = config["context_window"]
        max_output = config.get("max_output", 4096)
        
        # Montar texto completo para contagem
        full_text = prompt
        if context:
            for key, value in context.items():
                if isinstance(value, str):
                    full_text += "\n" + value
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict) and "content" in item:
                            full_text += "\n" + str(item["content"])
                        else:
                            full_text += "\n" + str(item)
        
        # Contagem real
        total_input = await self.count_tokens_real(full_text, model_name)
        
        buffer = 1000
        available = limit - total_input - max_output - buffer
        usage_percent = (total_input / limit) * 100
        
        status = "ok"
        message = ""
        
        if available < 0:
            status = "error"
            message = (f"🚨 Estouro de tokens! Contagem real: {total_input:,}. "
                       f"Limite do modelo ({model_name}): {limit:,}. "
                       f"Por favor, remova anexos ou reduza o histórico.")
        elif usage_percent > 80:
            status = "warning"
            message = (f"⚠️ Atenção: Uso de tokens alto ({usage_percent:.1f}%). "
                       f"Restam ~{available:,} tokens.")

        return {
            "status": status,
            "message": message,
            "precise": True,
            "metrics": {
                "input_tokens": total_input,
                "context_window": limit,
                "max_output_reserved": max_output,
                "available_margin": available,
                "usage_percent": usage_percent
            }
        }


    def check_budget(self, prompt: str, context: Optional[Dict[str, Any]], model_name: str) -> Dict[str, Any]:
        """
        Realiza pré-checagem do orçamento de tokens.
        Retorna ditado com status, uso estimado e margem.
        """
        config = get_model_config(model_name)
        limit = config["context_window"]
        max_output = config.get("max_output", 4096)
        
        # 1. Estimar tokens do prompt atual
        prompt_tokens = self.estimate_tokens(prompt)
        
        # 2. Estimar tokens do contexto (histórico + docs anexados)
        context_tokens = 0
        if context:
            # Estimar tokens de strings no contexto
            for key, value in context.items():
                if isinstance(value, str):
                    context_tokens += self.estimate_tokens(value)
                elif isinstance(value, list): # ex: histórico de mensagens
                    for item in value:
                        if isinstance(item, dict) and "content" in item:
                             context_tokens += self.estimate_tokens(str(item["content"]))
                        else:
                             context_tokens += self.estimate_tokens(str(item))

        total_input_estimated = prompt_tokens + context_tokens
        
        # Margem de segurança: precisamos deixar espaço para a resposta (max_output)
        # e uma gordura de segurança (buffer)
        buffer = 1000 
        available = limit - total_input_estimated - max_output - buffer
        
        usage_percent = (total_input_estimated / limit) * 100
        
        status = "ok" # ok, warning, error
        message = ""
        
        if available < 0:
            status = "error"
            message = (f"Estouro de tokens! Estimado: {total_input_estimated}. "
                       f"Limite do modelo ({model_name}): {limit}. "
                       f"Por favor, remova anexos ou reduza o histórico.")
        elif usage_percent > 80:
            status = "warning"
            message = (f"Atenção: Uso de tokens alto ({usage_percent:.1f}%). "
                       f"Restam ~{available} tokens.")

        return {
            "status": status,
            "message": message,
            "metrics": {
                "input_estimated": total_input_estimated,
                "context_window": limit,
                "max_output_reserved": max_output,
                "available_margin": available,
                "usage_percent": usage_percent
            }
        }

    def get_telemetry(self, usage_metadata: Any, model_name: str) -> Dict[str, Any]:
        """
        Extrai telemetria real após resposta da API (Gemini/Vertex/OpenAI).
        Tenta normalizar diferentes formatos de 'usage_metadata'.
        """
        input_tokens = 0
        output_tokens = 0
        total_tokens = 0
        
        try:
            # Formato Google Generative AI / Vertex
            if hasattr(usage_metadata, "prompt_token_count"):
                input_tokens = usage_metadata.prompt_token_count
                output_tokens = usage_metadata.candidates_token_count
                total_tokens = usage_metadata.total_token_count
            # Formato OpenAI (dict)
            elif isinstance(usage_metadata, dict):
                 input_tokens = usage_metadata.get("prompt_tokens", 0)
                 output_tokens = usage_metadata.get("completion_tokens", 0)
                 total_tokens = usage_metadata.get("total_tokens", 0)
            
            config = get_model_config(model_name)
            limit = config["context_window"]
            
            return {
                "provider": config["provider"],
                "model": model_name,
                "usage": {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": total_tokens
                },
                "limits": {
                    "context_window": limit,
                    "percent_used": (total_tokens / limit * 100) if limit > 0 else 0
                }
            }
            
        except Exception as e:
            logger.warning(f"Erro ao processar telemetria de tokens: {e}")
            return {}
