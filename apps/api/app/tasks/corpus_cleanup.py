"""
Corpus Cleanup Task — Remove documentos expirados com base nas retention policies.

Projetada para ser executada periodicamente (cron / Celery beat / BackgroundTasks).

Fluxo:
1. Carrega todos os CorpusRetentionConfig com auto_delete=True.
2. Para cada config, busca documentos cujo (rag_ingested_at + retention_days) < now.
3. Remove os documentos dos indices RAG (OpenSearch + Qdrant).
4. Atualiza status no PostgreSQL.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import List

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.corpus_retention import CorpusRetentionConfig
from app.models.document import Document

logger = logging.getLogger(__name__)


async def cleanup_expired_corpus_documents() -> dict:
    """
    Background task que remove documentos expirados com base nas
    politicas de retencao persistidas.

    Returns:
        dict com estatisticas: {"checked": int, "removed": int, "errors": int}
    """
    stats = {"checked": 0, "removed": 0, "errors": 0}

    async with AsyncSessionLocal() as db:
        try:
            # 1. Carregar todas as configs com auto_delete=True
            result = await db.execute(
                select(CorpusRetentionConfig).where(
                    CorpusRetentionConfig.auto_delete == True,  # noqa: E712
                    CorpusRetentionConfig.retention_days.isnot(None),
                )
            )
            configs = result.scalars().all()

            if not configs:
                logger.info("Nenhuma politica de retencao com auto_delete encontrada.")
                return stats

            now = datetime.now(timezone.utc)

            for config in configs:
                cutoff_date = now - timedelta(days=config.retention_days)

                # 2. Buscar documentos expirados para esta config
                filters = [
                    Document.organization_id == config.organization_id,
                    Document.rag_ingested == True,  # noqa: E712
                    Document.rag_scope == config.scope,
                    Document.rag_ingested_at < cutoff_date,
                ]
                if config.collection is not None:
                    # Filtrar por colecao via metadados
                    # Como collection nao e uma coluna direta, filtramos apos busca
                    pass

                doc_result = await db.execute(
                    select(Document).where(and_(*filters))
                )
                expired_docs = doc_result.scalars().all()
                stats["checked"] += len(expired_docs)

                for doc in expired_docs:
                    try:
                        # Se config tem collection especifica, verificar match
                        if config.collection is not None:
                            doc_collection = _infer_collection(doc)
                            if doc_collection != config.collection:
                                continue

                        # 3. Remover dos indices RAG
                        await _remove_from_rag_indices(doc.id)

                        # 4. Atualizar status no PostgreSQL
                        doc.rag_ingested = False
                        doc.rag_ingested_at = None
                        doc.rag_scope = None

                        stats["removed"] += 1
                        logger.info(
                            "Documento expirado removido do Corpus: id=%s, org=%s, scope=%s",
                            doc.id,
                            config.organization_id,
                            config.scope,
                        )

                    except Exception as e:
                        stats["errors"] += 1
                        logger.error(
                            "Erro ao remover documento expirado %s: %s",
                            doc.id,
                            e,
                        )

            await db.commit()

        except Exception as e:
            logger.error("Erro no cleanup de documentos expirados: %s", e)
            await db.rollback()

    logger.info(
        "Cleanup concluido: checked=%d, removed=%d, errors=%d",
        stats["checked"],
        stats["removed"],
        stats["errors"],
    )
    return stats


async def _remove_from_rag_indices(document_id: str) -> None:
    """Remove documento dos indices OpenSearch e Qdrant."""
    from app.services.corpus_service import (
        COLLECTION_TO_QDRANT,
        _get_opensearch_service,
        _get_qdrant_service,
    )

    # OpenSearch
    try:
        os_service = _get_opensearch_service()
        os_service.delete_by_doc_id(doc_id=document_id)
    except Exception as e:
        logger.warning("Falha ao remover %s do OpenSearch: %s", document_id, e)

    # Qdrant
    try:
        qdrant = _get_qdrant_service()
        for coll_type in COLLECTION_TO_QDRANT:
            try:
                from app.services.rag.storage.qdrant_service import (
                    FieldCondition,
                    Filter,
                    MatchValue,
                )

                delete_filter = Filter(
                    must=[
                        FieldCondition(
                            key="doc_id",
                            match=MatchValue(value=document_id),
                        )
                    ]
                )
                qdrant_coll = COLLECTION_TO_QDRANT[coll_type]
                qdrant.delete_by_filter(
                    collection_type=qdrant_coll,
                    filter_conditions=delete_filter,
                )
            except Exception:
                continue
    except Exception as e:
        logger.warning("Falha ao remover %s do Qdrant: %s", document_id, e)


def _infer_collection(doc: Document) -> str | None:
    """Infere colecao do documento (replica logica do CorpusService)."""
    meta = doc.doc_metadata or {}
    source_type = meta.get("source_type") or meta.get("dataset")
    if source_type:
        return source_type

    if doc.category:
        category_map = {
            "LEI": "lei",
            "SENTENCA": "juris",
            "ACORDAO": "juris",
            "PETICAO": "pecas_modelo",
            "PARECER": "sei",
        }
        cat_val = doc.category.value if hasattr(doc.category, "value") else str(doc.category)
        return category_map.get(cat_val)

    return None
