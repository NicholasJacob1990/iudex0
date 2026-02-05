"""
Endpoints de conhecimento (legislação, jurisprudência, web, verificação de citações)
Retornam resultados mockados para demonstração funcional.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger

from app.core.security import get_current_user
from app.services.legislation_service import legislation_service
from app.services.jurisprudence_service import jurisprudence_service
from app.services.web_search_service import web_search_service
from app.services.jurisprudence_verifier import (
    jurisprudence_verifier,
    ExtractedCitation,
)
from app.schemas.citation_verification import (
    VerifyCitationsRequest,
    VerifyCitationsResponse,
    ShepardizeRequest,
    ShepardizeResponse,
    CitationVerificationItem,
)
import hashlib

router = APIRouter()


@router.get("/legislation/search")
async def search_legislation(
    query: str = Query(..., min_length=2),
    tipo: str | None = None,
    limit: int = 10,
    current_user: dict = Depends(get_current_user),
):
    """
    Pesquisa semântica de legislação (base local).
    """
    payload = await legislation_service.search(query, tipo=tipo, limit=limit)
    raw_results = payload.get("results", []) if isinstance(payload, dict) else []

    items = []
    for law in raw_results:
        law_id = law.get("id") or hashlib.md5(
            f"{law.get('numero', '')}-{law.get('nome', '')}".encode()
        ).hexdigest()[:10]
        items.append(
            {
                "id": law_id,
                "title": law.get("nome") or law.get("titulo") or law.get("numero") or "Lei",
                "excerpt": law.get("ementa") or law.get("resumo") or "",
                "status": law.get("status") or law.get("tipo") or "Atualizada",
                "updated_at": law.get("updated_at") or law.get("ano"),
                "numero": law.get("numero"),
                "tipo": law.get("tipo"),
                "url": law.get("url"),
                "source": "local_database",
            }
        )

    return {"items": items, "total": len(items), "query": query, "tipo": tipo}


@router.get("/jurisprudence/search")
async def search_jurisprudence(
    query: str = Query(..., min_length=2),
    court: str | None = None,
    tema: str | None = None,
    limit: int = 10,
    current_user: dict = Depends(get_current_user),
):
    """
    Pesquisa de jurisprudência (base local).
    """
    return await jurisprudence_service.search(
        query=query,
        court=court,
        tema=tema,
        limit=limit
    )


@router.get("/web/search")
async def search_web(
    query: str = Query(..., min_length=2),
    limit: int = 10,
    multi_query: bool = True,
    use_cache: bool = True,
    country: str | None = None,
    search_region: str | None = None,
    search_city: str | None = None,
    search_latitude: str | None = None,
    search_longitude: str | None = None,
    domain_filter: list[str] | None = Query(None),
    language_filter: list[str] | None = Query(None),
    recency_filter: str | None = None,
    search_mode: str | None = None,
    search_after_date: str | None = None,
    search_before_date: str | None = None,
    last_updated_after: str | None = None,
    last_updated_before: str | None = None,
    max_tokens: int | None = None,
    max_tokens_per_page: int | None = None,
    return_images: bool = False,
    return_videos: bool = False,
    return_snippets: bool = True,
    current_user: dict = Depends(get_current_user),
):
    """
    Pesquisa web real com cache (Perplexity → Serper → DuckDuckGo).
    """
    search_kwargs = {
        "country": country,
        "search_region": search_region,
        "search_city": search_city,
        "search_latitude": search_latitude,
        "search_longitude": search_longitude,
        "domain_filter": domain_filter,
        "language_filter": language_filter,
        "recency_filter": recency_filter,
        "search_mode": search_mode,
        "search_after_date": search_after_date,
        "search_before_date": search_before_date,
        "last_updated_after": last_updated_after,
        "last_updated_before": last_updated_before,
        "max_tokens": max_tokens,
        "max_tokens_per_page": max_tokens_per_page,
        "return_images": return_images,
        "return_videos": return_videos,
        "return_snippets": return_snippets,
    }
    if multi_query:
        payload = await web_search_service.search_multi(
            query=query,
            num_results=limit,
            use_cache=use_cache,
            **search_kwargs,
        )
    else:
        payload = await web_search_service.search(
            query=query,
            num_results=limit,
            use_cache=use_cache,
            **search_kwargs,
        )

    raw_results = payload.get("results", []) if isinstance(payload, dict) else []
    items = []
    for idx, result in enumerate(raw_results):
        url = result.get("url", "")
        item_id = result.get("id") or (
            hashlib.md5(url.encode()).hexdigest()[:10] if url else f"web-{idx + 1}"
        )
        items.append(
            {
                "id": item_id,
                "title": result.get("title") or url,
                "url": url,
                "snippet": result.get("snippet"),
                "date": result.get("date"),
                "last_updated": result.get("last_updated"),
                "images": result.get("images"),
                "query": result.get("query"),
                "source": result.get("source") or payload.get("source"),
            }
        )

    return {
        "items": items,
        "total": len(items),
        "query": query,
        "queries": payload.get("queries"),
        "search_id": payload.get("search_id"),
        "source": payload.get("source"),
        "cached": payload.get("cached", False),
    }


# ---------------------------------------------------------------------------
# Verificação de Citações / Shepardização BR
# ---------------------------------------------------------------------------


@router.post("/verify-citations", response_model=VerifyCitationsResponse)
async def verify_citations(
    request: VerifyCitationsRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Verifica vigência de citações jurídicas (Shepardização BR).

    Aceita texto livre (extrai citações automaticamente) ou lista explícita de citações.
    Retorna status de cada citação: vigente, superada, revogada, alterada, inconstitucional.
    """
    if not request.text and not request.citations:
        raise HTTPException(
            status_code=422,
            detail="Informe 'text' (texto jurídico) ou 'citations' (lista de citações).",
        )

    try:
        if request.text:
            # Extrai e verifica citações do texto
            report = await jurisprudence_verifier.verify_text(
                text=request.text,
                use_llm_extraction=request.use_llm_extraction,
                use_cache=request.use_cache,
            )
        else:
            # Verifica lista explícita de citações
            extracted = [
                ExtractedCitation(
                    text=c,
                    citation_type="outro",
                    normalized=c,
                )
                for c in (request.citations or [])
            ]
            results = await jurisprudence_verifier.verify_citations(
                extracted,
                use_cache=request.use_cache,
            )

            vigentes = sum(1 for r in results if r.status == "vigente")
            problematic = sum(
                1 for r in results
                if r.status in ("superada", "revogada", "alterada", "inconstitucional")
            )
            nao_verificadas = sum(1 for r in results if r.status == "nao_verificada")
            from datetime import datetime, timezone

            report_data = {
                "total_citations": len(results),
                "verified": len(results) - nao_verificadas,
                "vigentes": vigentes,
                "problematic": problematic,
                "citations": [r.model_dump() for r in results],
                "summary": (
                    f"Total: {len(results)}. Vigentes: {vigentes}. "
                    + (f"Problemas: {problematic}." if problematic else "")
                ),
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }
            return VerifyCitationsResponse(**report_data)

        return VerifyCitationsResponse(**report.model_dump())

    except Exception as e:
        logger.error(f"Erro em verify-citations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/shepardize", response_model=ShepardizeResponse)
async def shepardize_document(
    request: ShepardizeRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Shepardização completa de um documento.

    Busca o documento pelo ID, extrai todas as citações e verifica vigência de cada uma.
    Retorna relatório completo.
    """
    from sqlalchemy import select
    from app.core.database import AsyncSessionLocal
    from app.models.document import Document

    try:
        # Buscar documento no banco
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Document).where(Document.id == request.document_id)
            )
            document = result.scalar_one_or_none()

        if not document:
            raise HTTPException(
                status_code=404,
                detail=f"Documento '{request.document_id}' não encontrado.",
            )

        # Obter texto do documento
        doc_text = document.extracted_text or document.content or ""
        if not doc_text.strip():
            raise HTTPException(
                status_code=422,
                detail="Documento não possui conteúdo textual extraído.",
            )

        # Shepardizar
        report = await jurisprudence_verifier.shepardize_document(
            document_id=request.document_id,
            document_text=doc_text,
            use_cache=request.use_cache,
        )

        return ShepardizeResponse(**report.model_dump())

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro em shepardize: {e}")
        raise HTTPException(status_code=500, detail=str(e))
