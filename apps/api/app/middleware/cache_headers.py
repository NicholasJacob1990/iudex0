"""
Middleware de Cache-Control e ETag para respostas da API.

Adiciona headers de cache com base no método HTTP e padrão de URL,
e gera ETags para respostas GET que permitem cache.
"""

import hashlib
import re
from typing import Callable, List, Tuple

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


# Regras de cache: (regex do path, valor do Cache-Control)
# A primeira regra que casar é usada.
_CACHE_RULES: List[Tuple[re.Pattern, str]] = [
    # SSE / streaming — não cachear (manter no-cache existente)
    (re.compile(r"/api/.*(stream|sse|chat/)"), "no-cache"),
    # Catálogo de workflows — público, 5 min
    (re.compile(r"/api/workflows/catalog"), "public, max-age=300"),
    # Stats do corpus — privado, 2 min
    (re.compile(r"/api/corpus/stats"), "private, max-age=120"),
    # Playbooks list — privado, 1 min
    (re.compile(r"/api/playbooks$"), "private, max-age=60"),
    # Health check — curto
    (re.compile(r"^/health$"), "public, max-age=10"),
]

# Paths que não devem receber ETag (streaming, SSE)
_NO_ETAG_PATTERNS = [
    re.compile(r"stream|sse|chat/"),
]


def _get_cache_control(method: str, path: str) -> str | None:
    """Retorna o valor de Cache-Control para um dado método/path."""
    # Métodos de escrita nunca são cacheados
    if method in ("POST", "PUT", "PATCH", "DELETE"):
        return "no-store"

    # Verificar regras específicas para GET/HEAD/OPTIONS
    for pattern, value in _CACHE_RULES:
        if pattern.search(path):
            return value

    # GET genérico — sem cache por padrão (seguro)
    return None


def _should_etag(path: str) -> bool:
    """Retorna True se o path deve receber ETag."""
    for pattern in _NO_ETAG_PATTERNS:
        if pattern.search(path):
            return False
    return True


def _compute_etag(body: bytes) -> str:
    """Gera um ETag a partir do hash MD5 do corpo da resposta."""
    digest = hashlib.md5(body).hexdigest()  # noqa: S324
    return f'W/"{digest}"'


class CacheHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware que adiciona Cache-Control e ETag a respostas da API.

    - Cache-Control é baseado no método HTTP e padrão de URL
    - ETag é gerado para respostas GET com corpo < 10MB
    - Respeita If-None-Match para retornar 304 Not Modified
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)

        method = request.method
        path = request.url.path

        # Adicionar Cache-Control se não já definido
        if "cache-control" not in response.headers:
            cc = _get_cache_control(method, path)
            if cc:
                response.headers["Cache-Control"] = cc

        # ETag para respostas GET com cache habilitado
        if (
            method == "GET"
            and response.status_code == 200
            and _should_etag(path)
            and hasattr(response, "body")
        ):
            body = response.body
            # Só gerar ETag para respostas < 10MB
            if body and len(body) < 10 * 1024 * 1024:
                etag = _compute_etag(body)
                response.headers["ETag"] = etag

                # Verificar If-None-Match
                if_none_match = request.headers.get("if-none-match")
                if if_none_match and if_none_match == etag:
                    return Response(
                        status_code=304,
                        headers={
                            "ETag": etag,
                            "Cache-Control": response.headers.get(
                                "Cache-Control", ""
                            ),
                        },
                    )

        return response
