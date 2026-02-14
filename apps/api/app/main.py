"""
Aplicacao FastAPI principal
"""

from contextlib import asynccontextmanager
import asyncio
import os
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pathlib import Path
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from loguru import logger

from app.api.routes import api_router
from app.core.config import settings
from app.core.database import init_db
from app.core.logging import setup_logging
from app.middleware.cache_headers import CacheHeadersMiddleware
from app.services.api_call_tracker import set_background_loop


async def _preload_rag_models() -> None:
    """
    Preload RAG models and warm-start DB connections on startup.

    Configurable via environment variables:
    - RAG_PRELOAD_RERANKER: Set to "true" to preload reranker model (default: true)
    - RAG_PRELOAD_EMBEDDINGS: Set to "true" to preload embeddings cache (default: true)
    - RAG_WARMUP_ON_STARTUP: Set to "true" to ping DB connections (default: true)

    Models are loaded in a thread pool to avoid blocking the event loop.
    """
    loop = asyncio.get_running_loop()

    # Preload reranker model
    if os.getenv("RAG_PRELOAD_RERANKER", "true").lower() == "true":
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
    if os.getenv("RAG_PRELOAD_EMBEDDINGS", "true").lower() == "true":
        try:
            from app.services.rag.core.embeddings import preload_embeddings_cache

            logger.info("Preloading embeddings cache...")
            load_time, count = await asyncio.wait_for(
                loop.run_in_executor(None, preload_embeddings_cache),
                timeout=30.0,
            )
            logger.info(f"Embeddings cache preloaded: {count} queries in {load_time:.2f}s")
        except asyncio.TimeoutError:
            logger.warning("Embeddings preload timed out after 30s (quota issue?). Skipping.")
        except ImportError as e:
            logger.warning(f"Embeddings module not available: {e}")
        except Exception as e:
            logger.error(f"Failed to preload embeddings cache: {e}")

    # Warm-start: ping DB connections to establish connection pools early
    if os.getenv("RAG_WARMUP_ON_STARTUP", "true").lower() == "true":
        logger.info("Warming up RAG database connections...")

        async def _ping_db(name: str, fn) -> None:
            try:
                await asyncio.wait_for(
                    loop.run_in_executor(None, fn),
                    timeout=5.0,
                )
                logger.info(f"  {name} connected")
            except asyncio.TimeoutError:
                logger.warning(f"  {name} warmup timeout (5s)")
            except Exception as e:
                logger.warning(f"  {name} unavailable: {e}")

        ping_tasks = []

        # Qdrant
        try:
            from qdrant_client import QdrantClient
            qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
            _qclient = QdrantClient(url=qdrant_url, timeout=5)
            ping_tasks.append(_ping_db("Qdrant", _qclient.get_collections))
        except ImportError:
            pass

        # OpenSearch
        try:
            from opensearchpy import OpenSearch
            os_host = os.getenv("OPENSEARCH_HOST", "localhost")
            os_port = int(os.getenv("OPENSEARCH_PORT", "9200"))
            _osclient = OpenSearch(
                hosts=[{"host": os_host, "port": os_port}],
                timeout=5,
            )
            ping_tasks.append(_ping_db("OpenSearch", _osclient.info))
        except ImportError:
            pass

        # Neo4j
        try:
            from neo4j import GraphDatabase
            neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
            neo4j_user = os.getenv("NEO4J_USER", "neo4j")
            neo4j_pass = os.getenv("NEO4J_PASSWORD", "")
            if neo4j_pass:
                _neo4j = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_pass))
                ping_tasks.append(_ping_db("Neo4j", _neo4j.verify_connectivity))
        except ImportError:
            pass

        if ping_tasks:
            await asyncio.gather(*ping_tasks, return_exceptions=True)
        logger.info("RAG warmup complete")


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

    # Inicializar AI Services (tools unificadas, registry, handlers)
    try:
        from app.services.ai.shared.startup import init_ai_services_async, get_tools_summary
        await init_ai_services_async()
        tools_info = get_tools_summary()
        logger.info(f"✅ AI Services: {tools_info['total_tools']} tools registradas")
    except Exception as e:
        logger.warning(f"AI Services parcialmente inicializados: {e}")

    logger.info(f"✅ API disponível em: http://{settings.HOST}:{settings.PORT}")
    logger.info(f"📝 Documentação: http://{settings.HOST}:{settings.PORT}/docs")
    
    yield
    
    # Shutdown
    logger.info("🛑 Encerrando Iudex API...")

    # Finalizar AI Services
    try:
        from app.services.ai.shared.startup import shutdown_ai_services
        shutdown_ai_services()
    except Exception:
        pass


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

# Validation error handler - log detalhado para debug 422
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.error(f"[422 VALIDATION ERROR] URL: {request.url}")
    logger.error(f"[422 VALIDATION ERROR] Method: {request.method}")
    logger.error(f"[422 VALIDATION ERROR] Errors: {exc.errors()}")
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors()},
    )

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Compressão (respostas > 1KB são comprimidas com gzip)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Cache headers (Cache-Control + ETag) para respostas da API
app.add_middleware(CacheHeadersMiddleware)

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
