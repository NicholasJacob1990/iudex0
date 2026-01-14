"""
Endpoints de conhecimento (legislação, jurisprudência, web)
Retornam resultados mockados para demonstração funcional.
"""

from fastapi import APIRouter, Depends, Query
from app.core.security import get_current_user
from app.services.legislation_service import legislation_service
from app.services.jurisprudence_service import jurisprudence_service
from app.services.web_search_service import web_search_service
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
    current_user: dict = Depends(get_current_user),
):
    """
    Pesquisa web real com cache (Serper ou DuckDuckGo).
    """
    if multi_query:
        payload = await web_search_service.search_multi(
            query=query,
            num_results=limit,
            use_cache=use_cache
        )
    else:
        payload = await web_search_service.search(
            query=query,
            num_results=limit,
            use_cache=use_cache
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
                "source": result.get("source") or payload.get("source"),
            }
        )

    return {
        "items": items,
        "total": len(items),
        "query": query,
        "source": payload.get("source"),
        "cached": payload.get("cached", False),
    }
