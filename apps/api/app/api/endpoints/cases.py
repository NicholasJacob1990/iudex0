import asyncio
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from loguru import logger
from pydantic import BaseModel

from app.core.database import get_db
from app.core.security import get_current_user, get_org_context, OrgContext, build_tenant_filter
from app.core.time_utils import utcnow
from app.models.user import User
from app.models.document import Document, DocumentStatus
from app.schemas.case import CaseCreate, CaseResponse, CaseUpdate
from app.services.case_service import CaseService

router = APIRouter()


# =============================================================================
# SCHEMAS
# =============================================================================


class DocumentAttachRequest(BaseModel):
    """Request to attach a document to a case."""
    auto_ingest_rag: bool = True
    auto_ingest_graph: bool = True


class CaseDocumentResponse(BaseModel):
    """Response for case document operations."""
    id: str
    name: str
    original_name: str
    type: str
    status: str
    case_id: Optional[str]
    rag_ingested: bool
    graph_ingested: bool
    created_at: datetime

    class Config:
        from_attributes = True


class AttachResponse(BaseModel):
    """Response after attaching document to case."""
    success: bool
    document_id: str
    case_id: str
    rag_ingestion_triggered: bool
    graph_ingestion_triggered: bool
    message: str

@router.get("/", response_model=List[CaseResponse])
async def get_cases(
    skip: int = 0,
    limit: int = 100,
    ctx: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db)
):
    """Listar casos do tenant (org ou usuário)"""
    service = CaseService(db)
    return await service.get_cases(ctx, skip, limit)

@router.post("/", response_model=CaseResponse)
async def create_case(
    case_in: CaseCreate,
    ctx: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db)
):
    """Criar novo caso"""
    service = CaseService(db)
    return await service.create_case(case_in, ctx)

@router.get("/{case_id}", response_model=CaseResponse)
async def get_case(
    case_id: str,
    ctx: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db)
):
    """Obter detalhes de um caso"""
    service = CaseService(db)
    case = await service.get_case(case_id, ctx)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return case

@router.put("/{case_id}", response_model=CaseResponse)
async def update_case(
    case_id: str,
    case_in: CaseUpdate,
    ctx: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db)
):
    """Atualizar caso"""
    service = CaseService(db)
    case = await service.update_case(case_id, case_in, ctx)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return case

@router.delete("/{case_id}")
async def delete_case(
    case_id: str,
    ctx: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db)
):
    """Arquivar/Deletar caso"""
    service = CaseService(db)
    success = await service.delete_case(case_id, ctx)
    if not success:
        raise HTTPException(status_code=404, detail="Case not found")
    return {"ok": True}


# =============================================================================
# DOCUMENT ATTACHMENT ENDPOINTS
# =============================================================================


@router.post("/{case_id}/documents/upload", response_model=AttachResponse)
async def upload_document_to_case(
    case_id: str,
    file: UploadFile = File(...),
    auto_ingest_rag: bool = Form(default=True),
    auto_ingest_graph: bool = Form(default=True),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    ctx: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db)
):
    """
    Upload a document directly to a case.

    This will:
    1. Upload and process the document
    2. Automatically attach it to the case
    3. Trigger RAG and Graph ingestion if enabled
    """
    import os
    import shutil
    import uuid as uuid_lib
    from app.core.config import settings
    from app.models.document import DocumentType

    current_user = ctx.user
    # Verify case ownership
    service = CaseService(db)
    case = await service.get_case(case_id, ctx)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    try:
        # Create upload directory
        upload_dir = os.path.join(settings.LOCAL_STORAGE_PATH, "uploads", str(current_user.id))
        os.makedirs(upload_dir, exist_ok=True)

        # Generate unique filename
        file_ext = os.path.splitext(file.filename)[1].lower()
        file_id = str(uuid_lib.uuid4())
        filename = f"{file_id}{file_ext}"
        file_path = os.path.join(upload_dir, filename)

        # Save file
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Determine document type
        doc_type = DocumentType.PDF
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
        elif file_ext in ['.html', '.htm']:
            doc_type = DocumentType.HTML
        elif file_ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff']:
            doc_type = DocumentType.IMAGE

        file_size = os.path.getsize(file_path)

        # Create document record with case_id
        document = Document(
            id=file_id,
            user_id=str(current_user.id),
            organization_id=ctx.organization_id,
            case_id=case_id,
            name=file.filename,
            original_name=file.filename,
            type=doc_type,
            status=DocumentStatus.PROCESSING,
            size=file_size,
            url=f"/uploads/{current_user.id}/{filename}",
            doc_metadata={"local_path": file_path},
            tags=[],
        )
        db.add(document)
        await db.commit()
        await db.refresh(document)

        # Extract text in background and trigger ingestion
        background_tasks.add_task(
            _process_and_ingest_document,
            doc_id=file_id,
            file_path=file_path,
            doc_type=doc_type,
            case_id=case_id,
            tenant_id=ctx.tenant_id,
            auto_ingest_rag=auto_ingest_rag,
            auto_ingest_graph=auto_ingest_graph,
        )

        return AttachResponse(
            success=True,
            document_id=file_id,
            case_id=case_id,
            rag_ingestion_triggered=auto_ingest_rag,
            graph_ingestion_triggered=auto_ingest_graph,
            message="Document uploaded. Processing and ingestion started in background."
        )

    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise HTTPException(status_code=500, detail="Falha no upload do documento")


@router.get("/{case_id}/documents", response_model=List[CaseDocumentResponse])
async def get_case_documents(
    case_id: str,
    ctx: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db)
):
    """List all documents attached to a case."""
    # Verify case ownership
    service = CaseService(db)
    case = await service.get_case(case_id, ctx)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    # Get documents for this case
    result = await db.execute(
        select(Document)
        .where(Document.case_id == case_id)
        .where(build_tenant_filter(ctx, Document))
        .where(Document.is_archived == False)
        .order_by(Document.created_at.desc())
    )
    documents = result.scalars().all()

    return [
        CaseDocumentResponse(
            id=doc.id,
            name=doc.name,
            original_name=doc.original_name,
            type=doc.type.value,
            status=doc.status.value,
            case_id=doc.case_id,
            rag_ingested=doc.rag_ingested,
            graph_ingested=doc.graph_ingested,
            created_at=doc.created_at,
        )
        for doc in documents
    ]


@router.post("/{case_id}/documents/{doc_id}/attach", response_model=AttachResponse)
async def attach_document_to_case(
    case_id: str,
    doc_id: str,
    request: DocumentAttachRequest = DocumentAttachRequest(),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    ctx: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db)
):
    """
    Attach an existing document to a case.

    This will:
    1. Update the document's case_id
    2. Optionally trigger RAG local ingestion
    3. Optionally trigger Graph (Neo4j) ingestion
    """
    # Verify case ownership
    service = CaseService(db)
    case = await service.get_case(case_id, ctx)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    # Verify document ownership
    result = await db.execute(
        select(Document)
        .where(Document.id == doc_id)
        .where(build_tenant_filter(ctx, Document))
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    if document.status != DocumentStatus.READY:
        raise HTTPException(
            status_code=400,
            detail=f"Document is not ready for attachment (status: {document.status.value})"
        )

    # Update document with case_id
    await db.execute(
        update(Document)
        .where(Document.id == doc_id)
        .values(case_id=case_id, updated_at=utcnow())
    )
    await db.commit()

    rag_triggered = False
    graph_triggered = False

    # Trigger RAG ingestion in background
    if request.auto_ingest_rag and document.extracted_text:
        background_tasks.add_task(
            _ingest_document_to_rag,
            doc_id=doc_id,
            case_id=case_id,
            tenant_id=ctx.tenant_id,
            text=document.extracted_text,
            metadata={
                "title": document.name,
                "source_type": document.type.value,
                "doc_id": doc_id,
            }
        )
        rag_triggered = True

    # Trigger Graph ingestion in background
    if request.auto_ingest_graph and document.extracted_text:
        background_tasks.add_task(
            _ingest_document_to_graph,
            doc_id=doc_id,
            case_id=case_id,
            tenant_id=ctx.tenant_id,
            text=document.extracted_text,
            metadata={
                "title": document.name,
                "source_type": document.type.value,
            }
        )
        graph_triggered = True

    return AttachResponse(
        success=True,
        document_id=doc_id,
        case_id=case_id,
        rag_ingestion_triggered=rag_triggered,
        graph_ingestion_triggered=graph_triggered,
        message="Document attached successfully" + (
            ". Ingestion started in background." if rag_triggered or graph_triggered else ""
        )
    )


@router.delete("/{case_id}/documents/{doc_id}/detach")
async def detach_document_from_case(
    case_id: str,
    doc_id: str,
    ctx: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db)
):
    """
    Detach a document from a case.

    Note: This does NOT delete the RAG/Graph ingested data.
    Use DELETE /rag/local/{case_id} to clean up RAG data.
    """
    # Verify case ownership
    service = CaseService(db)
    case = await service.get_case(case_id, ctx)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    # Verify document belongs to this case
    result = await db.execute(
        select(Document)
        .where(Document.id == doc_id)
        .where(Document.case_id == case_id)
        .where(build_tenant_filter(ctx, Document))
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found in this case")

    # Remove case_id from document
    await db.execute(
        update(Document)
        .where(Document.id == doc_id)
        .values(case_id=None, updated_at=utcnow())
    )
    await db.commit()

    return {"success": True, "message": "Document detached from case"}


# =============================================================================
# BACKGROUND TASKS
# =============================================================================


async def _ingest_document_to_rag(
    doc_id: str,
    case_id: str,
    tenant_id: str,
    text: str,
    metadata: dict
):
    """Background task to ingest document into RAG local collection."""
    from app.core.database import async_session_maker
    from app.services.rag.pipeline.rag_pipeline import get_pipeline

    try:
        logger.info(f"Starting RAG ingestion for doc={doc_id} case={case_id}")

        pipeline = get_pipeline()

        # Prepare metadata
        full_metadata = {
            **metadata,
            "tenant_id": tenant_id,
            "case_id": case_id,
            "scope": "local",
            "ingested_at": datetime.utcnow().isoformat(),
        }

        # Ingest to local collection
        if hasattr(pipeline, "ingest_local"):
            await pipeline.ingest_local(
                text=text,
                metadata=full_metadata,
                tenant_id=tenant_id,
                case_id=case_id,
            )
        elif hasattr(pipeline, "add_local_document"):
            await pipeline.add_local_document(
                doc_id=doc_id,
                text=text,
                metadata=full_metadata,
                tenant_id=tenant_id,
                case_id=case_id,
            )

        # Update document status
        async with async_session_maker() as db:
            await db.execute(
                update(Document)
                .where(Document.id == doc_id)
                .values(
                    rag_ingested=True,
                    rag_ingested_at=utcnow(),
                    rag_scope="local"
                )
            )
            await db.commit()

        logger.info(f"RAG ingestion completed for doc={doc_id}")

    except Exception as e:
        logger.error(f"RAG ingestion failed for doc={doc_id}: {e}")


async def _ingest_document_to_graph(
    doc_id: str,
    case_id: str,
    tenant_id: str,
    text: str,
    metadata: dict
):
    """Background task to ingest document into Neo4j graph."""
    from app.core.database import async_session_maker
    from app.services.rag.core.neo4j_mvp import get_neo4j_mvp
    import hashlib

    try:
        logger.info(f"Starting Graph ingestion for doc={doc_id} case={case_id}")

        neo4j = get_neo4j_mvp()

        # Create doc_hash
        doc_hash = hashlib.md5(f"{tenant_id}:{case_id}:{doc_id}".encode()).hexdigest()

        # Simple chunking (can be improved)
        chunk_size = 1000
        chunks = []
        for i in range(0, len(text), chunk_size):
            chunk_text = text[i:i + chunk_size]
            chunks.append({
                "chunk_uid": f"{doc_hash}_{i // chunk_size}",
                "text": chunk_text,
                "chunk_index": i // chunk_size,
            })

        # Ingest to Neo4j with semantic extraction (Gemini Flash)
        await neo4j.ingest_document_async(
            doc_hash=doc_hash,
            chunks=chunks,
            metadata={
                **metadata,
                "doc_id": doc_id,
            },
            tenant_id=tenant_id,
            scope="local",
            case_id=case_id,
            extract_entities=True,
            semantic_extraction=True,  # Enable LLM-based extraction for teses, conceitos
            extract_facts=True,  # Seed Fact nodes for local case graph connections
        )

        # Update document status
        async with async_session_maker() as db:
            await db.execute(
                update(Document)
                .where(Document.id == doc_id)
                .values(
                    graph_ingested=True,
                    graph_ingested_at=utcnow()
                )
            )
            await db.commit()

        logger.info(f"Graph ingestion completed for doc={doc_id}")

    except Exception as e:
        logger.error(f"Graph ingestion failed for doc={doc_id}: {e}")


async def _process_and_ingest_document(
    doc_id: str,
    file_path: str,
    doc_type,
    case_id: str,
    tenant_id: str,
    auto_ingest_rag: bool,
    auto_ingest_graph: bool,
):
    """Background task to process document (extract text) and trigger ingestion."""
    from app.core.database import async_session_maker
    from app.models.document import DocumentStatus
    from app.services.document_extraction_service import extract_text_from_path

    try:
        logger.info(f"Processing document doc={doc_id} file={file_path}")

        extraction = await extract_text_from_path(
            file_path,
            min_pdf_chars=50,
            allow_pdf_ocr_fallback=True,
        )
        extracted_text = extraction.text or ""
        extraction_meta = extraction.metadata if isinstance(extraction.metadata, dict) else {}

        # Update document with extracted text
        async with async_session_maker() as db:
            result = await db.execute(select(Document).where(Document.id == doc_id))
            doc = result.scalar_one_or_none()
            if doc is None:
                logger.warning(f"Documento {doc_id} não encontrado para atualização")
                return
            current_meta = doc.doc_metadata if isinstance(doc.doc_metadata, dict) else {}
            doc.extracted_text = extracted_text
            doc.doc_metadata = {**current_meta, **extraction_meta}
            doc.status = DocumentStatus.READY if extracted_text else DocumentStatus.ERROR
            await db.commit()

        if not extracted_text:
            logger.warning(f"No text extracted from doc={doc_id}")
            return

        logger.info(f"Extracted {len(extracted_text)} chars from doc={doc_id}")

        # Trigger RAG ingestion
        if auto_ingest_rag:
            await _ingest_document_to_rag(
                doc_id=doc_id,
                case_id=case_id,
                tenant_id=tenant_id,
                text=extracted_text,
                metadata={"source_type": doc_type.value},
            )

        # Trigger Graph ingestion
        if auto_ingest_graph:
            await _ingest_document_to_graph(
                doc_id=doc_id,
                case_id=case_id,
                tenant_id=tenant_id,
                text=extracted_text,
                metadata={"source_type": doc_type.value},
            )

        logger.info(f"Document processing completed for doc={doc_id}")

    except Exception as e:
        logger.error(f"Document processing failed for doc={doc_id}: {e}")

        # Mark as error
        try:
            async with async_session_maker() as db:
                await db.execute(
                    update(Document)
                    .where(Document.id == doc_id)
                    .values(status=DocumentStatus.ERROR)
                )
                await db.commit()
        except Exception:
            pass
