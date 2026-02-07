"""
Model Registry - Centralized configuration for all available models

Includes:
- Model IDs and families
- Context windows
- Latency and cost tiers
- Capabilities
- Flags for agents and juridico use
"""

import os
from typing import Dict, Any, Literal, List, Optional
from dataclasses import dataclass, field

LatencyTier = Literal["low", "medium", "high", "depends_self_host"]
CostTier = Literal["low", "medium", "medium_high", "high", "infra_only"]
# NEW: Thinking implementation category
ThinkingCategory = Literal["native", "xml", "agent", "none"]

@dataclass
class ModelConfig:
    id: str
    provider: str
    family: str
    label: str
    context_window: int
    latency_tier: LatencyTier
    cost_tier: CostTier
    capabilities: List[str]
    for_agents: bool
    for_juridico: bool
    default: bool = False
    icon: str = ""
    api_model: str = ""  # Actual API model name if different from id
    supports_streaming: bool = True
    thinking_category: ThinkingCategory = "xml"  # NEW: How to implement thinking
    max_output_tokens: int = 8192  # NEW: Max output tokens capability

# =============================================================================
# REGISTRY
# =============================================================================

MODEL_REGISTRY: Dict[str, ModelConfig] = {
    # ---------- OPENAI ----------
    "gpt-5.2": ModelConfig(
        id="gpt-5.2",
        provider="openai",
        family="gpt-5",
        label="GPT‑5.2",
        context_window=400_000,
        latency_tier="high",
        cost_tier="high",
        capabilities=["chat", "code", "agents", "analysis"],
        for_agents=True,
        for_juridico=True,
        default=False,
        icon="openai.svg",
        # Allow overriding the concrete provider model id via env.
        api_model=os.getenv("GPT_5_2_API_MODEL", "gpt-5.2"),
        thinking_category="xml",  # Uses XML parsing
        max_output_tokens=16384,
    ),
    "gpt-5.2-instant": ModelConfig(
        id="gpt-5.2-instant",
        provider="openai",
        family="gpt-5",
        label="GPT‑5.2 Instant",
        context_window=400_000,
        latency_tier="low",
        cost_tier="medium",
        capabilities=["chat", "tools", "high_volume"],
        for_agents=True,
        for_juridico=True,
        default=False,
        icon="openai.svg",
        api_model=os.getenv("GPT_5_2_INSTANT_API_MODEL", "gpt-4o-mini"),
        thinking_category="agent",
    ),
    "gpt-5": ModelConfig(
        id="gpt-5",
        provider="openai",
        family="gpt-5",
        label="GPT‑5",
        context_window=400_000,
        latency_tier="medium",
        cost_tier="medium_high",
        capabilities=["chat", "code", "analysis"],
        for_agents=True,
        for_juridico=True,
        default=True,
        icon="openai.svg",
        # Allow overriding the concrete provider model id via env.
        api_model=os.getenv("GPT_5_API_MODEL", "gpt-4o"),
    ),
    "gpt-5-mini": ModelConfig(
        id="gpt-5-mini",
        provider="openai",
        family="gpt-5",
        label="GPT‑5 mini",
        context_window=400_000,
        latency_tier="low",
        cost_tier="low",
        capabilities=["chat", "tools", "high_volume"],
        for_agents=True,
        for_juridico=True,
        default=False,
        icon="openai.svg",
        # Allow overriding the concrete provider model id via env.
        api_model=os.getenv("GPT_5_MINI_API_MODEL", "gpt-4o-mini"),
        thinking_category="agent",  # Light model: use agent-based
    ),
    "gpt-4o": ModelConfig(
        id="gpt-4o",
        provider="openai",
        family="gpt-4",
        label="GPT‑4o",
        context_window=128_000,
        latency_tier="medium",
        cost_tier="medium",
        capabilities=["chat", "code", "multimodal"],
        for_agents=True,
        for_juridico=True,
        default=False,
        icon="openai.svg",
        api_model="gpt-4o",
        max_output_tokens=16384,
    ),

    # ---------- XAI ----------
    "grok-4": ModelConfig(
        id="grok-4",
        provider="xai",
        family="grok-4",
        label="Grok 4",
        context_window=128_000,
        latency_tier="high",
        cost_tier="high",
        capabilities=["chat", "analysis", "agents"],
        for_agents=True,
        for_juridico=True,
        default=False,
        icon="xai.svg",
        api_model=os.getenv("GROK_4_API_MODEL", "grok-4"),
    ),
    "grok-4-fast": ModelConfig(
        id="grok-4-fast",
        provider="xai",
        family="grok-4",
        label="Grok 4 Fast",
        context_window=2_000_000,
        latency_tier="medium",
        cost_tier="high",
        capabilities=["chat", "analysis", "agents"],
        for_agents=True,
        for_juridico=True,
        default=False,
        icon="xai.svg",
        api_model=os.getenv("GROK_4_FAST_API_MODEL", "grok-4-fast"),
    ),
    "grok-4.1-fast": ModelConfig(
        id="grok-4.1-fast",
        provider="xai",
        family="grok-4",
        label="Grok 4.1 Fast",
        context_window=2_000_000,
        latency_tier="medium",
        cost_tier="high",
        capabilities=["chat", "analysis", "agents"],
        for_agents=True,
        for_juridico=True,
        default=False,
        icon="xai.svg",
        api_model=os.getenv("GROK_4_1_FAST_API_MODEL", "x-ai/grok-4.1-fast"),
    ),
    "grok-4.1": ModelConfig(
        id="grok-4.1",
        provider="xai",
        family="grok-4",
        label="Grok 4.1",
        context_window=2_000_000,
        latency_tier="medium",
        cost_tier="medium",
        capabilities=["chat", "analysis", "agents"],
        for_agents=True,
        for_juridico=True,
        default=False,
        icon="xai.svg",
        api_model=os.getenv("GROK_4_1_API_MODEL", "x-ai/grok-4.1"),
    ),

    # ---------- ANTHROPIC ----------
    "claude-4.6-opus": ModelConfig(
        id="claude-4.6-opus",
        provider="anthropic",
        family="claude-4.6",
        label="Claude 4.6 Opus",
        context_window=200_000,
        latency_tier="high",
        cost_tier="high",
        capabilities=["chat", "code", "agents", "deep_reasoning"],
        for_agents=True,
        for_juridico=True,
        default=False,
        icon="anthropic.svg",
        api_model=os.getenv("CLAUDE_4_6_OPUS_API_MODEL", "claude-opus-4-6"),
        thinking_category="native",
        max_output_tokens=64_000,
    ),
    "claude-4.5-opus": ModelConfig(
        id="claude-4.5-opus",
        provider="anthropic",
        family="claude-4.5",
        label="Claude 4.5 Opus",
        context_window=200_000,
        latency_tier="high",
        cost_tier="high",
        capabilities=["chat", "code", "agents", "deep_reasoning"],
        for_agents=True,
        for_juridico=True,
        default=False,
        icon="anthropic.svg",
        api_model=os.getenv("CLAUDE_4_5_OPUS_API_MODEL", "claude-opus-4-5"),
        thinking_category="native",  # Opus 4.5 supports native extended thinking
        max_output_tokens=64_000,
    ),
    "claude-4.5-sonnet": ModelConfig(
        id="claude-4.5-sonnet",
        provider="anthropic",
        family="claude-4.5",
        label="Claude 4.5 Sonnet",
        context_window=200_000,
        latency_tier="medium",
        cost_tier="medium",
        capabilities=["chat", "code", "analysis", "agents"],
        for_agents=True,
        for_juridico=True,
        default=True,
        icon="anthropic.svg",
        api_model=os.getenv("CLAUDE_4_5_SONNET_API_MODEL", "claude-sonnet-4-5"),
        thinking_category="native",  # Extended Thinking via API
        max_output_tokens=64_000,
    ),
    "claude-4.5-haiku": ModelConfig(
        id="claude-4.5-haiku",
        provider="anthropic",
        family="claude-4.5",
        label="Claude 4.5 Haiku",
        context_window=200_000,
        latency_tier="low",
        cost_tier="low",
        capabilities=["chat", "code", "high_volume", "agents"],
        for_agents=True,
        for_juridico=True,
        default=False,
        icon="anthropic.svg",
        # Allow overriding the concrete provider model id via env.
        api_model=os.getenv("CLAUDE_4_5_HAIKU_API_MODEL", "claude-haiku-4-5"),
        thinking_category="native",  # Haiku 4.5 supports extended thinking natively
        max_output_tokens=64_000,
    ),

    # ---------- GEMINI ----------
    "gemini-3-pro": ModelConfig(
        id="gemini-3-pro",
        provider="google",
        family="gemini-3",
        label="Gemini 3 Pro",
        context_window=1_000_000,
        latency_tier="medium",
        cost_tier="medium",
        capabilities=["chat", "code", "agents", "multimodal"],
        for_agents=True,
        for_juridico=True,
        default=True,
        icon="gemini.svg",
        api_model=os.getenv("GEMINI_3_PRO_API_MODEL", "gemini-3-pro-preview"),
        thinking_category="native",  # Native include_thoughts API
        max_output_tokens=8192,
    ),
    "gemini-3-flash": ModelConfig(
        id="gemini-3-flash",
        provider="google",
        family="gemini-3",
        label="Gemini 3 Flash",
        context_window=1_000_000,
        latency_tier="low",
        cost_tier="low",
        capabilities=["chat", "tools", "high_volume", "multimodal"],
        for_agents=True,
        for_juridico=True,
        default=False,
        icon="gemini.svg",
        api_model=os.getenv("GEMINI_3_FLASH_API_MODEL", "gemini-3-flash-preview"),
        thinking_category="native",  # Native include_thoughts API (Gemini 2.0+ supports it)
        max_output_tokens=8192,
    ),
    "gemini-2.5-pro": ModelConfig(
        id="gemini-2.5-pro",
        provider="google",
        family="gemini-2.5",
        label="Gemini 2.5 Pro",
        context_window=1_000_000,
        latency_tier="medium",
        cost_tier="medium",
        capabilities=["chat", "code", "analysis"],
        for_agents=True,
        for_juridico=True,
        default=False,
        icon="gemini.svg",
        api_model=os.getenv("GEMINI_2_5_PRO_API_MODEL", "gemini-2.5-pro"),
        thinking_category="native",  # Gemini 2.5+ supports native include_thoughts
        max_output_tokens=8192,
    ),
    "gemini-2.5-flash": ModelConfig(
        id="gemini-2.5-flash",
        provider="google",
        family="gemini-2.5",
        label="Gemini 2.5 Flash",
        context_window=1_000_000,
        latency_tier="low",
        cost_tier="low",
        capabilities=["chat", "high_volume", "multimodal"],
        for_agents=True,
        for_juridico=True,
        default=False,
        icon="gemini.svg",
        api_model=os.getenv("GEMINI_2_5_FLASH_API_MODEL", "gemini-2.5-flash"),
        thinking_category="native",  # Gemini 2.5+ supports native include_thoughts
        max_output_tokens=8192,
    ),

    # ---------- OPENROUTER / META ----------
    "llama-4": ModelConfig(
        id="llama-4",
        provider="openrouter",
        family="llama-4",
        label="Llama 4",
        context_window=128_000,
        latency_tier="medium",
        cost_tier="medium",
        capabilities=["chat", "analysis"],
        for_agents=True,
        for_juridico=True,
        default=False,
        icon="meta.svg",
        api_model=os.getenv("LLAMA_4_API_MODEL", "meta-llama/llama-4-maverick"),
    ),
    "llama-4-maverick-t": ModelConfig(
        id="llama-4-maverick-t",
        provider="openrouter",
        family="llama-4",
        label="Llama 4 Maverick T",
        context_window=500_000,
        latency_tier="medium",
        cost_tier="medium",
        capabilities=["chat", "analysis"],
        for_agents=True,
        for_juridico=True,
        default=False,
        icon="meta.svg",
        api_model=os.getenv("LLAMA_4_MAVERICK_T_API_MODEL", "meta-llama/llama-4-maverick-17b-128e-instruct-fp8"),
    ),

    # ---------- PERPLEXITY (SONAR) ----------
    "sonar": ModelConfig(
        id="sonar",
        provider="perplexity",
        family="sonar",
        label="Sonar",
        context_window=128_000,
        latency_tier="medium",
        cost_tier="medium",
        capabilities=["chat", "web_grounded"],
        for_agents=True,
        for_juridico=True,
        default=False,
        icon="perplexity.svg",
        api_model="sonar",
        thinking_category="none",
    ),
    "sonar-pro": ModelConfig(
        id="sonar-pro",
        provider="perplexity",
        family="sonar",
        label="Sonar Pro",
        context_window=128_000,
        latency_tier="medium",
        cost_tier="high",
        capabilities=["chat", "web_grounded"],
        for_agents=True,
        for_juridico=True,
        default=False,
        icon="perplexity.svg",
        api_model="sonar-pro",
        thinking_category="none",
    ),
    "sonar-deep-research": ModelConfig(
        id="sonar-deep-research",
        provider="perplexity",
        family="sonar",
        label="Sonar Deep Research",
        context_window=128_000,
        latency_tier="high",
        cost_tier="high",
        capabilities=["chat", "web_grounded", "deep_research"],
        for_agents=True,
        for_juridico=True,
        default=False,
        icon="perplexity.svg",
        api_model="sonar-deep-research",
        thinking_category="none",
    ),
    "sonar-reasoning-pro": ModelConfig(
        id="sonar-reasoning-pro",
        provider="perplexity",
        family="sonar",
        label="Sonar Reasoning Pro",
        context_window=128_000,
        latency_tier="high",
        cost_tier="high",
        capabilities=["chat", "web_grounded", "analysis"],
        for_agents=True,
        for_juridico=True,
        default=False,
        icon="perplexity.svg",
        api_model="sonar-reasoning-pro",
        thinking_category="none",
    ),

    # ---------- INTERNAL ----------
    "internal-rag": ModelConfig(
        id="internal-rag",
        provider="internal",
        family="iudex",
        label="Iudex RAG",
        context_window=1_000_000,
        latency_tier="low",
        cost_tier="low",
        capabilities=["rag", "juridico", "documentos"],
        for_agents=False,
        for_juridico=True,
        default=False,
        icon="iudex.svg",
        # Internamente roda como um agente RAG usando Gemini Flash no Vertex.
        api_model=os.getenv("GEMINI_3_FLASH_API_MODEL", "gemini-3-flash-preview"),
        supports_streaming=True,
    ),

    # ---------- OPEN-WEIGHT (opcional) ----------
    "deepseek-v3.2-reasoner": ModelConfig(
        id="deepseek-v3.2-reasoner",
        provider="deepseek",
        family="deepseek-v3.2",
        label="DeepSeek V3.2 Reasoner",
        context_window=128_000,
        latency_tier="depends_self_host",
        cost_tier="infra_only",
        capabilities=["code", "analysis", "agents"],
        for_agents=True,
        for_juridico=False,
        default=False,
        icon="deepseek.svg",
        api_model="deepseek-reasoner",
        thinking_category="native",  # Native reasoning_content field
    ),

    # ---------- AGENT EXECUTORS ----------
    "claude-agent": ModelConfig(
        id="claude-agent",
        provider="anthropic",
        family="agents",
        label="Claude Agent",
        context_window=200_000,
        latency_tier="high",
        cost_tier="high",
        capabilities=["chat", "agents", "tools", "juridico"],
        for_agents=True,
        for_juridico=True,
        icon="anthropic.svg",
        api_model=os.getenv("CLAUDE_AGENT_API_MODEL", "claude-opus-4-6"),
        thinking_category="native",
        max_output_tokens=16384,
    ),
    "openai-agent": ModelConfig(
        id="openai-agent",
        provider="openai",
        family="agents",
        label="OpenAI Agent",
        context_window=128_000,
        latency_tier="high",
        cost_tier="high",
        capabilities=["chat", "agents", "tools"],
        for_agents=True,
        for_juridico=True,
        icon="openai.svg",
        api_model=os.getenv("OPENAI_AGENT_API_MODEL", "gpt-5.2"),
        thinking_category="xml",
        max_output_tokens=16384,
    ),
    "google-agent": ModelConfig(
        id="google-agent",
        provider="google",
        family="agents",
        label="Google Agent",
        context_window=1_000_000,
        latency_tier="high",
        cost_tier="high",
        capabilities=["chat", "agents", "tools", "multimodal"],
        for_agents=True,
        for_juridico=True,
        icon="gemini.svg",
        api_model=os.getenv("GOOGLE_AGENT_API_MODEL", "gemini-3-pro-preview"),
        thinking_category="native",
        max_output_tokens=8192,
    ),
}

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_model_config(model_id: str) -> Optional[ModelConfig]:
    """Get config for a model ID"""
    return MODEL_REGISTRY.get(model_id)

def get_api_model_name(model_id: str) -> str:
    """Get the actual API model name to use in provider calls"""
    config = MODEL_REGISTRY.get(model_id)
    return config.api_model if config else model_id

def get_thinking_category(model_id: str) -> str:
    """Get the thinking implementation category for a model.
    
    Returns:
        'native': Model has native API support (reasoning_content, thinking_delta, include_thoughts)
        'xml': Model should use XML <thinking> tags via prompt engineering
        'agent': Light model, use 2-step agent approach
        'none': No thinking support
    """
    config = MODEL_REGISTRY.get(model_id)
    if not config:
        return "xml"  # Default fallback
    return config.thinking_category

AGENT_MODEL_IDS = frozenset({"claude-agent", "openai-agent", "google-agent"})

def is_agent_model(model_id: str) -> bool:
    """Check if a model ID corresponds to an agent executor."""
    return model_id in AGENT_MODEL_IDS

def validate_model_id(model_id: Optional[str], *, for_juridico: bool = False, for_agents: bool = False, field_name: str = "model") -> str:
    """
    Validate that a canonical model id exists in the registry (optionally filtered by usage flags).
    Returns the normalized model id (string). Raises ValueError with a clear message if invalid.
    """
    if not model_id or not str(model_id).strip():
        raise ValueError(f"Campo '{field_name}' vazio.")

    mid = str(model_id).strip()
    cfg = MODEL_REGISTRY.get(mid)
    if not cfg:
        allowed = list_available_models(for_juridico=for_juridico, for_agents=for_agents)
        allowed_ids = [m["id"] for m in allowed]
        raise ValueError(
            f"Modelo inválido em '{field_name}': '{mid}'. "
            f"Use um id canônico do registry. Exemplos: {allowed_ids[:12]}"
        )

    if for_juridico and not cfg.for_juridico:
        raise ValueError(f"Modelo '{mid}' não é permitido para jurídico (campo '{field_name}').")
    if for_agents and not cfg.for_agents:
        raise ValueError(f"Modelo '{mid}' não é permitido para agentes (campo '{field_name}').")

    return mid

def validate_model_list(
    model_ids: Optional[List[str]],
    *,
    for_juridico: bool = False,
    for_agents: bool = False,
    field_name: str = "models"
) -> List[str]:
    """
    Validate a list of canonical model ids. Returns a de-duplicated list preserving order.
    Empty/None returns [] so callers can decide on defaults.
    """
    if not model_ids:
        return []
    if not isinstance(model_ids, list):
        raise ValueError(f"Campo '{field_name}' deve ser uma lista.")

    normalized: List[str] = []
    seen = set()
    for idx, model_id in enumerate(model_ids):
        mid = validate_model_id(
            model_id,
            for_juridico=for_juridico,
            for_agents=for_agents,
            field_name=f"{field_name}[{idx}]"
        )
        if mid in seen:
            continue
        seen.add(mid)
        normalized.append(mid)

    return normalized

def list_available_models(for_juridico: bool = False, for_agents: bool = False) -> List[Dict[str, Any]]:
    """List available models with optional filtering"""
    models = []
    for cfg in MODEL_REGISTRY.values():
        if for_juridico and not cfg.for_juridico:
            continue
        if for_agents and not cfg.for_agents:
            continue
        models.append({
            "id": cfg.id,
            "label": cfg.label,
            "provider": cfg.provider,
            "family": cfg.family,
            "icon": f"/logos/{cfg.icon}",
            "context_window": cfg.context_window,
            "latency_tier": cfg.latency_tier,
            "cost_tier": cfg.cost_tier,
            "capabilities": cfg.capabilities,
            "default": cfg.default,
        })
    return models

def pick_model_for_job(
    purpose: str = "juridico",
    fast: bool = False,
    cheap: bool = False,
    task: Optional[str] = None,
) -> Optional[str]:
    """
    Pick a model based on purpose and constraints.

    When *task* is provided (e.g. "drafting", "research"), delegates to the
    intelligent ModelRouter for task-specific selection. Falls back to the
    legacy heuristic when no task is given, preserving backward compatibility.

    Args:
        purpose: 'juridico' or 'agents'
        fast: Prefer low latency
        cheap: Prefer low cost
        task: Optional task category for intelligent routing (see model_router.TaskCategory)
    """
    # --- Intelligent routing when task is specified ---
    if task:
        try:
            from app.services.ai.model_router import model_router, RouteRequest, TaskCategory
            task_enum = TaskCategory(task)
            req = RouteRequest(task=task_enum, prefer_fast=fast, prefer_cheap=cheap)
            import asyncio
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop and loop.is_running():
                # Already in an event loop — use sync fallback
                result = model_router.route_sync(task_enum)
            else:
                result = asyncio.run(model_router.route(req))
            return result.model_id
        except (ValueError, ImportError):
            pass  # Fall through to legacy heuristic

    # --- Legacy heuristic ---
    candidates = []
    for mid, cfg in MODEL_REGISTRY.items():
        if purpose == "juridico" and not cfg.for_juridico:
            continue
        if purpose == "agents" and not cfg.for_agents:
            continue
        candidates.append((mid, cfg))

    if fast:
        candidates = [(m, c) for m, c in candidates if c.latency_tier in ("low", "medium")]
    if cheap:
        candidates = [(m, c) for m, c in candidates if c.cost_tier in ("low", "medium")]

    # Prioritize defaults
    for mid, cfg in candidates:
        if cfg.default:
            return mid

    return candidates[0][0] if candidates else None

# Default models for different use cases
DEFAULT_CHAT_MODEL = "gemini-3-flash"
DEFAULT_JUDGE_MODEL = "gemini-3-flash"
DEFAULT_DEBATE_MODELS = ["gpt-5.2", "claude-4.5-sonnet", "gemini-3-flash"]
