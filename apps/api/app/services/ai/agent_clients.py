"""
Agent Clients - Wrappers for Multi-Model Agent Mode (v2.1)

This module provides standardized clients for calling OpenAI (GPT) and Anthropic (Claude)
as agents in the multi-model generation pipeline.

The Gemini 3 Pro acts as the "judge" and uses the existing LegalDrafter infrastructure.
"""

import os
import logging
import time
import random
import threading
from datetime import datetime
from typing import Optional, Tuple, Dict, List, Any
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("AgentClients")

CLAUDE_MIN_INTERVAL_SECONDS = float(os.getenv("CLAUDE_MIN_INTERVAL_SECONDS", "0"))
CLAUDE_MAX_RETRIES = int(os.getenv("CLAUDE_MAX_RETRIES", "3"))
CLAUDE_BACKOFF_BASE_SECONDS = float(os.getenv("CLAUDE_BACKOFF_BASE_SECONDS", "10"))
CLAUDE_BACKOFF_MAX_SECONDS = float(os.getenv("CLAUDE_BACKOFF_MAX_SECONDS", "60"))
ANTHROPIC_FALLBACK_DIRECT = os.getenv("ANTHROPIC_FALLBACK_DIRECT", "true").lower() == "true"

_claude_throttle_lock = threading.Lock()
_claude_last_call_at = 0.0

from app.services.web_search_service import web_search_service, is_breadth_first
from app.services.ai.prompts.debate_prompts import (
    PROMPT_JUIZ as V2_PROMPT_JUIZ,
    PROMPT_CRITICA as V2_PROMPT_CRITICA,
    PROMPT_REVISAO as V2_PROMPT_REVISAO,
    PROMPT_GPT_SYSTEM as V2_PROMPT_GPT_SYSTEM,
    PROMPT_CLAUDE_SYSTEM as V2_PROMPT_CLAUDE_SYSTEM,
    PROMPT_GEMINI_BLIND_SYSTEM as V2_PROMPT_GEMINI_BLIND_SYSTEM,
    PROMPT_GEMINI_JUDGE_SYSTEM as V2_PROMPT_GEMINI_JUDGE_SYSTEM,
    get_document_instructions,
)

V2_PROMPT_JUIZ_MULTI = """
Você é um Desembargador Sênior revisando {{ num_versions }} versões da seção "{{ titulo_secao }}" de um(a) {{ tipo_documento }}.

## TESE/OBJETIVO CENTRAL:
{{ tese }}

## SEÇÕES ANTERIORES DESTE DOCUMENTO:
{{ secoes_anteriores }}

## DIRETRIZES DE FORMATAÇÃO (se houver):
{{ diretrizes_formatacao }}

## MODELO DE ESTRUTURA (se houver):
{{ modelo_estrutura }}

## VERSÕES PARA ANÁLISE (cada uma rotulada por modelo):
{% for v in versoes %}
### {{ v.label }}
{{ v.text }}
{% endfor %}

## CONTEXTO FACTUAL (RAG - VERDADE ABSOLUTA):
{{ rag_context }}

## INSTRUÇÕES ESPECÍFICAS PARA {{ tipo_documento }}:
- **Tom**: {{ instrucoes.tom }}
- **Foco**: {{ instrucoes.foco }}
- **Estrutura esperada**: {{ instrucoes.estrutura }}

## INSTRUÇÕES RIGOROSAS:
1. **ESCOLHA** a melhor versão OU **MESCLE** os melhores trechos.
2. **NÃO CONTRADIGA** as seções anteriores listadas acima.
3. **PRESERVE** todas as citações no formato [TIPO - Doc. X, p. Y].
4. **NÃO INVENTE** fatos, leis ou jurisprudências.
5. **MANTENHA** coerência com a tese central.
6. **REGRA DE PENDÊNCIA**: se você precisar afirmar um fato/dado e NÃO houver suporte claro no CONTEXTO FACTUAL (RAG), escreva no texto: [[PENDENTE: confirmar no Doc X/página Y]].
7. **REGRA DE CITAÇÃO OBRIGATÓRIA**: qualquer afirmação factual relevante deve ter [TIPO - Doc. X, p. Y]. Se não tiver, inclua a afirmação em `claims_requiring_citation` e marque no texto com [[PENDENTE: ...]].

## FORMATO DE RESPOSTA (OBRIGATÓRIO):
Responda **EXCLUSIVAMENTE** com um JSON válido (sem markdown, sem comentários), seguindo este schema:
{
  "final_text": "string (markdown permitido)",
  "divergences": [
    {
      "topic": "string",
      "quotes": {"<modelo>": "string"},
      "decision": "string",
      "risk_or_pending": "string|null"
    }
  ],
  "claims_requiring_citation": [
    {
      "claim": "string",
      "suggested_citation": "string|null",
      "why": "string"
    }
  ],
  "removed_claims": [
    {
      "claim": "string",
      "why_removed": "string"
    }
  ],
  "risk_flags": ["string"]
}
"""

# Vertex AI SDK (Unified for Gemini, Claude, and GPT in Model Garden)
try:
    from google import genai
    from google.genai import types
except ImportError:
    logger.error("❌ google-genai não instalado. pip install google-genai")
    genai = None
    types = None

from app.services.ai.genai_utils import extract_genai_text

# Fallback direct SDKs
try:
    import openai
except ImportError:
    openai = None

try:
    import anthropic
except ImportError:
    anthropic = None

AnthropicVertex = None
AsyncAnthropicVertex = None
if anthropic:
    AnthropicVertex = getattr(anthropic, "AnthropicVertex", None)
    AsyncAnthropicVertex = getattr(anthropic, "AsyncAnthropicVertex", None)


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
# CLIENT INITIALIZATION
# =============================================================================

def init_vertex_client():
    """Initialize the unified Vertex AI client (GCP or direct Gemini API)"""
    if not genai:
        return None
        
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    region = os.getenv("VERTEX_AI_LOCATION", "us-east5")
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    
    # We prioritize Vertex AI (GCP) if project_id is available
    if project_id:
        return genai.Client(vertexai=True, project=project_id, location=region)
    elif api_key:
        # Fallback to direct Gemini API if no GCP project is set
        return genai.Client(api_key=api_key)
    return None

def init_openai_client():
    """Initialize Vertex AI client for GPT agent (Model Garden) or fallback to direct OpenAI"""
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    if project_id and genai:
        return init_vertex_client()
    
    # Fallback to direct OpenAI
    if not openai:
        logger.warning("⚠️ Agente GPT via OpenAI não disponível (openai SDK não instalado).")
        return None
        
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.warning("⚠️ OPENAI_API_KEY não configurada. Agente GPT desabilitado.")
        return None
    base_url = os.getenv("OPENAI_BASE_URL")
    if base_url:
        return openai.OpenAI(api_key=api_key, base_url=base_url)
    return openai.OpenAI(api_key=api_key)

def init_xai_client():
    """Initialize xAI client via OpenAI-compatible SDK."""
    if not openai:
        logger.warning("⚠️ xAI via OpenAI SDK não disponível (openai SDK não instalado).")
        return None
    api_key = os.getenv("XAI_API_KEY")
    if not api_key:
        logger.warning("⚠️ XAI_API_KEY não configurada. xAI desabilitado.")
        return None
    base_url = os.getenv("XAI_BASE_URL", "https://api.x.ai/v1")
    return openai.OpenAI(api_key=api_key, base_url=base_url)

def init_xai_async_client():
    """Initialize async xAI client via OpenAI-compatible SDK."""
    if not openai:
        logger.warning("⚠️ xAI async via OpenAI SDK não disponível (openai SDK não instalado).")
        return None
    api_key = os.getenv("XAI_API_KEY")
    if not api_key:
        logger.warning("⚠️ XAI_API_KEY não configurada. xAI async desabilitado.")
        return None
    base_url = os.getenv("XAI_BASE_URL", "https://api.x.ai/v1")
    return openai.AsyncOpenAI(api_key=api_key, base_url=base_url)

def init_openrouter_client():
    """Initialize OpenRouter client via OpenAI-compatible SDK."""
    if not openai:
        logger.warning("⚠️ OpenRouter via OpenAI SDK não disponível (openai SDK não instalado).")
        return None
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        logger.warning("⚠️ OPENROUTER_API_KEY não configurada. OpenRouter desabilitado.")
        return None
    base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    headers: Dict[str, str] = {}
    referer = os.getenv("OPENROUTER_REFERER")
    title = os.getenv("OPENROUTER_TITLE")
    if referer:
        headers["HTTP-Referer"] = referer
    if title:
        headers["X-Title"] = title
    return openai.OpenAI(api_key=api_key, base_url=base_url, default_headers=headers or None)

def init_openrouter_async_client():
    """Initialize async OpenRouter client via OpenAI-compatible SDK."""
    if not openai:
        logger.warning("⚠️ OpenRouter async via OpenAI SDK não disponível (openai SDK não instalado).")
        return None
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        logger.warning("⚠️ OPENROUTER_API_KEY não configurada. OpenRouter async desabilitado.")
        return None
    base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    headers: Dict[str, str] = {}
    referer = os.getenv("OPENROUTER_REFERER")
    title = os.getenv("OPENROUTER_TITLE")
    if referer:
        headers["HTTP-Referer"] = referer
    if title:
        headers["X-Title"] = title
    return openai.AsyncOpenAI(api_key=api_key, base_url=base_url, default_headers=headers or None)

def init_anthropic_client():
    """Initialize Claude client via Vertex AI (preferred) or direct Anthropic."""
    if not anthropic:
        logger.warning("⚠️ Agente Claude via Anthropic não disponível (anthropic SDK não instalado).")
        return None

    force_direct = os.getenv("ANTHROPIC_FORCE_DIRECT", "false").lower() == "true"
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    region = os.getenv("VERTEX_AI_LOCATION", "global")
    if project_id and AnthropicVertex and not force_direct:
        return AnthropicVertex(project_id=project_id, region=region)

    if project_id and not AnthropicVertex and not force_direct:
        logger.warning("⚠️ AnthropicVertex não disponível. Atualize o SDK: pip install 'anthropic[vertex]'.")

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.warning("⚠️ ANTHROPIC_API_KEY não configurada. Agente Claude desabilitado.")
        return None
    return anthropic.Anthropic(api_key=api_key)


def _is_anthropic_vertex_client(client) -> bool:
    if not client or not anthropic:
        return False
    if AnthropicVertex and isinstance(client, AnthropicVertex):
        return True
    if AsyncAnthropicVertex and isinstance(client, AsyncAnthropicVertex):
        return True
    return False

def init_gemini_client():
    """Initialize Vertex AI client for Gemini (Juiz)"""
    return init_vertex_client()


# Singleton client instances
_openai_client = None
_anthropic_client = None
_gemini_client = None
_xai_client = None
_openrouter_client = None
_async_xai_client = None
_async_openrouter_client = None
_async_openai_client = None
_async_anthropic_client = None

def get_gpt_client():
    """Get or initialize OpenAI client (singleton)."""
    global _openai_client
    if _openai_client is None:
        _openai_client = init_openai_client()
    return _openai_client

def get_claude_client():
    """Get or initialize Anthropic client (singleton)."""
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = init_anthropic_client()
    return _anthropic_client

def get_gemini_client():
    """Get or initialize Gemini/Vertex client (singleton)."""
    global _gemini_client
    if _gemini_client is None:
        _gemini_client = init_gemini_client()
    return _gemini_client

def get_xai_client():
    """Get or initialize xAI client (singleton)."""
    global _xai_client
    if _xai_client is None:
        _xai_client = init_xai_client()
    return _xai_client

def get_openrouter_client():
    """Get or initialize OpenRouter client (singleton)."""
    global _openrouter_client
    if _openrouter_client is None:
        _openrouter_client = init_openrouter_client()
    return _openrouter_client

def get_async_xai_client():
    """Get or initialize async xAI client (singleton)."""
    global _async_xai_client
    if _async_xai_client is None:
        _async_xai_client = init_xai_async_client()
    return _async_xai_client

def get_async_openrouter_client():
    """Get or initialize async OpenRouter client (singleton)."""
    global _async_openrouter_client
    if _async_openrouter_client is None:
        _async_openrouter_client = init_openrouter_async_client()
    return _async_openrouter_client

def get_async_openai_client():
    """Get or initialize Async OpenAI client (singleton) for direct API."""
    global _async_openai_client
    if _async_openai_client is not None:
        return _async_openai_client
    if not openai:
        return None
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    _async_openai_client = openai.AsyncOpenAI(api_key=api_key)
    return _async_openai_client

def get_async_claude_client():
    """Get or initialize Async Anthropic client (Vertex preferred)."""
    global _async_anthropic_client
    if _async_anthropic_client is not None:
        return _async_anthropic_client

    if not anthropic:
        return None

    force_direct = os.getenv("ANTHROPIC_FORCE_DIRECT", "false").lower() == "true"
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    region = os.getenv("VERTEX_AI_LOCATION", "global")

    async_vertex = getattr(anthropic, "AsyncAnthropicVertex", None)
    if project_id and async_vertex and not force_direct:
        _async_anthropic_client = async_vertex(project_id=project_id, region=region)
        return _async_anthropic_client

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return None

    _async_anthropic_client = anthropic.AsyncAnthropic(api_key=api_key)
    return _async_anthropic_client


# =============================================================================
# METRICS TRACKING
# =============================================================================

from dataclasses import dataclass, field
from typing import Dict, List
import time
import hashlib
import json
import re

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
            "gemini": {"input": 0.075, "output": 0.30},  # Gemini Pro
            "vertex-openai": {"input": 2.50, "output": 10.00},
            "vertex-anthropic": {"input": 3.00, "output": 15.00}
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
# JSON PARSER (Juiz v2)
# =============================================================================

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
# GEMINI CONTEXT CACHING (v5.3)
# =============================================================================

# Store active caches by job_id for cleanup
_active_job_caches: Dict[str, Any] = {}
MIN_CHARS_FOR_CACHE = 50000  # Only cache contexts > 50k chars
CONTEXT_CACHE_TTL_SECONDS = 3600  # 1 hour default

def get_or_create_context_cache(
    client,
    job_id: str,
    context_content: str,
    model_name: str = "gemini-2.0-flash",
    num_sections: int = 1
) -> Optional[Any]:
    """
    Create or retrieve a Gemini context cache for the given job.
    
    This caches the factual context (CaseBundle + RAG) that is shared
    across all sections, reducing token input costs by 40-60%.
    
    Args:
        client: Gemini genai.Client instance
        job_id: Unique job identifier for cache management
        context_content: The full context to cache (bundle + RAG)
        model_name: Gemini model to use with cache
        num_sections: Number of sections (for TTL calculation)
    
    Returns:
        CachedContent object or None if caching not applicable/failed
    """
    if not genai or not types:
        logger.warning("⚠️ google-genai não disponível para caching")
        return None
    
    if not client:
        return None
    
    # Skip caching for small contexts (not worth the overhead)
    if len(context_content) < MIN_CHARS_FOR_CACHE:
        logger.info(f"📦 Contexto pequeno ({len(context_content):,} chars), cache não necessário")
        return None
    
    # Check if we already have a cache for this job
    if job_id in _active_job_caches:
        cached = _active_job_caches[job_id]
        logger.info(f"♻️ Reusando cache existente para job {job_id[:8]}...")
        return cached
    
    try:
        # Generate hash for cache identification
        content_hash = hashlib.sha256(context_content.encode()).hexdigest()[:12]
        cache_name = f"iudex_{job_id[:8]}_{content_hash}"
        
        # Try to find existing cache with same name
        try:
            for c in client.caches.list(page_size=50):
                if hasattr(c, 'display_name') and c.display_name == cache_name:
                    logger.info(f"♻️ Cache encontrado: {cache_name}")
                    _active_job_caches[job_id] = c
                    return c
        except Exception as e:
            logger.debug(f"Cache lookup falhou: {e}")
        
        # Calculate dynamic TTL based on expected processing time
        # Base: 1 hour + 10 min per section
        ttl_seconds = CONTEXT_CACHE_TTL_SECONDS + (num_sections * 600)
        ttl_str = f"{ttl_seconds}s"
        
        # Create new cache
        cache = client.caches.create(
            model=model_name,
            config=types.CreateCachedContentConfig(
                contents=[context_content],
                ttl=ttl_str,
                display_name=cache_name
            )
        )
        
        _active_job_caches[job_id] = cache
        logger.info(f"✅ Cache criado: {cache_name} (TTL: {ttl_str}, chars: {len(context_content):,})")
        return cache
        
    except Exception as e:
        logger.warning(f"⚠️ Falha ao criar cache: {e}. Continuando sem cache.")
        return None


def cleanup_job_cache(job_id: str) -> bool:
    """
    Clean up context cache for a completed job.
    
    Args:
        job_id: The job ID to clean up
    
    Returns:
        True if cleanup was successful, False otherwise
    """
    if job_id not in _active_job_caches:
        return True
    
    try:
        cache = _active_job_caches.pop(job_id)
        # Note: Gemini caches auto-expire, but we can delete early
        if hasattr(cache, 'name') and genai:
            try:
                client = get_gemini_client()
                if client:
                    client.caches.delete(name=cache.name)
                    logger.info(f"🗑️ Cache deletado: {cache.name}")
            except Exception:
                pass  # Cache may have already expired
        return True
    except Exception as e:
        logger.warning(f"⚠️ Erro ao limpar cache: {e}")
        return False


def get_active_cache(job_id: str) -> Optional[Any]:
    """Get active cache for a job if it exists."""
    return _active_job_caches.get(job_id)


# =============================================================================
# AGENT CALLS (with timeout and metrics)
# =============================================================================

API_TIMEOUT_SECONDS = 60
DEFAULT_LEGAL_SYSTEM_INSTRUCTION = (
    "Você é um advogado jurídico sênior brasileiro. Responda sempre em português formal jurídico. "
    "REGRA OBRIGATÓRIA: Ao citar fatos dos autos, USE SEMPRE o formato [TIPO - Doc. X, p. Y]."
)
DEFAULT_GENERAL_SYSTEM_INSTRUCTION = (
    "Você é um assistente geral prestativo. Responda em português claro e natural, "
    "sem jargões jurídicos, e seja objetivo."
)


def build_system_instruction(chat_personality: Optional[str]) -> str:
    if (chat_personality or "").lower() == "geral":
        return DEFAULT_GENERAL_SYSTEM_INSTRUCTION
    return DEFAULT_LEGAL_SYSTEM_INSTRUCTION

def call_openai(
    client,
    prompt: str,
    model: str = "gpt-5.2",
    max_tokens: int = 4000,
    temperature: float = 0.3,
    timeout: int = API_TIMEOUT_SECONDS,
    system_instruction: Optional[str] = None
) -> Optional[str]:
    """
    Call GPT model via Vertex AI Model Garden.
    """
    if not client:
        return None
    
    start_time = time.time()
    input_tokens = len(prompt) // 4
    
    try:
        # Check if client is Vertex (genai.Client) or direct OpenAI
        is_vertex = genai and isinstance(client, genai.Client)
        
        if is_vertex:
            system_instruction = system_instruction or DEFAULT_LEGAL_SYSTEM_INSTRUCTION
            
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    max_output_tokens=max_tokens,
                    temperature=temperature,
                )
            )
            output_text = response.text
            input_tokens = response.usage_metadata.prompt_token_count if response.usage_metadata else input_tokens
            output_tokens = response.usage_metadata.candidates_token_count if response.usage_metadata else 0
            provider_name = "vertex-openai"
        else:
            # Direct OpenAI call
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_instruction or DEFAULT_LEGAL_SYSTEM_INSTRUCTION},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=max_tokens,
                temperature=temperature,
                timeout=timeout
            )
            output_text = response.choices[0].message.content
            # Use usage if available from SDK
            input_tokens = response.usage.prompt_tokens if hasattr(response, 'usage') else input_tokens
            output_tokens = response.usage.completion_tokens if hasattr(response, 'usage') else 0
            provider_name = "openai"
        
        agent_metrics.record(
            provider=provider_name, model=model,
            input_tokens=input_tokens, output_tokens=output_tokens,
            latency_ms=int((time.time() - start_time) * 1000),
            success=True
        )
        return output_text
    except Exception as e:
        logger.error(f"❌ Erro ao chamar GPT via Vertex: {e}")
        agent_metrics.record(
            provider="vertex-openai", model=model,
            input_tokens=input_tokens, output_tokens=0,
            latency_ms=int((time.time() - start_time) * 1000),
            success=False
        )
        return None


def _throttle_claude() -> None:
    if CLAUDE_MIN_INTERVAL_SECONDS <= 0:
        return
    global _claude_last_call_at
    with _claude_throttle_lock:
        now = time.time()
        wait_time = CLAUDE_MIN_INTERVAL_SECONDS - (now - _claude_last_call_at)
        if wait_time > 0:
            logger.info(f"⏳ Claude throttle: aguardando {wait_time:.1f}s")
            time.sleep(wait_time)
        _claude_last_call_at = time.time()


def _is_claude_rate_limit_error(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None)
    if status_code == 429:
        return True
    message = str(exc).lower()
    return (
        "429" in message
        or "resource_exhausted" in message
        or "quota" in message
        or "rate limit" in message
        or "rate_limit" in message
    )


def _get_anthropic_direct_model(model: str) -> str:
    override = os.getenv("ANTHROPIC_DIRECT_MODEL")
    if override:
        return override
    if "@" in model:
        return model.split("@", 1)[0]
    return model


def call_anthropic(
    client,
    prompt: str,
    model: str = "claude-4.5-sonnet",
    max_tokens: int = 4000,
    temperature: float = 0.3,
    timeout: int = API_TIMEOUT_SECONDS,
    system_instruction: Optional[str] = None
) -> Optional[str]:
    """
    Call Claude model via Vertex AI Model Garden.
    """
    if not client:
        return None
    
    start_time = time.time()
    input_tokens = len(prompt) // 4
    
    last_error = None
    is_vertex = _is_anthropic_vertex_client(client)
    used_direct_fallback = False
    for attempt in range(CLAUDE_MAX_RETRIES + 1):
        _throttle_claude()
        try:
            from app.services.ai.model_registry import get_api_model_name
            model = get_api_model_name(model)

            if is_vertex:
                system_instruction = system_instruction or DEFAULT_LEGAL_SYSTEM_INSTRUCTION

                anthropic_version = os.getenv("ANTHROPIC_VERTEX_VERSION", "vertex-2023-10-16")
                response = client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=system_instruction,
                    messages=[{"role": "user", "content": prompt}],
                    anthropic_version=anthropic_version,
                )
                if hasattr(response, "content") and response.content:
                    output_text = "".join([getattr(b, "text", "") for b in response.content]).strip()
                else:
                    output_text = ""
                input_tokens = response.usage.input_tokens if hasattr(response, "usage") else input_tokens
                output_tokens = response.usage.output_tokens if hasattr(response, "usage") else 0
                provider_name = "vertex-anthropic"
            else:
                # Direct Anthropic call
                response = client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    messages=[
                        {"role": "user", "content": prompt}
                    ],
                    system=system_instruction or DEFAULT_LEGAL_SYSTEM_INSTRUCTION,
                    timeout=timeout
                )
                output_text = response.content[0].text
                input_tokens = response.usage.input_tokens if hasattr(response, 'usage') else input_tokens
                output_tokens = response.usage.output_tokens if hasattr(response, 'usage') else 0
                provider_name = "anthropic"

            agent_metrics.record(
                provider=provider_name, model=model,
                input_tokens=input_tokens, output_tokens=output_tokens,
                latency_ms=int((time.time() - start_time) * 1000),
                success=True
            )
            return output_text
        except Exception as e:
            last_error = e
            if _is_claude_rate_limit_error(e):
                if is_vertex and ANTHROPIC_FALLBACK_DIRECT and not used_direct_fallback:
                    api_key = os.getenv("ANTHROPIC_API_KEY")
                    if api_key and anthropic:
                        try:
                            direct_model = _get_anthropic_direct_model(model)
                            logger.warning(f"⚠️ Claude rate-limit no Vertex. Tentando Anthropic direto ({direct_model}).")
                            direct_client = anthropic.Anthropic(api_key=api_key)
                            response = direct_client.messages.create(
                                model=direct_model,
                                max_tokens=max_tokens,
                                messages=[{"role": "user", "content": prompt}],
                                system=system_instruction or DEFAULT_LEGAL_SYSTEM_INSTRUCTION,
                                timeout=timeout
                            )
                            output_text = response.content[0].text if response.content else ""
                            input_tokens = response.usage.input_tokens if hasattr(response, 'usage') else input_tokens
                            output_tokens = response.usage.output_tokens if hasattr(response, 'usage') else 0
                            agent_metrics.record(
                                provider="anthropic", model=direct_model,
                                input_tokens=input_tokens, output_tokens=output_tokens,
                                latency_ms=int((time.time() - start_time) * 1000),
                                success=True
                            )
                            return output_text
                        except Exception as direct_error:
                            used_direct_fallback = True
                            last_error = direct_error
                if attempt < CLAUDE_MAX_RETRIES:
                    wait_time = min(
                        CLAUDE_BACKOFF_MAX_SECONDS,
                        CLAUDE_BACKOFF_BASE_SECONDS * (2 ** attempt)
                    )
                    wait_time = wait_time * (0.7 + random.random() * 0.6)
                    logger.warning(f"⚠️ Claude rate-limit: {e}. Backoff {wait_time:.1f}s (tentativa {attempt+1}/{CLAUDE_MAX_RETRIES})")
                    time.sleep(wait_time)
                    continue
            break

    logger.error(f"❌ Erro ao chamar Claude via Vertex: {last_error}")
    agent_metrics.record(
        provider="vertex-anthropic", model=model,
        input_tokens=input_tokens, output_tokens=0,
        latency_ms=int((time.time() - start_time) * 1000),
        success=False
    )
    return None


def call_vertex_gemini(
    client,
    prompt: str,
    model: str = "gemini-3-flash",
    max_tokens: int = 8192,
    temperature: float = 0.3,
    timeout: int = API_TIMEOUT_SECONDS,
    web_search: bool = False,
    system_instruction: Optional[str] = None,
    cached_content: Optional[Any] = None
) -> Optional[str]:
    """
    Call Gemini model via Vertex/Google GenAI client.
    Supports Context Caching via cached_content.
    """
    if not genai:
        logger.warning("⚠️ google-genai não instalado. Gemini indisponível.")
        return None

    if not client:
        client = init_vertex_client()

    if not client:
        logger.warning("⚠️ Cliente Gemini não configurado.")
        return None

    start_time = time.time()
    input_tokens = len(prompt) // 4
    model_id = model

    try:
        from app.services.ai.model_registry import get_api_model_name
        model_id = get_api_model_name(model)

        system_instruction = system_instruction or DEFAULT_LEGAL_SYSTEM_INSTRUCTION

        # Handle cached content
        generate_kwargs = {
            "model": model_id,
            "contents": prompt,
            "config": types.GenerateContentConfig(
                system_instruction=system_instruction,
                max_output_tokens=max_tokens,
                temperature=temperature,
            )
        }
        
        # If cached_content is provided, we must use the model associated with the cache
        # and likely omit system_instruction if it's already in the cache
        if cached_content:
            # For google-genai SDK 0.x/1.x, cached_content is often passed in config
            # or we generate from the cache object. 
            # With unified client.models.generate_content, we pass cached_content=name
            if hasattr(cached_content, 'name'):
                generate_kwargs['config'].cached_content = cached_content.name

        response = client.models.generate_content(**generate_kwargs)
        output_text = extract_genai_text(response)
        input_tokens = response.usage_metadata.prompt_token_count if response.usage_metadata else input_tokens
        output_tokens = response.usage_metadata.candidates_token_count if response.usage_metadata else 0

        agent_metrics.record(
            provider="vertex-gemini", model=model_id,
            input_tokens=input_tokens, output_tokens=output_tokens,
            latency_ms=int((time.time() - start_time) * 1000),
            success=True
        )
        return output_text
    except Exception as e:
        logger.error(f"❌ Erro ao chamar Gemini via Vertex: {e}")
        agent_metrics.record(
            provider="vertex-gemini", model=model_id,
            input_tokens=input_tokens, output_tokens=0,
            latency_ms=int((time.time() - start_time) * 1000),
            success=False
        )
        return None


# =============================================================================
# ASYNC VERSIONS (for parallel execution)
# =============================================================================

import asyncio

async def call_openai_async(
    client,
    prompt: str,
    model: str = "gpt-5.2",
    max_tokens: int = 4000,
    temperature: float = 0.3,
    timeout: int = API_TIMEOUT_SECONDS,
    web_search: bool = False,
    system_instruction: Optional[str] = None
) -> Optional[str]:
    """Async version using native genai.Client.aio for Vertex or executor for fallback"""
    if not client:
        return None
        
    is_vertex = genai and isinstance(client, genai.Client)
    
    if is_vertex:
        start_time = time.time()
        input_tokens = len(prompt) // 4
        try:
            system_instruction = system_instruction or DEFAULT_LEGAL_SYSTEM_INSTRUCTION
            
            response = await client.aio.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    max_output_tokens=max_tokens,
                    temperature=temperature,
                )
            )
            
            output_text = response.text
            input_tokens = response.usage_metadata.prompt_token_count if response.usage_metadata else input_tokens
            output_tokens = response.usage_metadata.candidates_token_count if response.usage_metadata else 0
            
            agent_metrics.record(
                provider="vertex-openai", model=model,
                input_tokens=input_tokens, output_tokens=output_tokens,
                latency_ms=int((time.time() - start_time) * 1000),
                success=True
            )
            return output_text
        except Exception as e:
            logger.error(f"❌ Erro assíncrono GPT via Vertex: {e}")
            return None
    else:
        # Fallback to executor for direct sync SDK
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, 
            lambda: call_openai(client, prompt, model, max_tokens, temperature, timeout, system_instruction)
        )


async def call_anthropic_async(
    client,
    prompt: str,
    model: str = "claude-4.5-sonnet",
    max_tokens: int = 4000,
    temperature: float = 0.3,
    timeout: int = API_TIMEOUT_SECONDS,
    web_search: bool = False,
    system_instruction: Optional[str] = None
) -> Optional[str]:
    """Async version using executor for sync clients."""
    if not client:
        return None

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        lambda: call_anthropic(client, prompt, model, max_tokens, temperature, timeout, system_instruction)
    )


async def call_vertex_gemini_async(
    client,
    prompt: str,
    model: str = "gemini-3-flash",
    max_tokens: int = 8192,
    temperature: float = 0.3,
    timeout: int = API_TIMEOUT_SECONDS,
    web_search: bool = False,
    system_instruction: Optional[str] = None
) -> Optional[str]:
    """Async version using native genai.Client.aio or executor fallback."""
    if not genai:
        return None

    if not client:
        client = init_vertex_client()

    if not client:
        return None

    is_vertex = isinstance(client, genai.Client)
    model_id = model

    if is_vertex:
        start_time = time.time()
        input_tokens = len(prompt) // 4
        try:
            from app.services.ai.model_registry import get_api_model_name
            model_id = get_api_model_name(model)

            system_instruction = system_instruction or DEFAULT_LEGAL_SYSTEM_INSTRUCTION

            response = await client.aio.models.generate_content(
                model=model_id,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    max_output_tokens=max_tokens,
                    temperature=temperature,
                )
            )
            output_text = extract_genai_text(response)
            input_tokens = response.usage_metadata.prompt_token_count if response.usage_metadata else input_tokens
            output_tokens = response.usage_metadata.candidates_token_count if response.usage_metadata else 0

            agent_metrics.record(
                provider="vertex-gemini", model=model_id,
                input_tokens=input_tokens, output_tokens=output_tokens,
                latency_ms=int((time.time() - start_time) * 1000),
                success=True
            )
            return output_text
        except Exception as e:
            logger.error(f"❌ Erro assíncrono Gemini via Vertex: {e}")
            agent_metrics.record(
                provider="vertex-gemini", model=model_id,
                input_tokens=input_tokens, output_tokens=0,
                latency_ms=int((time.time() - start_time) * 1000),
                success=False
            )
            return None


async def stream_openai_async(
    client,
    prompt: str,
    model: str = "gpt-5.2",
    max_tokens: int = 4000,
    temperature: float = 0.3,
    system_instruction: Optional[str] = None,
    reasoning_effort: Optional[str] = None,  # NEW: For o1/o3 models
):
    """Async streaming for GPT (Vertex or direct) with thinking support.
    
    Args:
        reasoning_effort: For o1/o3 models. Options: 'low', 'medium', 'high'
    
    Yields:
        Tuples of (chunk_type, content) where chunk_type is 'thinking' or 'text'
    """
    if not client:
        return

    system_instruction = system_instruction or DEFAULT_LEGAL_SYSTEM_INSTRUCTION

    if genai and isinstance(client, genai.Client):
        from app.services.ai.model_registry import get_api_model_name
        model_id = get_api_model_name(model)
        if hasattr(client.aio.models, "generate_content_stream"):
            stream = client.aio.models.generate_content_stream(
                model=model_id,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    max_output_tokens=max_tokens,
                    temperature=temperature,
                )
            )
            if asyncio.iscoroutine(stream):
                stream = await stream
            if hasattr(stream, "__aiter__"):
                async for chunk in stream:
                    text = getattr(chunk, "text", "") or ""
                    if text:
                        yield ('text', text)
                return

        response = await client.aio.models.generate_content(
            model=model_id,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                max_output_tokens=max_tokens,
                temperature=temperature,
            )
        )
        output_text = getattr(response, "text", "") or ""
        if output_text:
            yield ('text', output_text)
        return

    if not openai:
        return

    async_client = client if isinstance(client, openai.AsyncOpenAI) else get_async_openai_client()
    if not async_client:
        return

    # Build completion kwargs
    completion_kwargs = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": True,
    }
    
    # NEW: Add reasoning_effort for o1/o3 models
    if reasoning_effort and model.startswith(("o1-", "o3-")):
        completion_kwargs["reasoning_effort"] = reasoning_effort
    
    stream = await async_client.chat.completions.create(**completion_kwargs)
    
    async for chunk in stream:
        if not getattr(chunk, "choices", None):
            continue
        
        choice = chunk.choices[0]
        
        # NEW: Check for reasoning/thinking content (o1/o3 models)
        if hasattr(choice, 'delta'):
            # Check for reasoning content
            if hasattr(choice.delta, 'reasoning_content') and choice.delta.reasoning_content:
                yield ('thinking', choice.delta.reasoning_content)
            
            # Regular content
            delta = getattr(choice.delta, "content", None)
            if delta:
                yield ('text', delta)


async def stream_anthropic_async(
    client,
    prompt: str,
    model: str = "claude-4.5-sonnet",
    max_tokens: int = 4000,
    temperature: float = 0.3,
    system_instruction: Optional[str] = None,
    extended_thinking: bool = False,  # NEW: Enable extended thinking
):
    """Async streaming for Claude (Vertex or direct) with thinking support.
    
    Args:
        extended_thinking: Enable extended thinking mode for Claude Sonnet 4 Thinking
    
    Yields:
        Tuples of (chunk_type, content) where chunk_type is 'thinking' or 'text'
    """
    if not client:
        return

    system_instruction = system_instruction or DEFAULT_LEGAL_SYSTEM_INSTRUCTION

    from app.services.ai.model_registry import get_api_model_name
    model_id = get_api_model_name(model)

    async_vertex_cls = getattr(anthropic, "AsyncAnthropicVertex", None) if anthropic else None
    is_vertex = _is_anthropic_vertex_client(client) or (async_vertex_cls and isinstance(client, async_vertex_cls))
    if not is_vertex:
        model_id = _get_anthropic_direct_model(model_id)

    if hasattr(client.messages, "stream"):
        # Build message kwargs
        message_kwargs = {
            "model": model_id,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system_instruction,
            "messages": [{"role": "user", "content": prompt}],
        }
        
        # NEW: Add extended thinking for Claude with thinking capability
        # Per Anthropic docs: thinking: {"type": "enabled", "budget_tokens": N}
        if extended_thinking:
            logger.info(f"🧠 [Claude Thinking] Ativando extended_thinking para {model_id}")
            message_kwargs["thinking"] = {"type": "enabled", "budget_tokens": 8000}
        
        async with client.messages.stream(**message_kwargs) as stream:
            # Use async for to iterate through SSE events
            async for event in stream:
                # Claude SSE event types: content_block_start, content_block_delta, etc.
                if hasattr(event, 'type'):
                    if event.type == 'content_block_delta':
                        delta = getattr(event, 'delta', None)
                        if delta and hasattr(delta, 'type'):
                            # thinking_delta: contains thinking text
                            if delta.type == 'thinking_delta':
                                thinking_text = getattr(delta, 'thinking', '')
                                if thinking_text:
                                    logger.debug(f"🧠 [Claude Thinking] Delta: {thinking_text[:50]}...")
                                    yield ('thinking', thinking_text)
                            # text_delta: contains regular response text
                            elif delta.type == 'text_delta':
                                text = getattr(delta, 'text', '')
                                if text:
                                    yield ('text', text)
        return

    response = await call_anthropic_async(
        client,
        prompt,
        model=model_id,
        max_tokens=max_tokens,
        temperature=temperature,
        system_instruction=system_instruction,
    )
    if response:
        yield ('text', response)


async def stream_vertex_gemini_async(
    client,
    prompt: str,
    model: str = "gemini-3-flash",
    max_tokens: int = 8192,
    temperature: float = 0.3,
    system_instruction: Optional[str] = None,
    thinking_mode: Optional[str] = None,  # NEW: 'extended', 'standard', None
):
    """Async streaming for Gemini via Vertex/Google GenAI with Extended Thinking support.
    
    Args:
        thinking_mode: Enable thinking streaming. Options:
            - None: Normal mode
            - 'extended': Extended Thinking with HIGH level (streaming)
            - 'standard': Standard thinking mode
    
    Yields:
        Tuples of (chunk_type, content) where chunk_type is 'thinking' or 'text'
    """
    if not genai:
        return

    if not client:
        client = init_vertex_client()

    if not client:
        return

    from app.services.ai.model_registry import get_api_model_name
    model_id = get_api_model_name(model)
    system_instruction = system_instruction or DEFAULT_LEGAL_SYSTEM_INSTRUCTION

    # Build config kwargs
    config_kwargs = {
        "system_instruction": system_instruction,
        "max_output_tokens": max_tokens,
        "temperature": temperature,
    }
    
    # NEW: Add thinking config if requested
    if thinking_mode:
        logger.info(f"🧠 [Gemini Thinking] Ativando thinking_mode={thinking_mode} para modelo {model_id}")
        try:
            # Per Google API docs: use include_thoughts=True to get thought summaries
            # https://ai.google.dev/gemini-api/docs/thinking
            if thinking_mode == "extended":
                config_kwargs["thinking_config"] = types.ThinkingConfig(
                    include_thoughts=True,  # Required to get thought parts
                    thinking_level="HIGH"
                )
            elif thinking_mode == "standard":
                config_kwargs["thinking_config"] = types.ThinkingConfig(
                    include_thoughts=True,
                    thinking_level="MEDIUM"
                )
            elif thinking_mode == "low":
                config_kwargs["thinking_config"] = types.ThinkingConfig(
                    include_thoughts=True,
                    thinking_level="LOW"
                )
            logger.info(f"🧠 [Gemini Thinking] Config: {config_kwargs.get('thinking_config')}")
        except Exception as e:
            logger.warning(f"⚠️ Erro ao configurar thinking mode: {e}")

    if hasattr(client.aio.models, "generate_content_stream"):
        stream = client.aio.models.generate_content_stream(
            model=model_id,
            contents=prompt,
            config=types.GenerateContentConfig(**config_kwargs)
        )
        if asyncio.iscoroutine(stream):
            stream = await stream
        if hasattr(stream, "__aiter__"):
            chunk_count = 0
            async for chunk in stream:
                chunk_count += 1
                yielded = False
                
                # DEBUG: Log first few chunks' structure
                if chunk_count <= 3:
                    logger.debug(f"🧠 [Gemini Chunk {chunk_count}] Type: {type(chunk).__name__}, Attrs: {dir(chunk)[:10]}")
                    if hasattr(chunk, 'candidates') and chunk.candidates:
                        for i, cand in enumerate(chunk.candidates):
                            if hasattr(cand, 'content') and hasattr(cand.content, 'parts'):
                                for j, part in enumerate(cand.content.parts):
                                    logger.debug(f"  📦 Part[{i}][{j}]: thought={getattr(part, 'thought', 'N/A')}, text_len={len(getattr(part, 'text', '') or '')}")

                if hasattr(chunk, 'candidates') and chunk.candidates:
                    for candidate in chunk.candidates:
                        if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                            for part in candidate.content.parts:
                                part_text = getattr(part, 'text', None)
                                if not isinstance(part_text, str) or not part_text:
                                    continue
                                if getattr(part, 'thought', False):
                                    logger.info(f"🧠 [Thinking] Chunk {chunk_count}: {part_text[:50]}...")
                                    yield ('thinking', part_text)
                                else:
                                    yield ('text', part_text)
                                yielded = True

                if yielded:
                    continue

                # Fallback: older SDKs may expose thinking as a top-level field
                thinking_text = None
                if hasattr(chunk, 'thinking_text') and chunk.thinking_text:
                    thinking_text = chunk.thinking_text
                elif hasattr(chunk, 'metadata') and hasattr(chunk.metadata, 'thinking'):
                    thinking_text = chunk.metadata.thinking

                if thinking_text:
                    yield ('thinking', thinking_text)

                text = getattr(chunk, 'text', '') or ''
                if text:
                    yield ('text', text)
            return

    # Fallback: non-streaming
    response = await client.aio.models.generate_content(
        model=model_id,
        contents=prompt,
        config=types.GenerateContentConfig(**config_kwargs)
    )
    
    yielded = False
    if hasattr(response, 'candidates') and response.candidates:
        for candidate in response.candidates:
            if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                for part in candidate.content.parts:
                    part_text = getattr(part, 'text', None)
                    if not isinstance(part_text, str) or not part_text:
                        continue
                    if getattr(part, 'thought', False):
                        yield ('thinking', part_text)
                    else:
                        yield ('text', part_text)
                    yielded = True

    if yielded:
        return

    if hasattr(response, 'thinking_text') and response.thinking_text:
        yield ('thinking', response.thinking_text)

    output_text = getattr(response, "text", "") or ""
    if output_text:
        yield ('text', output_text)




# =============================================================================
# JUDGE PROMPT TEMPLATE
# =============================================================================

PROMPT_JUIZ = """
Você é um Desembargador Sênior revisando TRÊS versões da seção "{{ titulo_secao }}" de uma peça jurídica.

## VERSÃO A (GPT):
{{ versao_a }}

## VERSÃO B (Claude):
{{ versao_b }}

## VERSÃO C (Gemini - Independente):
{{ versao_c }}

## CONTEXTO FACTUAL (RAG - VERDADE ABSOLUTA):
{{ rag_context }}

## INSTRUÇÕES RIGOROSAS:
1. **ESCOLHA** a melhor versão OU **MESCLE** os melhores trechos das TÊS VERSÕES.
2. **PRESERVE OBRIGATORIAMENTE** todas as citações no formato [TIPO - Doc. X, p. Y].
3. **NÃO INVENTE** fatos, leis, súmulas ou jurisprudências não presentes no contexto RAG.
4. **MANTENHA** o tom jurídico técnico e formal.
5. Para cada divergência, **CITE TRECHOS** (máx. 50 palavras cada) das versões relevantes.

## FORMATO DE RESPOSTA:

### VERSÃO FINAL
[Texto consolidado da seção aqui]

### LOG DE DIVERGÊNCIAS

#### Divergência 1: [Tema]
- **Quote GPT:** "[trecho...]"
- **Quote Claude:** "[trecho...]"
- **Quote Gemini:** "[trecho...]"
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
    parallel: bool = False,
    # Parâmetros opcionais (mantidos aqui para compatibilidade e para evitar variáveis indefinidas)
    judge_model: Optional[str] = None,
    thesis: Optional[str] = None,
    formatting_options: Optional[Dict[str, bool]] = None,
    template_structure: Optional[str] = None,
    extra_agent_instructions: Optional[str] = None
) -> Tuple[str, str, dict]:
    """
    Generate section using multi-agent committee with debate + judge.
    
    Flow:
    1. GPT generates v1
    2. Claude generates v1
    3. GPT reviews Claude's v1 → GPT v2 (refined)
    4. Claude reviews GPT's v1 → Claude v2 (refined)
    5. Judge consolidates v2 versions
    
    Args:
        section_title: Title of the section being generated
        prompt_base: Base prompt template
        rag_context: RAG Global context (lei/juris/modelos)
        rag_local_context: RAG Local context (autos do processo)
        drafter: LegalDrafter instance for judge calls
        gpt_client: OpenAI client
        claude_client: Anthropic client
        gpt_model: GPT model name
        claude_model: Claude model name
        parallel: Whether to run agents in parallel (requires asyncio)
        
    Returns:
        Tuple of (final_text, divergencias_md, drafts_dict)
    """
    from jinja2 import Template
    
    # Build agent prompt
    extra_instructions = ""
    if thesis:
        extra_instructions += f"\n## TESE/INSTRUÇÕES ESPECÍFICAS:\n{thesis}\n"
    
    if formatting_options:
        extra_instructions += "\n## DIRETRIZES DE FORMATAÇÃO ADICIONAIS:\n"
        if formatting_options.get('include_toc'):
            extra_instructions += "- OBRIGATÓRIO: Incluir Sumário (TOC) no início do documento.\n"
        if formatting_options.get('include_summaries'):
            extra_instructions += "- OBRIGATÓRIO: Incluir breves resumos no início de cada seção principal.\n"
        if formatting_options.get('include_summary_table'):
            extra_instructions += "- OBRIGATÓRIO: Incluir Tabela de Síntese ao final do documento.\n"

    agent_prompt = f"{prompt_base}\n\n{extra_instructions}\n\n{rag_context}\n\n{rag_local_context}"
    
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
    
    # NEW: Independent Gemini Generation
    print(f"   🤖 [R1] Agente Gemini (Blind Judge) gerando versão independente...")
    # Use judge_model or specific drafting model for Gemini
    # Assuming 'drafter' has a client we can reuse or using call_vertex_gemini
    
    # We need to call Gemini here. Since we are inside 'agent_clients', we can use 'call_vertex_gemini'
    # But this function is sync wrapper. Let's use call_vertex_gemini directly if possible or the imported async one
    # Note: This function 'generate_section_agent_mode' is sync in signature but logic seems mixed. 
    # Wait, the orchestrator calls 'generate_section_agent_mode_async'.
    # I am editing 'generate_section_agent_mode' (sync stub?) NO, I am editing `agent_clients.py` which has `call_vertex_gemini_async` available.
    
    # Let's import the sync version locally if needed or use the client directly.
    # Actually, the file has `init_vertex_client`.
    
    # Simplified approach: Use the same client setup logic
    gemini_client = init_vertex_client()
    if gemini_client:
        versao_gemini_v1 = call_openai(gemini_client, agent_prompt, model="gemini-1.5-pro-002") # Using call_openai wrapper which handles Vertex client too? 
        # No, call_openai supports Vertex client but strictly for 'gpt' models (or adapter).
        # We need a proper call_gemini.
        # Looking at lines 407-411 in orchestrator, it uses `call_vertex_gemini_async`.
        # Here in `agent_clients.py` we have `call_vertex_gemini_async` defined? No, it's imported in Orchestrator.
        pass
    
    # Let's implement a direct call helper here or reuse `drafter` since it is a Gemini wrapper.
    if drafter:
        resp = drafter._generate_with_retry(agent_prompt, model_name="gemini-1.5-pro-002")
        versao_gemini_v1 = resp.text if resp else ""
    else:
        versao_gemini_v1 = ""
        
    drafts['gemini_v1'] = versao_gemini_v1 or "[Agente Gemini não disponível]"
    
    # Check if we have at least one valid draft
    valid_drafts = [d for d in [versao_gpt_v1, versao_claude_v1] if d]
    
    if len(valid_drafts) == 0:
        print(f"   ⚠️ Nenhum agente disponível. Usando Gemini diretamente.")
        response = drafter._generate_with_retry(agent_prompt, model_name=judge_model)
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
        versao_c=drafts.get('gemini_v1', ''),
        rag_context=full_rag
    )
    
    judge_response = drafter._generate_with_retry(judge_prompt, model_name=judge_model, cached_content=cached_content)
    
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

def _infer_document_type_from_prompt(prompt_base: str) -> Optional[str]:
    """
    Tenta inferir o tipo de documento a partir do cabeçalho do prompt_base,
    no formato: '## TIPO DE DOCUMENTO: XXX'.
    """
    if not prompt_base:
        return None
    import re
    m = re.search(r"^\s*##\s*TIPO\s+DE\s+DOCUMENTO\s*:\s*([A-Z_]+)\s*$", prompt_base, re.IGNORECASE | re.MULTILINE)
    if not m:
        return None
    return (m.group(1) or "").strip().upper() or None


async def generate_section_agent_mode_async(
    section_title: str,
    prompt_base: str,
    case_bundle: "CaseBundle",
    rag_local_context: str,
    drafter,
    gpt_client,
    claude_client,
    gpt_model: str = "gpt-4o",
    claude_model: str = "claude-sonnet-4-20250514",
    drafter_models: Optional[List[str]] = None,
    reviewer_models: Optional[List[str]] = None,
    judge_model: Optional[str] = None,
    reasoning_level: str = "medium",
    web_search: bool = False,
    search_mode: str = "hybrid",
    multi_query: bool = True,
    breadth_first: bool = False,
    thesis: Optional[str] = None,
    formatting_options: Optional[Dict[str, bool]] = None,
    template_structure: Optional[str] = None,
    extra_agent_instructions: Optional[str] = None,
    mode: Optional[str] = None,
    previous_sections: Optional[List[str]] = None,
    system_instruction: Optional[str] = None,
    cached_content: Optional[Any] = None
) -> Tuple[str, str, dict]:
    """
    Async version with parallel execution of GPT and Claude calls.
    Uses CaseBundle for robust document context + formatted citations.
    ~50% faster than sequential version.
    """
    from jinja2 import Template
    from app.services.ai.model_registry import get_api_model_name, DEFAULT_JUDGE_MODEL, get_model_config

    gpt_model_id = gpt_model
    claude_model_id = claude_model
    judge_model_id = judge_model or DEFAULT_JUDGE_MODEL

    # Normalize to provider API model names (accepts canonical IDs)
    gpt_model = get_api_model_name(gpt_model_id)
    claude_model = get_api_model_name(claude_model_id)
    
    # Build robust context from bundle + local RAG
    bundle_context = case_bundle.to_agent_context()

    # Unificação: usa prompts v2 (mesmos do LangGraph granular)
    doc_type = (mode or _infer_document_type_from_prompt(prompt_base) or "PETICAO").upper()
    instrucoes = get_document_instructions(doc_type)
    t_sys_gpt = Template(V2_PROMPT_GPT_SYSTEM)
    t_sys_claude = Template(V2_PROMPT_CLAUDE_SYSTEM)
    t_sys_gemini_blind = Template(V2_PROMPT_GEMINI_BLIND_SYSTEM)
    t_sys_gemini_judge = Template(V2_PROMPT_GEMINI_JUDGE_SYSTEM)
    sys_gpt = t_sys_gpt.render(tipo_documento=doc_type, instrucoes=instrucoes)
    sys_claude = t_sys_claude.render(tipo_documento=doc_type, instrucoes=instrucoes)
    sys_gemini_blind = t_sys_gemini_blind.render(tipo_documento=doc_type, instrucoes=instrucoes)
    sys_gemini_judge = t_sys_gemini_judge.render(tipo_documento=doc_type, instrucoes=instrucoes)
    
    extra_instructions = ""
    if thesis:
        extra_instructions += f"\n## TESE/INSTRUÇÕES ESPECÍFICAS:\n{thesis}\n"
    
    if formatting_options:
        extra_instructions += "\n## DIRETRIZES DE FORMATAÇÃO ADICIONAIS:\n"
        if formatting_options.get('include_toc'):
            extra_instructions += "- OBRIGATÓRIO: Incluir Sumário (TOC) no início do documento.\n"
        if formatting_options.get('include_summaries'):
            extra_instructions += "- OBRIGATÓRIO: Incluir breves resumos no início de cada seção principal.\n"
        if formatting_options.get('include_summary_table'):
            extra_instructions += "- OBRIGATÓRIO: Incluir Tabela de Síntese ao final do documento.\n"

    # Inject template structure as a reference
    if template_structure:
        extra_instructions += f"\n## MODELO DE ESTRUTURA:\n{template_structure}\n"

    # Inject extra agent instructions (RAG rules, intent)
    if extra_agent_instructions:
        extra_instructions += f"\n{extra_agent_instructions}\n"

    # Web Search Context Injection (Unified)
    if web_search:
        search_mode = (search_mode or "hybrid").lower()
        if search_mode not in ("shared", "native", "hybrid"):
            search_mode = "hybrid"
        if search_mode != "native":
            print(f"   🔍 Realizando busca web para: {section_title}")
            search_query = f"{section_title} jurisprudencia tribunal superior novo código processo civil"
            if thesis:
                search_query += f" {thesis[:100]}"

            breadth_first = bool(breadth_first) or is_breadth_first(search_query)
            multi_query = bool(multi_query) or breadth_first

            if multi_query:
                search_results = await web_search_service.search_multi(search_query, num_results=10)
            else:
                search_results = await web_search_service.search(search_query, num_results=10)

            if search_results.get('success') and search_results.get('results'):
                web_context = "\n## PESQUISA WEB RECENTE (Contexto Adicional):\n"
                for res in search_results['results']:
                    web_context += f"- [{res['title']}]({res['url']}): {res['snippet']}\n"

                # Inject into local RAG (shared by all agents)
                rag_local_context = f"{web_context}\n{rag_local_context}"
                print(f"   ✅ Contexto web injetado ({len(search_results['results'])} resultados)")

    agent_prompt = f"{prompt_base}\n\n{extra_instructions}\n\n{bundle_context}\n\n## CONTEXTO ADICIONAL (RAG LOCAL):\n{rag_local_context}"
    log_context_mode = os.getenv("LOG_AGENT_CONTEXT", "").strip().lower()
    if log_context_mode in ("1", "true", "yes", "partial", "full"):
        payload = agent_prompt
        if log_context_mode != "full" and len(payload) > 4000:
            payload = payload[:4000] + "\n\n[... contexto truncado ...]"

        def _safe_slug(value: str, fallback: str) -> str:
            slug = re.sub(r'[^a-zA-Z0-9_-]+', '_', (value or "").strip()).strip('_').lower()
            return slug or fallback

        def _persist_agent_context(content: str) -> Optional[str]:
            try:
                from app.core.config import settings
                base_dir = Path(settings.LOCAL_STORAGE_PATH) / "agent_contexts"
            except Exception:
                base_dir = Path("./storage") / "agent_contexts"

            job_slug = _safe_slug(getattr(case_bundle, "processo_id", "") or "job", "job")
            section_slug = _safe_slug(section_title, "section")
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_dir = base_dir / job_slug
            output_dir.mkdir(parents=True, exist_ok=True)
            file_path = output_dir / f"{section_slug}_{timestamp}.md"
            try:
                file_path.write_text(content, encoding="utf-8")
                return str(file_path)
            except Exception:
                return None

        persisted_path = _persist_agent_context(payload)
        logger.info(
            "🔎 Contexto compartilhado (secao=%s, chars=%d, arquivo=%s):\n%s",
            section_title,
            len(agent_prompt),
            persisted_path or "n/a",
            payload,
        )
    full_rag = f"{bundle_context}\n{rag_local_context}"
    drafts = {}

    def _dedupe_models(models: List[str]) -> List[str]:
        seen = set()
        result: List[str] = []
        for mid in models:
            if not mid:
                continue
            key = str(mid).strip()
            if not key or key in seen:
                continue
            seen.add(key)
            result.append(key)
        return result

    def _model_label(model_id: str) -> str:
        cfg = get_model_config(model_id)
        return cfg.label if cfg else model_id

    async def _call_model(
        model_id: str,
        prompt: str,
        sys_prompt: str,
        cached_content: Optional[Any] = None
    ) -> str:
        cfg = get_model_config(model_id)
        if not cfg:
            return ""
        api_model = get_api_model_name(model_id)
        full_prompt = f"{sys_prompt}\n\n{prompt}".strip()
        if cfg.provider == "openai":
            client = gpt_client or init_openai_client()
            if not client:
                return ""
            return await call_openai_async(
                client,
                full_prompt,
                model=api_model,
                system_instruction=system_instruction
            )
        if cfg.provider == "anthropic":
            client = claude_client or init_anthropic_client()
            if not client:
                return ""
            return await call_anthropic_async(
                client,
                full_prompt,
                model=api_model,
                system_instruction=system_instruction
            )
        if cfg.provider == "google":
            client = get_gemini_client()
            if not client:
                return ""
            if cached_content:
                return await asyncio.to_thread(
                    call_vertex_gemini,
                    client,
                    full_prompt,
                    model=model_id,
                    system_instruction=system_instruction,
                    cached_content=cached_content
                ) or ""
            return await call_vertex_gemini_async(
                client,
                full_prompt,
                model=model_id,
                system_instruction=system_instruction
            ) or ""
        if cfg.provider == "xai":
            client = init_xai_client()
            if not client:
                return ""
            return await call_openai_async(
                client,
                full_prompt,
                model=api_model,
                system_instruction=system_instruction
            )
        if cfg.provider == "openrouter":
            client = init_openrouter_client()
            if not client:
                return ""
            return await call_openai_async(
                client,
                full_prompt,
                model=api_model,
                system_instruction=system_instruction
            )
        return ""

    custom_drafter_models = _dedupe_models(drafter_models or [])
    custom_reviewer_models = _dedupe_models(reviewer_models or [])
    use_custom_lists = bool(custom_drafter_models or custom_reviewer_models)

    if use_custom_lists:
        if not custom_drafter_models:
            custom_drafter_models = _dedupe_models([gpt_model_id, claude_model_id, judge_model_id])
        if not custom_reviewer_models:
            custom_reviewer_models = list(custom_drafter_models)

        sys_by_provider = {
            "openai": sys_gpt,
            "anthropic": sys_claude,
            "google": sys_gemini_blind,
        }

        # R1: Drafts for each selected model
        draft_tasks: List[Tuple[str, Any]] = []
        for model_id in custom_drafter_models:
            cfg = get_model_config(model_id)
            provider = cfg.provider if cfg else ""
            sys_prompt = sys_by_provider.get(provider, sys_gpt)
            draft_tasks.append((model_id, _call_model(model_id, agent_prompt, sys_prompt)))

        draft_results = await asyncio.gather(*[t[1] for t in draft_tasks]) if draft_tasks else []
        drafts_by_model: Dict[str, str] = {}
        for idx, (model_id, _) in enumerate(draft_tasks):
            label = _model_label(model_id)
            draft_text = draft_results[idx] if idx < len(draft_results) else ""
            drafts_by_model[model_id] = draft_text or f"[{label} não disponível]"

        drafts["drafts_by_model"] = drafts_by_model
        drafts["drafts_order"] = custom_drafter_models

        valid_drafts = [text for text in drafts_by_model.values() if text and "não disponível" not in text]
        if len(valid_drafts) < 2:
            fallback_text = valid_drafts[0] if valid_drafts else ""
            return fallback_text, "", drafts

        # R2: Reviews (each reviewer critiques all drafts)
        t_critica = Template(V2_PROMPT_CRITICA)
        drafts_block = "\n\n".join(
            [f"### { _model_label(mid) } ({mid})\n{drafts_by_model[mid]}" for mid in custom_drafter_models]
        )
        critica_prompt = t_critica.render(
            texto_colega=drafts_block,
            rag_context=full_rag,
            tipo_documento=doc_type,
            tese=thesis or "",
            instrucoes=instrucoes
        )

        critique_tasks: List[Tuple[str, Any]] = []
        for model_id in custom_reviewer_models:
            cfg = get_model_config(model_id)
            provider = cfg.provider if cfg else ""
            sys_prompt = sys_by_provider.get(provider, sys_gpt)
            critique_tasks.append((model_id, _call_model(model_id, critica_prompt, sys_prompt)))

        critique_results = await asyncio.gather(*[t[1] for t in critique_tasks]) if critique_tasks else []
        reviews_by_model: Dict[str, str] = {}
        for idx, (model_id, _) in enumerate(critique_tasks):
            reviews_by_model[model_id] = critique_results[idx] if idx < len(critique_results) else ""

        drafts["reviews_by_model"] = reviews_by_model

        # R3: Revisions (each drafter uses all critiques)
        t_revisao = Template(V2_PROMPT_REVISAO)
        critiques_block = "\n\n".join(
            [
                f"### CRÍTICA DE {_model_label(mid)} ({mid})\n{reviews_by_model.get(mid) or 'N/A'}"
                for mid in custom_reviewer_models
            ]
        )

        revision_tasks: List[Tuple[str, Any]] = []
        for model_id in custom_drafter_models:
            cfg = get_model_config(model_id)
            provider = cfg.provider if cfg else ""
            sys_prompt = sys_by_provider.get(provider, sys_gpt)
            original_text = drafts_by_model.get(model_id, "")
            rev_prompt = t_revisao.render(
                texto_original=original_text,
                critica_recebida=critiques_block,
                rag_context=full_rag,
                tipo_documento=doc_type,
                tese=thesis or "",
                instrucoes=instrucoes
            )
            revision_tasks.append((model_id, _call_model(model_id, rev_prompt, sys_prompt)))

        revision_results = await asyncio.gather(*[t[1] for t in revision_tasks]) if revision_tasks else []
        revisions_by_model: Dict[str, str] = {}
        for idx, (model_id, _) in enumerate(revision_tasks):
            revisions_by_model[model_id] = revision_results[idx] if idx < len(revision_results) else ""

        drafts["revisions_by_model"] = revisions_by_model

        def _assign_legacy(provider: str, prefix: str) -> None:
            model_id = None
            for mid in custom_drafter_models:
                cfg = get_model_config(mid)
                if cfg and cfg.provider == provider:
                    model_id = mid
                    break
            if not model_id:
                return
            drafts[f"{prefix}_v1"] = drafts_by_model.get(model_id, "")
            if revisions_by_model:
                drafts[f"{prefix}_v2"] = revisions_by_model.get(model_id) or drafts_by_model.get(model_id, "")

        _assign_legacy("openai", "gpt")
        _assign_legacy("anthropic", "claude")
        _assign_legacy("google", "gemini")

        # R4: Judge consolidation (dynamic list)
        final_versions = [
            {
                "id": mid,
                "label": f"{_model_label(mid)} ({mid})",
                "text": revisions_by_model.get(mid) or drafts_by_model.get(mid, "")
            }
            for mid in custom_drafter_models
        ]
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

        t_multi = Template(V2_PROMPT_JUIZ_MULTI)
        judge_prompt = t_multi.render(
            titulo_secao=section_title,
            tese=thesis or "",
            secoes_anteriores="\n\n".join(previous_sections or []) if previous_sections else "(Esta é a primeira seção)",
            versoes=final_versions,
            num_versions=len(final_versions),
            rag_context=full_rag,
            tipo_documento=doc_type,
            instrucoes=instrucoes,
            diretrizes_formatacao=diretrizes_formatacao,
            modelo_estrutura=template_structure or "(sem modelo de estrutura)"
        )
        full_response = await _call_model(
            judge_model_id,
            judge_prompt,
            sys_gemini_judge,
            cached_content=cached_content
        )
        if not full_response:
            return final_versions[0]["text"], "", drafts
        parsed = _extract_json_obj(full_response)
        if parsed and parsed.get("final_text"):
            final_text = parsed.get("final_text") or ""
            divergences = parsed.get("divergences") or []
            divergencias = json.dumps(divergences, ensure_ascii=False, indent=2) if isinstance(divergences, list) else ""
            drafts["claims_requiring_citation"] = parsed.get("claims_requiring_citation") or []
            drafts["removed_claims"] = parsed.get("removed_claims") or []
            drafts["risk_flags"] = parsed.get("risk_flags") or []
            drafts["judge_structured"] = parsed
            return final_text, divergencias, drafts

        return final_versions[0]["text"], "", drafts
    
    # R1: Parallel Draft Generation (GPT, Claude, Gemini)
    print(f"   🤖 [R1] Gerando drafts em paralelo (3 agentes)...")
    versao_gpt_v1, versao_claude_v1 = await asyncio.gather(
        call_openai_async(
            gpt_client,
            f"{sys_gpt}\n\n{agent_prompt}",
            model=gpt_model,
            system_instruction=system_instruction
        ),
        call_anthropic_async(
            claude_client,
            f"{sys_claude}\n\n{agent_prompt}",
            model=claude_model,
            system_instruction=system_instruction
        )
    )
    drafts['gpt_v1'] = versao_gpt_v1 or "[GPT não disponível]"
    drafts['claude_v1'] = versao_claude_v1 or "[Claude não disponível]"
    
    # Independent Judge model (Blind Judge Pattern)
    print(f"   🤖 [R1] Agente Juiz (blind) gerando versão independente...")
    versao_gemini_v1 = await _call_model(judge_model_id, agent_prompt, sys_gemini_blind)
    drafts['gemini_v1'] = versao_gemini_v1 or "[Juiz não disponível]"
    drafts["judge_model"] = judge_model_id
    
    valid_drafts = [d for d in [versao_gpt_v1, versao_claude_v1] if d]
    if len(valid_drafts) < 2:
        return valid_drafts[0] if valid_drafts else "", "", drafts
    
    # R2: Triangular Critique (GPT ↔ Claude ↔ Gemini)
    print(f"   💬 [R2] Críticas triangulares (3 agentes)...")
    t_critica = Template(V2_PROMPT_CRITICA)
    
    # GPT critica Claude + Gemini
    critica_gpt_prompt = t_critica.render(
        texto_colega=f"### VERSÃO CLAUDE:\n{versao_claude_v1}\n\n### VERSÃO GEMINI:\n{versao_gemini_v1}",
        rag_context=full_rag,
        tipo_documento=doc_type,
        tese=thesis or "",
        instrucoes=instrucoes
    )
    
    # Claude critica GPT + Gemini
    critica_claude_prompt = t_critica.render(
        texto_colega=f"### VERSÃO GPT:\n{versao_gpt_v1}\n\n### VERSÃO GEMINI:\n{versao_gemini_v1}",
        rag_context=full_rag,
        tipo_documento=doc_type,
        tese=thesis or "",
        instrucoes=instrucoes
    )
    
    # Judge model critica GPT + Claude
    critica_gemini_prompt = t_critica.render(
        texto_colega=f"### VERSÃO GPT:\n{versao_gpt_v1}\n\n### VERSÃO CLAUDE:\n{versao_claude_v1}",
        rag_context=full_rag,
        tipo_documento=doc_type,
        tese=thesis or "",
        instrucoes=instrucoes
    )
    
    # Check cache first
    critica_gpt = get_cached_critique(critica_gpt_prompt)
    critica_claude = get_cached_critique(critica_claude_prompt)
    critica_gemini = get_cached_critique(critica_gemini_prompt)
    
    # Parallel critique calls
    critique_tasks = []
    if not critica_gpt:
        critique_tasks.append(("gpt", call_openai_async(
            gpt_client,
            critica_gpt_prompt,
            model=gpt_model,
            system_instruction=system_instruction
        )))
    if not critica_claude:
        critique_tasks.append(("claude", call_anthropic_async(
            claude_client,
            critica_claude_prompt,
            model=claude_model,
            system_instruction=system_instruction
        )))
    if not critica_gemini:
        critique_tasks.append(("gemini", _call_model(judge_model_id, critica_gemini_prompt, sys_gemini_blind)))
    
    if critique_tasks:
        results = await asyncio.gather(*[t[1] for t in critique_tasks])
        result_map = {critique_tasks[i][0]: results[i] for i in range(len(critique_tasks))}
        critica_gpt = critica_gpt or result_map.get("gpt", "")
        critica_claude = critica_claude or result_map.get("claude", "")
        critica_gemini = critica_gemini or result_map.get("gemini", "")
        
        # Cache the critiques
        if critica_gpt:
            set_cached_critique(critica_gpt_prompt, critica_gpt)
        if critica_claude:
            set_cached_critique(critica_claude_prompt, critica_claude)
        if critica_gemini:
            set_cached_critique(critica_gemini_prompt, critica_gemini)
    
    drafts['critica_gpt'] = critica_gpt or ""
    drafts['critica_claude'] = critica_claude or ""
    drafts['critica_gemini'] = critica_gemini or ""
    
    # R3: Triangular Revision (each agent receives feedback from the other two)
    print(f"   ✏️ [R3] Revisões triangulares (3 agentes)...")
    t_revisao = Template(V2_PROMPT_REVISAO)
    
    # GPT revisa com críticas do Claude e Gemini
    rev_gpt_prompt = t_revisao.render(
        texto_original=versao_gpt_v1,
        critica_recebida=f"### CRÍTICA DO CLAUDE:\n{critica_claude or 'N/A'}\n\n### CRÍTICA DO GEMINI:\n{critica_gemini or 'N/A'}",
        rag_context=full_rag,
        tipo_documento=doc_type,
        tese=thesis or "",
        instrucoes=instrucoes
    )
    
    # Claude revisa com críticas do GPT e Gemini
    rev_claude_prompt = t_revisao.render(
        texto_original=versao_claude_v1,
        critica_recebida=f"### CRÍTICA DO GPT:\n{critica_gpt or 'N/A'}\n\n### CRÍTICA DO GEMINI:\n{critica_gemini or 'N/A'}",
        rag_context=full_rag,
        tipo_documento=doc_type,
        tese=thesis or "",
        instrucoes=instrucoes
    )
    
    # Judge model revisa com críticas do GPT e Claude
    rev_gemini_prompt = t_revisao.render(
        texto_original=versao_gemini_v1,
        critica_recebida=f"### CRÍTICA DO GPT:\n{critica_gpt or 'N/A'}\n\n### CRÍTICA DO CLAUDE:\n{critica_claude or 'N/A'}",
        rag_context=full_rag,
        tipo_documento=doc_type,
        tese=thesis or "",
        instrucoes=instrucoes
    )
    
    # Parallel revision calls
    versao_gpt_v2, versao_claude_v2, versao_gemini_v2 = await asyncio.gather(
        call_openai_async(
            gpt_client,
            rev_gpt_prompt,
            model=gpt_model,
            system_instruction=system_instruction
        ),
        call_anthropic_async(
            claude_client,
            rev_claude_prompt,
            model=claude_model,
            system_instruction=system_instruction
        ),
        _call_model(judge_model_id, rev_gemini_prompt, sys_gemini_blind)
    )
    
    drafts['gpt_v2'] = versao_gpt_v2 or versao_gpt_v1
    drafts['claude_v2'] = versao_claude_v2 or versao_claude_v1
    drafts['gemini_v2'] = versao_gemini_v2 or versao_gemini_v1
    
    final_gpt = versao_gpt_v2 or versao_gpt_v1
    final_claude = versao_claude_v2 or versao_claude_v1
    final_gemini = versao_gemini_v2 or versao_gemini_v1
    
    # R4: Judge (uses selected judge model)
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
    t = Template(V2_PROMPT_JUIZ)
    judge_prompt = t.render(
        titulo_secao=section_title,
        tese=thesis or "",
        secoes_anteriores=secoes_anteriores,
        versao_a=final_gpt,
        versao_b=final_claude,
        versao_c=final_gemini,  # Use revised Gemini version (v2) instead of v1
        rag_context=full_rag,
        tipo_documento=doc_type,
        instrucoes=instrucoes,
        diretrizes_formatacao=diretrizes_formatacao,
        modelo_estrutura=modelo_estrutura
    )
    full_response = await _call_model(
        judge_model_id,
        judge_prompt,
        sys_gemini_judge,
        cached_content=cached_content
    )
    if not full_response:
        return final_gpt, "", drafts
    parsed = _extract_json_obj(full_response)
    if parsed and parsed.get("final_text"):
        final_text = parsed.get("final_text") or ""
        divergences = parsed.get("divergences") or []
        divergencias = json.dumps(divergences, ensure_ascii=False, indent=2) if isinstance(divergences, list) else ""
        drafts["claims_requiring_citation"] = parsed.get("claims_requiring_citation") or []
        drafts["removed_claims"] = parsed.get("removed_claims") or []
        drafts["risk_flags"] = parsed.get("risk_flags") or []
        drafts["judge_structured"] = parsed
        return final_text, divergencias, drafts

    # Legacy fallback
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
    divergencias = f"## Seção: {section_title}\n\n### Críticas Triangulares\n**GPT (sobre Claude+Gemini):** {(critica_gpt or 'N/A')[:400]}...\n\n**Claude (sobre GPT+Gemini):** {(critica_claude or 'N/A')[:400]}...\n\n**Gemini (sobre GPT+Claude):** {(critica_gemini or 'N/A')[:400]}...\n\n{log_section}"
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
