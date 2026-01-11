"""
Model Registry - Centralized configuration for all available models

Includes:
- Model IDs and families
- Context windows
- Latency and cost tiers
- Capabilities
- Flags for agents and juridico use
"""

from typing import Dict, Any, Literal, List, Optional
from dataclasses import dataclass, field

LatencyTier = Literal["low", "medium", "high", "depends_self_host"]
CostTier = Literal["low", "medium", "medium_high", "high", "infra_only"]

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
        api_model="gpt-5.2-chat-latest",
    ),
    "gpt-5": ModelConfig(
        id="gpt-5",
        provider="openai",
        family="gpt-5",
        label="GPT‑5",
        context_window=200_000,
        latency_tier="medium",
        cost_tier="medium_high",
        capabilities=["chat", "code", "analysis"],
        for_agents=True,
        for_juridico=True,
        default=True,
        icon="openai.svg",
        api_model="gpt-5",
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
        api_model="gpt-5-mini",
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
    ),

    # ---------- ANTHROPIC ----------
    "claude-4.5-opus": ModelConfig(
        id="claude-4.5-opus",
        provider="anthropic",
        family="claude-4.5",
        label="Claude 4.5 Opus",
        context_window=1_000_000,
        latency_tier="high",
        cost_tier="high",
        capabilities=["chat", "code", "agents", "deep_reasoning"],
        for_agents=True,
        for_juridico=True,
        default=False,
        icon="anthropic.svg",
        api_model="claude-opus-4-5@20250929",
    ),
    "claude-4.5-sonnet": ModelConfig(
        id="claude-4.5-sonnet",
        provider="anthropic",
        family="claude-4.5",
        label="Claude 4.5 Sonnet",
        context_window=1_000_000,
        latency_tier="medium",
        cost_tier="medium",
        capabilities=["chat", "code", "analysis"],
        for_agents=True,
        for_juridico=True,
        default=True,
        icon="anthropic.svg",
        api_model="claude-sonnet-4-5@20250929",
    ),
    "claude-4.5-haiku": ModelConfig(
        id="claude-4.5-haiku",
        provider="anthropic",
        family="claude-4.5",
        label="Claude 4.5 Haiku",
        context_window=200_000,
        latency_tier="low",
        cost_tier="low",
        capabilities=["chat", "high_volume"],
        for_agents=False,
        for_juridico=True,
        default=False,
        icon="anthropic.svg",
        api_model="claude-haiku-4-5@20250929",
    ),

    # ---------- GEMINI ----------
    "gemini-3-pro": ModelConfig(
        id="gemini-3-pro",
        provider="google",
        family="gemini-3",
        label="Gemini 3 Pro",
        context_window=200_000,
        latency_tier="medium",
        cost_tier="medium",
        capabilities=["chat", "code", "agents", "multimodal"],
        for_agents=True,
        for_juridico=True,
        default=True,
        icon="gemini.svg",
        api_model="gemini-3-pro",
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
        api_model="gemini-3-flash-preview",
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
        api_model="gemini-2.5-pro-preview-05-06",
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
        api_model="gemini-2.5-flash-preview-05-20",
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
        api_model="gemini-2.5-flash-preview-05-20",
        supports_streaming=False,
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

def pick_model_for_job(purpose: str = "juridico", fast: bool = False, cheap: bool = False) -> Optional[str]:
    """
    Pick a model based on purpose and constraints.
    
    Args:
        purpose: 'juridico' or 'agents'
        fast: Prefer low latency
        cheap: Prefer low cost
    """
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
DEFAULT_JUDGE_MODEL = "gemini-3-pro"
DEFAULT_DEBATE_MODELS = ["gpt-5.2", "claude-4.5-sonnet", "gemini-3-pro"]
