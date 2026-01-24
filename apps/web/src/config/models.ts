// config/models.ts - Model Registry for Frontend

export type ModelId =
    | "gpt-5.2"
    | "gpt-5.2-instant"
    | "gpt-5"
    | "gpt-5-mini"
    | "gpt-4o"
    | "grok-4"
    | "grok-4-fast"
    | "grok-4.1-fast"
    | "grok-4.1"
    | "claude-4.5-opus"
    | "claude-4.5-sonnet"
    | "claude-4.5-haiku"
    | "gemini-3-pro"
    | "gemini-3-flash"
    | "gemini-2.5-pro"
    | "gemini-2.5-flash"
    | "sonar"
    | "sonar-pro"
    | "sonar-deep-research"
    | "sonar-reasoning-pro"
    | "llama-4"
    | "llama-4-maverick-t"
    | "internal-rag";

export type Provider = "openai" | "anthropic" | "google" | "xai" | "openrouter" | "perplexity" | "internal";
export type LatencyTier = "low" | "medium" | "high";
export type CostTier = "low" | "medium" | "medium_high" | "high";

export interface ModelConfig {
    id: ModelId;
    provider: Provider;
    family: string;
    label: string;
    contextWindow: number;
    latencyTier: LatencyTier;
    costTier: CostTier;
    capabilities: string[];
    forAgents: boolean;
    forJuridico: boolean;
    default?: boolean;
    icon: string;
}

export const MODEL_REGISTRY: Record<ModelId, ModelConfig> = {
    // ---------- OPENAI ----------
    "gpt-5.2": {
        id: "gpt-5.2",
        provider: "openai",
        family: "gpt-5",
        label: "GPT‑5.2",
        contextWindow: 400_000,
        latencyTier: "high",
        costTier: "high",
        capabilities: ["chat", "code", "agents", "analysis"],
        forAgents: true,
        forJuridico: true,
        default: false,
        icon: "/logos/openai.png",
    },
    "gpt-5.2-instant": {
        id: "gpt-5.2-instant",
        provider: "openai",
        family: "gpt-5",
        label: "GPT‑5.2 Instant",
        contextWindow: 400_000,
        latencyTier: "low",
        costTier: "medium_high",
        capabilities: ["chat", "code", "analysis"],
        forAgents: true,
        forJuridico: true,
        default: false,
        icon: "/logos/openai.png",
    },
    "gpt-5": {
        id: "gpt-5",
        provider: "openai",
        family: "gpt-5",
        label: "GPT‑5",
        contextWindow: 400_000,
        latencyTier: "medium",
        costTier: "medium_high",
        capabilities: ["chat", "code", "analysis"],
        forAgents: true,
        forJuridico: true,
        default: true,
        icon: "/logos/openai.png",
    },
    "gpt-5-mini": {
        id: "gpt-5-mini",
        provider: "openai",
        family: "gpt-5",
        label: "GPT‑5 mini",
        contextWindow: 400_000,
        latencyTier: "low",
        costTier: "low",
        capabilities: ["chat", "tools", "high_volume"],
        forAgents: true,
        forJuridico: true,
        default: false,
        icon: "/logos/openai.png",
    },
    "gpt-4o": {
        id: "gpt-4o",
        provider: "openai",
        family: "gpt-4",
        label: "GPT‑4o",
        contextWindow: 128_000,
        latencyTier: "medium",
        costTier: "medium",
        capabilities: ["chat", "code", "multimodal"],
        forAgents: true,
        forJuridico: true,
        icon: "/logos/openai.png",
    },

    // ---------- XAI ----------
    "grok-4": {
        id: "grok-4",
        provider: "xai",
        family: "grok-4",
        label: "Grok 4",
        contextWindow: 128_000,
        latencyTier: "high",
        costTier: "high",
        capabilities: ["chat", "analysis", "agents"],
        forAgents: true,
        forJuridico: true,
        default: false,
        icon: "/logos/xai.png",
    },
    "grok-4-fast": {
        id: "grok-4-fast",
        provider: "xai",
        family: "grok-4",
        label: "Grok 4 Fast",
        contextWindow: 2_000_000,
        latencyTier: "medium",
        costTier: "high",
        capabilities: ["chat", "analysis", "agents"],
        forAgents: true,
        forJuridico: true,
        default: false,
        icon: "/logos/xai.png",
    },
    "grok-4.1-fast": {
        id: "grok-4.1-fast",
        provider: "xai",
        family: "grok-4",
        label: "Grok 4.1 Fast",
        contextWindow: 2_000_000,
        latencyTier: "medium",
        costTier: "high",
        capabilities: ["chat", "analysis", "agents"],
        forAgents: true,
        forJuridico: true,
        default: false,
        icon: "/logos/xai.png",
    },
    "grok-4.1": {
        id: "grok-4.1",
        provider: "xai",
        family: "grok-4",
        label: "Grok 4.1",
        contextWindow: 2_000_000,
        latencyTier: "medium",
        costTier: "medium",
        capabilities: ["chat", "analysis", "agents"],
        forAgents: true,
        forJuridico: true,
        default: false,
        icon: "/logos/xai.png",
    },

    // ---------- ANTHROPIC ----------
    "claude-4.5-opus": {
        id: "claude-4.5-opus",
        provider: "anthropic",
        family: "claude-4.5",
        label: "Claude 4.5 Opus",
        contextWindow: 200_000,
        latencyTier: "high",
        costTier: "high",
        capabilities: ["chat", "code", "agents", "deep_reasoning"],
        forAgents: true,
        forJuridico: true,
        icon: "/logos/anthropic.png",
    },
    "claude-4.5-sonnet": {
        id: "claude-4.5-sonnet",
        provider: "anthropic",
        family: "claude-4.5",
        label: "Claude 4.5 Sonnet",
        contextWindow: 1_000_000,
        latencyTier: "medium",
        costTier: "medium",
        capabilities: ["chat", "code", "analysis"],
        forAgents: true,
        forJuridico: true,
        default: true,
        icon: "/logos/anthropic.png",
    },
    "claude-4.5-haiku": {
        id: "claude-4.5-haiku",
        provider: "anthropic",
        family: "claude-4.5",
        label: "Claude 4.5 Haiku",
        contextWindow: 200_000,
        latencyTier: "low",
        costTier: "low",
        capabilities: ["chat", "high_volume"],
        forAgents: false,
        forJuridico: true,
        icon: "/logos/anthropic.png",
    },

    // ---------- GEMINI ----------
    "gemini-3-pro": {
        id: "gemini-3-pro",
        provider: "google",
        family: "gemini-3",
        label: "Gemini 3 Pro",
        contextWindow: 1_000_000,
        latencyTier: "medium",
        costTier: "medium",
        capabilities: ["chat", "code", "agents", "multimodal"],
        forAgents: true,
        forJuridico: true,
        default: true,
        icon: "/logos/gemini.png",
    },
    "gemini-3-flash": {
        id: "gemini-3-flash",
        provider: "google",
        family: "gemini-3",
        label: "Gemini 3 Flash",
        contextWindow: 1_000_000,
        latencyTier: "low",
        costTier: "low",
        capabilities: ["chat", "tools", "high_volume", "multimodal"],
        forAgents: true,
        forJuridico: true,
        icon: "/logos/gemini.png",
    },
    "gemini-2.5-pro": {
        id: "gemini-2.5-pro",
        provider: "google",
        family: "gemini-2.5",
        label: "Gemini 2.5 Pro",
        contextWindow: 1_000_000,
        latencyTier: "medium",
        costTier: "medium",
        capabilities: ["chat", "code", "analysis"],
        forAgents: true,
        forJuridico: true,
        icon: "/logos/gemini.png",
    },
    "gemini-2.5-flash": {
        id: "gemini-2.5-flash",
        provider: "google",
        family: "gemini-2.5",
        label: "Gemini 2.5 Flash",
        contextWindow: 1_000_000,
        latencyTier: "low",
        costTier: "low",
        capabilities: ["chat", "high_volume", "multimodal"],
        forAgents: true,
        forJuridico: true,
        icon: "/logos/gemini.png",
    },

    // ---------- PERPLEXITY (SONAR) ----------
    "sonar": {
        id: "sonar",
        provider: "perplexity",
        family: "sonar",
        label: "Sonar",
        contextWindow: 127_000,
        latencyTier: "medium",
        costTier: "medium",
        capabilities: ["chat", "web_grounded"],
        forAgents: true,
        forJuridico: true,
        icon: "/logos/perplexity.svg",
    },
    "sonar-pro": {
        id: "sonar-pro",
        provider: "perplexity",
        family: "sonar",
        label: "Sonar Pro",
        contextWindow: 200_000,
        latencyTier: "medium",
        costTier: "high",
        capabilities: ["chat", "web_grounded"],
        forAgents: true,
        forJuridico: true,
        icon: "/logos/perplexity.svg",
    },
    "sonar-deep-research": {
        id: "sonar-deep-research",
        provider: "perplexity",
        family: "sonar",
        label: "Sonar Deep Research",
        contextWindow: 128_000,
        latencyTier: "high",
        costTier: "high",
        capabilities: ["chat", "web_grounded", "deep_research"],
        forAgents: true,
        forJuridico: true,
        icon: "/logos/perplexity.svg",
    },
    "sonar-reasoning-pro": {
        id: "sonar-reasoning-pro",
        provider: "perplexity",
        family: "sonar",
        label: "Sonar Reasoning Pro",
        contextWindow: 128_000,
        latencyTier: "high",
        costTier: "high",
        capabilities: ["chat", "web_grounded", "analysis"],
        forAgents: true,
        forJuridico: true,
        icon: "/logos/perplexity.svg",
    },

    // ---------- OPENROUTER / META ----------
    "llama-4": {
        id: "llama-4",
        provider: "openrouter",
        family: "llama-4",
        label: "Llama 4",
        contextWindow: 128_000,
        latencyTier: "medium",
        costTier: "medium",
        capabilities: ["chat", "analysis"],
        forAgents: true,
        forJuridico: true,
        default: false,
        icon: "/logos/meta.png",
    },
    "llama-4-maverick-t": {
        id: "llama-4-maverick-t",
        provider: "openrouter",
        family: "llama-4",
        label: "Llama 4 Maverick T",
        contextWindow: 500_000,
        latencyTier: "medium",
        costTier: "medium",
        capabilities: ["chat", "analysis", "multimodal"],
        forAgents: true,
        forJuridico: true,
        default: false,
        icon: "/logos/meta.png",
    },

    // ---------- INTERNAL ----------
    "internal-rag": {
        id: "internal-rag",
        provider: "internal",
        family: "iudex",
        label: "Iudex RAG",
        contextWindow: 1_000_000,
        latencyTier: "low",
        costTier: "low",
        capabilities: ["rag", "juridico", "documentos"],
        forAgents: false,
        forJuridico: true,
        icon: "/logos/iudex.svg",
    },
};

// Helper functions
export function getModelConfig(modelId: ModelId): ModelConfig {
    return MODEL_REGISTRY[modelId];
}

export function listModels(options?: { forJuridico?: boolean; forAgents?: boolean }): ModelConfig[] {
    return Object.values(MODEL_REGISTRY).filter((cfg) => {
        if (options?.forJuridico && !cfg.forJuridico) return false;
        if (options?.forAgents && !cfg.forAgents) return false;
        return true;
    });
}

export function getDefaultModels(): ModelConfig[] {
    return Object.values(MODEL_REGISTRY).filter((cfg) => cfg.default);
}

export function getModelsByProvider(provider: Provider): ModelConfig[] {
    return Object.values(MODEL_REGISTRY).filter((cfg) => cfg.provider === provider);
}

// Icon color mapping for UI
export const PROVIDER_COLORS: Record<Provider, string> = {
    openai: "#10a37f",      // OpenAI green
    anthropic: "#d97706",   // Claude orange
    google: "#4285f4",      // Google blue
    xai: "#0f172a",         // xAI ink
    openrouter: "#0ea5a4",  // OpenRouter teal
    perplexity: "#111827",  // Perplexity charcoal
    internal: "#6366f1",    // Iudex purple
};
