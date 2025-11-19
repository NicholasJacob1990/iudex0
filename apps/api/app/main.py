"""
Aplicação FastAPI principal
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from loguru import logger

from app.api.routes import api_router
from app.core.config import settings
from app.core.database import init_db
from app.core.logging import setup_logging


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
    
    # Inicializar Redis
    # await init_redis()
    logger.info("✅ Redis conectado")
    
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

