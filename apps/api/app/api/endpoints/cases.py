from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.case import CaseCreate, CaseResponse, CaseUpdate
from app.services.case_service import CaseService

router = APIRouter()

@router.get("/", response_model=List[CaseResponse])
async def get_cases(
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Listar casos do usuário"""
    service = CaseService(db)
    return await service.get_cases(current_user.id, skip, limit)

@router.post("/", response_model=CaseResponse)
async def create_case(
    case_in: CaseCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Criar novo caso"""
    service = CaseService(db)
    return await service.create_case(case_in, current_user.id)

@router.get("/{case_id}", response_model=CaseResponse)
async def get_case(
    case_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Obter detalhes de um caso"""
    service = CaseService(db)
    case = await service.get_case(case_id, current_user.id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return case

@router.put("/{case_id}", response_model=CaseResponse)
async def update_case(
    case_id: str,
    case_in: CaseUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Atualizar caso"""
    service = CaseService(db)
    case = await service.update_case(case_id, case_in, current_user.id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return case

@router.delete("/{case_id}")
async def delete_case(
    case_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Arquivar/Deletar caso"""
    service = CaseService(db)
    success = await service.delete_case(case_id, current_user.id)
    if not success:
        raise HTTPException(status_code=404, detail="Case not found")
    return {"ok": True}
