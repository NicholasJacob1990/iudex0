"""
Aplicacao FastAPI principal
"""

from contextlib import asynccontextmanager
import asyncio
import os
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from loguru import logger

from app.api.routes import api_router
from app.core.config import settings
from app.core.database import init_db
from app.core.logging import setup_logging
from app.services.api_call_tracker import set_background_loop


async def _preload_rag_models() -> None:
    """
    Preload RAG models on startup to eliminate cold start latency.

    Configurable via environment variables:
    - RAG_PRELOAD_RERANKER: Set to "true" to preload reranker model
    - RAG_PRELOAD_EMBEDDINGS: Set to "true" to preload embeddings cache

    Models are loaded in a thread pool to avoid blocking the event loop.
    """
    loop = asyncio.get_running_loop()

    # Preload reranker model
    if os.getenv("RAG_PRELOAD_RERANKER", "false").lower() == "true":
        try:
            from app.services.rag.core.reranker import CrossEncoderReranker

            logger.info("Preloading reranker model...")
            load_time = await loop.run_in_executor(
                None, CrossEncoderReranker.preload
            )
            logger.info(f"Reranker preloaded in {load_time:.2f}s")
        except ImportError as e:
            logger.warning(f"Reranker module not available: {e}")
        except Exception as e:
            logger.error(f"Failed to preload reranker: {e}")

    # Preload embeddings cache with common legal queries
    if os.getenv("RAG_PRELOAD_EMBEDDINGS", "false").lower() == "true":
        try:
            from app.services.rag.core.embeddings import preload_embeddings_cache

            logger.info("Preloading embeddings cache...")
            load_time, count = await loop.run_in_executor(
                None, preload_embeddings_cache
            )
            logger.info(f"Embeddings cache preloaded: {count} queries in {load_time:.2f}s")
        except ImportError as e:
            logger.warning(f"Embeddings module not available: {e}")
        except Exception as e:
            logger.error(f"Failed to preload embeddings cache: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """
    Gerencia o ciclo de vida da aplicação
    """
    # Startup
    logger.info("🚀 Iniciando Iudex API...")
    
    # Configurar logging
    setup_logging()
    
    # Inicializar banco de dados
    await init_db()
    logger.info("✅ Banco de dados inicializado")

    # Registrar loop principal para persistencia de uso de API
    set_background_loop(asyncio.get_running_loop())

    # Inicializar Redis
    # await init_redis()
    logger.info("Redis conectado")

    # Preload RAG models to eliminate cold start latency
    await _preload_rag_models()
    
    logger.info(f"✅ API disponível em: http://{settings.HOST}:{settings.PORT}")
    logger.info(f"📝 Documentação: http://{settings.HOST}:{settings.PORT}/docs")
    
    yield
    
    # Shutdown
    logger.info("🛑 Encerrando Iudex API...")


# Criar aplicação FastAPI
app = FastAPI(
    title="Iudex API",
    description="Backend API para plataforma jurídica com IA multi-agente",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Compressão
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Arquivos estáticos (podcasts, diagramas)
storage_root = Path(settings.LOCAL_STORAGE_PATH)
podcasts_dir = storage_root / "podcasts"
diagrams_dir = storage_root / "diagrams"
podcasts_dir.mkdir(parents=True, exist_ok=True)
diagrams_dir.mkdir(parents=True, exist_ok=True)
app.mount("/podcasts", StaticFiles(directory=str(podcasts_dir)), name="podcasts")
app.mount("/diagrams", StaticFiles(directory=str(diagrams_dir)), name="diagrams")

# Incluir rotas
app.include_router(api_router, prefix="/api")


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "ok",
        "version": "0.1.0",
        "environment": settings.ENVIRONMENT,
    }


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Iudex API - Plataforma Jurídica com IA Multi-Agente",
        "version": "0.1.0",
        "docs": "/docs",
    }
