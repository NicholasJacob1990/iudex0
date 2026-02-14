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
import contextvars
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
from app.services.api_call_tracker import record_api_call, billing_context
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
    region = os.getenv("VERTEX_AI_LOCATION", "global")
    # Prefer the dedicated Gemini key when both are present.
    # `GOOGLE_API_KEY` is commonly used for other Google APIs and may have different quotas.
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    force_direct = os.getenv("GEMINI_FORCE_DIRECT", "false").lower() == "true"
    
    # We prioritize Vertex AI (GCP) if project_id is available AND not forced direct
    if project_id and not force_direct:
        logger.info(f"🔗 [Gemini] Inicializando via Vertex AI (project={project_id}, region={region})")
        return genai.Client(vertexai=True, project=project_id, location=region)
    elif api_key:
        if force_direct:
            logger.info("⚡ [Gemini] GEMINI_FORCE_DIRECT=true: Usando API keys diretas (bypass Vertex)")
        else:
            logger.info("🔑 [Gemini] Sem GOOGLE_CLOUD_PROJECT, usando API key direta")
        return genai.Client(api_key=api_key)
    logger.warning("⚠️ [Gemini] Sem credenciais: GOOGLE_CLOUD_PROJECT e GEMINI_API_KEY/GOOGLE_API_KEY ausentes")
    return None

def init_openai_client():
    """Initialize Vertex AI client for GPT agent (Model Garden) or fallback to direct OpenAI"""
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    force_direct = os.getenv("OPENAI_FORCE_DIRECT", "false").lower() == "true"

    if project_id and genai and not force_direct:
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
    
    if force_direct:
        logger.info("⚡ OPENAI_FORCE_DIRECT=true: Usando API keys diretas (bypass Vertex)")

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


# Cached direct client for code execution fallback (Vertex doesn't support code-execution beta)
_async_anthropic_direct_client = None

def get_async_claude_direct_client():
    """Get a direct (non-Vertex) Anthropic client for features not supported on Vertex AI.

    Used as fallback when the primary client is Vertex but the feature (e.g. code execution)
    requires the direct Anthropic API.
    """
    global _async_anthropic_direct_client
    if _async_anthropic_direct_client is not None:
        return _async_anthropic_direct_client

    if not anthropic:
        return None

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return None

    _async_anthropic_direct_client = anthropic.AsyncAnthropic(api_key=api_key)
    return _async_anthropic_direct_client


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
_INTERACTION_RULES = (
    "REGRA DE INTERAÇÃO: "
    "Para mensagens casuais (oi, olá, bom dia, obrigado, tudo bem), responda brevemente e de forma natural. "
    "NÃO gere templates, minutas ou peças jurídicas a menos que explicitamente solicitado. "
    "Adapte a extensão e formalidade da resposta à complexidade da pergunta."
)

DEFAULT_LEGAL_SYSTEM_INSTRUCTION = (
    "Você é um especialista jurídico brasileiro altamente qualificado. "
    f"{_INTERACTION_RULES} "
    "Quando o assunto exigir, use linguagem técnica e formal. "
    "Ao citar fatos dos autos, use o formato [TIPO - Doc. X, p. Y]. "
    "GRAFO (ask_graph): para CRIAR arestas use ask_graph(operation=\"link_entities\") e "
    "antes resolva entity_ids com ask_graph(operation=\"search\"); nunca invente IDs."
)
DEFAULT_GENERAL_SYSTEM_INSTRUCTION = (
    "Você é um assistente geral prestativo. Responda em português claro e natural, "
    "sem jargões jurídicos, e seja objetivo. "
    f"{_INTERACTION_RULES}"
)


def build_system_instruction(chat_personality: Optional[str]) -> str:
    if (chat_personality or "").lower() == "geral":
        return DEFAULT_GENERAL_SYSTEM_INSTRUCTION
    return DEFAULT_LEGAL_SYSTEM_INSTRUCTION


def _usage_meta(
    *,
    tokens_in: Optional[int] = None,
    tokens_out: Optional[int] = None,
    cached_tokens_in: Optional[int] = None,
    context_tokens: Optional[int] = None,
    seconds_audio: Optional[float] = None,
    seconds_video: Optional[float] = None,
    **extra: Any,
) -> Dict[str, Any]:
    meta: Dict[str, Any] = {}
    if tokens_in is not None:
        try:
            meta["tokens_in"] = int(tokens_in)
        except (TypeError, ValueError):
            pass
    if tokens_out is not None:
        try:
            meta["tokens_out"] = int(tokens_out)
        except (TypeError, ValueError):
            pass
    if cached_tokens_in is not None:
        try:
            meta["cached_tokens_in"] = int(cached_tokens_in)
        except (TypeError, ValueError):
            pass
    if context_tokens is not None:
        try:
            meta["context_tokens"] = int(context_tokens)
        except (TypeError, ValueError):
            pass
    if seconds_audio is not None:
        try:
            meta["seconds_audio"] = float(seconds_audio)
        except (TypeError, ValueError):
            pass
    if seconds_video is not None:
        try:
            meta["seconds_video"] = float(seconds_video)
        except (TypeError, ValueError):
            pass
    for key, value in extra.items():
        if value is not None:
            meta[key] = value
    return meta


def _get_usage_value(obj: Any, *keys: str) -> Optional[Any]:
    for key in keys:
        if isinstance(obj, dict):
            if key in obj:
                return obj.get(key)
        if hasattr(obj, key):
            return getattr(obj, key)
    return None


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
    output_tokens = 0
    is_vertex = genai and isinstance(client, genai.Client)
    provider_name = "vertex-openai" if is_vertex else "openai"
    
    try:
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
            usage = getattr(response, "usage_metadata", None)
            prompt_tokens = _get_usage_value(usage, "prompt_token_count", "input_tokens")
            if prompt_tokens is not None:
                input_tokens = prompt_tokens
            completion_tokens = _get_usage_value(usage, "candidates_token_count", "output_tokens")
            if completion_tokens is not None:
                output_tokens = completion_tokens
            cached_tokens = _get_usage_value(
                usage,
                "cached_content_token_count",
                "cached_token_count",
                "cached_tokens",
            )
            usage_meta = _usage_meta(
                tokens_in=input_tokens,
                tokens_out=output_tokens,
                cached_tokens_in=cached_tokens,
                context_tokens=input_tokens,
            )
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
            usage = getattr(response, "usage", None)
            prompt_tokens = _get_usage_value(usage, "prompt_tokens", "input_tokens")
            if prompt_tokens is not None:
                input_tokens = prompt_tokens
            completion_tokens = _get_usage_value(usage, "completion_tokens", "output_tokens")
            if completion_tokens is not None:
                output_tokens = completion_tokens
            details = _get_usage_value(usage, "prompt_tokens_details", "input_tokens_details")
            cached_tokens = _get_usage_value(details, "cached_tokens", "cached")
            usage_meta = _usage_meta(
                tokens_in=input_tokens,
                tokens_out=output_tokens,
                cached_tokens_in=cached_tokens,
                context_tokens=input_tokens,
            )
        
        agent_metrics.record(
            provider=provider_name, model=model,
            input_tokens=input_tokens, output_tokens=output_tokens,
            latency_ms=int((time.time() - start_time) * 1000),
            success=True
        )
        record_api_call(
            kind="llm",
            provider=provider_name,
            model=model,
            success=True,
            meta=usage_meta,
        )
        return output_text
    except Exception as e:
        logger.error(f"❌ Erro ao chamar GPT via Vertex: {e}")
        agent_metrics.record(
            provider=provider_name, model=model,
            input_tokens=input_tokens, output_tokens=0,
            latency_ms=int((time.time() - start_time) * 1000),
            success=False
        )
        record_api_call(
            kind="llm",
            provider=provider_name,
            model=model,
            success=False,
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
    output_tokens = 0
    
    last_error = None
    is_vertex = _is_anthropic_vertex_client(client)
    provider_name = "vertex-anthropic" if is_vertex else "anthropic"
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
                usage = getattr(response, "usage", None)
                prompt_tokens = _get_usage_value(usage, "input_tokens", "prompt_tokens")
                if prompt_tokens is not None:
                    input_tokens = prompt_tokens
                completion_tokens = _get_usage_value(usage, "output_tokens", "completion_tokens")
                if completion_tokens is not None:
                    output_tokens = completion_tokens
                cached_tokens = _get_usage_value(usage, "cache_read_input_tokens", "cached_input_tokens")
                cache_write_tokens = _get_usage_value(
                    usage,
                    "cache_creation_input_tokens",
                    "cache_write_input_tokens",
                )
                usage_meta = _usage_meta(
                    tokens_in=input_tokens,
                    tokens_out=output_tokens,
                    cached_tokens_in=cached_tokens,
                    context_tokens=input_tokens,
                    cache_write_tokens_in=cache_write_tokens,
                )
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
                usage = getattr(response, "usage", None)
                prompt_tokens = _get_usage_value(usage, "input_tokens", "prompt_tokens")
                if prompt_tokens is not None:
                    input_tokens = prompt_tokens
                completion_tokens = _get_usage_value(usage, "output_tokens", "completion_tokens")
                if completion_tokens is not None:
                    output_tokens = completion_tokens
                cached_tokens = _get_usage_value(usage, "cache_read_input_tokens", "cached_input_tokens")
                cache_write_tokens = _get_usage_value(
                    usage,
                    "cache_creation_input_tokens",
                    "cache_write_input_tokens",
                )
                usage_meta = _usage_meta(
                    tokens_in=input_tokens,
                    tokens_out=output_tokens,
                    cached_tokens_in=cached_tokens,
                    context_tokens=input_tokens,
                    cache_write_tokens_in=cache_write_tokens,
                )

            agent_metrics.record(
                provider=provider_name, model=model,
                input_tokens=input_tokens, output_tokens=output_tokens,
                latency_ms=int((time.time() - start_time) * 1000),
                success=True
            )
            record_api_call(
                kind="llm",
                provider=provider_name,
                model=model,
                success=True,
                meta=usage_meta,
            )
            return output_text
        except Exception as e:
            last_error = e
            record_api_call(
                kind="llm",
                provider=provider_name,
                model=model,
                success=False,
            )
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
                            usage = getattr(response, "usage", None)
                            prompt_tokens = _get_usage_value(usage, "input_tokens", "prompt_tokens")
                            if prompt_tokens is not None:
                                input_tokens = prompt_tokens
                            completion_tokens = _get_usage_value(usage, "output_tokens", "completion_tokens")
                            if completion_tokens is not None:
                                output_tokens = completion_tokens
                            cached_tokens = _get_usage_value(usage, "cache_read_input_tokens", "cached_input_tokens")
                            cache_write_tokens = _get_usage_value(
                                usage,
                                "cache_creation_input_tokens",
                                "cache_write_input_tokens",
                            )
                            usage_meta = _usage_meta(
                                tokens_in=input_tokens,
                                tokens_out=output_tokens,
                                cached_tokens_in=cached_tokens,
                                context_tokens=input_tokens,
                                cache_write_tokens_in=cache_write_tokens,
                            )
                            agent_metrics.record(
                                provider="anthropic", model=direct_model,
                                input_tokens=input_tokens, output_tokens=output_tokens,
                                latency_ms=int((time.time() - start_time) * 1000),
                                success=True
                            )
                            record_api_call(
                                kind="llm",
                                provider="anthropic",
                                model=direct_model,
                                success=True,
                                meta=usage_meta,
                            )
                            return output_text
                        except Exception as direct_error:
                            record_api_call(
                                kind="llm",
                                provider="anthropic",
                                model=direct_model,
                                success=False,
                            )
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
        provider=provider_name, model=model,
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
    output_tokens = 0
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
        usage = getattr(response, "usage_metadata", None)
        prompt_tokens = _get_usage_value(usage, "prompt_token_count", "input_tokens")
        if prompt_tokens is not None:
            input_tokens = prompt_tokens
        completion_tokens = _get_usage_value(usage, "candidates_token_count", "output_tokens")
        if completion_tokens is not None:
            output_tokens = completion_tokens
        cached_tokens = _get_usage_value(
            usage,
            "cached_content_token_count",
            "cached_token_count",
            "cached_tokens",
        )
        audio_seconds = _get_usage_value(
            usage,
            "prompt_audio_duration_seconds",
            "audio_duration_seconds",
            "audio_seconds",
        )
        video_seconds = _get_usage_value(
            usage,
            "prompt_video_duration_seconds",
            "video_duration_seconds",
            "video_seconds",
        )
        usage_meta = _usage_meta(
            tokens_in=input_tokens,
            tokens_out=output_tokens,
            cached_tokens_in=cached_tokens,
            context_tokens=input_tokens,
            seconds_audio=audio_seconds,
            seconds_video=video_seconds,
        )

        agent_metrics.record(
            provider="vertex-gemini", model=model_id,
            input_tokens=input_tokens, output_tokens=output_tokens,
            latency_ms=int((time.time() - start_time) * 1000),
            success=True
        )
        record_api_call(
            kind="llm",
            provider="vertex-gemini",
            model=model_id,
            success=True,
            meta=usage_meta,
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
        record_api_call(
            kind="llm",
            provider="vertex-gemini",
            model=model_id,
            success=False,
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
    system_instruction: Optional[str] = None,
    reasoning_effort: Optional[str] = None,  # NEW: 'none'|'low'|'medium'|'high'|'xhigh'
) -> Optional[str]:
    """Async version using native genai.Client.aio for Vertex or executor for fallback.
    
    Args:
        reasoning_effort: For o1/o3/GPT-5.2 models. Options: 'none', 'low', 'medium', 'high', 'xhigh'.
                         When 'none', no reasoning is triggered.
    """
    if not client:
        return None
        
    is_vertex = genai and isinstance(client, genai.Client)
    
    if is_vertex:
        start_time = time.time()
        input_tokens = len(prompt) // 4
        output_tokens = 0
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
            usage = getattr(response, "usage_metadata", None)
            prompt_tokens = _get_usage_value(usage, "prompt_token_count", "input_tokens")
            if prompt_tokens is not None:
                input_tokens = prompt_tokens
            completion_tokens = _get_usage_value(usage, "candidates_token_count", "output_tokens")
            if completion_tokens is not None:
                output_tokens = completion_tokens
            cached_tokens = _get_usage_value(
                usage,
                "cached_content_token_count",
                "cached_token_count",
                "cached_tokens",
            )
            usage_meta = _usage_meta(
                tokens_in=input_tokens,
                tokens_out=output_tokens,
                cached_tokens_in=cached_tokens,
                context_tokens=input_tokens,
            )
            
            agent_metrics.record(
                provider="vertex-openai", model=model,
                input_tokens=input_tokens, output_tokens=output_tokens,
                latency_ms=int((time.time() - start_time) * 1000),
                success=True
            )
            record_api_call(
                kind="llm",
                provider="vertex-openai",
                model=model,
                success=True,
                meta=usage_meta,
            )
            return output_text
        except Exception as e:
            logger.error(f"❌ Erro assíncrono GPT via Vertex: {e}")
            record_api_call(
                kind="llm",
                provider="vertex-openai",
                model=model,
                success=False,
            )
            return None
    else:
        # Fallback to executor for direct sync SDK
        # For reasoning models, use Responses API with reasoning_effort
        if openai and reasoning_effort and reasoning_effort != "none":
            is_reasoning_model = model.startswith(("o1-", "o3-")) or "gpt-5.2" in model.lower()
            if is_reasoning_model and hasattr(client, "responses"):
                try:
                    # Normalize effort
                    effort = reasoning_effort.lower()
                    if effort == "minimal":
                        effort = "low"
                    if effort == "xhigh":
                        effort = "high"
                    if effort not in ("low", "medium", "high"):
                        effort = "medium"
                    
                    system_instruction = system_instruction or DEFAULT_LEGAL_SYSTEM_INSTRUCTION
                    messages = [
                        {"role": "system", "content": system_instruction},
                        {"role": "user", "content": prompt},
                    ]
                    
                    response = client.responses.create(
                        model=model,
                        input=messages,
                        max_output_tokens=max_tokens,
                        reasoning={"effort": effort, "summary": "auto"},
                    )
                    record_api_call(
                        kind="llm",
                        provider="openai",
                        model=model,
                        success=True,
                        meta={"reasoning_effort": effort},
                    )
                    return getattr(response, "output_text", "") or ""
                except Exception as e:
                    logger.warning(f"OpenAI Responses API failed, falling back: {e}")
                    record_api_call(
                        kind="llm",
                        provider="openai",
                        model=model,
                        success=False,
                        meta={"reasoning_effort": reasoning_effort},
                    )
        
        loop = asyncio.get_event_loop()
        ctx = contextvars.copy_context()
        return await loop.run_in_executor(
            None,
            lambda: ctx.run(
                call_openai,
                client,
                prompt,
                model,
                max_tokens,
                temperature,
                timeout,
                system_instruction,
            ),
        )


async def call_anthropic_async(
    client,
    prompt: str,
    model: str = "claude-4.5-sonnet",
    max_tokens: int = 4000,
    temperature: float = 0.3,
    timeout: int = API_TIMEOUT_SECONDS,
    web_search: bool = False,
    system_instruction: Optional[str] = None,
    extended_thinking: bool = False,  # NEW: Enable extended thinking for Claude Sonnet
    thinking_budget: Optional[int] = None,  # NEW: Token budget for thinking (e.g. 8000)
) -> Optional[str]:
    """Async version using native async client or executor for sync clients.
    
    Args:
        extended_thinking: Enable extended thinking mode for Claude Sonnet.
        thinking_budget: Token budget for thinking. Default is 8000 if extended_thinking is True.
    """
    if not client:
        return None

    # If extended_thinking is requested, use native async with thinking support
    if extended_thinking and anthropic:
        from app.services.ai.model_registry import get_api_model_name
        
        system_instruction = system_instruction or DEFAULT_LEGAL_SYSTEM_INSTRUCTION
        model_id = get_api_model_name(model)
        
        # Normalize thinking budget (Claude supports 0-63999)
        # v6.1: Lower budget for minimal/low to speed up response
        default_budget = 4000 if not extended_thinking else 10000
        budget_tokens = thinking_budget if thinking_budget is not None else default_budget
        try:
            budget_tokens = int(budget_tokens)
        except (TypeError, ValueError):
            budget_tokens = 10000
        if budget_tokens <= 0:
            budget_tokens = 10000
        if budget_tokens > 63999:
            budget_tokens = 63999
        
        # Ensure max_tokens > budget_tokens
        effective_max_tokens = max_tokens
        if effective_max_tokens <= budget_tokens:
            effective_max_tokens = budget_tokens + 4000
        
        is_vertex = _is_anthropic_vertex_client(client)
        provider_name = "vertex-anthropic" if is_vertex else "anthropic"
        
        try:
            # Check if client supports async
            if hasattr(client, "messages") and hasattr(client.messages, "create"):
                create_kwargs = {
                    "model": model_id if not is_vertex else model_id,
                    "max_tokens": effective_max_tokens,
                    "messages": [{"role": "user", "content": prompt}],
                    "system": system_instruction,
                    "thinking": {"type": "enabled", "budget_tokens": budget_tokens},
                    "temperature": 1.0,  # Required for extended thinking
                }
                
                logger.info(f"🧠 [Claude Thinking Async] budget={budget_tokens}, max_tokens={effective_max_tokens}")
                
                response = client.messages.create(**create_kwargs)
                record_api_call(
                    kind="llm",
                    provider=provider_name,
                    model=model_id,
                    success=True,
                    meta={"extended_thinking": True, "budget_tokens": budget_tokens},
                )
                
                # Extract text content (skip thinking blocks)
                output_text = ""
                if hasattr(response, "content"):
                    for block in response.content:
                        if getattr(block, "type", "") == "text":
                            output_text += getattr(block, "text", "")
                
                return output_text
        except Exception as e:
            logger.warning(f"Claude extended thinking async failed: {e}")
            record_api_call(
                kind="llm",
                provider=provider_name,
                model=model_id,
                success=False,
                meta={"extended_thinking": True},
            )
            # Fall through to standard call

    loop = asyncio.get_event_loop()
    ctx = contextvars.copy_context()
    return await loop.run_in_executor(
        None,
        lambda: ctx.run(
            call_anthropic,
            client,
            prompt,
            model,
            max_tokens,
            temperature,
            timeout,
            system_instruction,
        ),
    )


async def call_perplexity_async(
    prompt: str,
    *,
    model: str = "sonar",
    max_tokens: int = 4096,
    temperature: float = 0.3,
    system_instruction: Optional[str] = None,
    web_search_enabled: bool = False,
    search_mode: Optional[str] = None,
    search_type: Optional[str] = None,
    search_context_size: Optional[str] = None,
    enable_search_classifier: bool = False,
    disable_search: bool = False,
    stream_mode: Optional[str] = None,
) -> Optional[str]:
    api_key = os.getenv("PERPLEXITY_API_KEY")
    if not api_key:
        return None

    try:
        from perplexity import AsyncPerplexity
    except Exception as exc:
        logger.warning(f"⚠️ Perplexity SDK indisponível: {exc}")
        return None

    from app.services.ai.perplexity_config import build_perplexity_chat_kwargs

    messages: List[Dict[str, str]] = []
    if system_instruction:
        messages.append({"role": "system", "content": system_instruction})
    messages.append({"role": "user", "content": prompt})

    perplexity_kwargs = build_perplexity_chat_kwargs(
        api_model=model,
        web_search_enabled=web_search_enabled,
        search_mode=search_mode,
        search_type=search_type,
        search_context_size=search_context_size,
        enable_search_classifier=enable_search_classifier,
        disable_search=disable_search,
        stream_mode=stream_mode,
    )

    def _get(obj: Any, key: str, default=None):
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    client = AsyncPerplexity(api_key=api_key)
    try:
        resp = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False,
            **perplexity_kwargs,
        )
        usage = _get(resp, "usage", None) or _get(resp, "usage_metadata", None)
        tokens_in = _get(usage, "prompt_tokens", None) or _get(usage, "input_tokens", None)
        tokens_out = _get(usage, "completion_tokens", None) or _get(usage, "output_tokens", None)
        meta = {
            "stream": False,
            "disable_search": bool(perplexity_kwargs.get("disable_search")),
            "search_mode": perplexity_kwargs.get("search_mode"),
            "search_type": perplexity_kwargs.get("search_type"),
            "search_context_size": perplexity_kwargs.get("search_context_size"),
            "stream_mode": perplexity_kwargs.get("stream_mode"),
            "has_web_search_options": bool(perplexity_kwargs.get("web_search_options")),
        }
        if tokens_in is not None:
            meta["tokens_in"] = int(tokens_in)
        if tokens_out is not None:
            meta["tokens_out"] = int(tokens_out)
        record_api_call(
            kind="llm",
            provider="perplexity",
            model=model,
            success=True,
            meta=meta,
        )
    except Exception:
        record_api_call(
            kind="llm",
            provider="perplexity",
            model=model,
            success=False,
            meta={"stream": False},
        )
        return None

    choices = _get(resp, "choices", []) or []
    if choices:
        message = _get(choices[0], "message", None) or {}
        content = _get(message, "content", None)
        if isinstance(content, str) and content.strip():
            return content.strip()

    output_text = _get(resp, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    return None


async def call_vertex_gemini_async(
    client,
    prompt: str,
    model: str = "gemini-3-flash",
    max_tokens: int = 8192,
    temperature: float = 0.3,
    timeout: int = API_TIMEOUT_SECONDS,
    web_search: bool = False,
    system_instruction: Optional[str] = None,
    thinking_mode: Optional[str] = None,  # NEW: 'none'|'minimal'|'low'|'medium'|'high'
) -> Optional[str]:
    """Async version using native genai.Client.aio or executor fallback.
    
    Args:
        thinking_mode: Enable thinking for Gemini 2.x/3.x models.
                      Options: None (disabled), 'minimal', 'low', 'medium', 'high'.
                      When 'none' or None, thinking is disabled.
    """
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
        output_tokens = 0
        api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        force_direct = os.getenv("GEMINI_FORCE_DIRECT", "false").lower() == "true"
        direct_fallback_used = False
        try:
            from app.services.ai.model_registry import get_api_model_name
            model_id = get_api_model_name(model)

            system_instruction = system_instruction or DEFAULT_LEGAL_SYSTEM_INSTRUCTION

            # Build config kwargs
            config_kwargs = {
                "system_instruction": system_instruction,
                "max_output_tokens": max_tokens,
                "temperature": temperature,
            }
            
            # Apply thinking mode if specified and not "none"
            if thinking_mode and thinking_mode.lower() not in ("none", "off", "disabled"):
                raw = thinking_mode.lower()
                # SDK ThinkingLevel enum expects UPPERCASE
                if raw in ("standard", "medium"):
                    normalized_thinking = "MEDIUM"
                elif raw in ("extended", "high", "xhigh"):
                    normalized_thinking = "HIGH"
                elif raw == "minimal":
                    normalized_thinking = "MINIMAL"
                elif raw == "low":
                    normalized_thinking = "LOW"
                else:
                    normalized_thinking = raw.upper()

                logger.info(f"🧠 [Gemini Async] Ativando thinking_mode={normalized_thinking} para {model_id}")
                if normalized_thinking in ("MEDIUM", "HIGH"):
                    try:
                        thinking_config = types.ThinkingConfig(
                            include_thoughts=True, thinking_level=normalized_thinking
                        )
                    except Exception:
                        thinking_config = types.ThinkingConfig(include_thoughts=True)
                else:
                    thinking_config = types.ThinkingConfig(include_thoughts=True)
                config_kwargs["thinking_config"] = thinking_config

            async def _call(active_client):
                return await active_client.aio.models.generate_content(
                    model=model_id,
                    contents=prompt,
                    config=types.GenerateContentConfig(**config_kwargs),
                )

            try:
                response = await _call(client)
            except Exception as exc:
                msg = str(exc).lower()
                is_not_found = (
                    ("404" in msg and ("not_found" in msg or "not found" in msg))
                    or ("publisher model" in msg and "not found" in msg)
                    or ("was not found" in msg)
                )
                # Check for 400 error with thinking (unsupported)
                if "400" in str(exc) and thinking_mode:
                    logger.warning(f"⚠️ Erro 400 com Thinking ({exc}). Tentando fallback sem thinking...")
                    config_kwargs.pop("thinking_config", None)
                    response = await _call(client)
                elif is_not_found and api_key and not force_direct:
                    logger.warning(f"⚠️ Modelo indisponível no Vertex ({model_id}). Tentando Gemini direto via API key...")
                    record_api_call(
                        kind="llm",
                        provider="vertex-gemini",
                        model=model_id,
                        success=False,
                        meta={"fallback": "direct"},
                    )
                    direct_fallback_used = True
                    direct_client = genai.Client(api_key=api_key)
                    response = await _call(direct_client)
                else:
                    raise
            output_text = extract_genai_text(response)
            usage = getattr(response, "usage_metadata", None)
            prompt_tokens = _get_usage_value(usage, "prompt_token_count", "input_tokens")
            if prompt_tokens is not None:
                input_tokens = prompt_tokens
            completion_tokens = _get_usage_value(usage, "candidates_token_count", "output_tokens")
            if completion_tokens is not None:
                output_tokens = completion_tokens
            cached_tokens = _get_usage_value(
                usage,
                "cached_content_token_count",
                "cached_token_count",
                "cached_tokens",
            )
            audio_seconds = _get_usage_value(
                usage,
                "prompt_audio_duration_seconds",
                "audio_duration_seconds",
                "audio_seconds",
            )
            video_seconds = _get_usage_value(
                usage,
                "prompt_video_duration_seconds",
                "video_duration_seconds",
                "video_seconds",
            )
            usage_meta = _usage_meta(
                tokens_in=input_tokens,
                tokens_out=output_tokens,
                cached_tokens_in=cached_tokens,
                context_tokens=input_tokens,
                seconds_audio=audio_seconds,
                seconds_video=video_seconds,
            )

            agent_metrics.record(
                provider="vertex-gemini", model=model_id,
                input_tokens=input_tokens, output_tokens=output_tokens,
                latency_ms=int((time.time() - start_time) * 1000),
                success=True
            )
            record_api_call(
                kind="llm",
                provider="vertex-gemini",
                model=model_id,
                success=True,
                meta={**usage_meta, **({"fallback": "direct"} if direct_fallback_used else {}), **({"thinking_mode": thinking_mode} if thinking_mode else {})},
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
            record_api_call(
                kind="llm",
                provider="vertex-gemini",
                model=model_id,
                success=False,
            )
            return None


async def stream_openai_async(
    client,
    prompt: str,
    model: str = "gpt-5.2",
    max_tokens: int = 4000,
    temperature: float = 0.3,
    system_instruction: Optional[str] = None,
    reasoning_effort: Optional[str] = None,  # For reasoning models (o1/o3, GPT-5.2)
    enable_code_interpreter: bool = True,  # OpenAI code interpreter (Responses API)
    container_id: Optional[str] = None,  # Container reuse for code interpreter
):
    """Async streaming for GPT (Vertex or direct) with thinking support.

    Args:
        reasoning_effort: Options: 'none', 'low', 'medium', 'high', 'xhigh'
        enable_code_interpreter: Enable code interpreter via Responses API
        container_id: Optional container ID to reuse sandbox state

    Yields:
        Tuples of (chunk_type, content) where chunk_type is 'thinking', 'text',
        'code_execution', 'code_execution_result', or 'container_id'
    """
    if not client:
        return

    system_instruction = system_instruction or DEFAULT_LEGAL_SYSTEM_INSTRUCTION

    if genai and isinstance(client, genai.Client):
        from app.services.ai.model_registry import get_api_model_name
        model_id = get_api_model_name(model)
        if hasattr(client.aio.models, "generate_content_stream"):
            try:
                stream = client.aio.models.generate_content_stream(
                    model=model_id,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        max_output_tokens=max_tokens,
                        temperature=temperature,
                    )
                )
                record_api_call(
                    kind="llm",
                    provider="vertex-openai",
                    model=model_id,
                    success=True,
                    meta={"stream": True},
                )
            except Exception:
                record_api_call(
                    kind="llm",
                    provider="vertex-openai",
                    model=model_id,
                    success=False,
                    meta={"stream": True},
                )
                raise
            if asyncio.iscoroutine(stream):
                stream = await stream
            if hasattr(stream, "__aiter__"):
                async for chunk in stream:
                    text = getattr(chunk, "text", "") or ""
                    if text:
                        yield ('text', text)
                return

        try:
            response = await client.aio.models.generate_content(
                model=model_id,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    max_output_tokens=max_tokens,
                    temperature=temperature,
                )
            )
            record_api_call(
                kind="llm",
                provider="vertex-openai",
                model=model_id,
                success=True,
            )
        except Exception:
            record_api_call(
                kind="llm",
                provider="vertex-openai",
                model=model_id,
                success=False,
            )
            raise
        output_text = getattr(response, "text", "") or ""
        if output_text:
            yield ('text', output_text)
        return

    if not openai:
        return

    async_client = client if isinstance(client, openai.AsyncOpenAI) else get_async_openai_client()
    if not async_client:
        return

    # --- Responses API path (when code_interpreter is enabled) ---
    # Chat Completions API does NOT support code_interpreter; Responses API does.
    _has_responses_api = hasattr(async_client, 'responses') and hasattr(async_client.responses, 'create')
    if enable_code_interpreter and _has_responses_api:
        logger.info(f"🔧 [OpenAI] Using Responses API with code_interpreter for model={model}")
        ci_tool: Dict[str, Any] = {"type": "code_interpreter"}
        if container_id:
            ci_tool["container"] = container_id
        else:
            ci_tool["container"] = {"type": "auto"}

        responses_kwargs: Dict[str, Any] = {
            "model": model,
            "tools": [ci_tool],
            "instructions": system_instruction,
            "input": prompt,
        }
        if max_tokens:
            responses_kwargs["max_output_tokens"] = max_tokens
        if temperature != 1.0:
            responses_kwargs["temperature"] = temperature
        if reasoning_effort and (model.startswith(("o1-", "o3-")) or "gpt-5" in model):
            responses_kwargs["reasoning"] = {"effort": reasoning_effort}

        # Include code_interpreter outputs in response
        responses_kwargs["include"] = ["code_interpreter_call.outputs"]

        try:
            # Use streaming if available
            if hasattr(async_client.responses, 'create'):
                response = await async_client.responses.create(stream=True, **responses_kwargs)
                record_api_call(
                    kind="llm", provider="openai", model=model,
                    success=True, meta={"stream": True, "code_interpreter": True, "api": "responses"},
                )

                # Process streaming events from Responses API
                # Event names per OpenAI docs (note underscores not dots between call_code):
                #   response.output_text.delta — text output
                #   response.reasoning_summary_text.delta — thinking
                #   response.code_interpreter_call_code.delta — code being generated
                #   response.code_interpreter_call_code.done — code generation complete
                #   response.code_interpreter_call.completed — execution finished (contains outputs)
                #   response.completed — full response done
                _ci_code_buffer = []
                async for event in response:
                    event_type = getattr(event, 'type', '')

                    # Text output delta
                    if event_type == 'response.output_text.delta':
                        delta_text = getattr(event, 'delta', '')
                        if delta_text:
                            yield ('text', delta_text)

                    # Reasoning/thinking
                    elif event_type == 'response.reasoning_summary_text.delta':
                        delta_text = getattr(event, 'delta', '')
                        if delta_text:
                            yield ('thinking', delta_text)

                    # Code interpreter: code being generated (delta)
                    elif event_type == 'response.code_interpreter_call_code.delta':
                        delta_code = getattr(event, 'delta', '')
                        if delta_code:
                            _ci_code_buffer.append(delta_code)
                            yield ('code_execution', {
                                'language': 'python',
                                'code_delta': delta_code,
                            })

                    # Code interpreter: execution completed (outputs available)
                    elif event_type == 'response.code_interpreter_call.completed':
                        item = getattr(event, 'item', None) or getattr(event, 'output_item', None)
                        if item:
                            results = getattr(item, 'results', None) or getattr(item, 'output', None) or []
                            logs = ''
                            files_out = []
                            if isinstance(results, list):
                                for r in results:
                                    r_type = getattr(r, 'type', '')
                                    if r_type == 'logs':
                                        logs = getattr(r, 'logs', '')
                                    elif r_type == 'files':
                                        files_out.extend(getattr(r, 'files', []))
                            yield ('code_execution_result', {
                                'outcome': 'OUTCOME_OK',
                                'output': logs,
                                'files': [
                                    {'file_id': getattr(f, 'file_id', ''), 'name': getattr(f, 'name', '')}
                                    for f in files_out
                                ],
                            })
                            # Extract container_id from the completed call item
                            _cid = getattr(item, 'container_id', None)
                            if _cid:
                                yield ('container_id', _cid)
                        _ci_code_buffer.clear()

                    # Response completed — fallback container_id extraction
                    elif event_type == 'response.completed':
                        resp_obj = getattr(event, 'response', None)
                        if resp_obj:
                            for output_item in getattr(resp_obj, 'output', []):
                                if getattr(output_item, 'type', '') == 'code_interpreter_call':
                                    _cid = getattr(output_item, 'container_id', None)
                                    if _cid:
                                        yield ('container_id', _cid)
                                        break

            return

        except Exception as e:
            record_api_call(
                kind="llm", provider="openai", model=model,
                success=False, meta={"stream": True, "code_interpreter": True, "api": "responses"},
            )
            logger.warning(f"Responses API failed ({e}), falling back to Chat Completions (no code_interpreter)")
            # Fall through to Chat Completions below

    # --- Chat Completions API path (standard, no code_interpreter) ---

    # Build completion kwargs
    completion_kwargs: Dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": prompt},
        ],
        "stream": True,
    }

    # Handle parameters for reasoning models (o1/o3) vs standard models
    is_reasoning_model = model.startswith(("o1-", "o3-")) or "gpt-5.2" in model
    if is_reasoning_model:
        # Reasoning models use max_completion_tokens and often don't support temperature
        completion_kwargs["max_completion_tokens"] = max_tokens
        # Only set temperature if it's 1.0 (default for o1) or if we want to risk it
        if temperature == 1.0:
             completion_kwargs["temperature"] = temperature
    else:
        # Standard models
        completion_kwargs["max_tokens"] = max_tokens
        completion_kwargs["temperature"] = temperature

    # Add reasoning_effort for o1/o3 models
    if reasoning_effort and (model.startswith(("o1-", "o3-")) or "gpt-5.2" in model):
        completion_kwargs["reasoning_effort"] = reasoning_effort

    try:
        stream = await async_client.chat.completions.create(**completion_kwargs)
        record_api_call(
            kind="llm",
            provider="openai",
            model=model,
            success=True,
            meta={"stream": True},
        )
    except Exception:
        record_api_call(
            kind="llm",
            provider="openai",
            model=model,
            success=False,
            meta={"stream": True},
        )
        raise

    async for chunk in stream:
        if not getattr(chunk, "choices", None):
            continue

        choice = chunk.choices[0]

        # Check for reasoning/thinking content (o1/o3 models)
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
    thinking_budget: Optional[int] = None,
    enable_code_execution: bool = True,  # Anthropic code execution server tool
    code_execution_effort: str = "medium",  # "low", "medium", "high", "max" (max for Opus 4.6 adaptive)
    container_id: Optional[str] = None,  # Container reuse for code execution
):
    """Async streaming for Claude (Vertex or direct) with thinking support.

    Args:
        extended_thinking: Enable extended thinking mode for Claude Sonnet 4 Thinking
        enable_code_execution: Enable Anthropic code execution server tool (beta)
        code_execution_effort: Effort level ("low", "medium", "high", "max")
        container_id: Optional container ID for reusing code execution sandbox state

    Yields:
        Tuples of (chunk_type, content) where chunk_type is 'thinking', 'text',
        'code_execution', 'code_execution_result', or 'container_id'
    """
    if not client:
        return

    system_instruction = system_instruction or DEFAULT_LEGAL_SYSTEM_INSTRUCTION

    from app.services.ai.model_registry import get_api_model_name
    model_id = get_api_model_name(model)

    async_vertex_cls = getattr(anthropic, "AsyncAnthropicVertex", None) if anthropic else None
    is_vertex = _is_anthropic_vertex_client(client) or (async_vertex_cls and isinstance(client, async_vertex_cls))

    # Vertex AI does not support code-execution beta — fallback to direct client if available
    if is_vertex and enable_code_execution:
        direct_client = get_async_claude_direct_client()
        if direct_client:
            logger.info("🔄 [Claude] Vertex não suporta code execution beta — usando client direto como fallback")
            client = direct_client
            is_vertex = False

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

        is_opus_46 = model_id.startswith("claude-opus-4-6")

        # Add code execution server tool if enabled (only for compatible models)
        # Compatible: claude-sonnet-4+, claude-opus-4+, claude-haiku-4.5+, claude-3-7-sonnet
        _ce_compatible = any(
            model_id.startswith(p)
            for p in (
                "claude-sonnet-4",   # Sonnet 4, 4.5
                "claude-opus-4",     # Opus 4, 4.1, 4.5
                "claude-haiku-4",    # Haiku 4.5
                "claude-3-7-sonnet", # 3.7 (deprecated)
                "claude-3-5-haiku",  # 3.5 Haiku (deprecated)
            )
        )
        if enable_code_execution and not is_vertex and _ce_compatible:
            message_kwargs["tools"] = [
                {"type": "code_execution_20250825", "name": "code_execution"},
            ]
            # Effort goes in output_config (not tool definition).
            # Legacy Opus 4.x (pre-4.6) still requires effort beta.
            if (
                not is_opus_46
                and code_execution_effort in ("low", "medium", "high")
                and model_id.startswith("claude-opus-4")
            ):
                message_kwargs["output_config"] = {"effort": code_execution_effort}

        # Thinking mode:
        # - Opus 4.6: adaptive thinking (opt-in via `thinking={"type":"adaptive"}`)
        # - Legacy models: extended thinking with budget_tokens
        if extended_thinking:
            if is_opus_46:
                effort = (code_execution_effort or "high").strip().lower()
                if effort == "xhigh":
                    effort = "high"
                if effort == "minimal":
                    effort = "low"
                if effort not in ("low", "medium", "high", "max"):
                    effort = "high"
                logger.info(
                    f"🧠 [Claude Adaptive] model={model_id}, effort={effort}"
                )
                message_kwargs["thinking"] = {"type": "adaptive"}
                message_kwargs["output_config"] = {"effort": effort}
            else:
                budget_tokens = thinking_budget if thinking_budget is not None else 10000
                try:
                    budget_tokens = int(budget_tokens)
                except (TypeError, ValueError):
                    budget_tokens = 10000
                if budget_tokens <= 0:
                    budget_tokens = 10000
                if budget_tokens > 63999:
                    budget_tokens = 63999
                # Ensure max_tokens > budget_tokens as required by Anthropic API
                if max_tokens <= budget_tokens:
                    max_tokens = budget_tokens + 8000  # Give 8k for response after thinking
                message_kwargs["max_tokens"] = max_tokens
                logger.info(
                    f"🧠 [Claude Thinking] Ativando extended_thinking para {model_id}, budget={budget_tokens}, max_tokens={max_tokens}"
                )
                message_kwargs["thinking"] = {"type": "enabled", "budget_tokens": budget_tokens}
        
        provider_name = "vertex-anthropic" if is_vertex else "anthropic"

        # Use beta API when code execution is enabled and model is compatible
        use_beta = enable_code_execution and not is_vertex and _ce_compatible
        if use_beta:
            _betas = ["code-execution-2025-08-25"]
            if "output_config" in message_kwargs and not is_opus_46:
                _betas.append("effort-2025-11-24")
            message_kwargs["betas"] = _betas
            # Pass container_id for sandbox state reuse
            if container_id:
                message_kwargs["container"] = container_id
            # Try beta.messages.stream first; fallback to beta.messages (no .stream)
            beta_stream_fn = getattr(getattr(client, 'beta', None), 'messages', None)
            if beta_stream_fn and hasattr(beta_stream_fn, 'stream'):
                stream_ctx_mgr = beta_stream_fn.stream(**message_kwargs)
            else:
                # Fallback: use regular messages.stream (beta header still sent via betas kwarg)
                stream_ctx_mgr = client.messages.stream(**message_kwargs)
        else:
            stream_ctx_mgr = client.messages.stream(**message_kwargs)

        try:
            async with stream_ctx_mgr as stream:
                record_api_call(
                    kind="llm",
                    provider=provider_name,
                    model=model_id,
                    success=True,
                    meta={"stream": True, "code_execution": use_beta},
                )
                # Use async for to iterate through SSE events
                async for event in stream:
                    # Claude SSE event types: content_block_start, content_block_delta, etc.
                    if not hasattr(event, 'type'):
                        continue

                    if event.type == 'content_block_start':
                        block = getattr(event, 'content_block', None)
                        block_type = getattr(block, 'type', None)
                        # server_tool_use: code execution started
                        if block_type == 'server_tool_use':
                            yield ('code_execution', {
                                'id': getattr(block, 'id', ''),
                                'name': getattr(block, 'name', 'code_execution'),
                            })
                        # Code execution results arrive as content_block_start (per Anthropic streaming docs)
                        elif block_type in (
                            'bash_code_execution_tool_result',
                            'text_editor_code_execution_tool_result',
                            'code_execution_tool_result',
                        ):
                            content = getattr(block, 'content', None)
                            yield ('code_execution_result', {
                                'stdout': getattr(content, 'stdout', '') if content else '',
                                'stderr': getattr(content, 'stderr', '') if content else '',
                                'return_code': getattr(content, 'return_code', -1) if content else -1,
                            })

                    elif event.type == 'content_block_delta':
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

                    # Capture container_id from message_stop or message events
                    elif event.type == 'message_stop':
                        msg = getattr(event, 'message', None) or getattr(stream, 'current_message_snapshot', None)
                        if msg:
                            _container = getattr(msg, 'container', None)
                            if _container and hasattr(_container, 'id'):
                                yield ('container_id', _container.id)

                # Also try getting container from final message snapshot
                final_msg = getattr(stream, 'get_final_message', None)
                if callable(final_msg):
                    try:
                        fm = final_msg()
                        _container = getattr(fm, 'container', None)
                        if _container and hasattr(_container, 'id'):
                            yield ('container_id', _container.id)
                    except Exception:
                        pass
        except Exception:
            record_api_call(
                kind="llm",
                provider=provider_name,
                model=model_id,
                success=False,
                meta={"stream": True},
            )
            raise
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
    thinking_mode: Optional[str] = None,  # 'minimal'|'low'|'medium'|'high' (or legacy 'standard'|'extended')
    enable_code_execution: bool = True,  # Gemini code_execution tool
):
    """Async streaming for Gemini via Vertex/Google GenAI with Extended Thinking support.
    
    Args:
        thinking_mode: Enable thinking streaming. Options:
            - None: Normal mode
            - 'minimal'|'low'|'medium'|'high': Thinking level (Gemini Flash/Pro)
            - legacy: 'standard' -> 'medium', 'extended' -> 'high'
    
    Yields:
        Tuples of (chunk_type, content) where chunk_type is 'thinking' or 'text'
    """
    if not genai:
        logger.error("❌ [Gemini] google-genai SDK não disponível. pip install google-genai")
        yield ("error", "Gemini SDK (google-genai) não instalado no servidor.")
        return

    if not client:
        client = init_vertex_client()

    if not client:
        logger.error("❌ [Gemini] Cliente não inicializado. Verifique GOOGLE_CLOUD_PROJECT ou GEMINI_API_KEY.")
        yield ("error", "Gemini Client não inicializado. Verifique credenciais do Vertex AI.")
        return

    from app.services.ai.model_registry import get_api_model_name

    model_id = get_api_model_name(model)
    system_instruction = system_instruction or DEFAULT_LEGAL_SYSTEM_INSTRUCTION

    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    force_direct = os.getenv("GEMINI_FORCE_DIRECT", "false").lower() == "true"

    def _is_not_found(exc: Exception) -> bool:
        msg = str(exc).lower()
        return (
            ("404" in msg and ("not_found" in msg or "not found" in msg))
            or ("publisher model" in msg and "not found" in msg)
            or ("was not found" in msg)
        )

    async def _start_stream(active_client, active_model_id: str, cfg_kwargs: dict) -> Any:
        cfg = types.GenerateContentConfig(**cfg_kwargs)
        models = active_client.aio.models
        if hasattr(models, "generate_content_stream"):
            stream_obj = models.generate_content_stream(
                model=active_model_id,
                contents=prompt,
                config=cfg,
            )
        else:
            try:
                stream_obj = models.generate_content(
                    model=active_model_id,
                    contents=prompt,
                    config=cfg,
                    stream=True,
                )
            except TypeError:
                stream_obj = models.generate_content(
                    model=active_model_id,
                    contents=prompt,
                    config=cfg,
                )
        if asyncio.iscoroutine(stream_obj):
            stream_obj = await stream_obj
        return stream_obj

    def _extract_grounding_metadata(obj: Any) -> Optional[Dict[str, Any]]:
        """Extract grounding metadata from Gemini chunk for web search queries and sources."""
        candidates = getattr(obj, "candidates", None) or []
        for candidate in candidates:
            meta = (
                getattr(candidate, "grounding_metadata", None) or
                getattr(candidate, "groundingMetadata", None)
            )
            if not meta:
                continue

            result: Dict[str, Any] = {}

            # Extract web search queries
            queries = (
                getattr(meta, "web_search_queries", None) or
                getattr(meta, "webSearchQueries", None) or []
            )
            if queries:
                result["web_search_queries"] = [str(q) for q in queries if q]

            # Extract grounding chunks (sources)
            chunks = (
                getattr(meta, "grounding_chunks", None) or
                getattr(meta, "groundingChunks", None) or []
            )
            if chunks:
                sources = []
                for gc in chunks:
                    web = getattr(gc, "web", None)
                    if web:
                        url = str(getattr(web, "uri", "") or "").strip()
                        title = str(getattr(web, "title", "") or url).strip()
                        if url:
                            sources.append({"title": title, "url": url})
                if sources:
                    result["sources"] = sources

            if result:
                return result
        return None

    def _yield_parts(obj: Any) -> bool:
        yielded_any = False
        candidates = getattr(obj, "candidates", None) or []
        for candidate in candidates:
            content = getattr(candidate, "content", None)
            parts = getattr(content, "parts", None) if content else None
            if not parts:
                continue
            for part in parts:
                # Code execution parts (Gemini code_execution tool)
                if hasattr(part, 'executable_code') and part.executable_code:
                    code = part.executable_code
                    yield ("code_execution", {
                        "language": str(getattr(code, 'language', 'PYTHON')),
                        "code": getattr(code, 'code', str(code)),
                    })
                    yielded_any = True
                    continue
                if hasattr(part, 'code_execution_result') and part.code_execution_result:
                    exec_result = part.code_execution_result
                    yield ("code_execution_result", {
                        "outcome": str(getattr(exec_result, 'outcome', 'UNKNOWN')),
                        "output": getattr(exec_result, 'output', ''),
                    })
                    yielded_any = True
                    continue

                text = getattr(part, "text", None)
                if not isinstance(text, str) or not text:
                    continue
                thought_attr = getattr(part, "thought", None)
                if isinstance(thought_attr, bool) and thought_attr:
                    # Gemini "thought summaries" arrive as parts flagged with `thought=True` and a text payload.
                    # We treat these as *standard thinking* to show full chain-of-thought in UI.
                    yield ("thinking", text)
                    yielded_any = True
                    continue
                thought_text = getattr(part, "thinking", None)
                if isinstance(thought_text, str) and thought_text.strip():
                    yield ("thinking", thought_text)
                    yielded_any = True
                    continue
                if isinstance(thought_attr, str) and thought_attr.strip():
                    yield ("thinking", thought_attr)
                    yielded_any = True
                    continue
                yield ("text", text)
                yielded_any = True
        return yielded_any

    # Build config kwargs
    config_kwargs: dict = {
        "system_instruction": system_instruction,
        "max_output_tokens": max_tokens,
        "temperature": temperature,
    }

    # Add code_execution tool if enabled (not supported by flash-lite models)
    _ce_gemini_compatible = not any(
        model_id.startswith(p) for p in ("gemini-2.0-flash-lite", "gemini-2-flash-lite")
    )
    if enable_code_execution and types and _ce_gemini_compatible:
        try:
            # Per Google docs: types.Tool(code_execution=types.ToolCodeExecution)
            # Try ToolCodeExecution (class ref, not instance), then CodeExecution(), then dict
            tool_ce = getattr(types, "ToolCodeExecution", None)
            if tool_ce is not None:
                config_kwargs["tools"] = [types.Tool(code_execution=tool_ce)]
            else:
                code_exec_cls = getattr(types, "CodeExecution", None)
                if code_exec_cls:
                    config_kwargs["tools"] = [types.Tool(code_execution=code_exec_cls())]
                else:
                    config_kwargs["tools"] = [types.Tool(code_execution={})]
            logger.debug("Code execution tool enabled for Gemini chat")
        except Exception as e:
            logger.warning(f"Could not enable Gemini code_execution: {e}")

    def _normalize_gemini_thinking(level: Optional[str]) -> Optional[str]:
        if not level:
            return None
        raw = str(level).strip().lower()
        # "none"/"off"/"disabled" -> return None to completely disable thinking
        if raw in ("none", "off", "disabled"):
            return None
        # SDK ThinkingLevel enum expects UPPERCASE: LOW, MEDIUM, HIGH, MINIMAL
        if raw in ("standard", "medium"):
            return "MEDIUM"
        if raw in ("extended", "high", "xhigh"):
            return "HIGH"
        if raw == "minimal":
            return "MINIMAL"
        if raw == "low":
            return "LOW"
        return raw.upper()

    normalized_thinking = _normalize_gemini_thinking(thinking_mode)
    if normalized_thinking:
        logger.info(
            f"🧠 [Gemini Thinking] Ativando thinking_mode={normalized_thinking} para modelo {model_id}"
        )
        # Only pass thinking_level for MEDIUM/HIGH; LOW/MINIMAL use just include_thoughts
        # to avoid Vertex AI 400 "thinking_level is not supported by this model"
        if normalized_thinking in ("MEDIUM", "HIGH"):
            try:
                thinking_config = types.ThinkingConfig(
                    include_thoughts=True, thinking_level=normalized_thinking
                )
            except Exception:
                thinking_config = types.ThinkingConfig(include_thoughts=True)
        else:
            thinking_config = types.ThinkingConfig(include_thoughts=True)
        config_kwargs["thinking_config"] = thinking_config

    active_client = client
    active_model_id = model_id

    async def _open_stream_with_thinking_fallback() -> Any:
        try:
            return await _start_stream(active_client, active_model_id, config_kwargs)
        except Exception as exc:
            if "400" in str(exc) and thinking_mode:
                logger.warning(f"⚠️ Erro 400 com Thinking ({exc}). Tentando fallback sem thinking...")
                record_api_call(
                    kind="llm",
                    provider="vertex-gemini",
                    model=active_model_id,
                    success=False,
                    meta={"stream": True, "thinking_mode": thinking_mode},
                )
                cfg = dict(config_kwargs)
                cfg.pop("thinking_config", None)
                return await _start_stream(active_client, active_model_id, cfg)
            raise

    try:
        stream_obj = await _open_stream_with_thinking_fallback()
    except Exception as exc:
        if _is_not_found(exc) and api_key and not force_direct:
            logger.warning(f"⚠️ Modelo indisponível no Vertex ({active_model_id}). Tentando Gemini direto via API key...")
            record_api_call(
                kind="llm",
                provider="vertex-gemini",
                model=active_model_id,
                success=False,
                meta={"stream": True, "fallback": "direct"},
            )
            active_client = genai.Client(api_key=api_key)
            stream_obj = await _open_stream_with_thinking_fallback()
        else:
            record_api_call(
                kind="llm",
                provider="vertex-gemini",
                model=active_model_id,
                success=False,
                meta={"stream": True},
            )
            raise

    record_api_call(
        kind="llm",
        provider="vertex-gemini",
        model=active_model_id,
        success=True,
        meta={"stream": True, **({"thinking_mode": thinking_mode} if thinking_mode else {})},
    )

    # Track seen grounding data to avoid duplicates
    seen_grounding_queries: set = set()
    seen_grounding_sources: set = set()

    if hasattr(stream_obj, "__aiter__"):
        async for chunk in stream_obj:
            yielded = False
            for kind, delta in _yield_parts(chunk):
                yielded = True
                yield (kind, delta)

            # Extract and emit grounding metadata
            grounding = _extract_grounding_metadata(chunk)
            if grounding:
                for query in grounding.get("web_search_queries", []):
                    if query and query not in seen_grounding_queries:
                        seen_grounding_queries.add(query)
                        yield ("grounding_query", query)
                for src in grounding.get("sources", []):
                    src_key = src.get("url") or src.get("title", "")
                    if src_key and src_key not in seen_grounding_sources:
                        seen_grounding_sources.add(src_key)
                        yield ("grounding_source", src)

            if yielded:
                continue
            thinking_text = getattr(chunk, "thinking_text", None)
            if isinstance(thinking_text, str) and thinking_text.strip():
                yield ("thinking", thinking_text)
            text = getattr(chunk, "text", "") or ""
            if text:
                yield ("text", text)
        return

    # Non-streaming response fallback
    yielded = False
    for kind, delta in _yield_parts(stream_obj):
        yielded = True
        yield (kind, delta)

    # Extract grounding for non-streaming
    grounding = _extract_grounding_metadata(stream_obj)
    if grounding:
        for query in grounding.get("web_search_queries", []):
            if query:
                yield ("grounding_query", query)
        for src in grounding.get("sources", []):
            yield ("grounding_source", src)

    if yielded:
        return
    thinking_text = getattr(stream_obj, "thinking_text", None)
    if isinstance(thinking_text, str) and thinking_text.strip():
        yield ("thinking", thinking_text)
    output_text = getattr(stream_obj, "text", "") or ""
    if output_text:
        yield ("text", output_text)




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
    temperature: float = 0.3,
    web_search: bool = False,
    search_mode: str = "hybrid",
    perplexity_search_mode: Optional[str] = None,
    multi_query: bool = True,
    breadth_first: bool = False,
    thesis: Optional[str] = None,
    formatting_options: Optional[Dict[str, bool]] = None,
    template_structure: Optional[str] = None,
    extra_agent_instructions: Optional[str] = None,
    mode: Optional[str] = None,
    previous_sections: Optional[List[str]] = None,
    system_instruction: Optional[str] = None,
    cached_content: Optional[Any] = None,
    num_committee_rounds: int = 1
) -> Tuple[str, str, dict]:
    """
    Async version with parallel execution of GPT and Claude calls.
    Uses CaseBundle for robust document context + formatted citations.
    ~50% faster than sequential version.
    """
    from jinja2 import Template
    from app.services.ai.model_registry import get_api_model_name, DEFAULT_JUDGE_MODEL, get_model_config
    from app.services.ai.perplexity_config import normalize_perplexity_search_mode

    gpt_model_id = gpt_model
    claude_model_id = claude_model
    judge_model_id = judge_model or DEFAULT_JUDGE_MODEL

    try:
        temperature = float(temperature)
    except (TypeError, ValueError):
        temperature = 0.3
    temperature = max(0.0, min(1.0, temperature))
    draft_temperature = temperature
    review_temperature = min(temperature, 0.3)

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
        if search_mode not in ("shared", "native", "hybrid", "perplexity"):
            search_mode = "hybrid"
        perplexity_search_mode = normalize_perplexity_search_mode(perplexity_search_mode)
        if search_mode != "native":
            print(f"   🔍 Realizando busca web para: {section_title}")
            search_query = f"{section_title} jurisprudencia tribunal superior novo código processo civil"
            if thesis:
                search_query += f" {thesis[:100]}"

            breadth_first = bool(breadth_first) or is_breadth_first(search_query)
            multi_query = bool(multi_query) or breadth_first

            if multi_query:
                search_results = await web_search_service.search_multi(
                    search_query,
                    num_results=10,
                    search_mode=perplexity_search_mode,
                )
            else:
                search_results = await web_search_service.search(
                    search_query,
                    num_results=10,
                    search_mode=perplexity_search_mode,
                )

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
        cached_content: Optional[Any] = None,
        temperature: float = 0.3,
        *,
        billing_node: Optional[str] = None,
        billing_size: Optional[str] = None,
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
            with billing_context(node=billing_node, size=billing_size):
                return await call_openai_async(
                    client,
                    full_prompt,
                    model=api_model,
                    temperature=temperature,
                    system_instruction=system_instruction
                )
        if cfg.provider == "anthropic":
            client = claude_client or init_anthropic_client()
            if not client:
                return ""
            with billing_context(node=billing_node, size=billing_size):
                return await call_anthropic_async(
                    client,
                    full_prompt,
                    model=api_model,
                    temperature=temperature,
                    system_instruction=system_instruction
                )
        if cfg.provider == "google":
            client = get_gemini_client()
            if not client:
                return ""
            if cached_content:
                with billing_context(node=billing_node, size=billing_size):
                    return await asyncio.to_thread(
                        call_vertex_gemini,
                        client,
                        full_prompt,
                        model=model_id,
                        temperature=temperature,
                        system_instruction=system_instruction,
                        cached_content=cached_content
                    ) or ""
            with billing_context(node=billing_node, size=billing_size):
                return await call_vertex_gemini_async(
                    client,
                    full_prompt,
                    model=model_id,
                    temperature=temperature,
                    system_instruction=system_instruction
                ) or ""
        if cfg.provider == "perplexity":
            effective_strategy = (search_mode or "hybrid").strip().lower()
            allow_model_search = bool(web_search) and effective_strategy == "native"
            with billing_context(node=billing_node, size=billing_size):
                return (
                    await call_perplexity_async(
                        full_prompt,
                        model=api_model or model_id,
                        temperature=temperature,
                        system_instruction=system_instruction,
                        web_search_enabled=allow_model_search,
                        search_mode=perplexity_search_mode,
                        disable_search=not allow_model_search,
                    )
                    or ""
                )
        if cfg.provider == "xai":
            client = init_xai_client()
            if not client:
                return ""
            with billing_context(node=billing_node, size=billing_size):
                return await call_openai_async(
                    client,
                    full_prompt,
                    model=api_model,
                    temperature=temperature,
                    system_instruction=system_instruction
                )
        if cfg.provider == "openrouter":
            client = init_openrouter_client()
            if not client:
                return ""
            with billing_context(node=billing_node, size=billing_size):
                return await call_openai_async(
                    client,
                    full_prompt,
                    model=api_model,
                    temperature=temperature,
                    system_instruction=system_instruction
                )
        return ""

    custom_drafter_models = _dedupe_models(drafter_models or [])
    custom_reviewer_models = _dedupe_models(reviewer_models or [])
    use_custom_lists = bool(custom_drafter_models or custom_reviewer_models)

    async def _call_openai_with_billing(
        client,
        prompt: str,
        *,
        model: str,
        temperature: float,
        billing_node: str,
        billing_size: str,
    ) -> Optional[str]:
        with billing_context(node=billing_node, size=billing_size):
            return await call_openai_async(
                client,
                prompt,
                model=model,
                temperature=temperature,
                system_instruction=system_instruction,
            )

    async def _call_anthropic_with_billing(
        client,
        prompt: str,
        *,
        model: str,
        temperature: float,
        billing_node: str,
        billing_size: str,
    ) -> Optional[str]:
        with billing_context(node=billing_node, size=billing_size):
            return await call_anthropic_async(
                client,
                prompt,
                model=model,
                temperature=temperature,
                system_instruction=system_instruction,
            )

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
            draft_tasks.append((model_id, _call_model(
                model_id,
                agent_prompt,
                sys_prompt,
                temperature=draft_temperature,
                billing_node="section_draft",
                billing_size="M",
            )))

        draft_results = await asyncio.gather(*[t[1] for t in draft_tasks]) if draft_tasks else []
        drafts_by_model: Dict[str, str] = {}
        for idx, (model_id, _) in enumerate(draft_tasks):
            label = _model_label(model_id)
            draft_text = draft_results[idx] if idx < len(draft_results) else ""
            drafts_by_model[model_id] = draft_text or f"[{label} não disponível]"

        drafts["drafts_by_model"] = drafts_by_model
        drafts["drafts_order"] = custom_drafter_models
        drafts["reviewers_order"] = list(custom_reviewer_models or [])
        drafts["judge_model"] = judge_model_id

        valid_drafts = [text for text in drafts_by_model.values() if text and "não disponível" not in text]
        if len(valid_drafts) < 2:
            fallback_text = valid_drafts[0] if valid_drafts else ""
            return fallback_text, "", drafts

        # =========================================================================
        # R2-R3 LOOP: Critique -> Revision (repeats num_committee_rounds times)
        # =========================================================================
        t_critica = Template(V2_PROMPT_CRITICA)
        t_revisao = Template(V2_PROMPT_REVISAO)
        
        # Track current versions (starts with initial drafts)
        current_versions_by_model: Dict[str, str] = dict(drafts_by_model)
        all_reviews_history: List[Dict[str, str]] = []
        all_revisions_history: List[Dict[str, str]] = []
        
        try:
            effective_rounds = int(num_committee_rounds)
        except (TypeError, ValueError):
            effective_rounds = 1
        effective_rounds = max(1, min(6, effective_rounds))
        print(f"   🔄 [Committee] Running {effective_rounds} round(s) of R2-R3...")
        
        for round_num in range(1, effective_rounds + 1):
            round_label = f"R{round_num}" if effective_rounds > 1 else ""
            
            # R2: Reviews (each reviewer critiques current versions)
            print(f"   💬 [R2{round_label}] Críticas (rodada {round_num}/{effective_rounds})...")
            versions_block = "\n\n".join(
                [f"### {_model_label(mid)} ({mid})\n{current_versions_by_model[mid]}" for mid in custom_drafter_models]
            )
            critica_prompt = t_critica.render(
                texto_colega=versions_block,
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
                critique_tasks.append((model_id, _call_model(
                    model_id,
                    critica_prompt,
                    sys_prompt,
                    temperature=review_temperature,
                    billing_node="section_critique",
                    billing_size="M",
                )))

            critique_results = await asyncio.gather(*[t[1] for t in critique_tasks]) if critique_tasks else []
            reviews_by_model: Dict[str, str] = {}
            for idx, (model_id, _) in enumerate(critique_tasks):
                reviews_by_model[model_id] = critique_results[idx] if idx < len(critique_results) else ""
            
            all_reviews_history.append(reviews_by_model)

            # R3: Revisions (each drafter uses all critiques)
            print(f"   ✏️ [R3{round_label}] Revisões (rodada {round_num}/{effective_rounds})...")
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
                original_text = current_versions_by_model.get(model_id, "")
                rev_prompt = t_revisao.render(
                    texto_original=original_text,
                    critica_recebida=critiques_block,
                    rag_context=full_rag,
                    tipo_documento=doc_type,
                    tese=thesis or "",
                    instrucoes=instrucoes
                )
                revision_tasks.append((model_id, _call_model(
                    model_id,
                    rev_prompt,
                    sys_prompt,
                    temperature=draft_temperature,
                    billing_node="section_revision",
                    billing_size="M",
                )))

            revision_results = await asyncio.gather(*[t[1] for t in revision_tasks]) if revision_tasks else []
            revisions_by_model: Dict[str, str] = {}
            for idx, (model_id, _) in enumerate(revision_tasks):
                revisions_by_model[model_id] = revision_results[idx] if idx < len(revision_results) else ""
            
            all_revisions_history.append(revisions_by_model)
            
            # Update current versions for next round (or for Judge)
            for mid in custom_drafter_models:
                if revisions_by_model.get(mid):
                    current_versions_by_model[mid] = revisions_by_model[mid]
        
        # Store final results
        drafts["reviews_by_model"] = all_reviews_history[-1] if all_reviews_history else {}
        drafts["revisions_by_model"] = all_revisions_history[-1] if all_revisions_history else {}
        drafts["committee_rounds_executed"] = effective_rounds
        if effective_rounds > 1:
            drafts["all_reviews_history"] = all_reviews_history
            drafts["all_revisions_history"] = all_revisions_history

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
            if current_versions_by_model:
                drafts[f"{prefix}_v2"] = current_versions_by_model.get(model_id) or drafts_by_model.get(model_id, "")

        _assign_legacy("openai", "gpt")
        _assign_legacy("anthropic", "claude")
        _assign_legacy("google", "gemini")

        # R4: Judge consolidation (dynamic list)
        print(f"   ⚖️ [R4] Juiz consolidando {effective_rounds} rodada(s) de debate...")
        final_versions = [
            {
                "id": mid,
                "label": f"{_model_label(mid)} ({mid})",
                "text": current_versions_by_model.get(mid) or drafts_by_model.get(mid, "")
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
            cached_content=cached_content,
            temperature=review_temperature,
            billing_node="section_judge",
            billing_size="S",
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
        _call_openai_with_billing(
            gpt_client,
            f"{sys_gpt}\n\n{agent_prompt}",
            model=gpt_model,
            temperature=draft_temperature,
            billing_node="section_draft",
            billing_size="M",
        ),
        _call_anthropic_with_billing(
            claude_client,
            f"{sys_claude}\n\n{agent_prompt}",
            model=claude_model,
            temperature=draft_temperature,
            billing_node="section_draft",
            billing_size="M",
        )
    )
    drafts['gpt_v1'] = versao_gpt_v1 or "[GPT não disponível]"
    drafts['claude_v1'] = versao_claude_v1 or "[Claude não disponível]"
    
    # Independent Judge model (Blind Judge Pattern)
    print(f"   🤖 [R1] Agente Juiz (blind) gerando versão independente...")
    versao_gemini_v1 = await _call_model(
        judge_model_id,
        agent_prompt,
        sys_gemini_blind,
        temperature=draft_temperature,
        billing_node="section_draft",
        billing_size="M",
    )
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
        critique_tasks.append(("gpt", _call_openai_with_billing(
            gpt_client,
            critica_gpt_prompt,
            model=gpt_model,
            temperature=review_temperature,
            billing_node="section_critique",
            billing_size="M",
        )))
    if not critica_claude:
        critique_tasks.append(("claude", _call_anthropic_with_billing(
            claude_client,
            critica_claude_prompt,
            model=claude_model,
            temperature=review_temperature,
            billing_node="section_critique",
            billing_size="M",
        )))
    if not critica_gemini:
        critique_tasks.append(("gemini", _call_model(
            judge_model_id,
            critica_gemini_prompt,
            sys_gemini_blind,
            temperature=review_temperature,
            billing_node="section_critique",
            billing_size="M",
        )))
    
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
        _call_openai_with_billing(
            gpt_client,
            rev_gpt_prompt,
            model=gpt_model,
            temperature=draft_temperature,
            billing_node="section_revision",
            billing_size="M",
        ),
        _call_anthropic_with_billing(
            claude_client,
            rev_claude_prompt,
            model=claude_model,
            temperature=draft_temperature,
            billing_node="section_revision",
            billing_size="M",
        ),
        _call_model(
            judge_model_id,
            rev_gemini_prompt,
            sys_gemini_blind,
            temperature=draft_temperature,
            billing_node="section_revision",
            billing_size="M",
        )
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
        cached_content=cached_content,
        temperature=review_temperature,
        billing_node="section_judge",
        billing_size="S",
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
