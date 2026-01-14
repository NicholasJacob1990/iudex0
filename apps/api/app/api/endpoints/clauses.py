from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List, Optional
from pydantic import BaseModel, Field
import uuid

from app.core.security import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.models.library import LibraryItem, LibraryItemType
from app.utils.token_counter import estimate_tokens

router = APIRouter()


class ClauseCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    content: str = Field(..., min_length=1)
    document_type: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


def _extract_doc_type(tags: List[str]) -> Optional[str]:
    for tag in tags or []:
        if tag.startswith("doc_type:"):
            return tag.split(":", 1)[1]
    return None


@router.get("/", response_model=dict)
async def list_clauses(
    skip: int = 0,
    limit: int = 50,
    search: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    query = select(LibraryItem).where(
        LibraryItem.user_id == current_user.id,
        LibraryItem.type == LibraryItemType.CLAUSE
    )
    if search:
        query = query.where(LibraryItem.name.ilike(f"%{search}%"))

    result = await db.execute(query.offset(skip).limit(limit))
    items = result.scalars().all()

    clauses = [
        {
            "id": item.id,
            "name": item.name,
            "title": item.name,
            "content": item.description,
            "document_type": _extract_doc_type(item.tags),
            "tags": item.tags,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }
        for item in items
    ]
    return {"clauses": clauses, "total": len(clauses)}


@router.post("/", status_code=status.HTTP_201_CREATED, response_model=dict)
async def create_clause(
    payload: ClauseCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    tags = list(payload.tags or [])
    if payload.document_type:
        tags = [t for t in tags if not t.startswith("doc_type:")]
        tags.append(f"doc_type:{payload.document_type}")

    item = LibraryItem(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        type=LibraryItemType.CLAUSE,
        name=payload.name,
        description=payload.content,
        tags=tags,
        folder_id=None,
        resource_id=str(uuid.uuid4()),
        token_count=estimate_tokens(payload.content)
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)

    return {
        "id": item.id,
        "name": item.name,
        "title": item.name,
        "content": item.description,
        "document_type": _extract_doc_type(item.tags),
        "tags": item.tags,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


@router.delete("/{clause_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_clause(
    clause_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(LibraryItem).where(
            LibraryItem.id == clause_id,
            LibraryItem.user_id == current_user.id,
            LibraryItem.type == LibraryItemType.CLAUSE
        )
    )
    item = result.scalars().first()
    if not item:
        raise HTTPException(status_code=404, detail="Clausula nao encontrada")
    await db.delete(item)
    await db.commit()
    return {}
