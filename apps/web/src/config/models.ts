// config/models.ts - Model Registry for Frontend

export type ModelId =
    | "gpt-5.2"
    | "gpt-5"
    | "gpt-5-mini"
    | "gpt-4o"
    | "claude-4.5-opus"
    | "claude-4.5-sonnet"
    | "claude-4.5-haiku"
    | "gemini-3-pro"
    | "gemini-3-flash"
    | "gemini-2.5-pro"
    | "gemini-2.5-flash"
    | "internal-rag";

export type Provider = "openai" | "anthropic" | "google" | "internal";
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
        icon: "/logos/openai.svg",
    },
    "gpt-5": {
        id: "gpt-5",
        provider: "openai",
        family: "gpt-5",
        label: "GPT‑5",
        contextWindow: 200_000,
        latencyTier: "medium",
        costTier: "medium_high",
        capabilities: ["chat", "code", "analysis"],
        forAgents: true,
        forJuridico: true,
        default: true,
        icon: "/logos/openai.svg",
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
        icon: "/logos/openai.svg",
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
        icon: "/logos/openai.svg",
    },

    // ---------- ANTHROPIC ----------
    "claude-4.5-opus": {
        id: "claude-4.5-opus",
        provider: "anthropic",
        family: "claude-4.5",
        label: "Claude 4.5 Opus",
        contextWindow: 1_000_000,
        latencyTier: "high",
        costTier: "high",
        capabilities: ["chat", "code", "agents", "deep_reasoning"],
        forAgents: true,
        forJuridico: true,
        icon: "/logos/anthropic.svg",
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
        icon: "/logos/anthropic.svg",
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
        icon: "/logos/anthropic.svg",
    },

    // ---------- GEMINI ----------
    "gemini-3-pro": {
        id: "gemini-3-pro",
        provider: "google",
        family: "gemini-3",
        label: "Gemini 3 Pro",
        contextWindow: 200_000,
        latencyTier: "medium",
        costTier: "medium",
        capabilities: ["chat", "code", "agents", "multimodal"],
        forAgents: true,
        forJuridico: true,
        default: true,
        icon: "/logos/gemini.svg",
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
        icon: "/logos/gemini.svg",
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
        icon: "/logos/gemini.svg",
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
        icon: "/logos/gemini.svg",
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
    internal: "#6366f1",    // Iudex purple
};
