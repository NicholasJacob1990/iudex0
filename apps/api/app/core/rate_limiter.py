"""
Rate Limiter usando Redis
Protege a API contra abuso e garante fair usage
"""

from typing import Optional, Callable
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from redis import Redis
from loguru import logger
import time

from app.core.config import settings


class RateLimiter:
    """
    Rate limiter baseado em sliding window
    Usa Redis para tracking distribuído
    """
    
    def __init__(self, redis_client: Optional[Redis] = None):
        self.redis_client = redis_client
        self.enabled = settings.RATE_LIMIT_ENABLED
        
        if self.enabled and not redis_client:
            try:
                from app.core.redis import get_redis_client
                self.redis_client = get_redis_client()
            except Exception as e:
                logger.warning(f"Redis não disponível, rate limiting desabilitado: {e}")
                self.enabled = False
    
    def _get_identifier(self, request: Request) -> str:
        """
        Obtém identificador único do cliente
        Usa user_id se autenticado, senão IP
        """
        # Tentar pegar user_id do token
        if hasattr(request.state, 'user_id'):
            return f"user:{request.state.user_id}"
        
        # Fallback: IP do cliente
        forwarded_for = request.headers.get('X-Forwarded-For')
        if forwarded_for:
            ip = forwarded_for.split(',')[0].strip()
        else:
            ip = request.client.host if request.client else 'unknown'
        
        return f"ip:{ip}"
    
    def _get_key(self, identifier: str, window: str) -> str:
        """Gera chave Redis para rate limiting"""
        return f"rate_limit:{identifier}:{window}"
    
    async def check_rate_limit(
        self,
        request: Request,
        max_requests: int,
        window_seconds: int,
        identifier: Optional[str] = None
    ) -> tuple[bool, dict]:
        """
        Verifica se requisição está dentro do rate limit
        
        Returns:
            (allowed, info) onde info contém remaining, reset_time, etc
        """
        if not self.enabled:
            return True, {}
        
        if not identifier:
            identifier = self._get_identifier(request)
        
        current_time = int(time.time())
        window_key = self._get_key(identifier, f"{current_time // window_seconds}")
        
        try:
            # Incrementar contador
            count = self.redis_client.incr(window_key)
            
            # Definir TTL na primeira requisição da janela
            if count == 1:
                self.redis_client.expire(window_key, window_seconds * 2)
            
            # Calcular tempo até reset
            reset_time = ((current_time // window_seconds) + 1) * window_seconds
            
            info = {
                "limit": max_requests,
                "remaining": max(0, max_requests - count),
                "reset": reset_time,
                "retry_after": reset_time - current_time if count > max_requests else 0
            }
            
            if count > max_requests:
                return False, info
            
            return True, info
            
        except Exception as e:
            logger.error(f"Erro ao verificar rate limit: {e}")
            # Em caso de erro, permitir requisição (fail open)
            return True, {}
    
    def limit(
        self,
        max_requests: int = 60,
        window_seconds: int = 60,
        error_message: str = "Muitas requisições. Tente novamente em breve."
    ):
        """
        Decorator para aplicar rate limiting a endpoints
        
        Exemplo:
            @router.get("/api/resource")
            @rate_limiter.limit(max_requests=10, window_seconds=60)
            async def get_resource():
                ...
        """
        def decorator(func: Callable):
            async def wrapper(request: Request, *args, **kwargs):
                allowed, info = await self.check_rate_limit(
                    request, max_requests, window_seconds
                )
                
                if not allowed:
                    logger.warning(
                        f"Rate limit excedido para {self._get_identifier(request)}"
                    )
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={
                            "error": error_message,
                            "retry_after": info.get("retry_after", window_seconds),
                            "limit": max_requests,
                            "window_seconds": window_seconds
                        },
                        headers={
                            "Retry-After": str(info.get("retry_after", window_seconds)),
                            "X-RateLimit-Limit": str(max_requests),
                            "X-RateLimit-Remaining": str(info.get("remaining", 0)),
                            "X-RateLimit-Reset": str(info.get("reset", 0))
                        }
                    )
                
                # Adicionar headers de rate limit na resposta
                response = await func(request, *args, **kwargs)
                if hasattr(response, 'headers'):
                    response.headers["X-RateLimit-Limit"] = str(max_requests)
                    response.headers["X-RateLimit-Remaining"] = str(info.get("remaining", max_requests))
                    response.headers["X-RateLimit-Reset"] = str(info.get("reset", 0))
                
                return response
            
            return wrapper
        return decorator


# Configurações de rate limit por tipo de operação
RATE_LIMITS = {
    "auth_login": {
        "max_requests": 5,
        "window_seconds": 300,  # 5 min
        "error": "Muitas tentativas de login. Aguarde 5 minutos."
    },
    "auth_register": {
        "max_requests": 3,
        "window_seconds": 3600,  # 1 hora
        "error": "Muitas tentativas de registro. Aguarde 1 hora."
    },
    "document_upload": {
        "max_requests": 20,
        "window_seconds": 3600,  # 1 hora
        "error": "Limite de uploads atingido. Aguarde 1 hora."
    },
    "ai_generation": {
        "max_requests": 10,
        "window_seconds": 3600,  # 1 hora
        "error": "Limite de gerações IA atingido. Aguarde 1 hora."
    },
    "api_general": {
        "max_requests": settings.RATE_LIMIT_PER_MINUTE,
        "window_seconds": 60,
        "error": "Taxa de requisições muito alta."
    }
}


def get_rate_limiter() -> RateLimiter:
    """Factory para obter instância do rate limiter"""
    return RateLimiter()


# Middleware global de rate limiting
class RateLimitMiddleware:
    """
    Middleware que aplica rate limiting global
    """
    
    def __init__(self, app, rate_limiter: RateLimiter):
        self.app = app
        self.rate_limiter = rate_limiter
    
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        # Criar request para análise
        from starlette.requests import Request
        request = Request(scope, receive)
        
        # Verificar rate limit geral
        config = RATE_LIMITS["api_general"]
        allowed, info = await self.rate_limiter.check_rate_limit(
            request,
            config["max_requests"],
            config["window_seconds"]
        )
        
        if not allowed:
            # Enviar resposta 429
            response = JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "detail": config["error"],
                    "retry_after": info.get("retry_after", 60)
                },
                headers={
                    "Retry-After": str(info.get("retry_after", 60)),
                    "X-RateLimit-Limit": str(config["max_requests"]),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(info.get("reset", 0))
                }
            )
            
            await response(scope, receive, send)
            return
        
        # Continuar com a requisição
        await self.app(scope, receive, send)


# Instância global
rate_limiter = get_rate_limiter()

