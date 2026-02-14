"""
Corpus API — Interface unificada de gestão da base de conhecimento RAG.

Endpoints para visualização, busca, ingestão e gerenciamento
de documentos indexados no pipeline RAG (OpenSearch + Qdrant + Neo4j).

Inspirado no conceito de "Vault" da Harvey AI.
"""

from __future__ import annotations

import mimetypes
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import FileResponse, HTMLResponse, Response

from app.core.database import get_db
from app.core.rate_limit import (
    corpus_read_limit,
    corpus_search_limit,
    corpus_write_limit,
)
from app.core.security import get_org_context, OrgContext
from app.models.user import User, UserRole
from app.schemas.corpus import (
    CorpusAdminActivityList,
    CorpusAdminOverview,
    CorpusAdminUserList,
    CorpusBackfillJurisdictionRequest,
    CorpusBackfillJurisdictionResponse,
    CorpusBackfillSourceIdRequest,
    CorpusBackfillSourceIdResponse,
    CorpusCollectionInfo,
    CorpusDocumentList,
    CorpusDocumentSource,
    CorpusDocumentViewerManifest,
    CorpusRegionalSourcesCatalogResponse,
    CorpusViewerBackfillRequest,
    CorpusViewerBackfillResponse,
    CorpusExtendTTLRequest,
    CorpusExtendTTLResponse,
    CorpusIngestRequest,
    CorpusIngestResponse,
    CorpusPromoteResponse,
    CorpusRetentionPolicy,
    CorpusRetentionPolicyList,
    CorpusSearchRequest,
    CorpusSearchResponse,
    CorpusStats,
    CorpusTransferRequest,
    CorpusTransferResponse,
    VerbatimExcerpt,
    VerbatimRequest,
    VerbatimResponse,
)
from app.services.corpus_service import CorpusService
from app.services.rag.regional_sources_catalog import get_regional_sources_catalog

router = APIRouter(tags=["corpus"])


# =============================================================================
# Dependencies
# =============================================================================


def get_corpus_service(db: AsyncSession = Depends(get_db)) -> CorpusService:
    """Dependency para obter o serviço do Corpus."""
    return CorpusService(db=db)


# =============================================================================
# Stats
# =============================================================================


@router.get("/stats", response_model=CorpusStats)
async def get_corpus_stats(
    ctx: OrgContext = Depends(get_org_context),
    service: CorpusService = Depends(get_corpus_service),
    _rl: None = Depends(corpus_read_limit),
) -> CorpusStats:
    """
    Estatísticas gerais do Corpus.

    Retorna contagens de documentos por escopo e coleção,
    pendências de ingestão e última indexação.
    """
    try:
        return await service.get_stats(
            user_id=ctx.user.id,
            org_id=ctx.organization_id,
        )
    except Exception as e:
        logger.exception(f"Erro ao obter estatísticas do Corpus: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falha ao obter estatísticas do Corpus.",
        )


# =============================================================================
# Documents
# =============================================================================


@router.get("/documents", response_model=CorpusDocumentList)
async def list_corpus_documents(
    scope: Optional[str] = Query(None, description="Filtrar por escopo (global, private, local)"),
    group_id: Optional[str] = Query(None, description="Filtrar por departamento (team id) quando scope=group"),
    collection: Optional[str] = Query(None, description="Filtrar por coleção"),
    search: Optional[str] = Query(None, description="Busca por nome do documento"),
    doc_status: Optional[str] = Query(
        None, alias="status", description="Filtrar por status (ingested, pending, processing, failed)"
    ),
    page: int = Query(1, ge=1, description="Página"),
    per_page: int = Query(20, ge=1, le=100, description="Itens por página"),
    ctx: OrgContext = Depends(get_org_context),
    service: CorpusService = Depends(get_corpus_service),
    _rl: None = Depends(corpus_read_limit),
) -> CorpusDocumentList:
    """
    Lista documentos no Corpus com filtros e paginação.

    Combina metadados do banco de dados com informações de ingestão RAG.
    """
    try:
        return await service.list_documents(
            user_id=ctx.user.id,
            org_id=ctx.organization_id,
            scope=scope,
            group_id=group_id,
            allowed_group_ids=list(ctx.team_ids or []),
            collection=collection,
            search=search,
            status=doc_status,
            page=page,
            per_page=per_page,
        )
    except Exception as e:
        logger.exception(f"Erro ao listar documentos do Corpus: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falha ao listar documentos do Corpus.",
        )


@router.get("/documents/export")
async def export_corpus_documents(
    format: str = Query("csv", pattern="^(csv|xlsx)$"),
    columns: Optional[str] = Query(None, description="Lista de colunas separadas por vírgula"),
    scope: Optional[str] = Query(None, description="Filtrar por escopo (global, private, group, local)"),
    group_id: Optional[str] = Query(None, description="Filtrar por departamento (team id) quando scope=group"),
    collection: Optional[str] = Query(None, description="Filtrar por coleção"),
    search: Optional[str] = Query(None, description="Busca por nome do documento"),
    doc_status: Optional[str] = Query(None, alias="status", description="Filtrar por status (ingested, pending, processing, failed)"),
    ctx: OrgContext = Depends(get_org_context),
    service: CorpusService = Depends(get_corpus_service),
    _rl: None = Depends(corpus_read_limit),
) -> Response:
    """Exporta inventário do Corpus como CSV ou XLSX."""
    try:
        cols = [c.strip() for c in (columns or "").split(",") if c.strip()] if columns else None
        content, filename, content_type = await service.export_documents(
            user_id=ctx.user.id,
            org_id=ctx.organization_id,
            scope=scope,
            group_id=group_id,
            allowed_group_ids=list(ctx.team_ids or []),
            collection=collection,
            search=search,
            status=doc_status,
            columns=cols,
            format=format,
        )
        return Response(
            content=content,
            media_type=content_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.exception(f"Erro ao exportar documentos do Corpus: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falha ao exportar documentos do Corpus.",
        )


@router.get("/documents/{document_id}/source", response_model=CorpusDocumentSource)
async def get_corpus_document_source(
    document_id: str = Path(..., description="ID do documento"),
    ctx: OrgContext = Depends(get_org_context),
    service: CorpusService = Depends(get_corpus_service),
    _rl: None = Depends(corpus_read_limit),
) -> CorpusDocumentSource:
    """
    Resolve metadados de fonte para visualização do documento original.

    Retorna URLs de viewer/download quando o arquivo original está disponível.
    """
    try:
        source = await service.get_document_source(
            document_id=document_id,
            user_id=ctx.user.id,
            org_id=ctx.organization_id,
        )
        if source is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Documento não encontrado ou sem permissão.",
            )
        return source
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Erro ao resolver source do documento do Corpus: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falha ao resolver documento fonte no Corpus.",
        )


@router.get(
    "/documents/{document_id}/viewer-manifest",
    response_model=CorpusDocumentViewerManifest,
)
async def get_corpus_document_viewer_manifest(
    document_id: str = Path(..., description="ID do documento"),
    ctx: OrgContext = Depends(get_org_context),
    service: CorpusService = Depends(get_corpus_service),
    _rl: None = Depends(corpus_read_limit),
) -> CorpusDocumentViewerManifest:
    """Retorna manifesto de viewer para navegação precisa em evidências."""
    try:
        manifest = await service.get_document_viewer_manifest(
            document_id=document_id,
            user_id=ctx.user.id,
            org_id=ctx.organization_id,
        )
        if manifest is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Documento não encontrado ou sem permissão.",
            )
        return manifest
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Erro ao resolver viewer-manifest do documento do Corpus: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falha ao resolver viewer-manifest do documento no Corpus.",
        )


@router.get("/documents/{document_id}/content")
async def get_corpus_document_content(
    document_id: str = Path(..., description="ID do documento"),
    download: bool = Query(False, description="Se true, força download em vez de visualização inline."),
    ctx: OrgContext = Depends(get_org_context),
    service: CorpusService = Depends(get_corpus_service),
    _rl: None = Depends(corpus_read_limit),
) -> Response:
    """
    Retorna o arquivo original do documento (streaming) para viewer RAG.
    """
    try:
        resolved = await service.get_document_file_path(
            document_id=document_id,
            user_id=ctx.user.id,
            org_id=ctx.organization_id,
        )
        if resolved is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Arquivo original não disponível para este documento.",
            )

        document, file_path = resolved
        filename = (document.original_name or document.name or f"{document.id}").strip()
        mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        disposition = "attachment" if download else "inline"

        return FileResponse(
            file_path,
            media_type=mime_type,
            headers={"Content-Disposition": f'{disposition}; filename="{filename}"'},
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Erro ao servir conteúdo do documento do Corpus: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falha ao abrir conteúdo do documento no Corpus.",
        )


@router.get("/documents/{document_id}/preview")
async def get_corpus_document_preview(
    document_id: str = Path(..., description="ID do documento"),
    q: Optional[str] = Query(None, description="Trecho para highlight (best-effort)"),
    page: Optional[int] = Query(None, ge=1, description="Página para navegação (best-effort)"),
    ctx: OrgContext = Depends(get_org_context),
    service: CorpusService = Depends(get_corpus_service),
    _rl: None = Depends(corpus_read_limit),
) -> Response:
    """
    Retorna preview HTML gerado para documentos Office/OpenOffice.
    """
    try:
        resolved = await service.get_document_preview_path(
            document_id=document_id,
            user_id=ctx.user.id,
            org_id=ctx.organization_id,
        )
        if resolved is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Preview não disponível para este documento.",
            )
        _document, preview_path = resolved

        # highlight/page query no HTML para navegação por evidência.
        # Mantemos comportamento best-effort sem alterar o arquivo original.
        if q or page:
            with open(preview_path, "r", encoding="utf-8", errors="ignore") as fh:
                html_text = fh.read()
            safe_q = (q or "").replace("\\", "\\\\").replace('"', '\\"')
            page_value = page or 1
            injection = f"""
<script>
(function () {{
  const targetPage = {int(page_value)};
  const q = "{safe_q}".trim();
  function markFirst(root, needle) {{
    if (!needle) return null;
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null);
    const lowerNeedle = needle.toLowerCase();
    while (walker.nextNode()) {{
      const node = walker.currentNode;
      const text = node.nodeValue || "";
      const idx = text.toLowerCase().indexOf(lowerNeedle);
      if (idx < 0) continue;
      const before = text.slice(0, idx);
      const hit = text.slice(idx, idx + needle.length);
      const after = text.slice(idx + needle.length);
      const span = document.createElement("span");
      span.textContent = before;
      const mark = document.createElement("mark");
      mark.textContent = hit;
      mark.style.background = "#fde68a";
      mark.style.padding = "0 2px";
      mark.style.borderRadius = "3px";
      const tail = document.createTextNode(after);
      const frag = document.createDocumentFragment();
      frag.appendChild(span);
      frag.appendChild(mark);
      frag.appendChild(tail);
      node.parentNode.replaceChild(frag, node);
      return mark;
    }}
    return null;
  }}
  const pageEl = document.querySelector('[data-page-number="' + targetPage + '"]') || null;
  if (pageEl) {{
    pageEl.scrollIntoView({{ behavior: "smooth", block: "start" }});
  }}
  const mark = markFirst(document.body, q);
  if (mark) {{
    setTimeout(function () {{
      mark.scrollIntoView({{ behavior: "smooth", block: "center" }});
    }}, 50);
  }}
}})();
</script>
"""
            if "</body>" in html_text:
                html_text = html_text.replace("</body>", f"{injection}</body>")
            else:
                html_text += injection
            return HTMLResponse(content=html_text, media_type="text/html")

        return FileResponse(
            preview_path,
            media_type="text/html; charset=utf-8",
            headers={"Content-Disposition": 'inline; filename="preview.html"'},
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Erro ao servir preview do documento do Corpus: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falha ao abrir preview do documento no Corpus.",
        )


# =============================================================================
# Regional Sources Catalog (Global)
# =============================================================================


@router.get("/sources/regional", response_model=CorpusRegionalSourcesCatalogResponse)
async def get_regional_sources_catalog_endpoint(
    _ctx: OrgContext = Depends(get_org_context),
    _rl: None = Depends(corpus_read_limit),
) -> CorpusRegionalSourcesCatalogResponse:
    """
    Retorna um catálogo declarativo de Fontes Regionais (por jurisdição) para o Corpus Global.

    A UI pode usar este endpoint para renderizar um seletor de sub-fontes (ex.: STF/STJ/Planalto).
    """
    data = get_regional_sources_catalog()
    return CorpusRegionalSourcesCatalogResponse(**data)


# =============================================================================
# Ingest
# =============================================================================


@router.post("/ingest", response_model=CorpusIngestResponse)
async def ingest_to_corpus(
    request: CorpusIngestRequest,
    ctx: OrgContext = Depends(get_org_context),
    service: CorpusService = Depends(get_corpus_service),
    _rl: None = Depends(corpus_write_limit),
) -> CorpusIngestResponse:
    """
    Dispara ingestão de documentos no Corpus.

    Os documentos serão processados e indexados nos backends RAG
    (OpenSearch para busca lexical, Qdrant para busca vetorial).

    Para ingestão global, requer permissões elevadas.
    """
    # Verificar permissão para ingestão global
    if request.scope == "global":
        if not _has_admin_permission(ctx.user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Ingestão global requer permissões de administrador.",
            )

    normalized_scope = str(request.scope or "").strip().lower()
    group_ids = [str(g).strip() for g in (request.group_ids or []) if str(g).strip()]
    if normalized_scope == "group":
        if not ctx.is_org_member:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Escopo de departamento requer organização ativa.",
            )
        if not group_ids:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="group_ids é obrigatório quando scope='group'.",
            )
        allowed = set(str(g) for g in (ctx.team_ids or []) if str(g))
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Usuário não pertence a nenhum departamento (team).",
            )
        requested = set(group_ids)
        if not requested.issubset(allowed):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Um ou mais departamentos não são permitidos para este usuário.",
            )

    try:
        return await service.ingest_documents(
            document_ids=request.document_ids,
            collection=request.collection,
            scope=normalized_scope or request.scope,
            user_id=ctx.user.id,
            group_ids=group_ids if normalized_scope == "group" else None,
            jurisdiction=request.jurisdiction,
            source_id=request.source_id,
        )
    except Exception as e:
        logger.exception(f"Erro na ingestão do Corpus: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falha na ingestão do Corpus.",
        )


# =============================================================================
# Remove
# =============================================================================


@router.delete("/documents/{document_id}")
async def remove_from_corpus(
    document_id: str = Path(..., description="ID do documento"),
    ctx: OrgContext = Depends(get_org_context),
    service: CorpusService = Depends(get_corpus_service),
    _rl: None = Depends(corpus_write_limit),
):
    """
    Remove documento dos índices RAG (OpenSearch + Qdrant).

    Não exclui o documento original do sistema, apenas remove
    dos índices de busca do Corpus.
    """
    try:
        success = await service.remove_from_corpus(
            document_id=document_id,
            user_id=ctx.user.id,
        )
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Documento não encontrado ou sem permissão.",
            )
        return {"success": True, "message": "Documento removido do Corpus."}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Erro ao remover documento do Corpus: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falha ao remover documento do Corpus.",
        )


# =============================================================================
# Search
# =============================================================================


@router.post("/search", response_model=CorpusSearchResponse)
async def search_corpus(
    request: CorpusSearchRequest,
    ctx: OrgContext = Depends(get_org_context),
    service: CorpusService = Depends(get_corpus_service),
    _rl: None = Depends(corpus_search_limit),
) -> CorpusSearchResponse:
    """
    Busca unificada no Corpus.

    Executa busca lexical (OpenSearch) e vetorial (Qdrant) em paralelo,
    combinando resultados por score de relevância.
    """
    try:
        return await service.search_corpus(
            query=request.query,
            collections=request.collections,
            scope=request.scope,
            user_id=ctx.user.id,
            org_id=ctx.organization_id,
            limit=request.limit,
        )
    except Exception as e:
        logger.exception(f"Erro na busca do Corpus: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falha na busca do Corpus.",
        )


# =============================================================================
# Collections
# =============================================================================


@router.get("/collections", response_model=list[CorpusCollectionInfo])
async def list_collections(
    ctx: OrgContext = Depends(get_org_context),
    service: CorpusService = Depends(get_corpus_service),
    _rl: None = Depends(corpus_read_limit),
) -> list[CorpusCollectionInfo]:
    """
    Lista coleções disponíveis no Corpus.

    Cada coleção representa um tipo de fonte de dados jurídicos
    (legislação, jurisprudência, modelos, etc.).
    """
    try:
        return await service.list_collections()
    except Exception as e:
        logger.exception(f"Erro ao listar coleções do Corpus: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falha ao listar coleções do Corpus.",
        )


@router.get("/collections/{collection_name}", response_model=CorpusCollectionInfo)
async def get_collection_details(
    collection_name: str = Path(..., description="Nome da coleção"),
    ctx: OrgContext = Depends(get_org_context),
    service: CorpusService = Depends(get_corpus_service),
    _rl: None = Depends(corpus_read_limit),
) -> CorpusCollectionInfo:
    """
    Detalhes de uma coleção específica do Corpus.
    """
    try:
        info = await service.get_collection_info(collection_name)
        if info is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Coleção '{collection_name}' não encontrada.",
            )
        return info
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Erro ao obter detalhes da coleção: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falha ao obter detalhes da coleção.",
        )


# =============================================================================
# Promote / Extend TTL
# =============================================================================


@router.post("/documents/{document_id}/promote", response_model=CorpusPromoteResponse)
async def promote_document(
    document_id: str = Path(..., description="ID do documento"),
    ctx: OrgContext = Depends(get_org_context),
    service: CorpusService = Depends(get_corpus_service),
    _rl: None = Depends(corpus_write_limit),
) -> CorpusPromoteResponse:
    """
    Promove documento de escopo local (temporário) para privado (permanente).

    Documentos locais são automaticamente excluídos após o TTL configurado.
    Ao promover para privado, o documento persiste indefinidamente.
    """
    try:
        return await service.promote_local_to_private(
            document_id=document_id,
            user_id=ctx.user.id,
        )
    except Exception as e:
        logger.exception(f"Erro ao promover documento: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falha ao promover documento.",
        )


@router.post("/documents/{document_id}/extend-ttl", response_model=CorpusExtendTTLResponse)
async def extend_document_ttl(
    request: CorpusExtendTTLRequest,
    document_id: str = Path(..., description="ID do documento"),
    ctx: OrgContext = Depends(get_org_context),
    service: CorpusService = Depends(get_corpus_service),
    _rl: None = Depends(corpus_write_limit),
) -> CorpusExtendTTLResponse:
    """
    Estende o TTL de um documento local.

    Documentos locais expiram automaticamente. Use este endpoint
    para adiar a expiração sem promover para privado.
    """
    try:
        return await service.extend_local_ttl(
            document_id=document_id,
            days=request.days,
            user_id=ctx.user.id,
        )
    except Exception as e:
        logger.exception(f"Erro ao estender TTL: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falha ao estender TTL do documento.",
        )


# =============================================================================
# Retention Policy
# =============================================================================


@router.get("/retention-policy", response_model=CorpusRetentionPolicyList)
async def get_retention_policies(
    ctx: OrgContext = Depends(get_org_context),
    service: CorpusService = Depends(get_corpus_service),
    _rl: None = Depends(corpus_read_limit),
) -> CorpusRetentionPolicyList:
    """
    Obtém políticas de retenção do Corpus.
    """
    try:
        return await service.get_retention_policies(
            org_id=ctx.organization_id,
        )
    except Exception as e:
        logger.exception(f"Erro ao obter políticas de retenção: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falha ao obter políticas de retenção.",
        )


@router.put("/retention-policy")
async def update_retention_policy(
    policy: CorpusRetentionPolicy,
    ctx: OrgContext = Depends(get_org_context),
    service: CorpusService = Depends(get_corpus_service),
    _rl: None = Depends(corpus_write_limit),
):
    """
    Atualiza política de retenção do Corpus.

    Requer permissões de administrador da organização.
    """
    # Verificar permissão admin
    if not _has_admin_permission(ctx.user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Atualização de política de retenção requer permissões de administrador.",
        )

    if not ctx.organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Política de retenção requer contexto organizacional.",
        )

    try:
        success = await service.update_retention_policy(
            org_id=ctx.organization_id,
            policy=policy,
        )
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Falha ao atualizar política de retenção.",
            )
        return {"success": True, "message": "Política de retenção atualizada."}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Erro ao atualizar política de retenção: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falha ao atualizar política de retenção.",
        )


# =============================================================================
# Admin — Dashboard administrativo do Corpus
# =============================================================================


def _require_admin_org(ctx: OrgContext) -> str:
    """Valida permissão admin e retorna org_id. Levanta HTTPException se inválido."""
    if not _has_admin_permission(ctx.user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito a administradores.",
        )
    if not ctx.organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Endpoints admin requerem contexto organizacional.",
        )
    return ctx.organization_id


@router.get("/admin/overview", response_model=CorpusAdminOverview)
async def get_corpus_admin_overview(
    request: Request,
    ctx: OrgContext = Depends(get_org_context),
    service: CorpusService = Depends(get_corpus_service),
) -> CorpusAdminOverview:
    """
    Visão geral administrativa do Corpus.

    Retorna estatísticas de todos os usuários da organização:
    total de documentos, armazenamento, fila de ingestão,
    top contribuidores e atividade recente.
    """
    await corpus_read_limit(request)
    org_id = _require_admin_org(ctx)
    try:
        return await service.get_admin_overview(org_id=org_id)
    except Exception as e:
        logger.exception(f"Erro ao obter visão geral admin do Corpus: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falha ao obter visão geral administrativa do Corpus.",
        )


@router.get("/admin/users", response_model=CorpusAdminUserList)
async def get_corpus_users(
    request: Request,
    skip: int = Query(0, ge=0, description="Pular N registros"),
    limit: int = Query(20, ge=1, le=100, description="Limite de registros"),
    ctx: OrgContext = Depends(get_org_context),
    service: CorpusService = Depends(get_corpus_service),
) -> CorpusAdminUserList:
    """
    Lista usuários da organização com estatísticas do Corpus.

    Retorna por usuário: contagem de documentos, armazenamento,
    última atividade e coleções utilizadas.
    """
    await corpus_read_limit(request)
    org_id = _require_admin_org(ctx)
    try:
        return await service.get_corpus_users(
            org_id=org_id,
            skip=skip,
            limit=limit,
        )
    except Exception as e:
        logger.exception(f"Erro ao listar usuários do Corpus: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falha ao listar usuários do Corpus.",
        )


@router.get("/admin/users/{user_id}/documents", response_model=CorpusDocumentList)
async def get_user_corpus_documents(
    request: Request,
    user_id: str = Path(..., description="ID do usuário"),
    scope: Optional[str] = Query(None, description="Filtrar por escopo"),
    collection: Optional[str] = Query(None, description="Filtrar por coleção"),
    doc_status: Optional[str] = Query(None, alias="status", description="Filtrar por status"),
    skip: int = Query(0, ge=0, description="Pular N registros"),
    limit: int = Query(20, ge=1, le=100, description="Limite de registros"),
    ctx: OrgContext = Depends(get_org_context),
    service: CorpusService = Depends(get_corpus_service),
) -> CorpusDocumentList:
    """
    Lista documentos de um usuário específico no Corpus (visão admin).
    """
    await corpus_read_limit(request)
    org_id = _require_admin_org(ctx)
    try:
        return await service.get_user_documents(
            user_id=user_id,
            org_id=org_id,
            scope=scope,
            collection=collection,
            status=doc_status,
            skip=skip,
            limit=limit,
        )
    except Exception as e:
        logger.exception(f"Erro ao listar documentos do usuário {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falha ao listar documentos do usuário.",
        )


@router.post("/admin/transfer/{document_id}", response_model=CorpusTransferResponse)
async def transfer_document_ownership(
    request: Request,
    body: CorpusTransferRequest,
    document_id: str = Path(..., description="ID do documento"),
    ctx: OrgContext = Depends(get_org_context),
    service: CorpusService = Depends(get_corpus_service),
) -> CorpusTransferResponse:
    """
    Transfere a propriedade de um documento para outro usuário da organização.
    """
    await corpus_write_limit(request)
    org_id = _require_admin_org(ctx)
    try:
        result = await service.transfer_ownership(
            document_id=document_id,
            new_owner_id=body.new_owner_id,
            org_id=org_id,
        )
        if not result.success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.message,
            )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Erro ao transferir documento {document_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falha ao transferir propriedade do documento.",
        )


@router.get("/admin/activity", response_model=CorpusAdminActivityList)
async def get_corpus_activity(
    request: Request,
    skip: int = Query(0, ge=0, description="Pular N registros"),
    limit: int = Query(50, ge=1, le=200, description="Limite de registros"),
    user_id: Optional[str] = Query(None, description="Filtrar por usuário"),
    action: Optional[str] = Query(None, description="Filtrar por ação"),
    ctx: OrgContext = Depends(get_org_context),
    service: CorpusService = Depends(get_corpus_service),
) -> CorpusAdminActivityList:
    """
    Log de atividades do Corpus na organização.
    """
    await corpus_read_limit(request)
    org_id = _require_admin_org(ctx)
    try:
        return await service.get_corpus_activity(
            org_id=org_id,
            skip=skip,
            limit=limit,
            user_id=user_id,
            action=action,
        )
    except Exception as e:
        logger.exception(f"Erro ao obter atividade do Corpus: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falha ao obter log de atividade do Corpus.",
        )


@router.post("/admin/backfill/jurisdiction", response_model=CorpusBackfillJurisdictionResponse)
async def backfill_jurisdiction(
    request: CorpusBackfillJurisdictionRequest,
    ctx: OrgContext = Depends(get_org_context),
    service: CorpusService = Depends(get_corpus_service),
    _rl: None = Depends(corpus_write_limit),
) -> CorpusBackfillJurisdictionResponse:
    """
    Backfill do campo de jurisdição nos índices RAG (OpenSearch + Qdrant).

    Útil quando você adiciona o filtro por jurisdição no chat, mas os chunks
    já existentes não têm `metadata.jurisdiction` (OpenSearch) / `jurisdiction` (Qdrant).

    Segurança:
    - Restringe a `scope=global`
    - Requer admin da organização
    """
    _require_admin_org(ctx)
    try:
        return await service.backfill_global_jurisdiction(
            jurisdiction=request.jurisdiction,
            collections=request.collections,
            dry_run=bool(request.dry_run),
            limit=int(request.limit or 0),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Erro no backfill de jurisdição: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falha ao executar backfill de jurisdição.",
        )


@router.post("/admin/backfill/source-id", response_model=CorpusBackfillSourceIdResponse)
async def backfill_source_id(
    request: CorpusBackfillSourceIdRequest,
    ctx: OrgContext = Depends(get_org_context),
    service: CorpusService = Depends(get_corpus_service),
    _rl: None = Depends(corpus_write_limit),
) -> CorpusBackfillSourceIdResponse:
    """
    Backfill do campo `source_id` nos índices RAG (OpenSearch + Qdrant).

    Útil quando você adiciona o seletor de "Fontes regionais" no chat, mas os chunks
    já existentes não têm `metadata.source_id` (OpenSearch) / `source_id` (Qdrant).

    Segurança:
    - Restringe a `scope=global`
    - Requer admin da organização
    """
    _require_admin_org(ctx)
    try:
        return await service.backfill_global_source_id(
            source_id=request.source_id,
            collections=request.collections,
            dry_run=bool(request.dry_run),
            limit=int(request.limit or 0),
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Erro no backfill de source_id: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falha ao executar backfill de source_id.",
        )


@router.post("/admin/viewer/backfill", response_model=CorpusViewerBackfillResponse)
async def backfill_viewer_previews(
    request: CorpusViewerBackfillRequest,
    ctx: OrgContext = Depends(get_org_context),
    service: CorpusService = Depends(get_corpus_service),
    _rl: None = Depends(corpus_write_limit),
) -> CorpusViewerBackfillResponse:
    """
    Enfileira geração assíncrona de previews de viewer para documentos legados.
    """
    org_id = _require_admin_org(ctx)
    try:
        return await service.backfill_viewer_previews(
            org_id=org_id,
            limit=int(request.limit or 200),
            dry_run=bool(request.dry_run),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Erro no backfill de viewer previews: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falha ao executar backfill de previews de viewer.",
        )


# =============================================================================
# Verbatim — Extração literal com proveniência
# =============================================================================


@router.post("/verbatim", response_model=VerbatimResponse)
async def verbatim_extract(
    request: VerbatimRequest,
    ctx: OrgContext = Depends(get_org_context),
    service: CorpusService = Depends(get_corpus_service),
    _rl: None = Depends(corpus_search_limit),
) -> VerbatimResponse:
    """
    Extração verbatim de trechos do corpus com proveniência.

    Retorna trechos literais (texto bruto dos chunks) com metadados de
    página, linha e arquivo de origem. Não passa pelo LLM — apenas busca
    RAG e retorna os chunks mais relevantes na íntegra.
    """
    try:
        # Reutilizar busca do corpus
        search_response = await service.search_corpus(
            query=request.query,
            collections=request.collections,
            scope=None,
            user_id=ctx.user.id,
            org_id=ctx.organization_id,
            limit=request.limit,
        )

        excerpts: list[VerbatimExcerpt] = []
        for result in search_response.results:
            meta = result.metadata or {}

            # Filtrar por document_id se especificado
            result_doc_id = meta.get("doc_id") or result.document_id
            if request.document_id and result_doc_id != request.document_id:
                continue

            excerpts.append(VerbatimExcerpt(
                text=result.chunk_text,
                page_number=meta.get("page_number") or meta.get("page"),
                line_start=meta.get("line_start"),
                line_end=meta.get("line_end"),
                source_file=meta.get("source_file"),
                doc_id=result_doc_id,
                score=result.score,
                collection=result.collection,
                chunk_index=meta.get("chunk_index"),
            ))

        return VerbatimResponse(
            excerpts=excerpts,
            total=len(excerpts),
            query=request.query,
        )
    except Exception as e:
        logger.exception(f"Erro na extração verbatim: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falha na extração verbatim do corpus.",
        )


# =============================================================================
# Helpers
# =============================================================================


def _has_admin_permission(user: User) -> bool:
    """Verifica se o usuário tem permissões de administrador."""
    if hasattr(user, "role") and user.role == UserRole.ADMIN:
        return True
    if hasattr(user, "is_superuser") and user.is_superuser:
        return True
    return False
