"""
Configuração do banco de dados com SQLAlchemy
"""

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from loguru import logger

from app.core.config import settings

# Engine assíncrono
# Configuração específica para SQLite vs PostgreSQL
engine_kwargs = {
    "echo": settings.DEBUG,
    "pool_pre_ping": True,
}

# SQLite não suporta pool_size/max_overflow da mesma forma
if "sqlite" not in settings.DATABASE_URL:
    engine_kwargs["pool_size"] = settings.DATABASE_POOL_SIZE
    engine_kwargs["max_overflow"] = settings.DATABASE_MAX_OVERFLOW

engine = create_async_engine(
    settings.DATABASE_URL,
    **engine_kwargs
)

# Session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# Base para os modelos
Base = declarative_base()


async def init_db() -> None:
    """
    Inicializa o banco de dados
    """
    try:
        # Importar modelos para registrar no Base.metadata
        # Isso garante que as tabelas sejam criadas
        from app.models.user import User
        from app.models.chat import Chat, ChatMessage
        from app.models.document import Document
        from app.models.library import LibraryItem
        
        # Testar conexão e criar tabelas
        async with engine.begin() as conn:
            # Cria tabelas se não existirem (útil para desenvolvimento/teste sem Alembic)
            await conn.run_sync(Base.metadata.create_all)
            
        logger.info("Conexão com banco de dados estabelecida e tabelas verificadas")
    except Exception as e:
        logger.error(f"Erro ao conectar ao banco de dados: {e}")
        raise


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency para obter sessão do banco de dados
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
