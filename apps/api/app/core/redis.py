"""
Configuração do Redis
"""

from typing import Optional
import json

import redis.asyncio as redis
from loguru import logger

from app.core.config import settings

# Cliente Redis
redis_client: Optional[redis.Redis] = None


async def init_redis() -> None:
    """
    Inicializa conexão com Redis
    """
    global redis_client
    try:
        redis_client = await redis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
        await redis_client.ping()
        logger.info("Conexão com Redis estabelecida")
    except Exception as e:
        logger.error(f"Erro ao conectar ao Redis: {e}")
        raise


async def close_redis() -> None:
    """
    Fecha conexão com Redis
    """
    global redis_client
    if redis_client:
        await redis_client.close()
        logger.info("Conexão com Redis fechada")


def get_redis() -> redis.Redis:
    """
    Retorna cliente Redis
    """
    if not redis_client:
        raise Exception("Redis não foi inicializado")
    return redis_client


class CacheService:
    """
    Serviço de cache usando Redis
    """
    
    @staticmethod
    async def get(key: str) -> Optional[dict]:
        """Obtém valor do cache"""
        try:
            client = get_redis()
            value = await client.get(key)
            return json.loads(value) if value else None
        except Exception as e:
            logger.error(f"Erro ao buscar cache: {e}")
            return None
    
    @staticmethod
    async def set(
        key: str,
        value: dict,
        ttl: int = settings.CACHE_TTL_SECONDS
    ) -> bool:
        """Define valor no cache"""
        try:
            client = get_redis()
            await client.setex(key, ttl, json.dumps(value))
            return True
        except Exception as e:
            logger.error(f"Erro ao salvar cache: {e}")
            return False
    
    @staticmethod
    async def delete(key: str) -> bool:
        """Remove valor do cache"""
        try:
            client = get_redis()
            await client.delete(key)
            return True
        except Exception as e:
            logger.error(f"Erro ao deletar cache: {e}")
            return False
    
    @staticmethod
    async def delete_pattern(pattern: str) -> bool:
        """Remove valores do cache por padrão"""
        try:
            client = get_redis()
            keys = await client.keys(pattern)
            if keys:
                await client.delete(*keys)
            return True
        except Exception as e:
            logger.error(f"Erro ao deletar cache por padrão: {e}")
            return False
    
    @staticmethod
    async def exists(key: str) -> bool:
        """Verifica se chave existe no cache"""
        try:
            client = get_redis()
            return await client.exists(key) > 0
        except Exception as e:
            logger.error(f"Erro ao verificar cache: {e}")
            return False

