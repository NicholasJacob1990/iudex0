"""
Tasks Celery para processamento de documentos
"""

from loguru import logger
import asyncio
import os

from sqlalchemy import select

from app.workers.celery_app import celery_app
from app.core.database import AsyncSessionLocal
from app.models.document import Document, DocumentStatus
from app.services.document_processor import (
    extract_text_from_pdf_with_ocr,
    extract_text_from_image,
    transcribe_audio_video,
)
from app.services.podcast_service import podcast_service
from app.services.diagram_generator_service import DiagramGeneratorService

diagram_generator_service = DiagramGeneratorService()


async def _get_document(document_id: str) -> Document | None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Document).where(Document.id == document_id)
        )
        return result.scalars().first()


async def _update_document(
    document_id: str,
    *,
    status: DocumentStatus | None = None,
    extracted_text: str | None = None,
    metadata_updates: dict | None = None,
) -> None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Document).where(Document.id == document_id)
        )
        document = result.scalars().first()
        if not document:
            return

        if extracted_text is not None:
            document.extracted_text = extracted_text
        if metadata_updates:
            document.doc_metadata = {**document.doc_metadata, **metadata_updates}
        if status:
            document.status = status

        await session.commit()


@celery_app.task(name="process_document")
def process_document_task(document_id: str, user_id: str, file_path: str, options: dict):
    """
    Task para processar documento
    - Extrai texto
    - Gera embeddings
    - Indexa para busca
    """
    logger.info(f"[TASK] Processando documento {document_id}")
    
    try:
        # TODO: Implementar processamento real
        # 1. Extrair texto baseado no tipo
        # 2. Gerar chunks
        # 3. Gerar embeddings
        # 4. Indexar no vector store
        # 5. Atualizar status no banco
        
        logger.info(f"[TASK] Documento {document_id} processado com sucesso")
        return {
            "success": True,
            "document_id": document_id,
            "message": "Documento processado"
        }
        
    except Exception as e:
        logger.error(f"[TASK] Erro ao processar documento {document_id}: {e}")
        return {
            "success": False,
            "document_id": document_id,
            "error": str(e)
        }


@celery_app.task(name="ocr_document")
def ocr_document_task(document_id: str, file_path: str, language: str = "por"):
    """
    Task para aplicar OCR em documento
    """
    logger.info(f"[TASK] Aplicando OCR no documento {document_id}")
    
    try:
        ext = os.path.splitext(file_path)[1].lower()
        if ext in {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff"}:
            extracted_text = asyncio.run(extract_text_from_image(file_path))
        else:
            extracted_text = asyncio.run(extract_text_from_pdf_with_ocr(file_path))

        asyncio.run(
            _update_document(
                document_id,
                status=DocumentStatus.READY,
                extracted_text=extracted_text,
                metadata_updates={"ocr_applied": True, "ocr_status": "completed"},
            )
        )
        logger.info(f"[TASK] OCR aplicado com sucesso no documento {document_id}")
        return {
            "success": True,
            "document_id": document_id,
            "extracted_text": extracted_text,
        }

    except Exception as e:
        logger.error(f"[TASK] Erro ao aplicar OCR no documento {document_id}: {e}")
        asyncio.run(
            _update_document(
                document_id,
                status=DocumentStatus.ERROR,
                metadata_updates={"ocr_status": "error", "ocr_error": str(e)},
            )
        )
        return {
            "success": False,
            "document_id": document_id,
            "error": str(e)
        }


@celery_app.task(name="transcribe_audio")
def transcribe_audio_task(
    document_id: str,
    audio_path: str,
    identify_speakers: bool = False
):
    """
    Task para transcrever áudio
    """
    logger.info(f"[TASK] Transcrevendo áudio do documento {document_id}")
    
    try:
        ext = os.path.splitext(audio_path)[1].lower()
        media_type = "video" if ext in {".mp4", ".avi", ".mov", ".wmv", ".flv", ".webm", ".mkv"} else "audio"

        transcription = asyncio.run(transcribe_audio_video(audio_path, media_type=media_type))
        asyncio.run(
            _update_document(
                document_id,
                status=DocumentStatus.READY,
                extracted_text=transcription,
                metadata_updates={
                    "transcribed": True,
                    "transcription_status": "completed",
                    "identify_speakers": identify_speakers,
                },
            )
        )

        logger.info(f"[TASK] Áudio transcrito com sucesso - Documento {document_id}")
        return {
            "success": True,
            "document_id": document_id,
            "transcription": transcription,
        }

    except Exception as e:
        logger.error(f"[TASK] Erro ao transcrever áudio do documento {document_id}: {e}")
        asyncio.run(
            _update_document(
                document_id,
                status=DocumentStatus.ERROR,
                metadata_updates={
                    "transcription_status": "error",
                    "transcription_error": str(e),
                },
            )
        )
        return {
            "success": False,
            "document_id": document_id,
            "error": str(e)
        }


@celery_app.task(name="generate_podcast")
def generate_podcast_task(document_id: str):
    """
    Task para gerar podcast (TTS) do documento.
    """
    logger.info(f"[TASK] Gerando podcast para o documento {document_id}")
    try:
        document = asyncio.run(_get_document(document_id))
        if not document:
            raise ValueError("Documento não encontrado")

        text = document.extracted_text or document.content or ""
        if not text:
            raise ValueError("Documento sem texto para TTS")

        result = asyncio.run(
            podcast_service.generate_podcast(
                text=text,
                title=f"Podcast: {document.name}",
            )
        )
        asyncio.run(
            _update_document(
                document_id,
                metadata_updates={
                    "podcast_url": result.get("url"),
                    "podcast_id": result.get("id"),
                    "podcast_status": result.get("status"),
                },
            )
        )
        return {"success": True, "document_id": document_id, **result}
    except Exception as e:
        logger.error(f"[TASK] Erro ao gerar podcast {document_id}: {e}")
        asyncio.run(
            _update_document(
                document_id,
                metadata_updates={"podcast_status": "error", "podcast_error": str(e)},
            )
        )
        return {"success": False, "document_id": document_id, "error": str(e)}


@celery_app.task(name="generate_diagram")
def generate_diagram_task(document_id: str, diagram_type: str = "flowchart"):
    """
    Task para gerar diagrama Mermaid a partir do conteúdo do documento.
    """
    logger.info(f"[TASK] Gerando diagrama para o documento {document_id}")
    try:
        document = asyncio.run(_get_document(document_id))
        if not document:
            raise ValueError("Documento não encontrado")

        text = document.extracted_text or document.content or ""
        if not text:
            raise ValueError("Documento sem texto para diagrama")

        result = asyncio.run(
            diagram_generator_service.generate_diagram(
                content=text,
                diagram_type=diagram_type,
            )
        )

        asyncio.run(
            _update_document(
                document_id,
                metadata_updates={
                    "diagram_status": "completed" if result.get("success") else "error",
                    "diagram_type": diagram_type,
                    "diagram_code": result.get("mermaid_code"),
                },
            )
        )
        return {"success": True, "document_id": document_id, **result}
    except Exception as e:
        logger.error(f"[TASK] Erro ao gerar diagrama {document_id}: {e}")
        asyncio.run(
            _update_document(
                document_id,
                metadata_updates={"diagram_status": "error", "diagram_error": str(e)},
            )
        )
        return {"success": False, "document_id": document_id, "error": str(e)}
