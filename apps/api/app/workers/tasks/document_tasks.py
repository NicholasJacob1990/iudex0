"""
Tasks Celery para processamento de documentos
"""

from loguru import logger
import asyncio
import os

from sqlalchemy import select

from app.workers.celery_app import celery_app
from app.core.database import AsyncSessionLocal
from app.core.time_utils import utcnow
from app.models.document import Document, DocumentStatus
from app.services.document_extraction_service import extract_text_from_path
from app.services.document_processor import (
    extract_text_from_image,
    transcribe_audio_video,
)
from app.services.document_viewer_service import DocumentViewerService
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
            current_meta = document.doc_metadata if isinstance(document.doc_metadata, dict) else {}
            document.doc_metadata = {**current_meta, **metadata_updates}
        if status:
            document.status = status

        await session.commit()


@celery_app.task(
    name="extract_document_text",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def extract_document_text_task(self, document_id: str, file_path: str) -> dict:
    """
    Extração assíncrona de texto para documentos grandes.
    """
    logger.info(f"[TASK] Extraindo texto do documento {document_id}")

    document = asyncio.run(_get_document(document_id))
    if not document:
        return {
            "success": False,
            "document_id": document_id,
            "error": "Documento não encontrado",
        }

    if (
        document.status == DocumentStatus.READY
        and bool((document.extracted_text or "").strip())
    ):
        logger.info(f"[TASK] Documento {document_id} já processado; ignorando")
        return {"success": True, "document_id": document_id, "skipped": True}

    try:
        asyncio.run(
            _update_document(
                document_id,
                status=DocumentStatus.PROCESSING,
                metadata_updates={
                    "extraction_status": "processing",
                    "extraction_task_id": getattr(self.request, "id", None),
                },
            )
        )

        result = asyncio.run(
            extract_text_from_path(
                file_path,
                min_pdf_chars=50,
                allow_pdf_ocr_fallback=True,
            )
        )
        text = str(result.text or "")
        ok = bool(text.strip())

        asyncio.run(
            _update_document(
                document_id,
                extracted_text=text,
                status=DocumentStatus.READY if ok else DocumentStatus.ERROR,
                metadata_updates={
                    **(result.metadata or {}),
                    "extraction_status": "completed" if ok else "failed",
                    "extraction_completed_at": utcnow().isoformat(),
                },
            )
        )

        return {
            "success": ok,
            "document_id": document_id,
            "extracted_chars": len(text),
        }
    except Exception as exc:
        logger.error(f"[TASK] Erro na extração {document_id}: {exc}")
        asyncio.run(
            _update_document(
                document_id,
                status=DocumentStatus.ERROR,
                metadata_updates={
                    "extraction_status": "error",
                    "extraction_error": str(exc),
                    "extraction_completed_at": utcnow().isoformat(),
                },
            )
        )
        raise self.retry(exc=exc)


@celery_app.task(
    name="generate_document_preview",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
)
def generate_document_preview_task(self, document_id: str, file_path: str) -> dict:
    """
    Gera preview HTML (office/openoffice) para viewer híbrido do corpus.
    """
    logger.info(f"[TASK] Gerando preview para documento {document_id}")

    document = asyncio.run(_get_document(document_id))
    if not document:
        return {
            "success": False,
            "document_id": document_id,
            "error": "Documento não encontrado",
        }

    viewer_service = DocumentViewerService()
    try:
        asyncio.run(
            _update_document(
                document_id,
                metadata_updates={
                    "viewer": {
                        "status": "processing",
                        "kind": "office_html",
                        "task_id": getattr(self.request, "id", None),
                    }
                },
            )
        )

        document = asyncio.run(_get_document(document_id))
        if not document:
            return {
                "success": False,
                "document_id": document_id,
                "error": "Documento não encontrado após atualização inicial",
            }

        preview_meta = viewer_service.generate_office_preview(
            document=document,
            local_path=file_path,
            extracted_text=document.extracted_text,
        )
        success = str(preview_meta.get("status") or "").lower() == "ready"

        asyncio.run(
            _update_document(
                document_id,
                metadata_updates={
                    "viewer": preview_meta,
                },
            )
        )

        return {
            "success": success,
            "document_id": document_id,
            "preview_status": preview_meta.get("status"),
            "viewer_kind": preview_meta.get("kind"),
        }
    except Exception as exc:
        logger.error(f"[TASK] Erro na geração de preview {document_id}: {exc}")
        asyncio.run(
            _update_document(
                document_id,
                metadata_updates={
                    "viewer": {
                        "status": "failed",
                        "kind": "office_html",
                        "error": str(exc),
                    }
                },
            )
        )
        raise self.retry(exc=exc)


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
            result = asyncio.run(
                extract_text_from_path(
                    file_path,
                    min_pdf_chars=50,
                    allow_pdf_ocr_fallback=True,
                    force_pdf_ocr=True,
                )
            )
            extracted_text = str(result.text or "")

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

    class JobCancelledError(Exception):
        """Sinaliza cancelamento cooperativo do job sem matar o worker."""

    def ensure_not_cancelled() -> None:
        current = job_manager.get_transcription_job(job_id)
        if str((current or {}).get("status", "")).lower() == "canceled":
            raise JobCancelledError("Cancelado pelo usuário.")

    def sync_on_progress(stage: str, progress: int, message: str):
        """Callback síncrono para atualizar progresso."""
        ensure_not_cancelled()
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
                    allow_provider_fallback=config.get("allow_provider_fallback"),
                    diarization=config.get("diarization"),
                    diarization_strict=config.get("diarization_strict", False),
                    diarization_provider=config.get("diarization_provider"),
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
                    allow_provider_fallback=config.get("allow_provider_fallback"),
                    diarization=config.get("diarization"),
                    diarization_strict=config.get("diarization_strict", False),
                    diarization_provider=config.get("diarization_provider"),
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
                    area=config.get("area"),
                    custom_keyterms=config.get("custom_keyterms"),
                )
        return result

    try:
        ensure_not_cancelled()
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
        if result is None:
            raise RuntimeError(
                "TranscriptionService retornou resultado vazio (None). "
                "Verifique provider/fallback configurado."
            )
        ensure_not_cancelled()

        # Salva resultado
        job_dir = Path(file_paths[0]).parent.parent
        result_path = job_dir / "result.json"

        def _resolve_storage_root() -> Path:
            try:
                from app.core.config import settings
                storage_path = Path(settings.LOCAL_STORAGE_PATH)
            except Exception:
                storage_path = Path("./storage")
            if not storage_path.is_absolute():
                backend_root = Path(__file__).resolve().parents[3]
                storage_path = backend_root / storage_path
            return storage_path

        def _infer_video_name(name_list: list[str]) -> str:
            if not name_list:
                return "Transcricao"
            base = Path(name_list[0]).stem or "Transcricao"
            if len(name_list) > 1:
                return f"{base}_UNIFICADO"
            return base

        def _discover_or_create_reports(
            *,
            report_map: dict,
            mode_value: str,
            name_list: list[str],
            content_value: str,
            raw_value: str,
            quality_map: dict,
        ) -> dict:
            reports = dict(report_map or {})
            if reports:
                return reports

            mode_suffix = (mode_value or "APOSTILA").upper()
            video_name = _infer_video_name(name_list)
            storage_root = _resolve_storage_root()
            transcriptions_root = storage_root / "transcriptions" / video_name

            expected_files = {
                "raw_path": f"{video_name}_RAW.txt",
                "md_path": f"{video_name}_{mode_suffix}.md",
                "analysis_path": f"{video_name}_{mode_suffix}_ANALISE.json",
                "validation_path": f"{video_name}_{mode_suffix}_FIDELIDADE.json",
                "legal_audit_path": f"{video_name}_{mode_suffix}_AUDITORIA.md",
                "preventive_fidelity_json_path": f"{video_name}_{mode_suffix}_AUDITORIA_FIDELIDADE.json",
                "preventive_fidelity_md_path": f"{video_name}_{mode_suffix}_AUDITORIA_FIDELIDADE.md",
                "structure_audit_path": f"{video_name}_{mode_suffix}_verificacao.txt",
                "coverage_path": f"{video_name}_validacao.txt",
                "fidelity_path": f"{video_name}_{mode_suffix}_fidelidade.json",
                "revision_path": f"{video_name}_{mode_suffix}_REVISAO.md",
                "suggestions_path": f"{video_name}_{mode_suffix}_SUGESTOES.json",
            }

            if transcriptions_root.exists():
                candidate_dirs = sorted(
                    [p for p in transcriptions_root.iterdir() if p.is_dir()],
                    key=lambda p: p.name,
                    reverse=True,
                )
                for run_dir in candidate_dirs:
                    recovered: dict[str, str] = {"output_dir": str(run_dir)}
                    for key, filename in expected_files.items():
                        fpath = run_dir / filename
                        if fpath.exists():
                            recovered[key] = str(fpath)
                    if recovered.get("md_path") and recovered.get("raw_path"):
                        if recovered.get("legal_audit_path") and not recovered.get("audit_path"):
                            recovered["audit_path"] = recovered["legal_audit_path"]
                        return recovered

            # Fallback defensivo: materializa artefatos mínimos no storage.
            from datetime import datetime
            run_dir = transcriptions_root / datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            run_dir.mkdir(parents=True, exist_ok=True)

            raw_path = run_dir / expected_files["raw_path"]
            md_path = run_dir / expected_files["md_path"]
            raw_path.write_text(raw_value or content_value or "", encoding="utf-8")
            md_path.write_text(content_value or raw_value or "", encoding="utf-8")

            recovered = {
                "output_dir": str(run_dir),
                "raw_path": str(raw_path),
                "md_path": str(md_path),
            }

            validation_report = quality_map.get("validation_report")
            analysis_result = quality_map.get("analysis_result")
            if validation_report:
                validation_path = run_dir / expected_files["validation_path"]
                validation_path.write_text(
                    json.dumps(validation_report, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                recovered["validation_path"] = str(validation_path)
            if analysis_result:
                analysis_path = run_dir / expected_files["analysis_path"]
                analysis_path.write_text(
                    json.dumps(analysis_result, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                recovered["analysis_path"] = str(analysis_path)
            return recovered

        # Prepara dados para salvar (inclui TODOS os campos retornados pelo TranscriptionService)
        mode = config.get("mode", "APOSTILA")
        content_text = result if isinstance(result, str) else str(result.get("content", "") or "")
        raw_text = content_text if isinstance(result, str) else str(result.get("raw_content") or content_text)
        quality_data = {} if isinstance(result, str) else (result.get("quality") or {})
        reports_data = {} if isinstance(result, str) else (result.get("reports") or {})
        if not isinstance(quality_data, dict):
            quality_data = {}
        if not isinstance(reports_data, dict):
            reports_data = {}
        if (mode or "").upper() != "RAW":
            reports_data = _discover_or_create_reports(
                report_map=reports_data,
                mode_value=mode,
                name_list=file_names,
                content_value=content_text,
                raw_value=raw_text,
                quality_map=quality_data,
            )

        content_path = job_dir / "content.md"
        raw_path = job_dir / "raw.txt"
        content_path.write_text(content_text, encoding="utf-8")
        raw_path.write_text(raw_text, encoding="utf-8")

        reports_path = None
        if reports_data:
            reports_path = job_dir / "reports.json"
            reports_path.write_text(json.dumps(reports_data, ensure_ascii=False, indent=2), encoding="utf-8")

        audit_issues = [] if isinstance(result, str) else (result.get("audit_issues") or [])
        if not isinstance(audit_issues, list):
            audit_issues = []
        audit_path = None
        if audit_issues:
            audit_path = job_dir / "audit_issues.json"
            audit_path.write_text(json.dumps(audit_issues, ensure_ascii=False, indent=2), encoding="utf-8")

        save_data = {
            "job_type": "vomo",
            "mode": mode,
            "file_names": file_names,
            "content": content_text,
            "raw_content": raw_text,
            "content_path": str(content_path),
            "raw_path": str(raw_path),
            "reports_path": str(reports_path) if reports_path else None,
            "reports": reports_data,
            "audit_path": str(audit_path) if audit_path else None,
            "audit_issues": audit_issues,
            "audit_summary": None if isinstance(result, str) else result.get("audit_summary"),
            "quality": quality_data,
            "words": None if isinstance(result, str) else result.get("words"),  # Word-level timestamps para player
            # Campos legacy para compatibilidade
            "validation_report": quality_data.get("validation_report"),
            "analysis_result": quality_data.get("analysis_result"),
        }

        ensure_not_cancelled()
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

    except JobCancelledError:
        current = job_manager.get_transcription_job(job_id) or {}
        job_manager.update_transcription_job(
            job_id,
            status="canceled",
            progress=int(current.get("progress") or 0),
            stage="canceled",
            message="Cancelado pelo usuário.",
        )
        logger.info(f"[CELERY] Job {job_id} cancelado cooperativamente")
        return {
            "success": False,
            "job_id": job_id,
            "canceled": True,
        }
    except Exception as e:
        logger.error(f"[CELERY] Erro na transcrição {job_id}: {e}")

        # Tenta retry se não excedeu o limite
        if self.request.retries < self.max_retries:
            retry_num = self.request.retries + 1
            logger.info(f"[CELERY] Tentando retry {retry_num}/{self.max_retries}")
            job_manager.update_transcription_job(
                job_id,
                stage="retrying",
                message=f"Retry {retry_num}/{self.max_retries}: {str(e)[:120]}",
                error=str(e),
            )
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
