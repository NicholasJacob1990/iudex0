from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks, Body
from fastapi.responses import StreamingResponse
from typing import Optional
import shutil
import os
import uuid
import logging
import io
from app.schemas.transcription import TranscriptionRequest, HearingSpeakersUpdateRequest
from app.services.transcription_service import TranscriptionService
from docx import Document
from pydantic import BaseModel

class ExportRequest(BaseModel):
    content: str
    filename: str = "transcription.docx"

router = APIRouter()
logger = logging.getLogger(__name__)

# Instância global do serviço (carrega modelos na init se necessário, aqui é leve)
service = TranscriptionService()

@router.post("/export/docx")
async def export_docx(request: ExportRequest):
    """
    Converte texto/markdown para DOCX usando VomoMLX.save_as_word.
    Usa a mesma lógica de formatação premium do mlx_vomo.py.
    """
    import tempfile
    import sys
    import os
    
    # Add project root to path
    PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../../../"))
    if PROJECT_ROOT not in sys.path:
        sys.path.append(PROJECT_ROOT)
    
    try:
        from mlx_vomo import VomoMLX
        
        # Create temp directory for output
        with tempfile.TemporaryDirectory() as temp_dir:
            # Extract video name from filename
            video_name = request.filename.replace('.docx', '').replace('_', ' ')
            
            # Initialize VomoMLX (lightweight, just for save_as_word)
            vomo = VomoMLX(provider="gemini")
            
            # Call the real save_as_word method
            output_path = vomo.save_as_word(
                formatted_text=request.content,
                video_name=video_name,
                output_folder=temp_dir,
                mode="APOSTILA"
            )
            
            if output_path and os.path.exists(output_path):
                # Read the generated file
                with open(output_path, 'rb') as f:
                    docx_content = f.read()
                
                buffer = io.BytesIO(docx_content)
                buffer.seek(0)
                
                return StreamingResponse(
                    buffer,
                    media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    headers={"Content-Disposition": f"attachment; filename={request.filename}"}
                )
            else:
                raise HTTPException(status_code=500, detail="Falha ao gerar documento Word")
                
    except ImportError as e:
        logger.error(f"Erro ao importar VomoMLX: {str(e)}")
        # Fallback to simple DOCX generation
        from docx import Document
        doc = Document()
        doc.add_heading(request.filename.replace('.docx', ''), 0)
        for para in request.content.split('\n'):
            if para.strip():
                doc.add_paragraph(para)
        buffer = io.BytesIO()
        doc.save(buffer)
        buffer.seek(0)
        return StreamingResponse(
            buffer,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f"attachment; filename={request.filename}"}
        )
    except Exception as e:
        logger.error(f"Erro ao exportar DOCX: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/vomo", response_model=dict)
async def transcribe_vomo(
    file: UploadFile = File(...),
    mode: str = Form("APOSTILA"),
    thinking_level: str = Form("medium"),
    custom_prompt: Optional[str] = Form(None),
    model_selection: str = Form("gemini-3-flash-preview"),
    high_accuracy: bool = Form(False)
):
    """
    Endpoint para transcrição e formatação usando MLX Vomo.
    Suporta arquivos de áudio e vídeo.
    Retorna o texto transcrito/formatado.
    
    WARNING: Processamento síncrono/longo por enquanto (MVP).
    Idealmente mover para BackgroundTasks e retornar JobID.
    """
    temp_file_path = f"/tmp/{uuid.uuid4()}_{file.filename}"
    
    try:
        # Salvar arquivo temporário
        with open(temp_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        logger.info(f"📁 Arquivo recebido: {file.filename} ({mode})")
        
        # Processar
        final_text = await service.process_file(
            file_path=temp_file_path,
            mode=mode,
            thinking_level=thinking_level,
            custom_prompt=custom_prompt,
            high_accuracy=high_accuracy,
            model_selection=model_selection
        )
        
        return {
            "status": "success",
            "filename": file.filename,
            "content": final_text
        }
        
    except Exception as e:
        logger.error(f"Erro na transcrição: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
        
    finally:
        # Cleanup
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)


@router.post("/vomo/stream")
async def transcribe_vomo_stream(
    file: UploadFile = File(...),
    mode: str = Form("APOSTILA"),
    thinking_level: str = Form("medium"),
    custom_prompt: Optional[str] = Form(None),
    model_selection: str = Form("gemini-3-flash-preview"),
    high_accuracy: bool = Form(False)
):
    """
    SSE endpoint that streams transcription progress in real-time.
    
    Events:
    - progress: { stage, progress, message }
    - complete: { status, filename, content }
    - error: { error }
    """
    from sse_starlette.sse import EventSourceResponse
    import json
    import asyncio
    
    temp_file_path = f"/tmp/{uuid.uuid4()}_{file.filename}"
    
    # Save uploaded file first (outside generator)
    with open(temp_file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    logger.info(f"📁 SSE: Arquivo recebido: {file.filename} ({mode})")
    
    async def event_generator():
        progress_queue = asyncio.Queue()
        final_result = {"content": None, "error": None}
        
        async def on_progress(stage: str, progress: int, message: str):
            """Callback chamado pelo service para reportar progresso."""
            await progress_queue.put({
                "event": "progress",
                "data": {"stage": stage, "progress": progress, "message": message}
            })
        
        async def process_task():
            """Task que executa o processamento."""
            try:
                result = await service.process_file_with_progress(
                    file_path=temp_file_path,
                    mode=mode,
                    thinking_level=thinking_level,
                    custom_prompt=custom_prompt,
                    high_accuracy=high_accuracy,
                    model_selection=model_selection,
                    on_progress=on_progress
                )
                if isinstance(result, dict):
                    final_result["content"] = result.get("content")
                    final_result["reports"] = result.get("reports")
                else:
                    final_result["content"] = result
            except Exception as e:
                final_result["error"] = str(e)
            finally:
                # Signal done
                await progress_queue.put(None)
        
        # Start processing in background
        task = asyncio.create_task(process_task())
        
        try:
            # Yield progress events as they come
            while True:
                item = await progress_queue.get()
                if item is None:
                    break
                yield {
                    "event": item["event"],
                    "data": json.dumps(item["data"])
                }
            
            # Wait for task to complete
            await task
            
            # Yield final result
            if final_result["error"]:
                yield {
                    "event": "error",
                    "data": json.dumps({"error": final_result["error"]})
                }
            else:
                yield {
                    "event": "complete",
                    "data": json.dumps({
                        "status": "success",
                        "filename": file.filename,
                        "content": final_result["content"],
                        "reports": final_result.get("reports")
                    })
                }
        finally:
            # Cleanup temp file
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
    
    return EventSourceResponse(
        event_generator(),
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Content-Encoding": "identity",
        }
    )


@router.post("/vomo/batch/stream")
async def transcribe_batch_stream(
    files: list[UploadFile] = File(...),
    mode: str = Form("APOSTILA"),
    thinking_level: str = Form("medium"),
    custom_prompt: Optional[str] = Form(None),
    model_selection: str = Form("gemini-3-flash-preview"),
    high_accuracy: bool = Form(False)
):
    """
    SSE endpoint for batch transcription of multiple files.
    
    Processes files in order and unifies output into a single document.
    Files are processed sequentially to maintain order (Aula 1, 2, 3...).
    
    Events:
    - progress: { stage, progress, message }
    - complete: { status, filenames, content }
    - error: { error }
    """
    from sse_starlette.sse import EventSourceResponse
    import json
    import asyncio
    
    if not files or len(files) == 0:
        raise HTTPException(status_code=400, detail="No files provided")
    
    # Save all uploaded files first
    temp_paths = []
    file_names = []
    
    for f in files:
        path = f"/tmp/{uuid.uuid4()}_{f.filename}"
        with open(path, "wb") as buffer:
            shutil.copyfileobj(f.file, buffer)
        temp_paths.append(path)
        file_names.append(f.filename)
    
    logger.info(f"📁 BATCH SSE: {len(files)} arquivos recebidos: {', '.join(file_names)}")
    
    async def event_generator():
        progress_queue = asyncio.Queue()
        final_result = {"content": None, "error": None}
        
        async def on_progress(stage: str, progress: int, message: str):
            await progress_queue.put({
                "event": "progress",
                "data": {"stage": stage, "progress": progress, "message": message}
            })
        
        async def process_task():
            try:
                result = await service.process_batch_with_progress(
                    file_paths=temp_paths,
                    file_names=file_names,
                    mode=mode,
                    thinking_level=thinking_level,
                    custom_prompt=custom_prompt,
                    high_accuracy=high_accuracy,
                    model_selection=model_selection,
                    on_progress=on_progress
                )
                if isinstance(result, dict):
                    final_result["content"] = result.get("content")
                    final_result["reports"] = result.get("reports")
                else:
                    final_result["content"] = result
            except Exception as e:
                final_result["error"] = str(e)
            finally:
                await progress_queue.put(None)
        
        task = asyncio.create_task(process_task())
        
        try:
            while True:
                item = await progress_queue.get()
                if item is None:
                    break
                yield {
                    "event": item["event"],
                    "data": json.dumps(item["data"])
                }
            
            await task
            
            if final_result["error"]:
                yield {
                    "event": "error",
                    "data": json.dumps({"error": final_result["error"]})
                }
            else:
                yield {
                    "event": "complete",
                    "data": json.dumps({
                        "status": "success",
                        "filenames": file_names,
                        "total_files": len(file_names),
                        "content": final_result["content"],
                        "reports": final_result.get("reports")
                    })
                }
        finally:
            # Cleanup all temp files
            for path in temp_paths:
                if os.path.exists(path):
                    os.remove(path)
    
    return EventSourceResponse(
        event_generator(),
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Content-Encoding": "identity",
        }
    )


class RevisionRequest(BaseModel):
    """Request body for applying HIL revisions."""
    content: str
    approved_issues: list  # List of issue objects with id, type, description, suggestion


@router.post("/apply-revisions")
async def apply_revisions(request: RevisionRequest):
    """
    Apply AI revisions to transcription based on user-approved issues.
    
    Takes the original content and list of approved issues,
    then uses AI to fix those specific issues in the text.
    """
    if not request.approved_issues:
        return {"revised_content": request.content, "changes_made": 0}
    
    try:
        from app.services.quality_service import quality_service

        structural_issues = [i for i in request.approved_issues if i.get("fix_type") == "structural"]
        content_issues = [i for i in request.approved_issues if i.get("fix_type") != "structural"]

        revised_content = request.content
        applied_structural = []

        if structural_issues:
            structural_result = await quality_service.apply_structural_fixes_from_issues(
                content=revised_content,
                approved_issues=structural_issues
            )
            revised_content = structural_result.get("content", revised_content)
            applied_structural = structural_result.get("fixes", []) or []

        if content_issues:
            import google.generativeai as genai
            from app.core.config import settings

            # Configure API Key
            if not os.getenv("GOOGLE_API_KEY") and hasattr(settings, "GOOGLE_API_KEY"):
                genai.configure(api_key=settings.GOOGLE_API_KEY)
            elif os.getenv("GOOGLE_API_KEY"):
                genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

            issues_text = "\n".join([
                f"- [{issue.get('type', 'unknown')}] {issue.get('description', '')} → Sugestão: {issue.get('suggestion', 'Corrigir')}"
                for issue in content_issues
            ])

            allow_insertions = any(
                str(issue.get("type", "")).startswith("missing_")
                or "omiss" in str(issue.get("description", "")).lower()
                or "lacuna" in str(issue.get("description", "")).lower()
                for issue in content_issues
            )
            if allow_insertions:
                insertion_rules = (
                    "3. Se algum issue indicar lacuna/omissão, você PODE inserir um parágrafo curto no local adequado.\n"
                    "4. Não invente fatos: se a informação não estiver explícita no texto original, use [VERIFICAR NO AUDIO].\n"
                    "5. Retorne APENAS o texto corrigido, sem explicações."
                )
            else:
                insertion_rules = (
                    "3. Não adicione conteúdo novo, apenas corrija os problemas apontados.\n"
                    "4. Retorne APENAS o texto corrigido, sem explicações."
                )

            revision_prompt = f"""Você é um revisor de transcrições jurídicas.
O usuário aprovou as seguintes correções de CONTEÚDO para aplicar ao texto:

## ISSUES APROVADOS PARA CORREÇÃO:
{issues_text}

## TEXTO ORIGINAL:
{revised_content}

## INSTRUÇÕES:
1. Aplique TODAS as correções listadas acima ao texto.
2. Mantenha a estrutura e formatação originais.
{insertion_rules}

## TEXTO CORRIGIDO:"""

            model = genai.GenerativeModel("gemini-2.0-flash")
            response = model.generate_content(revision_prompt)
            revised_content = response.text if response else revised_content

        return {
            "revised_content": revised_content,
            "changes_made": len(request.approved_issues),
            "issues_applied": [issue.get("id") for issue in request.approved_issues],
            "structural_fixes_applied": applied_structural,
        }
        
    except Exception as e:
        logger.error(f"Erro ao aplicar revisões HIL: {e}")
        raise HTTPException(status_code=500, detail=f"Falha na revisão: {str(e)}")


@router.post("/hearing/stream")
async def transcribe_hearing_stream(
    file: UploadFile = File(...),
    case_id: str = Form(...),
    goal: str = Form("alegacoes_finais"),
    thinking_level: str = Form("medium"),
    model_selection: str = Form("gemini-3-flash-preview"),
    high_accuracy: bool = Form(False),
    format_mode: str = Form("AUDIENCIA"),
    custom_prompt: Optional[str] = Form(None),
    format_enabled: bool = Form(True),
):
    """
    SSE endpoint for hearings/reunions transcription (structured JSON + evidence).
    """
    from sse_starlette.sse import EventSourceResponse
    import json
    import asyncio

    temp_file_path = f"/tmp/{uuid.uuid4()}_{file.filename}"

    with open(temp_file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    logger.info(f"📁 HEARING SSE: Arquivo recebido: {file.filename} (case_id={case_id})")

    async def event_generator():
        progress_queue = asyncio.Queue()
        final_result = {"payload": None, "error": None}

        async def on_progress(stage: str, progress: int, message: str):
            await progress_queue.put({
                "event": "progress",
                "data": {"stage": stage, "progress": progress, "message": message}
            })

        async def process_task():
            try:
                result = await service.process_hearing_with_progress(
                    file_path=temp_file_path,
                    case_id=case_id,
                    goal=goal,
                    thinking_level=thinking_level,
                    model_selection=model_selection,
                    high_accuracy=high_accuracy,
                    format_mode=format_mode,
                    custom_prompt=custom_prompt,
                    format_enabled=format_enabled,
                    on_progress=on_progress,
                )
                final_result["payload"] = result
            except Exception as e:
                final_result["error"] = str(e)
            finally:
                await progress_queue.put(None)

        task = asyncio.create_task(process_task())

        try:
            while True:
                item = await progress_queue.get()
                if item is None:
                    break
                yield {
                    "event": item["event"],
                    "data": json.dumps(item["data"])
                }

            await task

            if final_result["error"]:
                yield {
                    "event": "error",
                    "data": json.dumps({"error": final_result["error"]})
                }
            else:
                yield {
                    "event": "complete",
                    "data": json.dumps({
                        "status": "success",
                        "filename": file.filename,
                        "payload": final_result["payload"],
                    })
                }
        finally:
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)

    return EventSourceResponse(
        event_generator(),
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Content-Encoding": "identity",
        }
    )


@router.post("/hearing/speakers")
async def update_hearing_speakers(request: HearingSpeakersUpdateRequest):
    """
    Update hearing speaker registry (manual edits).
    """
    if not request.speakers:
        raise HTTPException(status_code=400, detail="Nenhum falante informado")
    speakers = service.update_hearing_speakers(request.case_id, [s.model_dump() for s in request.speakers])
    return {"status": "success", "speakers": speakers}


@router.post("/hearing/enroll")
async def enroll_hearing_speaker(
    file: UploadFile = File(...),
    case_id: str = Form(...),
    name: str = Form(...),
    role: str = Form("outro"),
):
    """
    Enroll speaker audio for a case (voice profile seed).
    """
    temp_file_path = f"/tmp/{uuid.uuid4()}_{file.filename}"
    with open(temp_file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    try:
        speaker = service.enroll_hearing_speaker(case_id=case_id, name=name, role=role, file_path=temp_file_path)
        return {"status": "success", "speaker": speaker}
    finally:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
