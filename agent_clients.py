"""
Agent Clients - Wrappers for Multi-Model Agent Mode (v2.1)

This module provides standardized clients for calling OpenAI (GPT) and Anthropic (Claude)
as agents in the multi-model generation pipeline.

The Gemini 3 Pro acts as the "judge" and uses the existing LegalDrafter infrastructure.
"""

import os
import logging
import sys
import asyncio
from typing import Optional, Tuple, Dict, List, Any
from dataclasses import dataclass, field
from pathlib import Path
import json
import re

logger = logging.getLogger("AgentClients")

# ---------------------------------------------------------------------------
# Tenta reutilizar os prompts v2 do backend (LangGraph granular) quando o repo
# estiver disponível no mesmo workspace (defesa em profundidade / consistência).
# Se não conseguir importar, cai para os prompts locais deste arquivo.
# ---------------------------------------------------------------------------

_APPS_API_PATH = os.path.join(os.path.dirname(__file__), "apps", "api")
if os.path.isdir(_APPS_API_PATH) and _APPS_API_PATH not in sys.path:
    sys.path.insert(0, _APPS_API_PATH)

try:
    from app.services.ai.prompts.debate_prompts import (  # type: ignore
        PROMPT_JUIZ as V2_PROMPT_JUIZ,
        PROMPT_CRITICA as V2_PROMPT_CRITICA,
        PROMPT_REVISAO as V2_PROMPT_REVISAO,
        PROMPT_GPT_SYSTEM as V2_PROMPT_GPT_SYSTEM,
        PROMPT_CLAUDE_SYSTEM as V2_PROMPT_CLAUDE_SYSTEM,
        PROMPT_GEMINI_BLIND_SYSTEM as V2_PROMPT_GEMINI_BLIND_SYSTEM,
        PROMPT_GEMINI_JUDGE_SYSTEM as V2_PROMPT_GEMINI_JUDGE_SYSTEM,
        get_document_instructions as v2_get_document_instructions,
    )
except Exception:
    V2_PROMPT_JUIZ = None
    V2_PROMPT_CRITICA = None
    V2_PROMPT_REVISAO = None
    V2_PROMPT_GPT_SYSTEM = None
    V2_PROMPT_CLAUDE_SYSTEM = None
    V2_PROMPT_GEMINI_BLIND_SYSTEM = None
    V2_PROMPT_GEMINI_JUDGE_SYSTEM = None
    v2_get_document_instructions = None


def _extract_json_obj(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    s = text.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(json)?", "", s, flags=re.IGNORECASE).strip()
        s = re.sub(r"```$", "", s).strip()
    try:
        obj = json.loads(s)
        return obj if isinstance(obj, dict) else None
    except Exception:
        pass
    m = re.search(r"\{[\s\S]*\}", s)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


# =============================================================================
# MODEL CONSTANTS (DECEMBER 2025)
# =============================================================================

# Anthropic
CLAUDE_SONNET_4_5 = "claude-sonnet-4-5@20250929" 
CLAUDE_DEFAULT = CLAUDE_SONNET_4_5
ANTHROPIC_VERTEX_VERSION = os.getenv("ANTHROPIC_VERTEX_VERSION", "vertex-2023-10-16")

# Google
GEMINI_3_FLASH = "gemini-3-flash-preview"
GEMINI_3_PRO = "gemini-3-pro"
GEMINI_DEFAULT = GEMINI_3_FLASH

# OpenAI
GPT_5_2 = "gpt-5.2" 
GPT_DEFAULT = GPT_5_2

# =============================================================================
# CASE BUNDLE (PDF + Text Pack)
# =============================================================================

@dataclass
class CaseBundle:
    """
    Bundle contendo documentos-chave do caso para os agentes.
    
    Attributes:
        processo_id: Identificador do processo
        text_pack: Texto extraído com marcadores [DOC - X, p. Y]
        pdf_paths: Caminhos dos PDFs-chave (máx. 5-8 docs)
        pdf_file_ids: IDs de upload no provider (opcional)
        max_pages_per_doc: Limite de páginas por documento
    """
    processo_id: str
    text_pack: str = ""
    pdf_paths: List[str] = field(default_factory=list)
    pdf_file_ids: Dict[str, str] = field(default_factory=dict)  # {path: file_id}
    max_pages_per_doc: int = 50
    
    def get_text_prefix(self, max_chars: int = 50000) -> str:
        """Get text pack truncated to max_chars for agent prompt prefix"""
        if len(self.text_pack) <= max_chars:
            return self.text_pack
        return self.text_pack[:max_chars] + "\n\n[... texto truncado para limite de contexto ...]"
    
    def to_agent_context(self) -> str:
        """Format bundle as agent context with citation instructions"""
        return f"""## DOCUMENTOS-CHAVE DO PROCESSO: {self.processo_id}

{self.text_pack}

⚠️ REGRA OBRIGATÓRIA DE CITAÇÃO:
Ao mencionar qualquer fato, valor, data ou afirmação extraída dos documentos acima,
VOCÊ DEVE citar a fonte no formato: [TIPO - Doc. X, p. Y]
Exemplos: [LAUDO - Doc. SEI nº 12345, p. 3], [CONTRATO - Cláusula 5.2], [INICIAL - fls. 15]
"""

# =============================================================================
# CLIENT INITIALIZATION (Sync)
# =============================================================================

def init_openai_client():
    """Initialize OpenAI client for GPT agent (Sync)"""
    try:
        import openai
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.warning("⚠️ OPENAI_API_KEY não configurada. Agente GPT desabilitado.")
            return None
        return openai.OpenAI(api_key=api_key)
    except ImportError:
        logger.warning("⚠️ openai não instalado. pip install openai")
        return None

# =============================================================================
# ASYNC CLIENT SINGLETONS (Reusable)
# =============================================================================

import threading

_async_openai_client = None
_async_openai_lock = threading.Lock()

_async_anthropic_client = None
_async_anthropic_lock = threading.Lock()

def get_async_openai_client():
    """
    Returns a singleton AsyncOpenAI client.
    Thread-safe with double-checked locking.
    """
    global _async_openai_client
    if _async_openai_client is None:
        with _async_openai_lock:
            if _async_openai_client is None:
                try:
                    import openai
                    api_key = os.getenv("OPENAI_API_KEY")
                    if api_key:
                        _async_openai_client = openai.AsyncOpenAI(api_key=api_key)
                        logger.info("AsyncOpenAI client initialized.")
                    else:
                        logger.warning("⚠️ OPENAI_API_KEY não configurada.")
                except ImportError:
                    logger.warning("⚠️ openai não instalado.")
    return _async_openai_client

def get_async_anthropic_client():
    """
    Returns a singleton AsyncAnthropicVertex client.
    Thread-safe with double-checked locking.
    """
    global _async_anthropic_client
    if _async_anthropic_client is None:
        with _async_anthropic_lock:
            if _async_anthropic_client is None:
                try:
                    from anthropic import AsyncAnthropicVertex
                    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
                    region = os.getenv("VERTEX_AI_LOCATION", "us-east5")
                    if project_id:
                        _async_anthropic_client = AsyncAnthropicVertex(project_id=project_id, region=region)
                        logger.info("AsyncAnthropicVertex client initialized.")
                    else:
                        logger.warning("⚠️ GOOGLE_CLOUD_PROJECT não configurado.")
                except ImportError:
                    logger.warning("⚠️ anthropic não instalado.")
    return _async_anthropic_client


def init_anthropic_client():
    """Initialize Claude client via Vertex AI Model Garden"""
    try:
        from anthropic import AnthropicVertex
        project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        region = os.getenv("VERTEX_AI_LOCATION", "global")
        
        if not project_id:
            logger.warning("⚠️ GOOGLE_CLOUD_PROJECT não configurado. Agente Claude desabilitado.")
            return None
        
        return AnthropicVertex(project_id=project_id, region=region)
    except ImportError:
        logger.warning("⚠️ anthropic não instalado. pip install anthropic[vertex]")
        return None


def init_gemini_client():
    """Initialize Google GenAI client for Gemini models"""
    try:
        from google import genai
        api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if not api_key:
            logger.warning("⚠️ GOOGLE_API_KEY não configurada. Agente Gemini desabilitado.")
            return None
        return genai.Client(api_key=api_key)
    except ImportError:
        logger.warning("⚠️ google-genai não instalado. pip install google-genai")
        return None


def init_vertex_client():
    """Initialize Vertex AI SDK for Gemini models"""
    try:
        import vertexai
        project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        location = os.getenv("VERTEX_AI_LOCATION", "us-east5")
        
        if not project_id:
            logger.warning("⚠️ GOOGLE_CLOUD_PROJECT não configurado. Vertex AI desabilitado.")
            return None
            
        vertexai.init(project=project_id, location=location)
        return True # Vertex AI uses global state
    except ImportError:
        logger.warning("⚠️ google-cloud-aiplatform não instalado. pip install google-cloud-aiplatform")
        return None


# =============================================================================
# METRICS TRACKING
# =============================================================================

from dataclasses import dataclass, field
from typing import Dict, List
import time
import hashlib
import json

@dataclass
class AgentMetrics:
    """Track API call metrics for cost analysis"""
    calls: List[Dict] = field(default_factory=list)
    
    def record(self, provider: str, model: str, input_tokens: int, output_tokens: int, 
               latency_ms: int, success: bool, timeout: bool = False):
        self.calls.append({
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "provider": provider,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "latency_ms": latency_ms,
            "success": success,
            "timeout": timeout
        })
    
    def total_tokens(self) -> Dict[str, int]:
        """Get total tokens by provider"""
        totals = {}
        for call in self.calls:
            provider = call["provider"]
            if provider not in totals:
                totals[provider] = {"input": 0, "output": 0}
            totals[provider]["input"] += call["input_tokens"]
            totals[provider]["output"] += call["output_tokens"]
        return totals
    
    def estimated_cost_usd(self) -> float:
        """Estimate cost based on typical pricing"""
        # Approximate pricing per 1M tokens
        pricing = {
            "openai": {"input": 2.50, "output": 10.00},  # GPT-4o
            "anthropic": {"input": 3.00, "output": 15.00},  # Claude Sonnet
            "gemini": {"input": 0.075, "output": 0.30}  # Gemini Pro
        }
        total = 0.0
        for call in self.calls:
            provider = call["provider"]
            if provider in pricing:
                total += (call["input_tokens"] / 1_000_000) * pricing[provider]["input"]
                total += (call["output_tokens"] / 1_000_000) * pricing[provider]["output"]
        return round(total, 4)
    
    def save(self, path: str):
        """Save metrics to JSON file"""
        with open(path, 'w', encoding='utf-8') as f:
            json.dump({
                "calls": self.calls,
                "totals": self.total_tokens(),
                "estimated_cost_usd": self.estimated_cost_usd()
            }, f, indent=2, ensure_ascii=False)

# Global metrics instance
agent_metrics = AgentMetrics()

# =============================================================================
# CRITIQUE CACHE
# =============================================================================

_critique_cache: Dict[str, str] = {}
CACHE_TTL_SECONDS = 3600  # 1 hour

def _cache_key(prompt: str) -> str:
    """Generate cache key from prompt hash"""
    return hashlib.sha256(prompt.encode()).hexdigest()[:16]

def get_cached_critique(prompt: str) -> Optional[str]:
    """Get cached critique if available"""
    key = _cache_key(prompt)
    return _critique_cache.get(key)

def set_cached_critique(prompt: str, critique: str):
    """Cache a critique response"""
    key = _cache_key(prompt)
    _critique_cache[key] = critique

# =============================================================================
# AGENT CALLS (with timeout and metrics)
# =============================================================================

API_TIMEOUT_SECONDS = 60

def call_openai(
    client,
    prompt: str,
    model: str = "gpt-4o",
    max_tokens: int = 4000,
    temperature: float = 0.3,
    timeout: int = API_TIMEOUT_SECONDS,
    web_search: bool = False
) -> Optional[str]:
    """
    Call OpenAI GPT model as an agent with timeout and metrics.
    """
    if not client:
        return None
    
    start_time = time.time()
    input_tokens = len(prompt) // 4  # Approximate
    
    try:
        tools = []
        if web_search:
            # ⚠️ WARNING: Web search is simulated/stub - NOT ACTUALLY EXECUTED
            # This can cause "false grounding" where the model thinks it has access
            # to web results but actually doesn't. Use with caution or implement properly.
            logger.warning("⚠️ web_search=True: Ferramenta simulada, não executa busca real. Pode causar falsa sensação de grounding.")
            tools.append({"type": "web_search"})
            
        kwargs = {
            "model": model,
            "messages": [
                {"role": "system", "content": "Você é um advogado jurídico sênior brasileiro. Responda sempre em português formal jurídico. REGRA OBRIGATÓRIA: Ao citar fatos dos autos, USE SEMPRE o formato [TIPO - Doc. X, p. Y]."},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "timeout": timeout
        }
        
        if tools:
            kwargs["tools"] = tools

        response = client.chat.completions.create(**kwargs)
        output_text = response.choices[0].message.content
        output_tokens = len(output_text) // 4 if output_text else 0
        
        agent_metrics.record(
            provider="openai", model=model,
            input_tokens=input_tokens, output_tokens=output_tokens,
            latency_ms=int((time.time() - start_time) * 1000),
            success=True
        )
        return output_text
    except Exception as e:
        # Tenta capturar erros específicos se a lib estiver disponível
        err_type = type(e).__name__
        if "Timeout" in err_type:
            logger.warning(f"⏱️ Timeout (OpenAI): {e}")
            timeout_flag = True
        else:
            logger.error(f"❌ Erro OpenAI ({err_type}): {e}")
            timeout_flag = False
            
        agent_metrics.record(
            provider="openai", model=model,
            input_tokens=input_tokens, output_tokens=0,
            latency_ms=int((time.time() - start_time) * 1000),
            success=False, timeout=timeout_flag
        )
        return None


def call_anthropic(
    client,
    prompt: str,
    model: str = CLAUDE_DEFAULT,
    max_tokens: int = 4000,
    temperature: float = 0.3,
    timeout: int = API_TIMEOUT_SECONDS,
    web_search: bool = False
) -> Optional[str]:
    """
    Call Anthropic Claude model as an agent with timeout and metrics.
    """
    if not client:
        return None
    
    start_time = time.time()
    input_tokens = len(prompt) // 4
    
    try:
        tools = []
        if web_search:
            # 2025 Explicit Web Search Tool Definition
            tools.append({
                "name": "web_search",
                "description": "Realiza buscas na internet para obter informações atuais sobre leis, jurisprudência e fatos recentes.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "O termo de busca otimizado"}
                    },
                    "required": ["query"]
                }
            })
            
        is_vertex = client.__class__.__name__ == "AnthropicVertex"

        kwargs = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "system": "Você é um advogado jurídico sênior brasileiro. Responda sempre em português formal jurídico. REGRA OBRIGATÓRIA: Ao citar fatos dos autos, USE SEMPRE o formato [TIPO - Doc. X, p. Y].",
        }

        if is_vertex:
            kwargs["anthropic_version"] = ANTHROPIC_VERTEX_VERSION
        else:
            kwargs["timeout"] = timeout
        
        if tools and not is_vertex:
            kwargs["tools"] = tools

        response = client.messages.create(**kwargs)
        
        # Checking for tool use (Stub implementation - in a real agent loop we would execute and recurse)
        # For now, we return the text content if available, or a note if it wanted to search
        
        if response.content and response.content[0].type == 'text':
             output_text = response.content[0].text
        elif any(block.type == 'tool_use' for block in response.content):
             # Simulating tool execution message for this single-shot implementation
             output_text = "[Nota do Sistema: O agente solicitou uma busca web, mas a execução real de ferramentas multi-etapa requer o 'Agent Loop' completo. Retornando resposta base baseada no conhecimento interno.]"
             # In a full implementation, we would execute web_search(query) and append result to context.
        else:
             output_text = ""

        output_tokens = len(output_text) // 4 if output_text else 0
        
        agent_metrics.record(
            provider="vertex-anthropic" if is_vertex else "anthropic", model=model,
            input_tokens=input_tokens, output_tokens=output_tokens,
            latency_ms=int((time.time() - start_time) * 1000),
            success=True
        )
        return output_text
    except Exception as e:
        err_type = type(e).__name__
        if "Timeout" in err_type:
             logger.warning(f"⏱️ Timeout (Anthropic): {e}")
             timeout_flag = True
        else:
             logger.error(f"❌ Erro Anthropic ({err_type}): {e}")
             timeout_flag = False

        agent_metrics.record(
            provider="anthropic", model=model,
            input_tokens=input_tokens, output_tokens=0,
            latency_ms=int((time.time() - start_time) * 1000),
            success=False, timeout=timeout_flag
        )
        return None


async def call_openai_async(
    client,
    prompt: str,
    model: str = "gpt-5-mini",
    max_tokens: int = 4000,
    temperature: float = 0.3,
    timeout: int = API_TIMEOUT_SECONDS,
    web_search: bool = False
) -> Optional[str]:
    """Async version using singleton AsyncOpenAI client"""
    start_time = time.time()
    input_tokens = len(prompt) // 4
    
    # Use singleton async client (preferred) or fallback to passed client
    aclient = get_async_openai_client()
    if not aclient:
        # Fallback: try to use passed client if it's async-compatible
        if client and hasattr(client, 'chat') and hasattr(client.chat, 'completions'):
            aclient = client
        else:
            logger.error("No async OpenAI client available")
            return None
    
    try:
        from openai import APITimeoutError, APIError
    except ImportError:
        logger.error("openai lib missing")
        return None

    try:
        tools = []
        if web_search:
            tools.append({"type": "web_search"})
            
        kwargs = {
            "model": model,
            "messages": [
                {"role": "system", "content": "Você é um advogado jurídico sênior brasileiro. Responda sempre em português formal jurídico. REGRA OBRIGATÓRIA: Ao citar fatos dos autos, USE SEMPRE o formato [TIPO - Doc. X, p. Y]."},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "timeout": timeout
        }
        if tools: kwargs["tools"] = tools

        response = await aclient.chat.completions.create(**kwargs)
        output_text = response.choices[0].message.content
        
        output_tokens = len(output_text) // 4 if output_text else 0
        agent_metrics.record(
            provider="openai", model=model,
            input_tokens=input_tokens, output_tokens=output_tokens,
            latency_ms=int((time.time() - start_time) * 1000),
            success=True
        )
        return output_text

    except APITimeoutError:
        logger.warning(f"⏱️ Async Timeout OpenAI")
        agent_metrics.record("openai", model, input_tokens, 0, timeout*1000, False, True)
        return None
    except Exception as e:
        logger.error(f"❌ Async Error OpenAI: {e}")
        agent_metrics.record("openai", model, input_tokens, 0, int((time.time()-start_time)*1000), False)
        return None


async def call_anthropic_async(
    client,
    prompt: str,
    model: str = "claude-sonnet-4-20250514",
    max_tokens: int = 4000,
    temperature: float = 0.3,
    timeout: int = API_TIMEOUT_SECONDS,
    web_search: bool = False
) -> Optional[str]:
    """Async version using singleton AsyncAnthropicVertex client"""
    start_time = time.time()
    input_tokens = len(prompt) // 4
    
    # Use singleton async client (preferred) or fallback
    aclient = get_async_anthropic_client()
    if not aclient:
        # Fallback: try passed client if async-compatible
        if client and hasattr(client, 'messages'):
            aclient = client
        else:
            logger.error("No async Anthropic client available")
            return None
    
    try:
        from anthropic import APITimeoutError
    except ImportError:
         logger.error("anthropic lib missing")
         return None

    try:
        tools = []
        if web_search:
             tools.append({
                "name": "web_search",
                "description": "Realiza buscas na internet.",
                "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}
            })

        kwargs = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
            "system": "Você é um advogado jurídico sênior brasileiro. Responda sempre em português formal jurídico. REGRA OBRIGATÓRIA: Ao citar fatos dos autos, USE SEMPRE o formato [TIPO - Doc. X, p. Y].",
            "timeout": timeout
        }
        if tools: kwargs["tools"] = tools

        response = await aclient.messages.create(**kwargs)
        
        if response.content and response.content[0].type == 'text':
             output_text = response.content[0].text
        else:
             output_text = ""

        output_tokens = len(output_text) // 4 if output_text else 0
        agent_metrics.record(
            provider="anthropic", model=model,
            input_tokens=input_tokens, output_tokens=output_tokens,
            latency_ms=int((time.time() - start_time) * 1000),
            success=True
        )
        return output_text
        
    except APITimeoutError:
        logger.warning(f"⏱️ Async Timeout Anthropic")
        agent_metrics.record("anthropic", model, input_tokens, 0, timeout*1000, False, True)
        return None
    except Exception as e:
        logger.error(f"❌ Async Error Anthropic: {e}")
        agent_metrics.record("anthropic", model, input_tokens, 0, int((time.time()-start_time)*1000), False)
        return None

# ... (Vertex Gemini Async wrapper also needs update, checking below ...)

def call_vertex_gemini(
    client_placeholder,
    prompt: str,
    model: str = "gemini-experimental",
    max_tokens: int = 8192,
    temperature: float = 0.3,
    timeout: int = API_TIMEOUT_SECONDS,
    web_search: bool = False
) -> Optional[str]:
    """
    Call Vertex AI Gemini model.
    """
    try:
        from vertexai.preview.generative_models import GenerativeModel, Tool
        # ... (rest of implementation)
        
        tools_config = []
        if web_search:
            # 2025 Native Grounding
            tools_config = [
                Tool.from_google_search_retrieval(
                    google_search_retrieval=vertexai.preview.generative_models.grounding.GoogleSearchRetrieval()
                )
            ]

        gemini = GenerativeModel(model)
        response = gemini.generate_content(
            prompt,
            generation_config={"max_output_tokens": max_tokens, "temperature": temperature},
            tools=tools_config
        )
        return response.text
    except Exception as e:
        logger.error(f"❌ Erro ao chamar Vertex Gemini: {e}")
        return None

async def call_vertex_gemini_async(
    client_placeholder,
    prompt: str,
    model: str = "gemini-experimental",
    max_tokens: int = 8192,
    temperature: float = 0.3,
    timeout: int = API_TIMEOUT_SECONDS,
    web_search: bool = False
) -> Optional[str]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        lambda: call_vertex_gemini(client_placeholder, prompt, model, max_tokens, temperature, timeout, web_search)
    )
# JUDGE PROMPT TEMPLATE
# =============================================================================

PROMPT_JUIZ = """
Você é um Desembargador Sênior revisando TRÊS versões da seção "{{ titulo_secao }}" de uma peça jurídica.

## VERSÃO A (GPT):
{{ versao_a }}

## VERSÃO B (Claude):
{{ versao_b }}

## VERSÃO C (Gemini):
{{ versao_c }}

## CONTEXTO FACTUAL (RAG - VERDADE ABSOLUTA):
{{ rag_context }}

## INSTRUÇÕES RIGOROSAS:
1. **ESCOLHA** a melhor versão OU **MESCLE** os melhores trechos das três.
2. **PRESERVE OBRIGATORIAMENTE** todas as citações no formato [TIPO - Doc. X, p. Y].
3. **NÃO INVENTE** fatos, leis, súmulas ou jurisprudência não presentes no contexto RAG.
4. **MANTENHA** o tom jurídico técnico e formal.
5. Para cada divergência, **CITE TRECHOS** (máx. 50 palavras cada) das versões relevantes.

## FORMATO DE RESPOSTA:

### VERSÃO FINAL
[Texto consolidado da seção aqui]

### LOG DE DIVERGÊNCIAS

#### Divergência 1: [Tema]
- **Quote GPT:** "[trecho de até 50 palavras]"
- **Quote Claude:** "[trecho de até 50 palavras]"
- **Quote Gemini:** "[trecho de até 50 palavras]"
- **Decisão:** [Escolhi X porque...]
- **Risco/Pendência:** [Se aplicável: "Confirmar no Doc. Y"]

#### Divergência 2: [Tema]
[mesmo formato]

### TRECHOS REMOVIDOS POR FALTA DE SUPORTE
- [Se houver afirmações sem base nos autos/RAG]

### CITAÇÕES OBRIGATÓRIAS PENDENTES
- [Itens que exigem citação nos autos para validação]
"""


# =============================================================================
# CRITIQUE PROMPT TEMPLATE
# =============================================================================

PROMPT_CRITICA = """
Você é um revisor jurídico técnico. Analise o texto abaixo e produza uma CRÍTICA LIVRE, objetiva e acionável.

## TEXTO A REVISAR:
{{ texto_colega }}

## CONTEXTO FACTUAL (RAG):
{{ rag_context }}

## FOQUE EM:
1. Afirmações sem suporte nos documentos-chave
2. Contradições internas
3. Pontos processuais omitidos
4. Teses fracas ou mal fundamentadas
5. Pedidos incoerentes com a narrativa

## REGRAS:
- **NÃO** critique estilo ou retórica.
- **NÃO** reescreva a peça inteira.
- Aponte trechos problemáticos por citação curta ("no parágrafo X...").
- Sugira correções objetivas.

## SUA CRÍTICA:
[Parágrafos curtos com bullets quando necessário]
"""


# =============================================================================
# REVISION PROMPT TEMPLATE  
# =============================================================================

PROMPT_REVISAO = """
Você é o autor original do texto abaixo. Recebeu uma crítica técnica de um colega revisor.

## SEU TEXTO ORIGINAL:
{{ texto_original }}

## CRÍTICA RECEBIDA:
{{ critica_recebida }}

## CONTEXTO FACTUAL (RAG):
{{ rag_context }}

## INSTRUÇÕES:
1. **INCORPORE** apenas críticas fundamentadas (com justificativa válida).
2. **IGNORE** críticas de estilo ou preferência pessoal.
3. **PRESERVE** todas as citações no formato [TIPO - Doc. X, p. Y].
4. **NÃO INVENTE** fatos ou jurisprudência não presentes no RAG.
5. Quando possível, aponte no texto onde está o suporte documental.

## SUA VERSÃO REVISADA:
[Texto melhorado incorporando as críticas válidas]
"""


# =============================================================================
# AGENT MODE ORCHESTRATION
# =============================================================================

def generate_section_agent_mode(
    section_title: str,
    prompt_base: str,
    rag_context: str,
    rag_local_context: str,
    drafter,  # LegalDrafter instance (Gemini - Judge)
    gpt_client,
    claude_client,
    gpt_model: str = "gpt-4o",
    claude_model: str = "claude-sonnet-4-20250514",
    parallel: bool = False
) -> Tuple[str, str, dict]:
    """
    Generate section using multi-agent committee with debate + judge.
    
    Flow:
    1. GPT generates v1 (Version A)
    2. Claude generates v1 (Version B)
    3. Gemini generates v1 (Version C) - NEW
    4. Judge (Gemini) consolidates vA, vB, vC
    
    Args:
        gpt_client: OpenAI client
        claude_client: Anthropic client
        gpt_model: GPT model name
        claude_model: Claude model name
        parallel: Whether to run agents in parallel (requires asyncio)
        
    Returns:
        Tuple of (final_text, divergencias_md, drafts_dict)
    """
    from jinja2 import Template
    
    # Build agent prompt (without full PDFs, only RAG extracts)
    agent_prompt = f"{prompt_base}\n\n{rag_context}\n\n{rag_local_context}"
    
    drafts = {}
    
    # =========================================================================
    # ROUND 1: Initial Generation
    # =========================================================================
    print(f"   🤖 [R1] Agente GPT gerando versão inicial...")
    versao_gpt_v1 = call_openai(gpt_client, agent_prompt, model=gpt_model)
    drafts['gpt_v1'] = versao_gpt_v1 or "[Agente GPT não disponível]"
    
    print(f"   🤖 [R1] Agente Claude gerando versão inicial...")
    versao_claude_v1 = call_anthropic(claude_client, agent_prompt, model=claude_model)
    drafts['claude_v1'] = versao_claude_v1 or "[Agente Claude não disponível]"
    
    # New: Gemini (Drafter) generates its own draft
    print(f"   🤖 [R1] Agente Gemini gerando versão inicial...")
    gemini_resp = drafter._generate_with_retry(agent_prompt)
    versao_gemini_v1 = gemini_resp.text if gemini_resp else "[Agente Gemini falhou]"
    drafts['gemini_v1'] = versao_gemini_v1
    
    # Check if we have at least one valid draft
    valid_drafts = [d for d in [versao_gpt_v1, versao_claude_v1] if d]
    
    if len(valid_drafts) == 0:
        print(f"   ⚠️ Nenhum agente disponível. Usando Gemini diretamente.")
        response = drafter._generate_with_retry(agent_prompt)
        return response.text if response else "", "", drafts
    
    if len(valid_drafts) == 1:
        print(f"   ⚠️ Apenas 1 agente disponível. Sem debate.")
        return valid_drafts[0], "", drafts
    
    full_rag = f"{rag_context}\n{rag_local_context}"
    
    # =========================================================================
    # ROUND 2: Cross-Critique (Free-form)
    # =========================================================================
    t_critica = Template(PROMPT_CRITICA)
    
    # GPT criticizes Claude's draft
    print(f"   💬 [R2] GPT criticando draft do Claude...")
    critica_gpt_prompt = t_critica.render(texto_colega=versao_claude_v1, rag_context=full_rag)
    critica_gpt = call_openai(gpt_client, critica_gpt_prompt, model=gpt_model)
    drafts['critica_gpt_on_claude'] = critica_gpt or ""
    
    # Claude criticizes GPT's draft
    print(f"   💬 [R2] Claude criticando draft do GPT...")
    critica_claude_prompt = t_critica.render(texto_colega=versao_gpt_v1, rag_context=full_rag)
    critica_claude = call_anthropic(claude_client, critica_claude_prompt, model=claude_model)
    drafts['critica_claude_on_gpt'] = critica_claude or ""
    
    # =========================================================================
    # ROUND 3: Revision (incorporate valid critiques)
    # =========================================================================
    t_revisao = Template(PROMPT_REVISAO)
    
    # GPT revises based on Claude's critique
    print(f"   ✏️ [R3] GPT revisando com críticas do Claude...")
    if critica_claude:
        rev_gpt_prompt = t_revisao.render(
            texto_original=versao_gpt_v1,
            critica_recebida=critica_claude,
            rag_context=full_rag
        )
        versao_gpt_v2 = call_openai(gpt_client, rev_gpt_prompt, model=gpt_model)
    else:
        versao_gpt_v2 = versao_gpt_v1
    drafts['gpt_v2'] = versao_gpt_v2 or versao_gpt_v1
    
    # Claude revises based on GPT's critique
    print(f"   ✏️ [R3] Claude revisando com críticas do GPT...")
    if critica_gpt:
        rev_claude_prompt = t_revisao.render(
            texto_original=versao_claude_v1,
            critica_recebida=critica_gpt,
            rag_context=full_rag
        )
        versao_claude_v2 = call_anthropic(claude_client, rev_claude_prompt, model=claude_model)
    else:
        versao_claude_v2 = versao_claude_v1
    drafts['claude_v2'] = versao_claude_v2 or versao_claude_v1
    
    # Use revised versions for judge
    final_gpt = versao_gpt_v2 or versao_gpt_v1
    final_claude = versao_claude_v2 or versao_claude_v1
    
    # =========================================================================
    # ROUND 4: Judge Consolidation with Quotes
    # =========================================================================
    print(f"   ⚖️ [R4] Juiz (Gemini) consolidando com log de divergências...")
    
    t = Template(PROMPT_JUIZ)
    judge_prompt = t.render(
        titulo_secao=section_title,
        versao_a=final_gpt,
        versao_b=final_claude,
        rag_context=full_rag
    )
    
    judge_response = drafter._generate_with_retry(judge_prompt)
    
    if not judge_response or not judge_response.text:
        return final_gpt, "", drafts
    
    # Parse judge response (new format with LOG DE DIVERGÊNCIAS)
    full_response = judge_response.text
    import re
    
    # Normalize headers for robustness
    # Regex to find "### VERSÃO FINAL" case insensitive
    match_final = re.search(r'###\s*VERS[ÃA]O\s*FINAL', full_response, re.IGNORECASE)
    
    # Regex to find "### LOG DE DIVERGÊNCIAS" or "### DIVERGÊNCIAS" case insensitive
    match_log = re.search(r'###\s*(LOG\s*DE\s*)?DIVERG[ÊE]NCIAS', full_response, re.IGNORECASE)
    
    final_text = ""
    log_section = ""

    if match_final:
        start_final = match_final.end()
        # If log section exists, end final text there
        if match_log:
            end_final = match_log.start()
            final_text = full_response[start_final:end_final].strip()
            log_section = full_response[match_log.end():].strip()
        else:
            final_text = full_response[start_final:].strip()
    else:
        # Fallback if "VERSÃO FINAL" header is missing
        if match_log:
             final_text = full_response[:match_log.start()].strip()
             log_section = full_response[match_log.end():].strip()
        else:
             final_text = full_response.strip()

    # Build full divergencias log with critique summaries
    divergencias_completo = f"""## Seção: {section_title}

### Críticas Cruzadas
**GPT sobre Claude:** {(critica_gpt or 'N/A')[:500]}...

**Claude sobre GPT:** {(critica_claude or 'N/A')[:500]}...

{log_section}
"""
    
    return final_text, divergencias_completo, drafts


# =============================================================================
# ASYNC ORCHESTRATION (Parallel Execution)
# =============================================================================

async def generate_section_agent_mode_async(
    section_title: str,
    prompt_base: str,
    case_bundle: "CaseBundle",
    rag_local_context: str,
    drafter: Any,
    gpt_client,
    claude_client,
    gpt_model: str = GPT_DEFAULT,
    claude_model: str = CLAUDE_DEFAULT,
    reasoning_level: str = "medium",
    web_search: bool = False,
    thesis: Optional[str] = None,
    formatting_options: Optional[Dict[str, bool]] = None,
    template_structure: Optional[str] = None,
    extra_agent_instructions: Optional[str] = None,
    mode: Optional[str] = None,
    previous_sections: Optional[List[str]] = None,
    judge_model: Optional[str] = None
) -> Tuple[str, str, Dict[str, str]]:
    
    start_time = time.time()
    
    # Preparar contexto extendido
    full_rag = f"{rag_local_context}\n\n{case_bundle.get_text_prefix()}"
    
    # Inject Instructions
    reasoning_instruction = ""
    if reasoning_level == "high":
        reasoning_instruction = "\n[INSTRUÇÃO: Analise profundamente doutrina e jurisprudência antes de escrever. Seja exaustivo.]"
    elif reasoning_level == "low":
        reasoning_instruction = "\n[INSTRUÇÃO: Seja direto e objetivo.]"
        
    web_search_context = ""
    if web_search:
        web_search_context = "\n[INSTRUÇÃO: Considere fatos recentes e pesquisa web se disponível.]"
        
    enhanced_prompt_base = f"{prompt_base}{reasoning_instruction}{web_search_context}"
    
    # R1: Draft (Parallel Generation)
    print(f"   🚀 [R1] Gerando drafts iniciais em paralelo...")
    """
    Async version with parallel execution of GPT and Claude calls.
    Uses CaseBundle for robust document context + formatted citations.
    ~50% faster than sequential version.
    """
    from jinja2 import Template
    
    # Build robust context from bundle + local RAG
    bundle_context = case_bundle.to_agent_context()
    extra_instructions = ""
    if thesis:
        extra_instructions += f"\n## TESE/INSTRUÇÕES ESPECÍFICAS:\n{thesis}\n"
    if template_structure:
        extra_instructions += f"\n## MODELO DE ESTRUTURA:\n{template_structure}\n"
    if formatting_options:
        extra_instructions += "\n## DIRETRIZES DE FORMATAÇÃO ADICIONAIS:\n"
        if formatting_options.get('include_toc'):
            extra_instructions += "- OBRIGATÓRIO: Incluir Sumário (TOC) no início do documento.\n"
        if formatting_options.get('include_summaries'):
            extra_instructions += "- OBRIGATÓRIO: Incluir breves resumos no início de cada seção principal.\n"
        if formatting_options.get('include_summary_table'):
            extra_instructions += "- OBRIGATÓRIO: Incluir Tabela de Síntese ao final do documento.\n"
    if extra_agent_instructions:
        extra_instructions += f"\n{extra_agent_instructions}\n"

    agent_prompt = f"{prompt_base}\n\n{extra_instructions}\n\n{bundle_context}\n\n## CONTEXTO ADICIONAL (RAG LOCAL):\n{rag_local_context}"
    full_rag = f"{bundle_context}\n{rag_local_context}"
    drafts = {}

    # Seleciona prompts v2 (preferido) ou fallback local
    from jinja2 import Template
    doc_type = (mode or "PETICAO").upper()
    instrucoes = v2_get_document_instructions(doc_type) if v2_get_document_instructions else {"tom": "técnico", "foco": "clareza", "estrutura": "introdução, desenvolvimento, conclusão"}
    sys_gpt = Template(V2_PROMPT_GPT_SYSTEM).render(tipo_documento=doc_type, instrucoes=instrucoes) if V2_PROMPT_GPT_SYSTEM else ""
    sys_claude = Template(V2_PROMPT_CLAUDE_SYSTEM).render(tipo_documento=doc_type, instrucoes=instrucoes) if V2_PROMPT_CLAUDE_SYSTEM else ""
    sys_gemini_blind = Template(V2_PROMPT_GEMINI_BLIND_SYSTEM).render(tipo_documento=doc_type, instrucoes=instrucoes) if V2_PROMPT_GEMINI_BLIND_SYSTEM else ""
    sys_gemini_judge = Template(V2_PROMPT_GEMINI_JUDGE_SYSTEM).render(tipo_documento=doc_type, instrucoes=instrucoes) if V2_PROMPT_GEMINI_JUDGE_SYSTEM else ""
    
    # R1: Parallel Draft Generation
    print(f"   🤖 [R1] Gerando drafts em paralelo...")
    versao_gpt_v1, versao_claude_v1 = await asyncio.gather(
        call_openai_async(gpt_client, f"{sys_gpt}\n\n{agent_prompt}", model=gpt_model),
        call_anthropic_async(claude_client, f"{sys_claude}\n\n{agent_prompt}", model=claude_model)
    )
    drafts['gpt_v1'] = versao_gpt_v1 or "[GPT não disponível]"
    drafts['claude_v1'] = versao_claude_v1 or "[Claude não disponível]"
    
    # Gemini blind (opcional, mas mantém padrão do comitê)
    try:
        gemini_prompt = f"{sys_gemini_blind}\n\n{agent_prompt}" if sys_gemini_blind else agent_prompt
        gemini_resp = drafter._generate_with_retry(gemini_prompt)
        versao_gemini_v1 = gemini_resp.text if gemini_resp else ""
    except Exception:
        versao_gemini_v1 = ""
    drafts["gemini_v1"] = versao_gemini_v1 or "[Gemini não disponível]"
    
    valid_drafts = [d for d in [versao_gpt_v1, versao_claude_v1] if d]
    if len(valid_drafts) < 2:
        return valid_drafts[0] if valid_drafts else "", "", drafts
    
    # R2: Parallel Critique
    print(f"   💬 [R2] Críticas cruzadas em paralelo...")
    t_critica = Template(V2_PROMPT_CRITICA) if V2_PROMPT_CRITICA else Template(PROMPT_CRITICA)
    if V2_PROMPT_CRITICA:
        critica_gpt_prompt = t_critica.render(texto_colega=versao_claude_v1, rag_context=full_rag, tipo_documento=doc_type, tese=thesis or "", instrucoes=instrucoes)
        critica_claude_prompt = t_critica.render(texto_colega=versao_gpt_v1, rag_context=full_rag, tipo_documento=doc_type, tese=thesis or "", instrucoes=instrucoes)
    else:
        critica_gpt_prompt = t_critica.render(texto_colega=versao_claude_v1, rag_context=full_rag)
        critica_claude_prompt = t_critica.render(texto_colega=versao_gpt_v1, rag_context=full_rag)
    
    # Check cache first
    critica_gpt = get_cached_critique(critica_gpt_prompt)
    critica_claude = get_cached_critique(critica_claude_prompt)
    
    if not critica_gpt or not critica_claude:
        results = await asyncio.gather(
            call_openai_async(gpt_client, critica_gpt_prompt, model=gpt_model) if not critica_gpt else asyncio.coroutine(lambda: critica_gpt)(),
            call_anthropic_async(claude_client, critica_claude_prompt, model=claude_model) if not critica_claude else asyncio.coroutine(lambda: critica_claude)()
        )
        critica_gpt = critica_gpt or results[0]
        critica_claude = critica_claude or results[1]
        
        # Cache the critiques
        if critica_gpt:
            set_cached_critique(critica_gpt_prompt, critica_gpt)
        if critica_claude:
            set_cached_critique(critica_claude_prompt, critica_claude)
    
    drafts['critica_gpt_on_claude'] = critica_gpt or ""
    drafts['critica_claude_on_gpt'] = critica_claude or ""
    
    # R3: Parallel Revision
    print(f"   ✏️ [R3] Revisões em paralelo...")
    t_revisao = Template(V2_PROMPT_REVISAO) if V2_PROMPT_REVISAO else Template(PROMPT_REVISAO)
    if V2_PROMPT_REVISAO:
        rev_gpt_prompt = t_revisao.render(texto_original=versao_gpt_v1, critica_recebida=critica_claude or "", rag_context=full_rag, tipo_documento=doc_type, tese=thesis or "", instrucoes=instrucoes)
        rev_claude_prompt = t_revisao.render(texto_original=versao_claude_v1, critica_recebida=critica_gpt or "", rag_context=full_rag, tipo_documento=doc_type, tese=thesis or "", instrucoes=instrucoes)
    else:
        rev_gpt_prompt = t_revisao.render(texto_original=versao_gpt_v1, critica_recebida=critica_claude or "", rag_context=full_rag)
        rev_claude_prompt = t_revisao.render(texto_original=versao_claude_v1, critica_recebida=critica_gpt or "", rag_context=full_rag)
    
    versao_gpt_v2, versao_claude_v2 = await asyncio.gather(
        call_openai_async(gpt_client, rev_gpt_prompt, model=gpt_model),
        call_anthropic_async(claude_client, rev_claude_prompt, model=claude_model)
    )
    drafts['gpt_v2'] = versao_gpt_v2 or versao_gpt_v1
    drafts['claude_v2'] = versao_claude_v2 or versao_claude_v1
    
    final_gpt = versao_gpt_v2 or versao_gpt_v1
    final_claude = versao_claude_v2 or versao_claude_v1
    
    # R4: Judge (sync, uses Gemini context cache)
    print(f"   ⚖️ [R4] Juiz consolidando...")
    secoes_anteriores = "\n\n".join(previous_sections or []) if previous_sections else "(Esta é a primeira seção)"

    diretrizes_formatacao = ""
    if formatting_options:
        if formatting_options.get("include_toc"):
            diretrizes_formatacao += "- Incluir sumário (TOC) quando aplicável.\n"
        if formatting_options.get("include_summaries"):
            diretrizes_formatacao += "- Incluir resumos curtos no início de seções principais.\n"
        if formatting_options.get("include_summary_table"):
            diretrizes_formatacao += "- Incluir tabela de síntese ao final.\n"
    if not diretrizes_formatacao:
        diretrizes_formatacao = "(sem diretrizes adicionais)"
    modelo_estrutura = template_structure or "(sem modelo de estrutura)"
    if V2_PROMPT_JUIZ:
        t = Template(V2_PROMPT_JUIZ)
        judge_prompt = t.render(
            titulo_secao=section_title,
            tese=thesis or "",
            secoes_anteriores=secoes_anteriores,
            versao_a=final_gpt,
            versao_b=final_claude,
            versao_c=drafts.get("gemini_v1", ""),
            rag_context=full_rag,
            tipo_documento=doc_type,
            instrucoes=instrucoes,
            diretrizes_formatacao=diretrizes_formatacao,
            modelo_estrutura=modelo_estrutura
        )
        full_judge_prompt = f"{sys_gemini_judge}\n\n{judge_prompt}" if sys_gemini_judge else judge_prompt
    else:
        t = Template(PROMPT_JUIZ)
        judge_prompt = t.render(
            titulo_secao=section_title,
            versao_a=final_gpt,
            versao_b=final_claude,
            rag_context=full_rag
        )
        full_judge_prompt = judge_prompt
    
    judge_response = drafter._generate_with_retry(full_judge_prompt, model_name=(judge_model or None))
    if not judge_response or not judge_response.text:
        return final_gpt, "", drafts

    parsed = _extract_json_obj(judge_response.text)
    if parsed and parsed.get("final_text"):
        final_text = parsed.get("final_text") or ""
        divergences = parsed.get("divergences") or []
        divergencias = json.dumps(divergences, ensure_ascii=False, indent=2) if isinstance(divergences, list) else ""
        drafts["claims_requiring_citation"] = parsed.get("claims_requiring_citation") or []
        drafts["removed_claims"] = parsed.get("removed_claims") or []
        drafts["risk_flags"] = parsed.get("risk_flags") or []
        drafts["judge_structured"] = parsed
        return final_text, divergencias, drafts
    
    # Parse (same as sync version)
    import re
    full_response = judge_response.text
    match_final = re.search(r'###\s*VERS[ÃA]O\s*FINAL', full_response, re.IGNORECASE)
    match_log = re.search(r'###\s*(LOG\s*DE\s*)?DIVERG[ÊE]NCIAS', full_response, re.IGNORECASE)
    
    final_text = ""
    log_section = ""
    if match_final:
        start_final = match_final.end()
        if match_log:
            final_text = full_response[start_final:match_log.start()].strip()
            log_section = full_response[match_log.end():].strip()
        else:
            final_text = full_response[start_final:].strip()
    else:
        final_text = full_response.strip()
    
    divergencias = f"## Seção: {section_title}\n\n### Críticas Cruzadas\n**GPT:** {(critica_gpt or 'N/A')[:500]}...\n\n**Claude:** {(critica_claude or 'N/A')[:500]}...\n\n{log_section}"
    
    return final_text, divergencias, drafts


# =============================================================================
# STRUCTURED CRITIQUE (JSON Format)
# =============================================================================

PROMPT_CRITICA_ESTRUTURADA = """
Você é um revisor jurídico técnico. Analise o texto abaixo e produza uma crítica ESTRUTURADA em JSON.

## TEXTO A REVISAR:
{{ texto_colega }}

## CONTEXTO FACTUAL (RAG):
{{ rag_context }}

## RESPONDA EXCLUSIVAMENTE EM JSON COM ESTE SCHEMA:
{
    "erros_factuais": [
        {"trecho": "texto problemático", "motivo": "porque está errado", "correcao": "sugestão"}
    ],
    "lacunas_probatorias": [
        {"assunto": "o que falta", "documento_sugerido": "onde buscar prova"}
    ],
    "teses_fracas": [
        {"tese": "argumento fraco", "motivo": "porque é fraco", "alternativa": "argumento melhor"}
    ],
    "omissoes_processuais": [
        {"item_omitido": "o que faltou", "relevancia": "alta/media/baixa"}
    ],
    "pontos_fortes": [
        {"trecho": "bom argumento", "motivo": "porque é bom"}
    ]
}
"""


def parse_structured_critique(json_text: str) -> Optional[Dict]:
    """Parse JSON critique response"""
    try:
        # Clean markdown code blocks if present
        clean = json_text.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
        return json.loads(clean)
    except:
        return None


# =============================================================================
# DIVERGENCE DASHBOARD (HTML)
# =============================================================================

DASHBOARD_TEMPLATE = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dashboard de Divergências - {{ titulo_documento }}</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: 'Segoe UI', system-ui, sans-serif; background: #0f172a; color: #e2e8f0; line-height: 1.6; }
        .container { max-width: 1400px; margin: 0 auto; padding: 2rem; }
        h1 { font-size: 2rem; margin-bottom: 1rem; color: #38bdf8; }
        .metrics { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin-bottom: 2rem; }
        .metric-card { background: #1e293b; padding: 1.5rem; border-radius: 12px; text-align: center; }
        .metric-value { font-size: 2rem; font-weight: bold; color: #38bdf8; }
        .metric-label { font-size: 0.875rem; color: #94a3b8; margin-top: 0.5rem; }
        .section { background: #1e293b; border-radius: 12px; margin-bottom: 1.5rem; overflow: hidden; }
        .section-header { background: #334155; padding: 1rem 1.5rem; font-weight: 600; display: flex; justify-content: space-between; }
        .section-body { padding: 1.5rem; }
        .diff-container { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
        .diff-column { background: #0f172a; padding: 1rem; border-radius: 8px; font-family: monospace; font-size: 0.875rem; white-space: pre-wrap; max-height: 400px; overflow-y: auto; }
        .diff-column.gpt { border-left: 4px solid #22c55e; }
        .diff-column.claude { border-left: 4px solid #a855f7; }
        .divergence { background: #1e293b; padding: 1rem; border-radius: 8px; margin-bottom: 1rem; border-left: 4px solid #f59e0b; }
        .divergence h4 { color: #f59e0b; margin-bottom: 0.5rem; }
        .quote { background: #0f172a; padding: 0.75rem; border-radius: 4px; margin: 0.5rem 0; font-style: italic; }
        .decision { color: #22c55e; font-weight: 600; }
        .badge { display: inline-block; padding: 0.25rem 0.75rem; border-radius: 9999px; font-size: 0.75rem; font-weight: 600; }
        .badge-success { background: #166534; color: #bbf7d0; }
        .badge-warning { background: #854d0e; color: #fef08a; }
        .badge-error { background: #991b1b; color: #fecaca; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🔍 Dashboard de Divergências</h1>
        <p style="margin-bottom: 2rem; color: #94a3b8;">{{ titulo_documento }} - Gerado em {{ data_geracao }}</p>
        
        <div class="metrics">
            <div class="metric-card">
                <div class="metric-value">{{ total_secoes }}</div>
                <div class="metric-label">Seções Processadas</div>
            </div>
            <div class="metric-card">
                <div class="metric-value">{{ total_divergencias }}</div>
                <div class="metric-label">Divergências Encontradas</div>
            </div>
            <div class="metric-card">
                <div class="metric-value">${{ custo_estimado }}</div>
                <div class="metric-label">Custo Estimado (USD)</div>
            </div>
            <div class="metric-card">
                <div class="metric-value">{{ total_tokens }}</div>
                <div class="metric-label">Tokens Totais</div>
            </div>
        </div>
        
        {% for secao in secoes %}
        <div class="section">
            <div class="section-header">
                <span>{{ secao.titulo }}</span>
                <span class="badge badge-{{ secao.status }}">{{ secao.status_label }}</span>
            </div>
            <div class="section-body">
                <div class="diff-container">
                    <div class="diff-column gpt">
                        <strong>🤖 GPT (Versão Final)</strong>
                        <hr style="border-color: #334155; margin: 0.5rem 0;">
                        {{ secao.versao_gpt[:1000] }}...
                    </div>
                    <div class="diff-column claude">
                        <strong>🟣 Claude (Versão Final)</strong>
                        <hr style="border-color: #334155; margin: 0.5rem 0;">
                        {{ secao.versao_claude[:1000] }}...
                    </div>
                </div>
                
                {% if secao.divergencias %}
                <div style="margin-top: 1.5rem;">
                    <h3 style="margin-bottom: 1rem;">⚠️ Divergências</h3>
                    {% for div in secao.divergencias %}
                    <div class="divergence">
                        <h4>{{ div.tema }}</h4>
                        <div class="quote"><strong>GPT:</strong> {{ div.quote_gpt }}</div>
                        <div class="quote"><strong>Claude:</strong> {{ div.quote_claude }}</div>
                        <p class="decision">✓ Decisão: {{ div.decisao }}</p>
                    </div>
                    {% endfor %}
                </div>
                {% endif %}
            </div>
        </div>
        {% endfor %}
    </div>
</body>
</html>
"""


def generate_divergence_dashboard(
    titulo_documento: str,
    secoes: List[Dict],
    metrics: AgentMetrics,
    output_path: str
):
    """Generate HTML dashboard for divergence visualization"""
    from jinja2 import Template
    from datetime import datetime
    
    # Calculate totals
    totals = metrics.total_tokens()
    total_tokens = sum(p["input"] + p["output"] for p in totals.values())
    total_divergencias = sum(len(s.get("divergencias", [])) for s in secoes)
    
    template = Template(DASHBOARD_TEMPLATE)
    html = template.render(
        titulo_documento=titulo_documento,
        data_geracao=datetime.now().strftime("%Y-%m-%d %H:%M"),
        total_secoes=len(secoes),
        total_divergencias=total_divergencias,
        custo_estimado=f"{metrics.estimated_cost_usd():.4f}",
        total_tokens=f"{total_tokens:,}",
        secoes=secoes
    )
    
    import os
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    
    logger.info(f"📊 Dashboard salvo em: {output_path}")
    return output_path


# =============================================================================
# CLI TEST
# =============================================================================

if __name__ == "__main__":
    print("🧪 Testando inicialização de clientes...")
    
    gpt = init_openai_client()
    print(f"   OpenAI: {'✅ OK' if gpt else '❌ Não disponível'}")
    
    claude = init_anthropic_client()
    print(f"   Anthropic: {'✅ OK' if claude else '❌ Não disponível'}")
    
    print(f"\n📊 Métricas disponíveis: agent_metrics.save('path.json')")
    print(f"📊 Dashboard: generate_divergence_dashboard(...)")
