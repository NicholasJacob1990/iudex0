"""
Endpoints de biblioteca
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user

router = APIRouter()


@router.get("/items")
async def list_library_items(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Listar itens da biblioteca
    """
    # TODO: Buscar itens
    return {"items": [], "total": 0}


@router.post("/items")
async def create_library_item(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Criar item na biblioteca
    """
    # TODO: Criar item
    return {"item": {}}


@router.get("/folders")
async def list_folders(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Listar pastas
    """
    # TODO: Buscar pastas
    return {"folders": [], "total": 0}


@router.post("/folders")
async def create_folder(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Criar pasta
    """
    # TODO: Criar pasta
    return {"folder": {}}


@router.get("/librarians")
async def list_librarians(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Listar bibliotecários (assistentes personalizados)
    """
    # TODO: Buscar bibliotecários
    return {"librarians": [], "total": 0}


@router.post("/librarians")
async def create_librarian(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Criar bibliotecário
    """
    # TODO: Criar bibliotecário
    return {"librarian": {}}


@router.post("/share")
async def share_resource(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Compartilhar recurso
    """
    # TODO: Implementar compartilhamento
    return {"message": "Resource shared"}

