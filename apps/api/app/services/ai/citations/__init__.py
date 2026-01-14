from .base import Source, render_perplexity
from .openai import openai_extract_perplexity
from .gemini import gemini_extract_perplexity
from .claude import claude_extract_perplexity


def to_perplexity(provider: str, resp):
    provider = (provider or "").lower()
    if provider in ("openai", "gpt"):
        text, sources = openai_extract_perplexity(resp)
    elif provider in ("gemini", "google"):
        text, sources = gemini_extract_perplexity(resp)
    elif provider in ("claude", "anthropic", "vertex-claude", "claude-vertex"):
        text, sources = claude_extract_perplexity(resp)
    else:
        raise ValueError(f"Provider desconhecido: {provider}")
    if not sources:
        return (text or "").strip()
    return render_perplexity(text, sources)
