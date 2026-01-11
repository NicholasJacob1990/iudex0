"""
Endpoints de biblioteca
"""

import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.library import LibraryItem, Folder, Librarian, LibraryItemType
from app.models.user import User
from app.utils.token_counter import estimate_tokens
from app.schemas.library import (
    LibraryItemCreate,
    LibraryItemResponse,
    FolderCreate,
    FolderResponse,
    LibrarianCreate,
    LibrarianResponse,
    ShareRequest,
    ShareResponse,
    SharedResourcesResponse,
    AcceptShareRequest,
    RejectShareRequest,
    RevokeShareRequest,
)

router = APIRouter()


@router.get("/", response_model=dict)
async def list_items_root(
    skip: int = 0,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    item_type: Optional[str] = None,
    search: Optional[str] = None,
):
    """
    Compatibilidade com cliente web: lista itens da biblioteca.
    """
    query = select(LibraryItem).where(LibraryItem.user_id == current_user.id)
    if item_type:
        query = query.where(LibraryItem.type == LibraryItemType(item_type))
        
    if search:
        query = query.where(LibraryItem.name.ilike(f"%{search}%"))
        
    result = await db.execute(query.offset(skip).limit(limit))
    items = result.scalars().all()
    return {"items": items, "total": len(items)}


@router.post("/", response_model=LibraryItemResponse, status_code=status.HTTP_201_CREATED)
async def create_item_root(
    payload: LibraryItemCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Compatibilidade com cliente web: cria item da biblioteca.
    """
    item_type = LibraryItemType(payload.type)
    
    # Calcular tokens baseado no tipo e conteúdo disponível
    token_count = payload.token_count
    if token_count == 0 and payload.description:
        # Estimar tokens da descrição se não foi fornecido
        token_count = estimate_tokens(payload.description)
    
    item = LibraryItem(
        id=str(uuid.uuid4()),
        user_id=current_user["id"],
        type=item_type,
        name=payload.name,
        description=payload.description,
        tags=payload.tags,
        folder_id=payload.folder_id,
        resource_id=payload.resource_id,
        token_count=token_count,
        is_shared=False,
        shared_with=[],
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item_root(
    item_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Remover item da biblioteca (rota simplificada).
    """
    result = await db.execute(
        select(LibraryItem).where(LibraryItem.id == item_id, LibraryItem.user_id == current_user.id)
    )
    item = result.scalars().first()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item não encontrado")
    await db.delete(item)
    await db.commit()
    return {}


@router.get("/items")
async def list_library_items(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Listar itens da biblioteca
    """
    result = await db.execute(
        select(LibraryItem).where(LibraryItem.user_id == current_user.id).order_by(LibraryItem.created_at.desc())
    )
    items = result.scalars().all()
    return {"items": items, "total": len(items)}


@router.post("/items", response_model=LibraryItemResponse, status_code=status.HTTP_201_CREATED)
async def create_library_item(
    payload: LibraryItemCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Criar item na biblioteca
    """
    item_type = LibraryItemType(payload.type)
    
    # Calcular tokens baseado no tipo e conteúdo disponível
    token_count = payload.token_count
    if token_count == 0 and payload.description:
        # Estimar tokens da descrição se não foi fornecido
        token_count = estimate_tokens(payload.description)
    
    item = LibraryItem(
        id=str(uuid.uuid4()),
        user_id=current_user["id"],
        type=item_type,
        name=payload.name,
        description=payload.description,
        tags=payload.tags,
        folder_id=payload.folder_id,
        resource_id=payload.resource_id,
        token_count=token_count,
        is_shared=False,
        shared_with=[],
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


@router.get("/folders")
async def list_folders(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Listar pastas
    """
    result = await db.execute(
        select(Folder).where(Folder.user_id == current_user.id).order_by(Folder.created_at.desc())
    )
    folders = result.scalars().all()
    return {"folders": folders, "total": len(folders)}


@router.post("/folders", response_model=FolderResponse, status_code=status.HTTP_201_CREATED)
async def create_folder(
    payload: FolderCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Criar pasta
    """
    folder_type = LibraryItemType(payload.type)
    folder = Folder(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        name=payload.name,
        description=payload.description,
        parent_id=payload.parent_id,
        type=folder_type,
        icon=payload.icon,
        color=payload.color,
    )
    db.add(folder)
    await db.commit()
    await db.refresh(folder)
    return folder


@router.get("/librarians")
async def list_librarians(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Listar bibliotecários (assistentes personalizados)
    """
    result = await db.execute(
        select(Librarian).where(Librarian.user_id == current_user.id).order_by(Librarian.created_at.desc())
    )
    librarians = result.scalars().all()
    return {"librarians": librarians, "total": len(librarians)}


@router.post("/librarians", response_model=LibrarianResponse, status_code=status.HTTP_201_CREATED)
async def create_librarian(
    payload: LibrarianCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Criar bibliotecário
    """
    librarian = Librarian(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        name=payload.name,
        description=payload.description,
        icon=payload.icon,
        resources=payload.resources,
        is_shared=False,
        shared_with=[],
    )
    db.add(librarian)
    await db.commit()
    await db.refresh(librarian)
    return librarian


@router.post("/librarians/{librarian_id}/activate")
async def activate_librarian(
    librarian_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Ativar bibliotecário - carrega todos os recursos associados
    """
    from app.models.document import Document
    
    # Buscar bibliotecário
    result = await db.execute(
        select(Librarian).where(
            Librarian.id == librarian_id,
            Librarian.user_id == current_user.id
        )
    )
    librarian = result.scalars().first()
    
    if not librarian:
        raise HTTPException(status_code=404, detail="Bibliotecário não encontrado")
    
    # Carregar todos os recursos associados
    loaded_resources = []
    
    for resource_id in librarian.resources:
        # Tentar como Library Item
        lib_result = await db.execute(
            select(LibraryItem).where(LibraryItem.id == resource_id)
        )
        lib_item = lib_result.scalars().first()
        
        if lib_item:
            # Buscar o documento/modelo real
            if lib_item.type.value in ["DOCUMENT", "MODEL"]:
                doc_result = await db.execute(
                    select(Document).where(Document.id == lib_item.resource_id)
                )
                doc = doc_result.scalars().first()
                
                if doc:
                    loaded_resources.append({
                        "id": lib_item.id,
                        "type": lib_item.type.value,
                        "name": lib_item.name,
                        "description": lib_item.description,
                        "resource_id": lib_item.resource_id,
                        "token_count": lib_item.token_count,
                        "content": doc.extracted_text or doc.content,
                        "metadata": doc.doc_metadata
                    })
            else:
                # Outros tipos de recursos
                loaded_resources.append({
                    "id": lib_item.id,
                    "type": lib_item.type.value,
                    "name": lib_item.name,
                    "description": lib_item.description,
                    "resource_id": lib_item.resource_id,
                    "token_count": lib_item.token_count,
                })
    
    return {
        "librarian_id": librarian_id,
        "librarian_name": librarian.name,
        "description": librarian.description,
        "total_resources": len(loaded_resources),
        "total_tokens": sum(r.get("token_count", 0) for r in loaded_resources),
        "resources": loaded_resources,
        "message": f"Bibliotecário '{librarian.name}' ativado com {len(loaded_resources)} recurso(s)"
    }


@router.post("/share")
async def share_resource(
    request: ShareRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Compartilhar recurso com usuários
    """
    from app.models.library import Share, SharePermission as SharePermEnum, ShareStatus
    
    # 1. Verificar se o recurso existe e pertence ao usuário
    if request.resource_type in ["library_item", "document", "model", "precedent", "prompt"]:
        result = await db.execute(
            select(LibraryItem).where(
                LibraryItem.id == request.resource_id,
                LibraryItem.user_id == current_user.id
            )
        )
        resource = result.scalars().first()
    elif request.resource_type == "librarian":
        result = await db.execute(
            select(Librarian).where(
                Librarian.id == request.resource_id,
                Librarian.user_id == current_user.id
            )
        )
        resource = result.scalars().first()
    elif request.resource_type == "folder":
        result = await db.execute(
            select(Folder).where(
                Folder.id == request.resource_id,
                Folder.user_id == current_user.id
            )
        )
        resource = result.scalars().first()
    else:
        raise HTTPException(status_code=400, detail="Tipo de recurso inválido")
    
    if not resource:
        raise HTTPException(status_code=404, detail="Recurso não encontrado ou você não tem permissão")
    
    # 2. Criar compartilhamentos para cada usuário
    shared_with_users = []
    for user_perm in request.users:
        # Verificar se usuário existe
        user_result = await db.execute(
            select(User).where(User.email == user_perm.email)
        )
        target_user = user_result.scalars().first()
        
        # Verificar se já existe compartilhamento
        existing_share = await db.execute(
            select(Share).where(
                Share.resource_id == request.resource_id,
                Share.resource_type == request.resource_type,
                (Share.shared_with_email == user_perm.email) | (
                    Share.shared_with_user_id == (target_user.id if target_user else None)
                )
            )
        )
        if existing_share.scalars().first():
            continue  # Já compartilhado
        
        # Criar compartilhamento
        share = Share(
            id=str(uuid.uuid4()),
            resource_type=request.resource_type,
            resource_id=request.resource_id,
            owner_id=current_user.id,
            shared_with_user_id=target_user.id if target_user else None,
            shared_with_email=user_perm.email,
            permission=SharePermEnum.VIEW if user_perm.permission == "view" else SharePermEnum.EDIT,
            status=ShareStatus.PENDING
        )
        db.add(share)
        shared_with_users.append({
            "email": user_perm.email,
            "permission": user_perm.permission,
            "user_exists": target_user is not None
        })
    
    # 3. Atualizar flag is_shared no recurso
    resource.is_shared = True
    
    await db.commit()
    
    return ShareResponse(
        resource_id=request.resource_id,
        resource_type=request.resource_type,
        shared_with_users=shared_with_users,
        shared_with_groups=[],  # TODO: Implementar grupos
        success=True,
        message=f"Recurso compartilhado com {len(shared_with_users)} usuário(s)"
    )


@router.get("/shares")
async def list_shares(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Listar compartilhamentos (compartilhados por mim, comigo, e pendentes)
    """
    from app.models.library import Share, ShareStatus
    
    # Compartilhamentos que EU criei
    result_by_me = await db.execute(
        select(Share).where(Share.owner_id == current_user.id)
    )
    shares_by_me = result_by_me.scalars().all()
    
    # Compartilhamentos recebidos
    result_with_me = await db.execute(
        select(Share).where(
            (Share.shared_with_user_id == current_user.id) &
            (Share.status == ShareStatus.ACCEPTED)
        )
    )
    shares_with_me = result_with_me.scalars().all()
    
    # Compartilhamentos pendentes
    result_pending = await db.execute(
        select(Share).where(
            (Share.shared_with_user_id == current_user.id) &
            (Share.status == ShareStatus.PENDING)
        )
    )
    shares_pending = result_pending.scalars().all()
    
    # Converter para dicts com informações adicionais
    async def enrich_share(share):
        # Buscar informações do proprietário
        owner_result = await db.execute(
            select(User).where(User.id == share.owner_id)
        )
        owner = owner_result.scalars().first()
        
        # Buscar nome do recurso
        resource_name = "Unknown"
        if share.resource_type in ["library_item", "document", "model", "precedent", "prompt"]:
            res = await db.execute(select(LibraryItem).where(LibraryItem.id == share.resource_id))
            resource = res.scalars().first()
            if resource:
                resource_name = resource.name
        elif share.resource_type == "librarian":
            res = await db.execute(select(Librarian).where(Librarian.id == share.resource_id))
            resource = res.scalars().first()
            if resource:
                resource_name = resource.name
        
        return {
            "id": share.id,
            "resource_type": share.resource_type,
            "resource_id": share.resource_id,
            "resource_name": resource_name,
            "owner_email": owner.email if owner else "Unknown",
            "shared_with_email": share.shared_with_email,
            "permission": share.permission.value,
            "status": share.status.value,
            "created_at": share.created_at.isoformat()
        }
    
    shared_by_me_enriched = [await enrich_share(s) for s in shares_by_me]
    shared_with_me_enriched = [await enrich_share(s) for s in shares_with_me]
    pending_enriched = [await enrich_share(s) for s in shares_pending]
    
    return SharedResourcesResponse(
        shared_by_me=shared_by_me_enriched,
        shared_with_me=shared_with_me_enriched,
        pending=pending_enriched
    )


@router.post("/shares/accept")
async def accept_share(
    request: AcceptShareRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Aceitar compartilhamento pendente
    """
    from app.models.library import Share, ShareStatus
    from datetime import datetime
    
    result = await db.execute(
        select(Share).where(
            Share.id == request.share_id,
            Share.shared_with_user_id == current_user["id"],
            Share.status == ShareStatus.PENDING
        )
    )
    share = result.scalars().first()
    
    if not share:
        raise HTTPException(status_code=404, detail="Compartilhamento não encontrado ou já processado")
    
    share.status = ShareStatus.ACCEPTED
    share.accepted_at = datetime.utcnow()
    
    await db.commit()
    
    return {"success": True, "message": "Compartilhamento aceito"}


@router.post("/shares/reject")
async def reject_share(
    request: RejectShareRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Rejeitar compartilhamento pendente
    """
    from app.models.library import Share, ShareStatus
    
    result = await db.execute(
        select(Share).where(
            Share.id == request.share_id,
            Share.shared_with_user_id == current_user.id,
            Share.status == ShareStatus.PENDING
        )
    )
    share = result.scalars().first()
    
    if not share:
        raise HTTPException(status_code=404, detail="Compartilhamento não encontrado ou já processado")
    
    share.status = ShareStatus.REJECTED
    
    await db.commit()
    
    return {"success": True, "message": "Compartilhamento rejeitado"}


@router.post("/shares/revoke")
async def revoke_share(
    request: RevokeShareRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Revogar compartilhamento (apenas o proprietário pode fazer)
    """
    from app.models.library import Share
    
    for email in request.user_emails:
        result = await db.execute(
            select(Share).where(
                Share.resource_id == request.resource_id,
                Share.resource_type == request.resource_type,
                Share.owner_id == current_user.id,
                Share.shared_with_email == email
            )
        )
        share = result.scalars().first()
        if share:
            await db.delete(share)
    
    await db.commit()
    
    return {"success": True, "message": f"Compartilhamento revogado para {len(request.user_emails)} usuário(s)"}

