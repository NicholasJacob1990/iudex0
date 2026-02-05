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

def _int_env(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except Exception:
        return int(default)


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


@celery_app.task(name="visual_index")
def visual_index_task(
    document_id: str,
    file_path: str,
    tenant_id: str,
    case_id: str | None = None,
):
    """
    Task para indexação visual de PDF usando ColPali.

    Processa o PDF como imagens e cria embeddings visuais para
    retrieval de documentos com tabelas, figuras e infográficos.
    """
    logger.info(f"[TASK] Indexando visualmente documento {document_id}")

    try:
        # Importa ColPali só quando necessário (modelo grande)
        from app.services.rag.core.colpali_service import get_colpali_service

        colpali = get_colpali_service()

        # Verifica se está habilitado
        if not colpali.config.enabled:
            logger.info(f"[TASK] ColPali desabilitado, pulando indexação visual")
            asyncio.run(
                _update_document(
                    document_id,
                    metadata_updates={
                        "visual_index_status": "skipped",
                        "visual_index_reason": "ColPali disabled",
                    },
                )
            )
            return {
                "success": True,
                "document_id": document_id,
                "status": "skipped",
                "reason": "ColPali disabled",
            }

        # Carrega modelo se necessário
        if not colpali._model_loaded:
            loaded = asyncio.run(colpali.load_model())
            if not loaded:
                raise RuntimeError("Failed to load ColPali model")

        # Indexa o PDF
        result = asyncio.run(
            colpali.index_pdf(
                pdf_path=file_path,
                doc_id=document_id,
                tenant_id=tenant_id,
                case_id=case_id,
            )
        )

        pages_indexed = result.get("pages_indexed", 0)

        asyncio.run(
            _update_document(
                document_id,
                metadata_updates={
                    "visual_index_status": "completed",
                    "visual_pages_indexed": pages_indexed,
                    "visual_index_collection": colpali.config.qdrant_collection,
                },
            )
        )

        logger.info(
            f"[TASK] Indexação visual concluída - Documento {document_id}, "
            f"{pages_indexed} páginas indexadas"
        )
        return {
            "success": True,
            "document_id": document_id,
            "pages_indexed": pages_indexed,
        }

    except Exception as e:
        logger.error(f"[TASK] Erro na indexação visual do documento {document_id}: {e}")
        asyncio.run(
            _update_document(
                document_id,
                metadata_updates={
                    "visual_index_status": "error",
                    "visual_index_error": str(e),
                },
            )
        )
        return {
            "success": False,
            "document_id": document_id,
            "error": str(e),
        }


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


@celery_app.task(
    name="transcription_job",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
    queue=os.getenv("IUDEX_CELERY_TRANSCRIPTION_QUEUE", "transcription"),
    soft_time_limit=_int_env("IUDEX_CELERY_TRANSCRIPTION_SOFT_TIME_LIMIT_SECONDS", 21600),  # 6 horas
    time_limit=_int_env("IUDEX_CELERY_TRANSCRIPTION_TIME_LIMIT_SECONDS", 22800),  # 6h20m (hard limit)
)
def transcription_job_task(
    self,
    job_id: str,
    file_paths: list[str],
    file_names: list[str],
    config: dict,
):
    """
    Task Celery para transcrição completa (APOSTILA, FIDELIDADE, etc).

    Roda em worker separado, sobrevive a restarts do servidor web.
    Suporta retry automático e checkpoints.
    """
    from app.services.transcription_service import TranscriptionService
    from app.services.job_manager import job_manager
    from app.services.api_call_tracker import job_context
    from pathlib import Path
    import json

    logger.info(f"[CELERY] Iniciando transcrição job {job_id}, files={file_names}")

    service = TranscriptionService()

    def sync_on_progress(stage: str, progress: int, message: str):
        """Callback síncrono para atualizar progresso."""
        job_manager.update_transcription_job(
            job_id,
            status="running",
            progress=progress,
            stage=stage,
            message=message,
        )

    async def async_on_progress(stage: str, progress: int, message: str):
        """Wrapper async para o callback."""
        sync_on_progress(stage, progress, message)

    async def run_transcription():
        """Executa a transcrição de forma assíncrona."""
        mode = config.get("mode", "APOSTILA")

        with job_context(job_id):
            if len(file_paths) == 1:
                result = await service.process_file_with_progress(
                    file_path=file_paths[0],
                    mode=mode,
                    thinking_level=config.get("thinking_level", "medium"),
                    custom_prompt=config.get("custom_prompt"),
                    disable_tables=bool(config.get("disable_tables", False)),
                    high_accuracy=config.get("high_accuracy", False),
                    transcription_engine=config.get("transcription_engine", "whisper"),
                    diarization=config.get("diarization"),
                    diarization_strict=config.get("diarization_strict", False),
                    on_progress=async_on_progress,
                    model_selection=config.get("model_selection", "gemini-3-flash-preview"),
                    use_cache=config.get("use_cache", True),
                    auto_apply_fixes=config.get("auto_apply_fixes", True),
                    auto_apply_content_fixes=config.get("auto_apply_content_fixes", False),
                    skip_legal_audit=config.get("skip_legal_audit", False),
                    skip_audit=config.get("skip_legal_audit", False),
                    skip_fidelity_audit=config.get("skip_fidelity_audit", False),
                    skip_sources_audit=config.get("skip_sources_audit", False),
                    language=config.get("language", "pt"),
                    output_language=config.get("output_language", ""),
                    speaker_roles=config.get("speaker_roles"),
                    speakers_expected=config.get("speakers_expected"),
                    subtitle_format=config.get("subtitle_format"),
                    area=config.get("area"),
                    custom_keyterms=config.get("custom_keyterms"),
                )
            else:
                result = await service.process_batch_with_progress(
                    file_paths=file_paths,
                    file_names=file_names,
                    mode=mode,
                    thinking_level=config.get("thinking_level", "medium"),
                    custom_prompt=config.get("custom_prompt"),
                    disable_tables=bool(config.get("disable_tables", False)),
                    high_accuracy=config.get("high_accuracy", False),
                    transcription_engine=config.get("transcription_engine", "whisper"),
                    diarization=config.get("diarization"),
                    diarization_strict=config.get("diarization_strict", False),
                    model_selection=config.get("model_selection", "gemini-3-flash-preview"),
                    on_progress=async_on_progress,
                    use_cache=config.get("use_cache", True),
                    auto_apply_fixes=config.get("auto_apply_fixes", True),
                    auto_apply_content_fixes=config.get("auto_apply_content_fixes", False),
                    skip_legal_audit=config.get("skip_legal_audit", False),
                    skip_audit=config.get("skip_legal_audit", False),
                    skip_fidelity_audit=config.get("skip_fidelity_audit", False),
                    skip_sources_audit=config.get("skip_sources_audit", False),
                    language=config.get("language", "pt"),
                    output_language=config.get("output_language", ""),
                )
        return result

    try:
        job_manager.update_transcription_job(
            job_id,
            status="running",
            progress=0,
            stage="starting",
            message="Iniciando processamento (Celery worker)",
            celery_task_id=getattr(self.request, "id", None),
        )

        # Executa a transcrição
        result = asyncio.run(run_transcription())

        # Salva resultado
        job_dir = Path(file_paths[0]).parent.parent
        result_path = job_dir / "result.json"

        # Prepara dados para salvar
        mode = config.get("mode", "APOSTILA")
        save_data = {
            "mode": mode,
            "file_names": file_names,
            "content": result if isinstance(result, str) else result.get("content", ""),
            "raw_content": result.get("raw_content") if isinstance(result, dict) else None,
            "validation_report": result.get("validation_report") if isinstance(result, dict) else None,
            "analysis_result": result.get("analysis_result") if isinstance(result, dict) else None,
        }
        result_path.write_text(json.dumps(save_data, ensure_ascii=False, indent=2), encoding="utf-8")

        job_manager.update_transcription_job(
            job_id,
            status="completed",
            progress=100,
            stage="complete",
            message="Concluído",
            result_path=str(result_path.resolve()),
        )

        logger.info(f"[CELERY] Transcrição {job_id} concluída com sucesso")
        return {
            "success": True,
            "job_id": job_id,
            "result_path": str(result_path),
        }

    except Exception as e:
        logger.error(f"[CELERY] Erro na transcrição {job_id}: {e}")

        # Tenta retry se não excedeu o limite
        if self.request.retries < self.max_retries:
            logger.info(f"[CELERY] Tentando retry {self.request.retries + 1}/{self.max_retries}")
            raise self.retry(exc=e)

        job_manager.update_transcription_job(
            job_id,
            status="error",
            progress=100,
            stage="error",
            message=str(e),
            error=str(e),
        )
        return {
            "success": False,
            "job_id": job_id,
            "error": str(e),
        }
