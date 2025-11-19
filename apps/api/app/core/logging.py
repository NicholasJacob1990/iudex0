"""
Configuração de logging com Loguru
"""

import sys
from loguru import logger

from app.core.config import settings


def setup_logging() -> None:
    """
    Configura o sistema de logging
    """
    # Remover handler padrão
    logger.remove()
    
    # Formato para desenvolvimento
    if settings.is_development:
        logger.add(
            sys.stdout,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
            level=settings.LOG_LEVEL,
            colorize=True,
        )
    # Formato para produção (JSON)
    else:
        logger.add(
            sys.stdout,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
            level=settings.LOG_LEVEL,
            serialize=settings.LOG_FORMAT == "json",
        )
    
    # Adicionar arquivo de log em produção
    if settings.is_production:
        logger.add(
            "logs/iudex-api.log",
            rotation="500 MB",
            retention="10 days",
            compression="zip",
            level="INFO",
        )
        
        logger.add(
            "logs/iudex-api-errors.log",
            rotation="500 MB",
            retention="30 days",
            compression="zip",
            level="ERROR",
        )
    
    logger.info(f"Logging configurado - Nível: {settings.LOG_LEVEL}")

