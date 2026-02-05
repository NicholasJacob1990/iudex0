"""
Endpoints de documentos
"""

import os
import shutil
import uuid
import secrets
from datetime import timedelta
from typing import Optional, Dict, Any
import tempfile

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status, Form, Body
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger
from sqlalchemy.future import select
from sqlalchemy import func
from pydantic import BaseModel

from app.core.database import get_db
from app.core.config import settings
from app.core.security import get_current_user, get_org_context, OrgContext, build_tenant_filter
from app.core.time_utils import utcnow
from app.models.user import User
from app.models.document import Document, DocumentType, DocumentStatus
from app.schemas.document import (
    DocumentGenerationRequest,
    DocumentGenerationResponse,
    DocumentResponse,
    SignatureRequest,
    SignatureResponse,
)
from functools import lru_cache
from app.services.document_generator import DocumentGenerator
from app.services.ai.model_registry import (
    DEFAULT_JUDGE_MODEL,
    DEFAULT_DEBATE_MODELS,
    validate_model_id,
    validate_model_list,
)
from app.services.document_processor import (
    extract_text_from_pdf,
    extract_text_from_docx,
    extract_text_from_odt,
    extract_text_from_pptx,
    extract_text_from_xlsx,
    extract_text_from_csv,
    extract_text_from_rtf,
    extract_text_from_zip,
)

from app.services.docs_utils import save_as_word_juridico
from app.workers.tasks.document_tasks import (
    ocr_document_task,
    transcribe_audio_task,
    generate_podcast_task,
    generate_diagram_task,
    process_document_task,
    visual_index_task,
)

router = APIRouter()

# Lazy singleton: evita inicialização pesada (RAG/embeddings) em import-time.
@lru_cache(maxsize=1)
def get_document_generator() -> DocumentGenerator:
    return DocumentGenerator()


class ExportLegalDocxRequest(BaseModel):
    content: str
    filename: str = "documento.docx"
    modo: str = "GENERICO"


@router.post("/export/docx")
async def export_legal_docx(
    request: ExportLegalDocxRequest,
    ctx: OrgContext = Depends(get_org_context),
):
    """
    Converte Markdown em DOCX com formatação jurídica (ABNT/forense) e retorna como download.
    """
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            out_name = request.filename if request.filename.lower().endswith(".docx") else f"{request.filename}.docx"
            # Gera arquivo no tmpdir e devolve bytes
            save_as_word_juridico(request.content, out_name, tmpdir, modo=request.modo)
            out_path = os.path.join(tmpdir, out_name)
            if not os.path.exists(out_path):
                raise HTTPException(status_code=500, detail="Falha ao gerar DOCX")

            def iterfile():
                with open(out_path, "rb") as f:
                    yield from iter(lambda: f.read(1024 * 1024), b"")

            return StreamingResponse(
                iterfile(),
                media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                headers={"Content-Disposition": f'attachment; filename="{out_name}"'},
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao exportar DOCX jurídico: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/")
async def list_documents(
    skip: int = 0,
    limit: int = 50,
    search: Optional[str] = None,
    ctx: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db)
):
    """
    Listar documentos do tenant (org ou usuário)
    """
    current_user = ctx.user
    tenant_filter = build_tenant_filter(ctx, Document)
    query = select(Document).where(tenant_filter)

    if search:
        query = query.where(Document.name.ilike(f"%{search}%"))

    count_query = select(func.count()).select_from(Document).where(tenant_filter)
    if search:
        count_query = count_query.where(Document.name.ilike(f"%{search}%"))

    total = (await db.execute(count_query)).scalar() or 0
    result = await db.execute(
        query.order_by(Document.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    documents = result.scalars().all()
    return {"documents": documents, "total": total}


@router.get("/{document_id}")
async def get_document(
    document_id: str,
    ctx: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db)
):
    """
    Obter documento específico
    """
    result = await db.execute(
        select(Document).where(Document.id == document_id, build_tenant_filter(ctx, Document))
    )
    document = result.scalars().first()
    if not document:
        raise HTTPException(status_code=404, detail="Documento não encontrado")
    return document


@router.post("/upload", response_model=DocumentResponse)
async def upload_document(
    file: UploadFile = File(...),
    metadata: str | None = Form(default=None),
    ctx: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db)
):
    """
    Upload de documento com processamento automático
    """
    current_user = ctx.user
    try:
        parsed_metadata = {}
        if metadata:
            try:
                import json
                parsed_metadata = json.loads(metadata)
            except Exception:
                logger.warning("Não foi possível parsear metadata enviada, usando vazio.")
                parsed_metadata = {}

        # Criar diretório de upload se não existir
        upload_dir = os.path.join(settings.LOCAL_STORAGE_PATH, "uploads", str(current_user.id))
        os.makedirs(upload_dir, exist_ok=True)
        
        # Gerar nome de arquivo único
        file_ext = os.path.splitext(file.filename)[1].lower()
        file_id = str(uuid.uuid4())
        filename = f"{file_id}{file_ext}"
        file_path = os.path.join(upload_dir, filename)
        
        # Salvar arquivo
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # Determinar tipo de documento baseado na extensão
        doc_type = DocumentType.PDF  # Default
        
        # Documentos de texto
        if file_ext in ['.pdf']:
            doc_type = DocumentType.PDF
        elif file_ext in ['.docx']:
            doc_type = DocumentType.DOCX
        elif file_ext in ['.doc']:
            doc_type = DocumentType.DOC
        elif file_ext in ['.odt']:
            doc_type = DocumentType.ODT
        elif file_ext in ['.txt']:
            doc_type = DocumentType.TXT
        elif file_ext in ['.rtf']:
            doc_type = DocumentType.RTF
        elif file_ext in ['.html', '.htm']:
            doc_type = DocumentType.HTML
        elif file_ext in ['.pptx']:
            doc_type = DocumentType.PPTX
        elif file_ext in ['.xlsx']:
            doc_type = DocumentType.XLSX
        elif file_ext in ['.xls']:
            doc_type = DocumentType.XLS
        elif file_ext in ['.csv']:
            doc_type = DocumentType.CSV

        # Imagens
        elif file_ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff']:
            doc_type = DocumentType.IMAGE
        
        # Áudio
        elif file_ext in ['.mp3', '.wav', '.m4a', '.aac', '.ogg', '.flac']:
            doc_type = DocumentType.AUDIO
        
        # Vídeo
        elif file_ext in ['.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm', '.mkv']:
            doc_type = DocumentType.VIDEO
        
        # Arquivos compactados
        elif file_ext in ['.zip', '.rar', '.7z', '.tar', '.gz']:
            doc_type = DocumentType.ZIP
            
        # Criar registro no banco
        file_size = os.path.getsize(file_path)
        max_size_bytes = settings.max_upload_size_bytes
        if file_size > max_size_bytes:
            try:
                os.remove(file_path)
            except OSError:
                pass
            max_mb = settings.MAX_UPLOAD_SIZE_MB
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Arquivo excede o limite de {max_mb}MB.",
            )
        
        document = Document(
            id=file_id,
            user_id=current_user.id,
            organization_id=ctx.organization_id,
            name=file.filename,
            original_name=file.filename,
            type=doc_type,
            status=DocumentStatus.PROCESSING,
            size=file_size,
            url=file_path, # Em produção seria URL do S3
            doc_metadata={"local_path": file_path, **parsed_metadata},
            tags=parsed_metadata.get("tags", []),
            folder_id=parsed_metadata.get("folder_id")
        )
        
        db.add(document)
        await db.commit()
        
        # Extrair texto baseado no tipo de documento
        extracted_text = ""
        queued_task = False
        ocr_flag = parsed_metadata.get("ocr")
        transcribe_flag = parsed_metadata.get("transcribe")
        visual_index_flag = parsed_metadata.get("visual_index")
        try:
            if doc_type == DocumentType.PDF:
                extracted_text = await extract_text_from_pdf(file_path)
                # OCR assíncrono quando solicitado ou quando o PDF tem pouco texto
                needs_ocr = ocr_flag is True or (
                    ocr_flag is None and (not extracted_text or len(extracted_text.strip()) < 50)
                )
                if needs_ocr:
                    logger.info(f"PDF com pouco texto detectado, enfileirando OCR: {file_path}")
                    task = ocr_document_task.delay(document.id, file_path, settings.TESSERACT_LANG)
                    document.doc_metadata = {
                        **document.doc_metadata,
                        "ocr_status": "queued",
                        "ocr_task_id": task.id,
                        "ocr_requested": bool(ocr_flag),
                    }
                    queued_task = True

                # Indexação visual (ColPali) para PDFs com tabelas/figuras
                if visual_index_flag:
                    logger.info(f"Enfileirando indexação visual (ColPali): {file_path}")
                    tenant_id = parsed_metadata.get("tenant_id", str(current_user.id))
                    case_id = parsed_metadata.get("case_id")
                    visual_task = visual_index_task.delay(
                        document.id, file_path, tenant_id, case_id
                    )
                    document.doc_metadata = {
                        **document.doc_metadata,
                        "visual_index_status": "queued",
                        "visual_index_task_id": visual_task.id,
                    }
                    queued_task = True

                    
            elif doc_type == DocumentType.DOCX:
                extracted_text = await extract_text_from_docx(file_path)
                
            elif doc_type == DocumentType.ODT:
                extracted_text = await extract_text_from_odt(file_path)

            elif doc_type == DocumentType.PPTX:
                extracted_text = await extract_text_from_pptx(file_path)

            elif doc_type in (DocumentType.XLSX, DocumentType.XLS):
                extracted_text = await extract_text_from_xlsx(file_path)

            elif doc_type == DocumentType.CSV:
                extracted_text = await extract_text_from_csv(file_path)

            elif doc_type == DocumentType.RTF:
                extracted_text = await extract_text_from_rtf(file_path)

            elif doc_type == DocumentType.IMAGE:
                if ocr_flag is False:
                    logger.info(f"OCR desativado para imagem: {file_path}")
                else:
                    task = ocr_document_task.delay(document.id, file_path, settings.TESSERACT_LANG)
                    document.doc_metadata = {
                        **document.doc_metadata,
                        "ocr_status": "queued",
                        "ocr_task_id": task.id,
                        "ocr_requested": True,
                    }
                    queued_task = True
                
            elif doc_type == DocumentType.AUDIO:
                task = transcribe_audio_task.delay(
                    document.id,
                    file_path,
                    parsed_metadata.get("identify_speakers", False),
                )
                document.doc_metadata = {
                    **document.doc_metadata,
                    "transcription_status": "queued",
                    "transcription_task_id": task.id,
                    "transcribe_requested": bool(transcribe_flag),
                }
                queued_task = True
                
            elif doc_type == DocumentType.VIDEO:
                task = transcribe_audio_task.delay(
                    document.id,
                    file_path,
                    parsed_metadata.get("identify_speakers", False),
                )
                document.doc_metadata = {
                    **document.doc_metadata,
                    "transcription_status": "queued",
                    "transcription_task_id": task.id,
                    "transcribe_requested": bool(transcribe_flag),
                }
                queued_task = True
                
            elif doc_type == DocumentType.ZIP:
                zip_result = await extract_text_from_zip(file_path)
                extracted_text = zip_result.get("extracted_text", "")
                document.doc_metadata = {
                    **document.doc_metadata,
                    "zip_files": zip_result.get("files", []),
                    "zip_total_files": zip_result.get("total_files", 0),
                    "zip_errors": zip_result.get("errors", [])
                }
            
            if extracted_text:
                document.extracted_text = extracted_text

            # Atualizar status do documento
            if queued_task:
                document.status = DocumentStatus.PROCESSING
            else:
                # Documento aceito mas sem texto extraído (pode ser áudio, vídeo, etc)
                document.status = DocumentStatus.READY
                
            await db.commit()
            await db.refresh(document)
            
        except Exception as e:
            logger.error(f"Erro na extração de texto: {e}")
            document.status = DocumentStatus.ERROR
            document.doc_metadata = {**document.doc_metadata, "error": str(e)}
            await db.commit()
            
        return DocumentResponse.from_document(document)

    except Exception as e:
        logger.error(f"Erro no upload: {e}")
        raise HTTPException(status_code=500, detail=f"Erro no upload: {str(e)}")


@router.post("/from-text", response_model=DocumentResponse)
async def create_document_from_text(
    title: str = Form(...),
    content: str = Form(...),
    tags: str = Form(default=""),
    folder_id: Optional[str] = Form(default=None),
    ctx: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db)
):
    """
    Criar documento a partir de texto inserido manualmente
    """
    current_user = ctx.user
    try:
        # Parse tags
        tags_list = []
        if tags:
            tags_list = [tag.strip() for tag in tags.split(",") if tag.strip()]
        
        # Gerar ID único
        doc_id = str(uuid.uuid4())
        
        document = Document(
            id=doc_id,
            user_id=current_user.id,
            name=title,
            original_name=f"{title}.txt",
            type=DocumentType.TXT,
            status=DocumentStatus.READY,
            size=len(content.encode('utf-8')),
            url="",  # Texto inline, sem arquivo físico
            content=content,
            extracted_text=content,
            doc_metadata={"source": "manual_input"},
            tags=tags_list,
            folder_id=folder_id
        )
        
        db.add(document)
        await db.commit()
        await db.refresh(document)
        
        logger.info(f"Documento criado a partir de texto: {doc_id}")
        return DocumentResponse.from_document(document)
        
    except Exception as e:
        logger.error(f"Erro ao criar documento de texto: {e}")
        # Tentar fallback se for erro de integridade (ex: folder_id inválido)
        if "foreign key constraint" in str(e).lower() or "integrity" in str(e).lower():
            logger.warning(f"Falha de integridade ao salvar documento '{title}' com folder_id='{folder_id}'. Tentando salvar sem pasta.")
            try:
                # Rollback da transação falha
                await db.rollback()
                
                # Criar nova instância sem folder_id
                doc_id = str(uuid.uuid4())
                retry_document = Document(
                    id=doc_id,
                    user_id=current_user.id,
                    name=title,
                    original_name=f"{title}.txt",
                    type=DocumentType.TXT,
                    status=DocumentStatus.READY,
                    size=len(content.encode('utf-8')),
                    url="",
                    content=content,
                    extracted_text=content,
                    doc_metadata={"source": "manual_input", "fallback": "true", "original_error": str(e)},
                    tags=tags_list,
                    folder_id=None # Força None no retry
                )
                db.add(retry_document)
                await db.commit()
                await db.refresh(retry_document)
                logger.info(f"Documento salvo com sucesso no fallback (sem pasta): {doc_id}")
                return DocumentResponse.from_document(retry_document)
            except Exception as retry_idx:
                logger.error(f"Erro fatal no fallback de salvamento: {retry_idx}")
                raise HTTPException(status_code=500, detail=f"Erro ao salvar documento (fallback falhou): {str(retry_idx)}")

        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Erro ao criar documento: {str(e)}")


@router.post("/from-url", response_model=DocumentResponse)
async def create_document_from_url(
    url: str = Form(...),
    tags: str = Form(default=""),
    folder_id: Optional[str] = Form(default=None),
    ctx: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db)
):
    """
    Criar documento a partir de URL (web scraping)
    """
    current_user = ctx.user
    try:
        from app.services.url_scraper_service import url_scraper_service
        
        # Fazer scraping da URL
        scraped_data = await url_scraper_service.extract_content_from_url(url)
        
        # Verificar se houve erro
        if "error" in scraped_data:
            raise HTTPException(status_code=400, detail=scraped_data["error"])
        
        # Parse tags
        tags_list = []
        if tags:
            tags_list = [tag.strip() for tag in tags.split(",") if tag.strip()]
        
        # Adicionar tag de fonte
        tags_list.append("web_import")
        
        # Gerar ID único
        doc_id = str(uuid.uuid4())
        
        # Criar documento com conteúdo extraído
        title = scraped_data.get("title", "Documento sem título")
        content = scraped_data.get("content", "")
        
        document = Document(
            id=doc_id,
            user_id=current_user.id,
            name=title[:255],  # Limitar tamanho do título
            original_name=f"{title[:100]}.txt",
            type=DocumentType.TXT,
            status=DocumentStatus.READY,
            size=len(content.encode('utf-8')),
            url=url,  # URL de origem
            content=content,
            extracted_text=content,
            doc_metadata={
                "source": "url_import",
                "original_url": url,
                "scraped_metadata": scraped_data.get("metadata", {}),
                "word_count": scraped_data.get("word_count", 0)
            },
            tags=tags_list,
            folder_id=folder_id
        )
        
        db.add(document)
        await db.commit()
        await db.refresh(document)
        
        logger.info(f"Documento criado a partir de URL: {doc_id} - {url}")
        return DocumentResponse.from_document(document)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao importar de URL: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao importar URL: {str(e)}")


@router.get("/{document_id}")
async def get_document(
    document_id: str,
    ctx: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db)
):
    """
    Obter documento
    """
    result = await db.execute(
        select(Document).where(Document.id == document_id, build_tenant_filter(ctx, Document))
    )
    document = result.scalars().first()
    if not document:
        raise HTTPException(status_code=404, detail="Documento não encontrado")
    return document


@router.delete("/{document_id}")
async def delete_document(
    document_id: str,
    ctx: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db)
):
    """
    Deletar documento
    """
    result = await db.execute(
        select(Document).where(Document.id == document_id, build_tenant_filter(ctx, Document))
    )
    document = result.scalars().first()
    if not document:
        raise HTTPException(status_code=404, detail="Documento não encontrado")

    # Remover arquivo físico se existir
    if document.url and os.path.exists(document.url):
        try:
            os.remove(document.url)
        except Exception as e:
            logger.warning(f"Não foi possível remover arquivo local {document.url}: {e}")

    await db.delete(document)
    await db.commit()
    return {"message": "Document deleted"}


@router.post("/{document_id}/ocr")
async def apply_ocr(
    document_id: str,
    ctx: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db)
):
    """
    Aplicar OCR no documento
    """
    result = await db.execute(
        select(Document).where(Document.id == document_id, build_tenant_filter(ctx, Document))
    )
    document = result.scalars().first()
    if not document:
        raise HTTPException(status_code=404, detail="Documento não encontrado")

    if not document.url or not os.path.exists(document.url):
        raise HTTPException(status_code=400, detail="Arquivo do documento não encontrado")

    task = ocr_document_task.delay(document.id, document.url, settings.TESSERACT_LANG)
    document.status = DocumentStatus.PROCESSING
    document.doc_metadata = {
        **document.doc_metadata,
        "ocr_status": "queued",
        "ocr_task_id": task.id,
    }
    await db.commit()
    return {"message": "OCR queued", "document_id": document_id, "task_id": task.id}


@router.post("/{document_id}/summary")
async def generate_summary(
    document_id: str,
    ctx: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db)
):
    """
    Gerar resumo do documento
    """
    result = await db.execute(
        select(Document).where(Document.id == document_id, build_tenant_filter(ctx, Document))
    )
    document = result.scalars().first()
    if not document:
        raise HTTPException(status_code=404, detail="Documento não encontrado")

    summary = (document.extracted_text or document.content or "")[:500]
    return {"summary": summary, "document_id": document_id}


@router.post("/{document_id}/transcribe")
async def transcribe_audio(
    document_id: str,
    ctx: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db)
):
    """
    Transcrever áudio
    """
    result = await db.execute(
        select(Document).where(Document.id == document_id, build_tenant_filter(ctx, Document))
    )
    document = result.scalars().first()
    if not document:
        raise HTTPException(status_code=404, detail="Documento não encontrado")

    if not document.url or not os.path.exists(document.url):
        raise HTTPException(status_code=400, detail="Arquivo do documento não encontrado")

    task = transcribe_audio_task.delay(document.id, document.url, False)
    document.status = DocumentStatus.PROCESSING
    document.doc_metadata = {
        **document.doc_metadata,
        "transcription_status": "queued",
        "transcription_task_id": task.id,
    }
    await db.commit()
    return {"message": "Transcription queued", "document_id": document_id, "task_id": task.id}


@router.post("/{document_id}/podcast")
async def generate_podcast(
    document_id: str,
    ctx: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db)
):
    """
    Gerar podcast do documento usando TTS
    """
    result = await db.execute(
        select(Document).where(Document.id == document_id, build_tenant_filter(ctx, Document))
    )
    document = result.scalars().first()
    if not document:
        raise HTTPException(status_code=404, detail="Documento não encontrado")

    # Obter texto do documento
    text = document.extracted_text or document.content
    if not text:
        raise HTTPException(status_code=400, detail="Documento não possui texto para conversão")

    task = generate_podcast_task.delay(document.id)
    document.doc_metadata = {
        **document.doc_metadata,
        "podcast_status": "queued",
        "podcast_task_id": task.id,
    }
    await db.commit()

    return {"message": "Podcast queued", "document_id": document_id, "task_id": task.id}


@router.post("/{document_id}/diagram")
async def generate_diagram(
    document_id: str,
    diagram_type: str = "flowchart",
    ctx: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db)
):
    """
    Gerar diagrama Mermaid a partir do documento
    """
    result = await db.execute(
        select(Document).where(Document.id == document_id, build_tenant_filter(ctx, Document))
    )
    document = result.scalars().first()
    if not document:
        raise HTTPException(status_code=404, detail="Documento não encontrado")

    text = document.extracted_text or document.content
    if not text:
        raise HTTPException(status_code=400, detail="Documento não possui texto para diagrama")

    task = generate_diagram_task.delay(document.id, diagram_type)
    document.doc_metadata = {
        **document.doc_metadata,
        "diagram_status": "queued",
        "diagram_task_id": task.id,
        "diagram_type": diagram_type,
    }
    await db.commit()
    return {"message": "Diagram queued", "document_id": document_id, "task_id": task.id}


@router.post("/{document_id}/process")
async def process_document(
    document_id: str,
    options: Optional[Dict[str, Any]] = None,
    ctx: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db)
):
    """
    Processar documento (normalização, OCR ou IA). Atualiza status para PROCESSING.
    """
    current_user = ctx.user
    result = await db.execute(
        select(Document).where(Document.id == document_id, build_tenant_filter(ctx, Document))
    )
    document = result.scalars().first()
    if not document:
        raise HTTPException(status_code=404, detail="Documento não encontrado")

    if not document.url or not os.path.exists(document.url):
        raise HTTPException(status_code=400, detail="Arquivo do documento não encontrado")

    task = process_document_task.delay(document_id, str(current_user.id), document.url, options or {})
    document.status = DocumentStatus.PROCESSING
    document.doc_metadata = {
        **document.doc_metadata,
        "processing_options": options or {},
        "processing_task_id": task.id,
        "processing_status": "queued",
    }
    await db.commit()
    return {"message": "Processamento enfileirado", "document_id": document_id, "task_id": task.id}


@router.post("/generate", response_model=DocumentGenerationResponse)
async def generate_document(
    request: DocumentGenerationRequest,
    ctx: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db)
):
    """
    Gerar novo documento jurídico usando IA multi-agente

    Suporta:
    - Geração com diferentes níveis de esforço (1-5)
    - Templates personalizados
    - Assinatura automática (individual ou institucional)
    - Contexto de documentos existentes
    """
    current_user = ctx.user
    try:
        logger.info(f"Requisição de geração de documento: user={current_user.id}, type={request.document_type}")

        # Validar modelos (ids canônicos)
        try:
            judge_model = validate_model_id(
                request.model_selection or DEFAULT_JUDGE_MODEL,
                for_juridico=True,
                field_name="model_selection"
            )
            gpt_model = validate_model_id(
                request.model_gpt or (DEFAULT_DEBATE_MODELS[0] if DEFAULT_DEBATE_MODELS else "gpt-5.2"),
                for_agents=True,
                field_name="model_gpt"
            )
            claude_model = validate_model_id(
                request.model_claude or (DEFAULT_DEBATE_MODELS[1] if len(DEFAULT_DEBATE_MODELS) > 1 else "claude-4.5-sonnet"),
                for_agents=True,
                field_name="model_claude"
            )
            strategist_model = request.strategist_model
            if strategist_model:
                strategist_model = validate_model_id(strategist_model, for_agents=True, field_name="strategist_model")
            drafter_models = validate_model_list(request.drafter_models, for_agents=True, field_name="drafter_models")
            reviewer_models = validate_model_list(request.reviewer_models, for_agents=True, field_name="reviewer_models")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        request = request.copy(update={
            "model_selection": judge_model,
            "model_gpt": gpt_model,
            "model_claude": claude_model,
            "strategist_model": strategist_model,
            "drafter_models": drafter_models,
            "reviewer_models": reviewer_models,
        })
        
        # TODO: Buscar documentos de contexto se fornecidos
        context_data = {}
        if request.context_documents:
            # context_data["documents"] = await fetch_documents(request.context_documents, db)
            pass
        
        # Gerar documento
        result = await get_document_generator().generate_document(
            request=request,
            user=current_user,
            db=db,
            context_data=context_data
        )
        
        logger.info(f"Documento gerado com sucesso: {result.document_id}")
        
        # TODO: Salvar documento no banco de dados
        # await save_document_to_db(result, current_user.id, db)
        
        return result
        
    except Exception as e:
        logger.error(f"Erro ao gerar documento: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao gerar documento: {str(e)}"
        )


@router.post("/{document_id}/audit")
async def audit_document(
    document_id: str,
    ctx: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db)
):
    """
    Realizar Auditoria Jurídica no documento (Anti-Alucinação + Requisitos Processuais)
    Gera relatório em Markdown e DOCX.
    """
    current_user = ctx.user
    try:
        # 1. Buscar documento
        result = await db.execute(
            select(Document).where(Document.id == document_id, build_tenant_filter(ctx, Document))
        )
        document = result.scalars().first()
        if not document:
            raise HTTPException(status_code=404, detail="Documento não encontrado")
            
        # 2. Obter conteúdo
        content_to_audit = document.content or document.extracted_text
        if not content_to_audit or len(content_to_audit.strip()) < 50:
            raise HTTPException(status_code=400, detail="Documento sem conteúdo suficiente para auditoria")
            
        # 3. Executar Auditoria
        from app.services.ai.audit_service import AuditService
        audit_service = AuditService()
        
        # Definir pasta de output (mesma do upload/geração)
        if document.url and os.path.exists(document.url):
            output_folder = os.path.dirname(document.url)
        else:
             # Fallback folder
             output_folder = os.path.join(settings.LOCAL_STORAGE_PATH, "audit_reports", str(current_user.id))
             os.makedirs(output_folder, exist_ok=True)
             
        filename_base = os.path.splitext(document.original_name)[0]
        
        audit_result = await audit_service.auditar_peca(
            texto_completo=content_to_audit,
            output_folder=output_folder,
            filename_base=filename_base,
            raw_transcript=document.extracted_text or document.content or None,
        )
        
        if "error" in audit_result:
            raise HTTPException(status_code=500, detail=audit_result["error"])
            
        # 4. Atualizar Metadata
        document.doc_metadata = {
            **document.doc_metadata,
            "audit_report_md": audit_result["markdown_path"],
            "audit_report_docx": audit_result["docx_path"],
            "audit_date": utcnow().isoformat()
        }
        await db.commit()
        
        return {
            "message": "Auditoria concluída com sucesso",
            "document_id": document_id,
            "report_md": audit_result["markdown_path"],
            "report_docx": audit_result["docx_path"]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro na auditoria: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro na auditoria: {str(e)}"
        )


@router.get("/signature", response_model=SignatureResponse)
async def get_user_signature(
    ctx: OrgContext = Depends(get_org_context)
):
    """
    Obter dados de assinatura do usuário atual
    """
    current_user = ctx.user
    return SignatureResponse(
        user_id=current_user.id,
        signature_data=current_user.full_signature_data,
        created_at=current_user.created_at,
        updated_at=current_user.updated_at
    )


@router.put("/signature", response_model=SignatureResponse)
async def update_user_signature(
    signature: SignatureRequest,
    ctx: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db)
):
    """
    Atualizar assinatura do usuário

    Aceita:
    - signature_image: Imagem em base64
    - signature_text: Texto personalizado da assinatura
    """
    current_user = ctx.user
    try:
        logger.info(f"Atualizando assinatura do usuário: {current_user.id}")
        
        if signature.signature_image:
            current_user.signature_image = signature.signature_image
        
        if signature.signature_text:
            current_user.signature_text = signature.signature_text
        
        await db.commit()
        await db.refresh(current_user)
        
        logger.info(f"Assinatura atualizada: {current_user.id}")
        
        return SignatureResponse(
            user_id=current_user.id,
            signature_data=current_user.full_signature_data,
            created_at=current_user.created_at,
            updated_at=current_user.updated_at
        )
        
    except Exception as e:
        logger.error(f"Erro ao atualizar assinatura: {e}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao atualizar assinatura: {str(e)}"
        )


@router.post("/{document_id}/add-signature")
async def add_signature_to_document(
    document_id: str,
    ctx: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db)
):
    """
    Adicionar assinatura a um documento existente
    """
    current_user = ctx.user
    try:
        logger.info(f"Adicionando assinatura ao documento: {document_id}")
        
        # TODO: Buscar documento
        # document = await get_document_by_id(document_id, db)
        
        # TODO: Verificar se documento pertence ao usuário
        # if document.user_id != current_user.id:
        #     raise HTTPException(status_code=403, detail="Acesso negado")
        
        # TODO: Adicionar assinatura ao conteúdo do documento
        signature_data = current_user.full_signature_data
        
        # TODO: Salvar documento atualizado
        
        return {
            "message": "Assinatura adicionada com sucesso",
            "document_id": document_id,
            "signature_data": signature_data
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao adicionar assinatura: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao adicionar assinatura: {str(e)}"
        )


@router.post("/{document_id}/share")
async def share_document(
    document_id: str,
    expires_in_days: int = 7,
    access_level: str = "VIEW",
    ctx: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db)
):
    """
    Compartilhar documento via link público
    """
    result = await db.execute(
        select(Document).where(Document.id == document_id, build_tenant_filter(ctx, Document))
    )
    document = result.scalars().first()
    if not document:
        raise HTTPException(status_code=404, detail="Documento não encontrado")

    if not document.share_token:
        document.share_token = secrets.token_urlsafe(32)
    
    document.is_shared = True
    document.share_expires_at = utcnow() + timedelta(days=expires_in_days)
    document.share_access_level = access_level
    
    await db.commit()
    
    # Em produção, usar URL configurada
    base_url = settings.CORS_ORIGINS[0] if settings.CORS_ORIGINS else "http://localhost:3000"
    
    return {
        "share_url": f"{base_url}/share/{document.share_token}",
        "token": document.share_token,
        "expires_at": document.share_expires_at
    }


@router.delete("/{document_id}/share")
async def unshare_document(
    document_id: str,
    ctx: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db)
):
    """
    Remover compartilhamento do documento
    """
    result = await db.execute(
        select(Document).where(Document.id == document_id, build_tenant_filter(ctx, Document))
    )
    document = result.scalars().first()
    if not document:
        raise HTTPException(status_code=404, detail="Documento não encontrado")

    document.is_shared = False
    document.share_token = None
    document.share_expires_at = None
    
    await db.commit()
    
    return {"message": "Compartilhamento removido"}


@router.get("/share/{token}")
async def get_shared_document(
    token: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Acessar documento compartilhado (Público)
    """
    result = await db.execute(
        select(Document).where(Document.share_token == token)
    )
    document = result.scalars().first()
    
    if not document:
        raise HTTPException(status_code=404, detail="Documento não encontrado ou link inválido")
        
    if not document.is_shared:
        raise HTTPException(status_code=404, detail="Este link de compartilhamento foi desativado")
        
    if document.share_expires_at and document.share_expires_at < utcnow():
        raise HTTPException(status_code=410, detail="Este link de compartilhamento expirou")
        
    return {
        "id": document.id,
        "name": document.name,
        "content": document.content,
        "extracted_text": document.extracted_text,
        "type": document.type,
        "created_at": document.created_at,
        "access_level": document.share_access_level
    }
