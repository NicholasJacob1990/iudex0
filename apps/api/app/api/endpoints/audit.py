"""
Endpoints de Auditoria Jurídica (upload direto)

Compatível com o frontend: POST /api/audit/run (retorna DOCX)
"""

import os
import re
import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from loguru import logger

from app.core.security import get_current_user
from app.core.time_utils import utcnow
from app.models.user import User
from app.services.ai.audit_service import AuditService
from app.services.document_processor import (
    extract_text_from_docx,
    extract_text_from_pdf,
    extract_text_from_pdf_with_ocr,
)


router = APIRouter()


def _safe_filename_base(name: str) -> str:
    base = Path(name).stem or "documento"
    base = re.sub(r"[^a-zA-Z0-9_\-]+", "_", base).strip("_")
    return base[:80] or "documento"


async def _extract_text(file_path: str, ext: str) -> str:
    ext = ext.lower()
    if ext == ".pdf":
        text = await extract_text_from_pdf(file_path)
        # Fallback OCR para PDFs escaneados (pouco texto)
        if not text or len(text.strip()) < 50:
            try:
                ocr_text = await extract_text_from_pdf_with_ocr(file_path)
                if ocr_text and len(ocr_text.strip()) > len(text.strip()):
                    return ocr_text
            except Exception as e:
                logger.warning(f"OCR falhou no PDF: {e}")
        return text or ""

    if ext == ".docx":
        return await extract_text_from_docx(file_path) or ""

    if ext == ".txt" or ext == ".md":
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read() or ""

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Formato não suportado para auditoria. Envie PDF, DOCX, TXT ou MD.",
    )


@router.post("/run")
async def run_audit(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """
    Executa auditoria jurídica a partir de um arquivo enviado e retorna o relatório em DOCX.
    """
    filename = file.filename or "documento"
    ext = Path(filename).suffix.lower()
    filename_base = _safe_filename_base(filename)

    audit_service = AuditService()

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = os.path.join(tmpdir, f"upload{ext or ''}")
        try:
            with open(tmp_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)

            content = await _extract_text(tmp_path, ext)
            if not content or len(content.strip()) < 50:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Documento sem conteúdo suficiente para auditoria.",
                )

            result = await audit_service.auditar_peca(
                texto_completo=content,
                output_folder=tmpdir,
                filename_base=f"{filename_base}_{current_user.id[:8]}",
            )

            docx_path = result.get("docx_path")
            if not docx_path or not os.path.exists(docx_path):
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Falha ao gerar DOCX da auditoria.",
                )

            def iterfile():
                with open(docx_path, "rb") as f:
                    yield from iter(lambda: f.read(1024 * 1024), b"")

            out_name = f"Auditoria_{filename_base}.docx"
            return StreamingResponse(
                iterfile(),
                media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                headers={"Content-Disposition": f'attachment; filename="{out_name}"'},
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Erro ao executar auditoria: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Erro ao executar auditoria: {str(e)}",
            )


@router.post("/verify-snippet")
async def verify_snippet(
    request: dict,
    current_user: User = Depends(get_current_user),
):
    """
    Verificação rápida de citações jurídicas em um trecho de texto.
    Usado pelo Bubble Menu do Canvas para auditoria inline.
    
    Request body:
        {"text": "Segundo a Súmula 123 do STF..."}
    
    Response:
        {"status": "valid|suspicious|not_found", "message": "...", "suggestions": [...]}
    """
    text = request.get("text", "").strip()
    if not text or len(text) < 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Texto muito curto para verificação.",
        )
    
    try:
        audit_service = AuditService()
        
        # Use a simplified verification focusing on citations only
        result = await audit_service.verificar_citacoes_rapido(text)
        
        return {
            "status": result.get("status", "unknown"),
            "message": result.get("message", "Verificação concluída."),
            "citations": result.get("citations", []),
            "suggestions": result.get("suggestions", []),
        }
    
    except Exception as e:
        logger.error(f"Erro na verificação de snippet: {e}")
        # Fallback: return a safe response instead of failing
        return {
            "status": "unknown",
            "message": f"Não foi possível verificar: {str(e)}",
            "citations": [],
            "suggestions": [],
        }


@router.post("/edit-proposal")
async def create_edit_proposal(
    request: dict,
    current_user: User = Depends(get_current_user),
):
    """
    Cria uma proposta de edição estruturada para auditoria e reversão.
    
    Usado pelo Canvas para registrar alterações da IA com metadados completos.
    
    Request body:
        {
            "document_id": "uuid",
            "range": {"from": 100, "to": 150},
            "original": "texto original",
            "replacement": "texto novo",
            "agent": "gemini-1.5-pro",
            "sources_used": ["Lei 8.112/90", "Súmula 123"],
            "reason": "Melhoria de clareza jurídica"
        }
    
    Response:
        {
            "proposal_id": "uuid",
            "change_stats": {...},
            "requires_approval": true
        }
    """
    document_id = request.get("document_id")
    original = request.get("original", "")
    replacement = request.get("replacement", "")
    agent = request.get("agent", "unknown")
    sources_used = request.get("sources_used", [])
    reason = request.get("reason", "")
    range_data = request.get("range", {})
    
    if not original and not replacement:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Original ou replacement deve ser fornecido.",
        )
    
    import uuid
    
    proposal_id = str(uuid.uuid4())
    
    # Calculate change statistics
    original_words = len(original.split())
    replacement_words = len(replacement.split())
    words_added = max(0, replacement_words - original_words)
    words_removed = max(0, original_words - replacement_words)
    
    # Determine if approval is required based on change size
    change_percentage = abs(replacement_words - original_words) / max(original_words, 1) * 100
    requires_approval = change_percentage > 30 or len(replacement) > 500
    
    logger.info(f"Edit proposal created: {proposal_id} by agent {agent} for user {current_user.id[:8]}")
    
    return {
        "proposal_id": proposal_id,
        "document_id": document_id,
        "timestamp": utcnow().isoformat(),
        "agent": agent,
        "sources_used": sources_used,
        "reason": reason,
        "change_stats": {
            "original_words": original_words,
            "replacement_words": replacement_words,
            "words_added": words_added,
            "words_removed": words_removed,
            "change_percentage": round(change_percentage, 1),
        },
        "requires_approval": requires_approval,
        "status": "pending",
    }


@router.post("/edit-proposal/{proposal_id}/apply")
async def apply_edit_proposal(
    proposal_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    Aplica uma proposta de edição aprovada.
    """
    logger.info(f"Edit proposal {proposal_id} applied by user {current_user.id[:8]}")
    
    return {
        "proposal_id": proposal_id,
        "status": "applied",
        "message": "Edição aplicada com sucesso.",
    }


@router.post("/edit-proposal/{proposal_id}/reject")
async def reject_edit_proposal(
    proposal_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    Rejeita uma proposta de edição.
    """
    logger.info(f"Edit proposal {proposal_id} rejected by user {current_user.id[:8]}")
    
    return {
        "proposal_id": proposal_id,
        "status": "rejected",
        "message": "Edição rejeitada.",
    }
