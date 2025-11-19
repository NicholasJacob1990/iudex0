"""
Configuração do banco de dados com SQLAlchemy
"""

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from loguru import logger

from app.core.config import settings

# Engine assíncrono
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    pool_pre_ping=True,
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
        # from app.models.document import Document # Se existir
        
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
