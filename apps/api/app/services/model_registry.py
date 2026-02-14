"""
Registro de modelos e seus limites de tokens.
Fonte de verdade para o TokenBudgetService.
"""

MODEL_REGISTRY = {
    # === GEMINI (Google Vertex AI) ===
    # Fonte: https://ai.google.dev/gemini-api/docs/models/gemini
    "gemini-2.5-pro-preview-06-05": {
        "context_window": 2_000_000, # 2M tokens (Preview)
        "max_output": 8_192,
        "provider": "vertex",
        "input_price_1k": 0.00, # Preview grátis ou variável
        "output_price_1k": 0.00
    },
    "gemini-3-flash-preview": {
        "context_window": 1_000_000, # 1M tokens
        "max_output": 8_192,
        "provider": "vertex"
    },
    # Aliases canônicos (IDs do app) -> valores aproximados para budget
    "gemini-3-flash": {
        "context_window": 1_000_000,
        "max_output": 8_192,
        "provider": "vertex"
    },
    "gemini-3-pro": {
        "context_window": 1_000_000,
        "max_output": 8_192,
        "provider": "vertex"
    },
    # Internal RAG Agent (powered by Gemini Flash)
    "internal-rag": {
        "context_window": 1_000_000,
        "max_output": 8_192,
        "provider": "vertex"
    },
    "gemini-1.5-pro-001": {
        "context_window": 2_097_152, # 2M tokens
        "max_output": 8_192,
        "provider": "vertex"
    },
    
    # === OPENAI (GPT) ===
    # Fonte: https://platform.openai.com/docs/models
    "gpt-5.2-chat-latest": {
        "context_window": 400_000, # Conforme user report
        "max_output": 128_000,
        "provider": "openai"
    },
    "gpt-5.2": {
        "context_window": 400_000,
        "max_output": 128_000,
        "provider": "openai"
    },
    "gpt-5.3-codex": {
        "context_window": 400_000,
        "max_output": 128_000,
        "provider": "openai"
    },
    "gpt-5.2-instant": {
        "context_window": 400_000,
        "max_output": 128_000,
        "provider": "openai"
    },
    "gpt-5": {
        "context_window": 200_000,
        "max_output": 16_000,
        "provider": "openai"
    },
    "gpt-4o": {
        "context_window": 128_000,
        "max_output": 4_096,
        "provider": "openai"
    },

    # === XAI (GROK) ===
    "grok-4": {
        "context_window": 128_000,
        "max_output": 8_192,
        "provider": "xai"
    },
    "grok-4-fast": {
        "context_window": 2_000_000,
        "max_output": 8_192,
        "provider": "xai"
    },
    "grok-4.1-fast": {
        "context_window": 2_000_000,
        "max_output": 8_192,
        "provider": "xai"
    },
    "grok-4.1": {
        "context_window": 2_000_000,
        "max_output": 8_192,
        "provider": "xai"
    },

    # === ANTHROPIC (CLAUDE) ===
    # Fonte: https://docs.anthropic.com/en/docs/about-claude/models
    "claude-sonnet-4-5-20250514": {
        "context_window": 200_000, # Padrão (pode chegar a 1M com flag)
        "max_output": 64_000,     # Max output expandido recentemente?
        "provider": "anthropic"
    },
    # Provider names used pelo registry novo
    "claude-sonnet-4-5@20250929": {
        "context_window": 200_000,
        "max_output": 8_192,
        "provider": "anthropic"
    },
    "claude-opus-4-5@20250929": {
        "context_window": 200_000,
        "max_output": 8_192,
        "provider": "anthropic"
    },
    # Aliases canônicos
    "claude-4.5-sonnet": {
        "context_window": 200_000,
        "max_output": 8_192,
        "provider": "anthropic"
    },
    "claude-4.5-opus": {
        "context_window": 200_000,
        "max_output": 8_192,
        "provider": "anthropic"
    },
    "claude-3-5-sonnet-20240620": {
        "context_window": 200_000,
        "max_output": 8_192,
        "provider": "anthropic"
    },
    # === META (LLAMA) ===
    "llama-4": {
        "context_window": 128_000,
        "max_output": 8_192,
        "provider": "openrouter"
    },
    "llama-4-maverick-t": {
        "context_window": 500_000,
        "max_output": 8_192,
        "provider": "openrouter"
    },

    # === PERPLEXITY (SONAR) ===
    # Valores conservadores para budget (evita estourar contexto).
    "sonar": {
        "context_window": 128_000,
        "max_output": 4_096,
        "provider": "perplexity"
    },
    "sonar-pro": {
        "context_window": 128_000,
        "max_output": 4_096,
        "provider": "perplexity"
    },
    "sonar-deep-research": {
        "context_window": 128_000,
        "max_output": 4_096,
        "provider": "perplexity"
    },
    "sonar-reasoning-pro": {
        "context_window": 128_000,
        "max_output": 4_096,
        "provider": "perplexity"
    }
}

def get_model_config(model_name: str) -> dict:
    """Retorna configuração do modelo ou default seguro"""
    return MODEL_REGISTRY.get(model_name, {
        "context_window": 32_000,
        "max_output": 4_096,
        "provider": "unknown"
    })
