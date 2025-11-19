"""
Router principal da API
"""

from fastapi import APIRouter

from app.api.endpoints import auth, users, documents, chats, library, templates

api_router = APIRouter()

# Incluir rotas
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(documents.router, prefix="/documents", tags=["documents"])
api_router.include_router(templates.router, prefix="/templates", tags=["templates"])
api_router.include_router(chats.router, prefix="/chats", tags=["chats"])
api_router.include_router(library.router, prefix="/library", tags=["library"])

