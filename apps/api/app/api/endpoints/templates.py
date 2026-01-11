from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Body, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from app.core.security import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.models.library import LibraryItem, LibraryItemType
from app.services.template_service import template_service
from app.utils.token_counter import estimate_tokens
from loguru import logger
import shutil
import os
import uuid
from pathlib import Path
from app.core.config import settings

router = APIRouter()


class TemplateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    content_template: Optional[str] = None
    document_type: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


def _extract_doc_type(tags: List[str]) -> Optional[str]:
    for tag in tags or []:
        if tag.startswith("doc_type:"):
            return tag.split(":", 1)[1]
    return None


@router.get("/", response_model=dict)
async def list_templates(
    skip: int = 0,
    limit: int = 50,
    search: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    query = select(LibraryItem).where(
        LibraryItem.user_id == current_user.id,
        LibraryItem.type == LibraryItemType.MODEL
    )
    if search:
        query = query.where(LibraryItem.name.ilike(f"%{search}%"))

    result = await db.execute(query.offset(skip).limit(limit))
    items = result.scalars().all()

    templates = [
        {
            "id": item.id,
            "name": item.name,
            "title": item.name,
            "description": item.description,
            "document_type": _extract_doc_type(item.tags),
            "tags": item.tags,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }
        for item in items
    ]
    return {"templates": templates, "total": len(templates)}


@router.post("/", status_code=status.HTTP_201_CREATED, response_model=dict)
async def create_template(
    payload: TemplateCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    content = payload.description or payload.content_template
    if not content:
        raise HTTPException(status_code=400, detail="Descrição do template é obrigatória")

    tags = list(payload.tags or [])
    if payload.document_type:
        tags = [t for t in tags if not t.startswith("doc_type:")]
        tags.append(f"doc_type:{payload.document_type}")

    item = LibraryItem(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        type=LibraryItemType.MODEL,
        name=payload.name,
        description=content,
        tags=tags,
        folder_id=None,
        resource_id=str(uuid.uuid4()),
        token_count=estimate_tokens(content)
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)

    return {
        "id": item.id,
        "name": item.name,
        "title": item.name,
        "description": item.description,
        "document_type": _extract_doc_type(item.tags),
        "tags": item.tags,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(LibraryItem).where(
            LibraryItem.id == template_id,
            LibraryItem.user_id == current_user.id,
            LibraryItem.type == LibraryItemType.MODEL
        )
    )
    item = result.scalars().first()
    if not item:
        raise HTTPException(status_code=404, detail="Template não encontrado")
    await db.delete(item)
    await db.commit()
    return {}

@router.post("/extract-variables")
async def extract_template_variables(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
):
    """
    Extrai variáveis de um arquivo DOCX template
    """
    temp_path = Path(settings.LOCAL_STORAGE_PATH) / "temp" / f"temp_{uuid.uuid4()}.docx"
    temp_path.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        variables = await template_service.extract_variables(str(temp_path))
        
        return {
            "filename": file.filename,
            "variables": variables,
            "count": len(variables)
        }
        
    except Exception as e:
        logger.error(f"Erro ao extrair variáveis: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if temp_path.exists():
            os.remove(temp_path)

@router.post("/apply")
async def apply_template(
    file: UploadFile = File(...),
    variables: str = Form(...),  # JSON string
    current_user: User = Depends(get_current_user)
):
    """
    Aplica variáveis em um template DOCX e retorna o arquivo gerado
    """
    import json
    
    temp_path = Path(settings.LOCAL_STORAGE_PATH) / "temp" / f"temp_{uuid.uuid4()}.docx"
    temp_path.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        # Salvar arquivo temporário
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # Parse variáveis
        try:
            vars_dict = json.loads(variables)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Variáveis inválidas (JSON esperado)")
            
        # Aplicar template
        result = await template_service.apply_template(
            template_path=str(temp_path),
            variables=vars_dict
        )
        
        if not result["success"]:
            raise HTTPException(status_code=500, detail=result["error"])
            
        # Retornar informações do arquivo gerado
        return {
            "success": True,
            "generated_file": result["filename"],
            "download_url": f"/api/documents/download/generated/{result['filename']}",
            "replacements": result["replacements"]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao aplicar template: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if temp_path.exists():
            os.remove(temp_path)
