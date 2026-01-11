from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from typing import List, Optional
from io import BytesIO
import json
import os

from app.core.security import get_current_user
from app.models.user import User
from app.services.rag_module import create_rag_manager, PecaModeloMetadata
from loguru import logger

try:
    from PyPDF2 import PdfReader
except ImportError:
    PdfReader = None

try:
    from docx import Document as DocxDocument
except ImportError:
    DocxDocument = None

router = APIRouter()

_rag_manager = None


def get_rag_manager():
    global _rag_manager
    if _rag_manager is None:
        _rag_manager = create_rag_manager()
    return _rag_manager


def _read_text_from_upload(filename: str, data: bytes) -> str:
    ext = os.path.splitext(filename)[1].lower()
    if ext == ".pdf":
        if not PdfReader:
            raise HTTPException(status_code=500, detail="PyPDF2 não instalado no servidor")
        reader = PdfReader(BytesIO(data))
        text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        return text.strip()
    if ext == ".docx":
        if not DocxDocument:
            raise HTTPException(status_code=500, detail="python-docx não instalado no servidor")
        doc = DocxDocument(BytesIO(data))
        return "\n".join([p.text for p in doc.paragraphs]).strip()
    if ext in [".txt", ".md", ".text"]:
        return data.decode("utf-8", errors="ignore").strip()
    return ""


@router.post("/index")
async def index_rag_models(
    files: List[UploadFile] = File(...),
    tipo_peca: str = Form("geral"),
    area: str = Form("geral"),
    rito: str = Form("ordinario"),
    tribunal_destino: Optional[str] = Form(None),
    tese: Optional[str] = Form(None),
    resultado: Optional[str] = Form(None),
    versao: str = Form("v1"),
    aprovado: bool = Form(True),
    chunk: bool = Form(True),
    paths: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user)
):
    if not files:
        raise HTTPException(status_code=400, detail="Nenhum arquivo enviado")

    rel_paths = []
    if paths:
        try:
            rel_paths = json.loads(paths)
        except Exception:
            raise HTTPException(status_code=400, detail="Formato inválido de paths")

    rag = get_rag_manager()
    results = []
    total_chunks = 0
    errors = []

    for idx, upload in enumerate(files):
        filename = upload.filename or f"arquivo_{idx}"
        rel_path = rel_paths[idx] if idx < len(rel_paths) else None
        try:
            data = await upload.read()
            text = _read_text_from_upload(filename, data)
            if len(text) < 20:
                raise ValueError("Conteúdo insuficiente para indexação")

            meta = PecaModeloMetadata(
                tipo_peca=tipo_peca or "geral",
                area=area or "geral",
                rito=rito or "ordinario",
                tribunal_destino=tribunal_destino or None,
                tese=tese or None,
                resultado=resultado or None,
                versao=versao or "v1",
                aprovado=bool(aprovado)
            )

            chunks = rag.add_peca_modelo(text, meta, chunk=bool(chunk))
            total_chunks += chunks
            results.append({
                "filename": filename,
                "path": rel_path,
                "chunks": chunks
            })
        except Exception as e:
            logger.error(f"Erro ao indexar {filename}: {e}")
            errors.append({
                "filename": filename,
                "path": rel_path,
                "error": str(e)
            })
        finally:
            try:
                await upload.close()
            except Exception:
                pass

    indexed = len(results)
    return {
        "indexed": indexed,
        "total_files": len(files),
        "total_chunks": total_chunks,
        "results": results,
        "errors": errors
    }
