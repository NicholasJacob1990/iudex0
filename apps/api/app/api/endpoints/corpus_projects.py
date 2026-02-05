"""
Corpus Projects API — Endpoints para projetos dinâmicos de corpus.

Permite criar, gerenciar e compartilhar projetos organizacionais
com suporte a Knowledge Base para consulta workspace-wide.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from loguru import logger
from sqlalchemy import and_, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.security import get_org_context, OrgContext
from app.models.corpus_project import (
    CorpusProject,
    CorpusProjectDocument,
    CorpusProjectShare,
    ProjectDocumentStatus,
    ProjectScope,
    ProjectSharePermission,
)
from app.models.document import Document
from app.models.user import User, UserRole
from app.schemas.corpus_project import (
    CreateFolderRequest,
    CorpusProjectCreate,
    CorpusProjectDocumentAdd,
    CorpusProjectDocumentAddResponse,
    CorpusProjectDocumentResponse,
    CorpusProjectListResponse,
    CorpusProjectResponse,
    CorpusProjectShareCreate,
    CorpusProjectShareResponse,
    CorpusProjectTransferRequest,
    CorpusProjectUpdate,
    FolderNode,
    FolderTreeResponse,
    MoveDocumentRequest,
)

router = APIRouter(tags=["corpus-projects"])


# =============================================================================
# Helpers
# =============================================================================


def _generate_collection_slug(name: str, user_id: str) -> str:
    """Gera slug único para coleção OpenSearch/Qdrant."""
    # Normalizar nome: lowercase, replace non-alphanum com underscore
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    # Limitar tamanho e adicionar sufixo único
    slug = slug[:60]
    short_id = uuid.uuid4().hex[:8]
    return f"proj_{slug}_{short_id}"


def _project_to_response(project: CorpusProject) -> CorpusProjectResponse:
    """Converte modelo para schema de resposta."""
    return CorpusProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        owner_id=project.owner_id,
        organization_id=project.organization_id,
        is_knowledge_base=project.is_knowledge_base,
        scope=project.scope.value if hasattr(project.scope, "value") else str(project.scope),
        collection_name=project.collection_name,
        max_documents=project.max_documents,
        retention_days=project.retention_days,
        document_count=project.document_count,
        chunk_count=project.chunk_count,
        storage_size_bytes=project.storage_size_bytes,
        last_indexed_at=project.last_indexed_at,
        metadata=project.metadata_,
        is_active=project.is_active,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


async def _get_project_or_404(
    project_id: str,
    db: AsyncSession,
    user_id: str,
    require_edit: bool = False,
) -> CorpusProject:
    """Busca projeto verificando permissão de acesso."""
    result = await db.execute(
        select(CorpusProject).where(
            CorpusProject.id == project_id,
            CorpusProject.is_active == True,  # noqa: E712
        )
    )
    project = result.scalar_one_or_none()

    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Projeto não encontrado.",
        )

    # Verificar acesso: owner, ou compartilhado
    if project.owner_id == user_id:
        return project

    # Verificar compartilhamento
    share_q = select(CorpusProjectShare).where(
        CorpusProjectShare.project_id == project_id,
        CorpusProjectShare.shared_with_user_id == user_id,
    )
    share_result = await db.execute(share_q)
    share = share_result.scalar_one_or_none()

    if share is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sem permissão para acessar este projeto.",
        )

    if require_edit and share.permission == ProjectSharePermission.VIEW.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sem permissão de edição neste projeto.",
        )

    return project


def _has_admin_permission(user: User) -> bool:
    """Verifica se o usuário tem permissões de administrador."""
    if hasattr(user, "role") and user.role == UserRole.ADMIN:
        return True
    if hasattr(user, "is_superuser") and user.is_superuser:
        return True
    return False


# =============================================================================
# CRUD — Projects
# =============================================================================


@router.post("", response_model=CorpusProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    request: CorpusProjectCreate,
    ctx: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
) -> CorpusProjectResponse:
    """
    Cria um novo projeto de corpus.

    Projetos são containers organizacionais para documentos RAG.
    Podem ser marcados como Knowledge Base para consulta workspace-wide.
    """
    try:
        collection_name = _generate_collection_slug(request.name, ctx.user.id)

        project = CorpusProject(
            id=str(uuid.uuid4()),
            name=request.name,
            description=request.description,
            owner_id=ctx.user.id,
            organization_id=ctx.organization_id if request.scope == "organization" else None,
            is_knowledge_base=request.is_knowledge_base,
            scope=ProjectScope(request.scope),
            collection_name=collection_name,
            max_documents=request.max_documents,
            retention_days=request.retention_days,
            metadata_=request.metadata,
        )

        db.add(project)
        await db.flush()
        await db.refresh(project)

        logger.info(
            f"Projeto de corpus criado: {project.id} ({project.name}) "
            f"por user={ctx.user.id}"
        )

        return _project_to_response(project)

    except Exception as e:
        logger.exception(f"Erro ao criar projeto de corpus: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falha ao criar projeto de corpus.",
        )


@router.get("", response_model=CorpusProjectListResponse)
async def list_projects(
    scope: Optional[str] = Query(None, description="Filtrar por escopo (personal, organization)"),
    is_knowledge_base: Optional[bool] = Query(None, description="Filtrar por Knowledge Base"),
    search: Optional[str] = Query(None, max_length=255, description="Buscar por nome"),
    page: int = Query(1, ge=1, description="Página"),
    per_page: int = Query(20, ge=1, le=100, description="Itens por página"),
    ctx: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
) -> CorpusProjectListResponse:
    """
    Lista projetos de corpus do usuário.

    Inclui projetos próprios e compartilhados. Suporta filtros por escopo,
    tipo Knowledge Base e busca por nome.
    """
    try:
        # Projetos próprios ou compartilhados com o usuário
        own_filter = and_(
            CorpusProject.owner_id == ctx.user.id,
            CorpusProject.is_active == True,  # noqa: E712
        )

        # Subquery para projetos compartilhados
        shared_ids_q = (
            select(CorpusProjectShare.project_id)
            .where(CorpusProjectShare.shared_with_user_id == ctx.user.id)
        )

        shared_filter = and_(
            CorpusProject.id.in_(shared_ids_q),
            CorpusProject.is_active == True,  # noqa: E712
        )

        # Projetos da organização (se KB)
        org_kb_filter = None
        if ctx.organization_id:
            org_kb_filter = and_(
                CorpusProject.organization_id == ctx.organization_id,
                CorpusProject.is_knowledge_base == True,  # noqa: E712
                CorpusProject.is_active == True,  # noqa: E712
            )

        if org_kb_filter is not None:
            base_filter = or_(own_filter, shared_filter, org_kb_filter)
        else:
            base_filter = or_(own_filter, shared_filter)

        filters = [base_filter]

        if scope:
            filters.append(CorpusProject.scope == ProjectScope(scope))
        if is_knowledge_base is not None:
            filters.append(CorpusProject.is_knowledge_base == is_knowledge_base)
        if search:
            filters.append(CorpusProject.name.ilike(f"%{search}%"))

        # Contagem total
        count_q = select(func.count(CorpusProject.id)).where(and_(*filters))
        count_result = await db.execute(count_q)
        total = count_result.scalar() or 0

        # Query paginada
        offset = (page - 1) * per_page
        projects_q = (
            select(CorpusProject)
            .where(and_(*filters))
            .order_by(CorpusProject.updated_at.desc())
            .offset(offset)
            .limit(per_page)
        )
        projects_result = await db.execute(projects_q)
        projects = projects_result.scalars().all()

        items = [_project_to_response(p) for p in projects]

        return CorpusProjectListResponse(
            items=items,
            total=total,
            page=page,
            per_page=per_page,
        )

    except Exception as e:
        logger.exception(f"Erro ao listar projetos de corpus: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falha ao listar projetos de corpus.",
        )


@router.get("/{project_id}", response_model=CorpusProjectResponse)
async def get_project(
    project_id: str = Path(..., description="ID do projeto"),
    ctx: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
) -> CorpusProjectResponse:
    """
    Obtém detalhes de um projeto de corpus com estatísticas atualizadas.
    """
    project = await _get_project_or_404(project_id, db, ctx.user.id)
    return _project_to_response(project)


@router.put("/{project_id}", response_model=CorpusProjectResponse)
async def update_project(
    request: CorpusProjectUpdate,
    project_id: str = Path(..., description="ID do projeto"),
    ctx: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
) -> CorpusProjectResponse:
    """
    Atualiza um projeto de corpus existente.

    Apenas o owner ou usuários com permissão 'edit'/'admin' podem atualizar.
    """
    project = await _get_project_or_404(project_id, db, ctx.user.id, require_edit=True)

    try:
        if request.name is not None:
            project.name = request.name
        if request.description is not None:
            project.description = request.description
        if request.is_knowledge_base is not None:
            project.is_knowledge_base = request.is_knowledge_base
        if request.max_documents is not None:
            project.max_documents = request.max_documents
        if request.retention_days is not None:
            project.retention_days = request.retention_days
        if request.metadata is not None:
            project.metadata_ = request.metadata

        await db.flush()
        await db.refresh(project)

        logger.info(f"Projeto de corpus atualizado: {project.id} por user={ctx.user.id}")
        return _project_to_response(project)

    except Exception as e:
        logger.exception(f"Erro ao atualizar projeto de corpus: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falha ao atualizar projeto de corpus.",
        )


@router.delete("/{project_id}")
async def delete_project(
    project_id: str = Path(..., description="ID do projeto"),
    ctx: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    """
    Soft-delete de um projeto de corpus.

    Apenas o owner pode deletar. Documentos associados não são excluídos,
    apenas a associação é removida.
    """
    project = await _get_project_or_404(project_id, db, ctx.user.id)

    if project.owner_id != ctx.user.id and not _has_admin_permission(ctx.user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas o proprietário pode excluir o projeto.",
        )

    try:
        project.is_active = False
        await db.flush()

        logger.info(f"Projeto de corpus excluído (soft): {project_id} por user={ctx.user.id}")
        return {"success": True, "message": "Projeto excluído com sucesso."}

    except Exception as e:
        logger.exception(f"Erro ao excluir projeto de corpus: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falha ao excluir projeto de corpus.",
        )


# =============================================================================
# Documents in Project
# =============================================================================


@router.post("/{project_id}/documents", response_model=CorpusProjectDocumentAddResponse)
async def add_documents_to_project(
    request: CorpusProjectDocumentAdd,
    project_id: str = Path(..., description="ID do projeto"),
    ctx: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
) -> CorpusProjectDocumentAddResponse:
    """
    Adiciona documentos a um projeto de corpus.

    Documentos são associados ao projeto e marcados para ingestão.
    """
    project = await _get_project_or_404(project_id, db, ctx.user.id, require_edit=True)

    # Verificar limite
    if project.document_count + len(request.document_ids) > project.max_documents:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Limite de {project.max_documents} documentos seria excedido.",
        )

    added = 0
    skipped = 0
    errors: list = []

    for doc_id in request.document_ids:
        try:
            # Verificar se documento existe
            doc_result = await db.execute(
                select(Document).where(Document.id == doc_id)
            )
            doc = doc_result.scalar_one_or_none()

            if doc is None:
                errors.append({"document_id": doc_id, "error": "Documento não encontrado"})
                continue

            # Verificar se já está no projeto
            existing = await db.execute(
                select(CorpusProjectDocument).where(
                    CorpusProjectDocument.project_id == project_id,
                    CorpusProjectDocument.document_id == doc_id,
                )
            )
            if existing.scalar_one_or_none() is not None:
                skipped += 1
                continue

            # Adicionar ao projeto
            project_doc = CorpusProjectDocument(
                id=str(uuid.uuid4()),
                project_id=project_id,
                document_id=doc_id,
                folder_path=request.folder_path,
                status=ProjectDocumentStatus.PENDING,
            )
            db.add(project_doc)
            added += 1

        except Exception as e:
            errors.append({"document_id": doc_id, "error": str(e)})

    # Atualizar contagem
    if added > 0:
        project.document_count = project.document_count + added
        await db.flush()

    return CorpusProjectDocumentAddResponse(
        added=added,
        skipped=skipped,
        errors=errors,
    )


@router.delete("/{project_id}/documents/{document_id}")
async def remove_document_from_project(
    project_id: str = Path(..., description="ID do projeto"),
    document_id: str = Path(..., description="ID do documento"),
    ctx: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    """
    Remove um documento de um projeto de corpus.

    Não exclui o documento original, apenas remove a associação.
    """
    project = await _get_project_or_404(project_id, db, ctx.user.id, require_edit=True)

    result = await db.execute(
        select(CorpusProjectDocument).where(
            CorpusProjectDocument.project_id == project_id,
            CorpusProjectDocument.document_id == document_id,
        )
    )
    project_doc = result.scalar_one_or_none()

    if project_doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Documento não encontrado neste projeto.",
        )

    await db.delete(project_doc)

    # Atualizar contagem
    project.document_count = max(0, project.document_count - 1)
    await db.flush()

    return {"success": True, "message": "Documento removido do projeto."}


# =============================================================================
# Duplicate Detection
# =============================================================================


@router.get("/{project_id}/duplicates")
async def detect_duplicates(
    project_id: str = Path(..., description="ID do projeto"),
    threshold: float = Query(0.9, ge=0.5, le=1.0, description="Limiar de similaridade (0.5-1.0)"),
    ctx: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    """
    Detecta documentos potencialmente duplicados no projeto.

    Compara hashes e nomes de documentos. Para documentos com mesmo hash
    (conteúdo idêntico), retorna score 1.0. Para nomes similares, calcula
    similaridade baseada em Levenshtein.
    """
    import hashlib
    from difflib import SequenceMatcher

    project = await _get_project_or_404(project_id, db, ctx.user.id)

    # Load project documents
    docs_q = (
        select(CorpusProjectDocument, Document)
        .join(Document, CorpusProjectDocument.document_id == Document.id)
        .where(CorpusProjectDocument.project_id == project_id)
    )
    docs_result = await db.execute(docs_q)
    rows = docs_result.all()

    if len(rows) < 2:
        return {"duplicates": [], "total_checked": len(rows)}

    # Build document info list
    doc_infos = []
    for proj_doc, doc in rows:
        doc_hash = getattr(doc, "file_hash", None) or getattr(doc, "hash", None) or ""
        doc_name = getattr(doc, "title", None) or getattr(doc, "filename", None) or getattr(doc, "name", "") or ""
        doc_size = getattr(doc, "file_size", None) or getattr(doc, "size", 0) or 0
        doc_infos.append({
            "document_id": str(doc.id),
            "name": doc_name,
            "hash": doc_hash,
            "size": doc_size,
        })

    duplicates = []
    seen_pairs = set()

    for i in range(len(doc_infos)):
        for j in range(i + 1, len(doc_infos)):
            a, b = doc_infos[i], doc_infos[j]
            pair_key = tuple(sorted([a["document_id"], b["document_id"]]))
            if pair_key in seen_pairs:
                continue

            score = 0.0
            reason = ""

            # Check hash match (exact duplicate)
            if a["hash"] and b["hash"] and a["hash"] == b["hash"]:
                score = 1.0
                reason = "Conteúdo idêntico (mesmo hash)"
            # Check size + name similarity
            elif a["size"] > 0 and a["size"] == b["size"]:
                name_sim = SequenceMatcher(None, a["name"].lower(), b["name"].lower()).ratio()
                if name_sim >= threshold:
                    score = name_sim
                    reason = f"Mesmo tamanho e nomes similares ({name_sim:.0%})"
            else:
                # Name similarity only
                if a["name"] and b["name"]:
                    name_sim = SequenceMatcher(None, a["name"].lower(), b["name"].lower()).ratio()
                    if name_sim >= threshold:
                        score = name_sim * 0.8  # lower confidence without size match
                        reason = f"Nomes similares ({name_sim:.0%})"

            if score >= threshold:
                seen_pairs.add(pair_key)
                duplicates.append({
                    "document_a": {
                        "id": a["document_id"],
                        "name": a["name"],
                    },
                    "document_b": {
                        "id": b["document_id"],
                        "name": b["name"],
                    },
                    "similarity_score": round(score, 3),
                    "reason": reason,
                })

    # Sort by score descending
    duplicates.sort(key=lambda d: d["similarity_score"], reverse=True)

    return {
        "duplicates": duplicates,
        "total_checked": len(doc_infos),
        "threshold": threshold,
    }


# =============================================================================
# Folders
# =============================================================================


@router.get("/{project_id}/folders", response_model=FolderTreeResponse)
async def get_project_folders(
    project_id: str = Path(..., description="ID do projeto"),
    ctx: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
) -> FolderTreeResponse:
    """
    Retorna a árvore de pastas de um projeto de corpus.

    Reconstrói a hierarquia a partir dos folder_path dos documentos.
    """
    project = await _get_project_or_404(project_id, db, ctx.user.id)

    # Buscar todos os folder_paths distintos do projeto
    result = await db.execute(
        select(
            CorpusProjectDocument.folder_path,
            func.count(CorpusProjectDocument.id).label("doc_count"),
        )
        .where(
            CorpusProjectDocument.project_id == project_id,
            CorpusProjectDocument.folder_path.isnot(None),
            CorpusProjectDocument.folder_path != "",
        )
        .group_by(CorpusProjectDocument.folder_path)
    )
    folder_rows = result.all()

    # Contar documentos na raiz (sem folder_path)
    root_count_result = await db.execute(
        select(func.count(CorpusProjectDocument.id)).where(
            CorpusProjectDocument.project_id == project_id,
            or_(
                CorpusProjectDocument.folder_path.is_(None),
                CorpusProjectDocument.folder_path == "",
            ),
        )
    )
    _root_count = root_count_result.scalar() or 0

    # Construir árvore de pastas
    folder_map: dict[str, int] = {}
    for row in folder_rows:
        path = row[0]
        count = row[1]
        folder_map[path] = count

        # Garantir que pastas intermediárias existam
        parts = path.split("/")
        for i in range(1, len(parts)):
            parent_path = "/".join(parts[:i])
            if parent_path not in folder_map:
                folder_map[parent_path] = 0

    # Construir a árvore hierárquica
    root_folders: list[FolderNode] = []
    all_nodes: dict[str, FolderNode] = {}

    # Ordenar por profundidade (mais rasos primeiro)
    sorted_paths = sorted(folder_map.keys(), key=lambda p: p.count("/"))

    for path in sorted_paths:
        parts = path.split("/")
        name = parts[-1]
        node = FolderNode(
            name=name,
            path=path,
            document_count=folder_map[path],
            children=[],
        )
        all_nodes[path] = node

        if len(parts) == 1:
            root_folders.append(node)
        else:
            parent_path = "/".join(parts[:-1])
            parent_node = all_nodes.get(parent_path)
            if parent_node:
                parent_node.children.append(node)
            else:
                root_folders.append(node)

    return FolderTreeResponse(
        project_id=project_id,
        folders=root_folders,
        total_folders=len(folder_map),
    )


@router.post("/{project_id}/folders")
async def create_folder(
    request: CreateFolderRequest,
    project_id: str = Path(..., description="ID do projeto"),
    ctx: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    """
    Cria uma pasta virtual no projeto.

    Como pastas são virtuais (derivadas de folder_path dos documentos),
    criamos um placeholder. Se a pasta já existe (há documentos com
    este path), retorna sucesso sem alteração.
    """
    project = await _get_project_or_404(project_id, db, ctx.user.id, require_edit=True)

    # Verificar se já existe algum documento com este folder_path
    existing = await db.execute(
        select(func.count(CorpusProjectDocument.id)).where(
            CorpusProjectDocument.project_id == project_id,
            CorpusProjectDocument.folder_path == request.folder_path,
        )
    )
    count = existing.scalar() or 0

    return {
        "success": True,
        "folder_path": request.folder_path,
        "already_exists": count > 0,
        "message": f"Pasta '{request.folder_path}' {'já existe' if count > 0 else 'criada com sucesso'}.",
    }


@router.get("/{project_id}/documents", response_model=list[CorpusProjectDocumentResponse])
async def list_project_documents(
    project_id: str = Path(..., description="ID do projeto"),
    folder: Optional[str] = Query(None, description="Filtrar por caminho de pasta"),
    doc_status: Optional[str] = Query(None, alias="status", description="Filtrar por status"),
    sort: Optional[str] = Query("recent", description="Ordenação: recent, oldest, alpha"),
    page: int = Query(1, ge=1, description="Página"),
    per_page: int = Query(50, ge=1, le=200, description="Itens por página"),
    ctx: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
) -> list[CorpusProjectDocumentResponse]:
    """
    Lista documentos de um projeto, opcionalmente filtrados por pasta e status.
    """
    project = await _get_project_or_404(project_id, db, ctx.user.id)

    filters = [CorpusProjectDocument.project_id == project_id]

    if folder is not None:
        if folder == "" or folder == "/":
            # Raiz: documentos sem folder_path
            filters.append(
                or_(
                    CorpusProjectDocument.folder_path.is_(None),
                    CorpusProjectDocument.folder_path == "",
                )
            )
        else:
            # Documentos na pasta exata (não subpastas)
            filters.append(CorpusProjectDocument.folder_path == folder)

    if doc_status:
        filters.append(CorpusProjectDocument.status == ProjectDocumentStatus(doc_status))

    # Ordenação
    if sort == "oldest":
        order = CorpusProjectDocument.created_at.asc()
    elif sort == "alpha":
        order = CorpusProjectDocument.id.asc()  # Fallback, ideally join with Document.name
    else:
        order = CorpusProjectDocument.created_at.desc()

    offset = (page - 1) * per_page
    query = (
        select(CorpusProjectDocument)
        .where(and_(*filters))
        .order_by(order)
        .offset(offset)
        .limit(per_page)
    )
    result = await db.execute(query)
    project_docs = result.scalars().all()

    # Buscar nomes dos documentos
    items = []
    for pd in project_docs:
        doc_name = None
        try:
            doc_result = await db.execute(
                select(Document.name).where(Document.id == pd.document_id)
            )
            doc_name = doc_result.scalar_one_or_none()
        except Exception:
            pass

        items.append(CorpusProjectDocumentResponse(
            id=pd.id,
            project_id=pd.project_id,
            document_id=pd.document_id,
            document_name=doc_name,
            folder_path=pd.folder_path,
            status=pd.status.value if hasattr(pd.status, "value") else str(pd.status),
            ingested_at=pd.ingested_at,
            error_message=pd.error_message,
            created_at=pd.created_at,
        ))

    return items


@router.patch("/{project_id}/documents/{document_id}/move")
async def move_document(
    request: MoveDocumentRequest,
    project_id: str = Path(..., description="ID do projeto"),
    document_id: str = Path(..., description="ID do documento (corpus_project_document.id)"),
    ctx: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    """
    Move um documento para outra pasta dentro do projeto.

    O document_id aqui é o ID da associação (CorpusProjectDocument.id),
    não o Document.id original.
    """
    project = await _get_project_or_404(project_id, db, ctx.user.id, require_edit=True)

    result = await db.execute(
        select(CorpusProjectDocument).where(
            CorpusProjectDocument.project_id == project_id,
            CorpusProjectDocument.document_id == document_id,
        )
    )
    project_doc = result.scalar_one_or_none()

    if project_doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Documento não encontrado neste projeto.",
        )

    old_path = project_doc.folder_path
    project_doc.folder_path = request.folder_path
    await db.flush()

    logger.info(
        f"Documento {document_id} movido de '{old_path}' para '{request.folder_path}' "
        f"no projeto {project_id}"
    )

    return {
        "success": True,
        "document_id": document_id,
        "old_folder_path": old_path,
        "new_folder_path": request.folder_path,
        "message": "Documento movido com sucesso.",
    }


# =============================================================================
# Share
# =============================================================================


@router.post("/{project_id}/share", response_model=CorpusProjectShareResponse, status_code=status.HTTP_201_CREATED)
async def share_project(
    request: CorpusProjectShareCreate,
    project_id: str = Path(..., description="ID do projeto"),
    ctx: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
) -> CorpusProjectShareResponse:
    """
    Compartilha um projeto de corpus com um usuário ou organização.
    """
    project = await _get_project_or_404(project_id, db, ctx.user.id)

    # Apenas owner ou admin pode compartilhar
    if project.owner_id != ctx.user.id:
        # Verificar se tem permissão admin
        share_q = select(CorpusProjectShare).where(
            CorpusProjectShare.project_id == project_id,
            CorpusProjectShare.shared_with_user_id == ctx.user.id,
            CorpusProjectShare.permission == ProjectSharePermission.ADMIN.value,
        )
        share_result = await db.execute(share_q)
        if share_result.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Apenas o proprietário ou admin pode compartilhar.",
            )

    if not request.shared_with_user_id and not request.shared_with_org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Informe shared_with_user_id ou shared_with_org_id.",
        )

    try:
        share = CorpusProjectShare(
            id=str(uuid.uuid4()),
            project_id=project_id,
            shared_with_user_id=request.shared_with_user_id,
            shared_with_org_id=request.shared_with_org_id,
            permission=ProjectSharePermission(request.permission),
        )
        db.add(share)
        await db.flush()
        await db.refresh(share)

        return CorpusProjectShareResponse(
            id=share.id,
            project_id=share.project_id,
            shared_with_user_id=share.shared_with_user_id,
            shared_with_org_id=share.shared_with_org_id,
            permission=share.permission.value if hasattr(share.permission, "value") else str(share.permission),
            created_at=share.created_at,
        )

    except Exception as e:
        logger.exception(f"Erro ao compartilhar projeto: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falha ao compartilhar projeto.",
        )


@router.delete("/{project_id}/share/{share_id}")
async def unshare_project(
    project_id: str = Path(..., description="ID do projeto"),
    share_id: str = Path(..., description="ID do compartilhamento"),
    ctx: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    """
    Remove compartilhamento de um projeto.
    """
    project = await _get_project_or_404(project_id, db, ctx.user.id)

    if project.owner_id != ctx.user.id and not _has_admin_permission(ctx.user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sem permissão para remover compartilhamento.",
        )

    result = await db.execute(
        select(CorpusProjectShare).where(
            CorpusProjectShare.id == share_id,
            CorpusProjectShare.project_id == project_id,
        )
    )
    share = result.scalar_one_or_none()

    if share is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Compartilhamento não encontrado.",
        )

    await db.delete(share)
    await db.flush()

    return {"success": True, "message": "Compartilhamento removido."}


# =============================================================================
# Transfer
# =============================================================================


@router.post("/{project_id}/transfer")
async def transfer_project(
    request: CorpusProjectTransferRequest,
    project_id: str = Path(..., description="ID do projeto"),
    ctx: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    """
    Transfere a propriedade de um projeto para outro usuário.

    Apenas o owner pode transferir.
    """
    project = await _get_project_or_404(project_id, db, ctx.user.id)

    if project.owner_id != ctx.user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas o proprietário pode transferir o projeto.",
        )

    # Verificar se novo owner existe
    new_owner_result = await db.execute(
        select(User).where(User.id == request.new_owner_id)
    )
    new_owner = new_owner_result.scalar_one_or_none()

    if new_owner is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Novo proprietário não encontrado.",
        )

    try:
        old_owner_id = project.owner_id
        project.owner_id = request.new_owner_id
        await db.flush()

        logger.info(
            f"Projeto {project_id} transferido de {old_owner_id} "
            f"para {request.new_owner_id}"
        )
        return {
            "success": True,
            "message": f"Projeto transferido para {new_owner.id}.",
        }

    except Exception as e:
        logger.exception(f"Erro ao transferir projeto: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falha ao transferir projeto.",
        )
