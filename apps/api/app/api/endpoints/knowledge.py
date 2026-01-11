"""
Endpoints de conhecimento (legislação, jurisprudência, web)
Retornam resultados mockados para demonstração funcional.
"""

from fastapi import APIRouter, Depends, Query
from app.core.security import get_current_user

router = APIRouter()


@router.get("/legislation/search")
async def search_legislation(
    query: str = Query(..., min_length=2),
    current_user: dict = Depends(get_current_user),
):
    """
    Pesquisa semântica de legislação (mock).
    """
    results = [
        {
            "id": "leg-1",
            "title": "Lei Geral de Proteção de Dados (Lei 13.709/2018)",
            "excerpt": "Dispõe sobre o tratamento de dados pessoais...",
            "status": "Consolidada",
            "updated_at": "2024-04-01T10:00:00Z",
        },
        {
            "id": "leg-2",
            "title": "Lei nº 14.133/2021 - Nova Lei de Licitações",
            "excerpt": "Institui normas gerais de licitação e contratação...",
            "status": "Atualizada em 34 minutos",
            "updated_at": "2024-04-10T09:30:00Z",
        },
    ]
    return {"items": results, "total": len(results), "query": query}


@router.get("/jurisprudence/search")
async def search_jurisprudence(
    query: str = Query(..., min_length=2),
    court: str | None = None,
    current_user: dict = Depends(get_current_user),
):
    """
    Pesquisa de jurisprudência (mock).
    """
    data = [
        {
            "id": "jp-1",
            "court": "STJ",
            "title": "Dano Moral por Negativação Indevida",
            "summary": "Caracteriza dano moral in re ipsa a inscrição indevida...",
            "date": "2024-03-15",
            "tags": ["Dano Moral", "Consumidor"],
            "processNumber": "REsp 1.234.567/SP",
        },
        {
            "id": "jp-2",
            "court": "STF",
            "title": "Tema 1234 - Repercussão Geral",
            "summary": "Inconstitucional a exigência de garantia para impressão de notas fiscais...",
            "date": "2024-02-10",
            "tags": ["Tributário", "Livre Iniciativa"],
            "processNumber": "RE 987.654/RJ",
        },
    ]
    if court:
        data = [item for item in data if item["court"] == court]
    return {"items": data, "total": len(data), "query": query, "court": court}


@router.get("/web/search")
async def search_web(
    query: str = Query(..., min_length=2),
    current_user: dict = Depends(get_current_user),
):
    """
    Pesquisa web simplificada (mock).
    """
    results = [
        {"id": "web-1", "title": "Resumo sobre repercussão geral", "url": "https://example.com/artigo", "snippet": "Entenda como funciona a repercussão geral no STF..."},
        {"id": "web-2", "title": "Guia prático de temas repetitivos", "url": "https://example.com/guia", "snippet": "Saiba como localizar e citar temas repetitivos do STJ..."},
    ]
    return {"items": results, "total": len(results), "query": query}

