"""
Rate Limit — Dependências reutilizáveis para rate-limiting de endpoints.

Utiliza o RateLimiter existente (core/rate_limiter.py) como base.
Cada endpoint pode declarar um Depends(...) com limites customizados.

Inspirado nos rate limits da Harvey AI (10 req/min em Vault).
"""

from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from loguru import logger

from app.core.rate_limiter import RateLimiter, get_rate_limiter


def _get_identifier(request: Request) -> str:
    """Extrai identificador do cliente (user_id ou IP)."""
    if hasattr(request.state, "user_id"):
        return f"user:{request.state.user_id}"
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        ip = forwarded_for.split(",")[0].strip()
    else:
        ip = request.client.host if request.client else "unknown"
    return f"ip:{ip}"


class RateLimitDep:
    """
    Classe que gera uma FastAPI Dependency para rate-limiting.

    Uso:
        @router.post("/search")
        async def search(
            ...,
            _rl: None = Depends(RateLimitDep(10, 60, "corpus:search")),
        ):
            ...
    """

    def __init__(
        self,
        max_requests: int,
        window_seconds: int = 60,
        scope: str = "default",
        error_message: str = "Muitas requisições. Tente novamente em breve.",
    ):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.scope = scope
        self.error_message = error_message

    async def __call__(self, request: Request) -> None:
        limiter = get_rate_limiter()

        if not limiter.enabled:
            return

        identifier = _get_identifier(request)
        scoped_id = f"{identifier}:{self.scope}"

        allowed, info = await limiter.check_rate_limit(
            request=request,
            max_requests=self.max_requests,
            window_seconds=self.window_seconds,
            identifier=scoped_id,
        )

        if not allowed:
            logger.warning(
                "Rate limit excedido: scope=%s, identifier=%s, limit=%d/%ds",
                self.scope,
                identifier,
                self.max_requests,
                self.window_seconds,
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error": self.error_message,
                    "retry_after": info.get("retry_after", self.window_seconds),
                    "limit": self.max_requests,
                    "window_seconds": self.window_seconds,
                },
                headers={
                    "Retry-After": str(info.get("retry_after", self.window_seconds)),
                    "X-RateLimit-Limit": str(self.max_requests),
                    "X-RateLimit-Remaining": str(info.get("remaining", 0)),
                    "X-RateLimit-Reset": str(info.get("reset", 0)),
                },
            )


# ---------------------------------------------------------------------------
# Pre-configured rate limit dependencies for Corpus / Playbook endpoints
# ---------------------------------------------------------------------------

# Corpus
corpus_search_limit = RateLimitDep(
    max_requests=10,
    window_seconds=60,
    scope="corpus:search",
    error_message="Limite de buscas no Corpus atingido (10/min).",
)

corpus_read_limit = RateLimitDep(
    max_requests=30,
    window_seconds=60,
    scope="corpus:read",
    error_message="Limite de leituras no Corpus atingido (30/min).",
)

corpus_write_limit = RateLimitDep(
    max_requests=5,
    window_seconds=60,
    scope="corpus:write",
    error_message="Limite de escritas no Corpus atingido (5/min).",
)

# Playbooks
playbook_read_limit = RateLimitDep(
    max_requests=30,
    window_seconds=60,
    scope="playbook:read",
    error_message="Limite de leituras de Playbook atingido (30/min).",
)

playbook_write_limit = RateLimitDep(
    max_requests=10,
    window_seconds=60,
    scope="playbook:write",
    error_message="Limite de escritas de Playbook atingido (10/min).",
)

playbook_analyze_limit = RateLimitDep(
    max_requests=5,
    window_seconds=60,
    scope="playbook:analyze",
    error_message="Limite de análises de Playbook atingido (5/min).",
)

playbook_generate_limit = RateLimitDep(
    max_requests=3,
    window_seconds=60,
    scope="playbook:generate",
    error_message="Limite de gerações de Playbook atingido (3/min).",
)
