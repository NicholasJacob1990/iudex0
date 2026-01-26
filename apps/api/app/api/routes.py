"""
Router principal da API
"""

from fastapi import APIRouter

from app.api.endpoints import auth, users, documents, chats, library, templates, clauses, knowledge, transcription, cases, chat_integration, jobs, chat, audit, quality_control, rag, advanced, djen, config, billing, admin_rag, health, mcp, tribunais, webhooks, graph

api_router = APIRouter()

# Health check routes (no prefix, accessible at /api/health/*)
api_router.include_router(health.router, tags=["health"])

# Incluir rotas
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(config.router, prefix="/config", tags=["config"])
api_router.include_router(billing.router, prefix="/billing", tags=["billing"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(cases.router, prefix="/cases", tags=["cases"])
api_router.include_router(documents.router, prefix="/documents", tags=["documents"])
api_router.include_router(templates.router, prefix="/templates", tags=["templates"])
api_router.include_router(clauses.router, prefix="/clauses", tags=["clauses"])
api_router.include_router(chats.router, prefix="/chats", tags=["chats"])
api_router.include_router(chat_integration.router, prefix="/chat", tags=["chat-docs"])
api_router.include_router(chat.router, prefix="/multi-chat", tags=["multi-model-chat"])
api_router.include_router(library.router, prefix="/library", tags=["library"])
api_router.include_router(knowledge.router, prefix="/knowledge", tags=["knowledge"])
api_router.include_router(transcription.router, prefix="/transcription", tags=["transcription"])
api_router.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
api_router.include_router(audit.router, prefix="/audit", tags=["audit"])
api_router.include_router(quality_control.router, prefix="/quality", tags=["quality-control"])
api_router.include_router(rag.router, prefix="/rag", tags=["rag"])
api_router.include_router(admin_rag.router, tags=["admin-rag"])
api_router.include_router(advanced.router, prefix="/advanced", tags=["advanced"])
api_router.include_router(djen.router, prefix="/djen", tags=["djen"])
api_router.include_router(mcp.router, prefix="/mcp", tags=["mcp"])
api_router.include_router(tribunais.router, prefix="/tribunais", tags=["tribunais"])
api_router.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])
api_router.include_router(graph.router, prefix="/graph", tags=["graph"])
