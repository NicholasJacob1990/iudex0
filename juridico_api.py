"""
juridico_api.py - FastAPI SSE Endpoint para Juridico AI
Streaming de geração de peças jurídicas para frontend Next.js
Refactored: Uses SQLite persistence and Unified Vertex SDK (via LegalDrafter).

Uso:
    uvicorn juridico_api:app --reload --port 8000
"""

import os
import sys
import json
import time
import datetime
from pathlib import Path
from typing import Optional, List
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Import Job Persistence
from job_manager import job_manager

# Import do módulo principal
try:
    from jinja2 import Template
    from juridico_gemini import PROMPT_MAP, TEMPLATE_OUTLINE_BASE, TEMPLATE_SECAO, LegalDrafter
except ImportError as e:
    print(f"❌ Erro de importação: {e}")
    # Don't exit here, allow partial loading if possible, but core logic needs LegalDrafter
    # sys.exit(1)

app = FastAPI(title="Juridico AI API", version="2.1")

# CORS para Next.js (Secured)
# Em produção, pode puxar de variável de ambiente ALLOWED_ORIGINS
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# =============================================================================
# SCHEMAS (Pydantic)
# =============================================================================

class JobConfig(BaseModel):
    """Configuração do job de geração - alinhado com spec do frontend"""
    tema: str
    user_prompt: Optional[str] = ""
    template_id: Optional[str] = "parecer_sobrio_v1"
    template_text: Optional[str] = None  # Template Jinja2 raw
    mode: str = "PARECER"
    
    # Flags de formatação (controladas pelo frontend)
    include_toc: bool = False
    include_section_summaries: bool = False
    include_summary_table: bool = False
    
    # Controle de extensão
    target_pages: int = 0  # 0 = sem limite
    strictness: str = "soft"  # "soft" ou "hard"
    
    # Output
    output_format: str = "md"  # "md", "docx", "pdf"

class JobStatus(BaseModel):
    job_id: str
    status: str
    progress: int = 0
    current_section: Optional[str] = None

# =============================================================================
# SSE HELPERS
# =============================================================================

def sse_event(data: dict, event: Optional[str] = None) -> bytes:
    """Formata mensagem SSE"""
    msg = ""
    if event:
        msg += f"event: {event}\n"
    msg += f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
    return msg.encode("utf-8")

# =============================================================================
# ENDPOINTS
# =============================================================================

@app.post("/jobs", response_model=JobStatus)
async def create_job(config: JobConfig):
    """Cria um novo job de geração"""
    job_id = job_manager.create_job(config.dict())
    return JobStatus(job_id=job_id, status="pending")

@app.get("/jobs/{job_id}/stream")
async def stream_job(job_id: str):
    """
    Endpoint SSE para streaming da geração.
    Frontend conecta via EventSource e recebe updates em tempo real.
    """
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job não encontrado")
    
    # Configurar job context
    config = JobConfig(**job["config"])
    job_manager.update_job(job_id, status="processing", progress=1)

    def generate():
        # 1. Job Start
        yield sse_event({"type": "job_start", "job_id": job_id}, event="job_start")
        
        try:
            # 2. Inicializar Drafter (Usa core logic com auth própria)
            template = config.template_text or TEMPLATE_SECAO
            drafter = LegalDrafter(section_template=template)
            
            # 3. Gerar Outline
            yield sse_event({"type": "status", "message": "Gerando estrutura..."}, event="status")
            
            outline = drafter.generate_outline(
                tipo_peca=config.mode,
                resumo_caso=config.tema,
                tese_usuario=config.user_prompt or "Análise completa"
            )
            
            yield sse_event({
                "type": "outline_done",
                "sections": outline
            }, event="outline_done")
            
            if not outline:
                job_manager.update_job(job_id, status="failed", result={"error": "Falha ao gerar outline"})
                yield sse_event({"type": "error", "message": "Falha ao gerar outline"}, event="error")
                return
            
            # Update DB with significant progress
            job_manager.update_job(job_id, progress=10)
            
            # 4. Calcular word budget
            WORDS_PER_PAGE = 350
            total_budget = config.target_pages * WORDS_PER_PAGE if config.target_pages > 0 else 0
            budget_per_section = total_budget // len(outline) if total_budget > 0 else 1000
            
            # 5. Gerar cada seção com streaming
            full_document = ""
            section_summaries = []
            contexto_anterior = "Início do documento."
            
            total_sections = len(outline)
            
            for i, section_title in enumerate(outline):
                # Section Start
                yield sse_event({
                    "type": "section_start",
                    "index": i + 1,
                    "total": total_sections,
                    "title": section_title
                }, event="section_start")
                
                # Render prompt
                t = Template(drafter.section_template)
                prompt = t.render(
                    titulo_secao=section_title,
                    tipo_peca=config.mode,
                    indice=i+1,
                    total=total_sections,
                    contexto_anterior=contexto_anterior[-2000:]
                )
                
                if total_budget > 0:
                    prompt += f"\nLIMITE: ~{budget_per_section} palavras."
                
                # Stream com updates parciais (20/40/60/80%)
                current_section_text = ""
                for update in drafter.stream_section_updates(prompt, target_words=budget_per_section):
                    if update['type'] == 'section_progress':
                        yield sse_event({
                            "type": "section_progress",
                            "index": i + 1,
                            "percent": update['percent'],
                            "word_count": update['word_count'],
                            "delta": update['delta']
                        }, event="section_progress")
                    
                    elif update['type'] == 'section_done':
                        section_text = update['markdown']
                        current_section_text = section_text
                        full_document += f"\n\n# {section_title}\n\n{section_text}"
                        contexto_anterior += f"\nResumo {section_title}: {section_text[:500]}..."
                        
                        yield sse_event({
                            "type": "section_done",
                            "index": i + 1,
                            "title": section_title,
                            "markdown": section_text,
                            "word_count": update['word_count']
                        }, event="section_done")
                
                # Gerar síntese da seção (se flag ativa)
                if config.include_section_summaries:
                    summary_prompt = f"Gere 3-5 bullets resumindo: {current_section_text[:2000]}"
                    try:
                        resp = drafter._generate_with_retry(summary_prompt)
                        if resp and resp.text:
                            summary = resp.text.strip()
                            section_summaries.append({"title": section_title, "summary": summary})
                            yield sse_event({
                                "type": "section_summary",
                                "index": i + 1,
                                "summary": summary
                            }, event="section_summary")
                    except:
                        pass
                
                # Update progress in DB (interpolated 10% -> 90%)
                progress_pct = 10 + int((i + 1) / total_sections * 80)
                job_manager.update_job(job_id, progress=progress_pct, status=f"generating section {i+1}/{total_sections}")
            
            # 6. Finalização
            # TOC
            if config.include_toc:
                toc = "# Sumário\n\n" + "\n".join([f"{i+1}. {t}" for i, t in enumerate(outline)])
                full_document = toc + "\n\n---\n" + full_document
            
            # Summary Table
            if config.include_summary_table and section_summaries:
                table = "\n\n# Tabela de Síntese\n\n| Seção | Síntese |\n|-------|--------|\n"
                for item in section_summaries:
                    table += f"| {item['title']} | {item['summary'][:100]}... |\n"
                full_document += table
            
            # 7. Salvar e enviar resultado (Persistent Store)
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
            filename = f"JuridicoAI_{config.mode}_{timestamp}"
            
            final_result = {
                "markdown": full_document,
                "filename": filename
            }
            
            job_manager.update_job(job_id, status="done", result=final_result, progress=100)
            
            yield sse_event({
                "type": "done",
                "job_id": job_id,
                "md_content": full_document,
                "filename": filename
            }, event="done")
            
        except Exception as e:
            error_msg = str(e)
            job_manager.update_job(job_id, status="error", result={"error": error_msg})
            yield sse_event({
                "type": "error",
                "message": error_msg
            }, event="error")
        
        finally:
            if 'drafter' in locals():
                drafter.cleanup()
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

@app.get("/jobs/{job_id}")
async def get_job_status(job_id: str):
    """Retorna status do job (Persistent)"""
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job não encontrado")
    
    return {
        "job_id": job["job_id"],
        "status": job["status"],
        "created_at": job["created_at"],
        "progress": job["progress"],
        "result": job["result"]
    }

@app.get("/templates")
async def list_templates():
    """Lista templates disponíveis"""
    return {
        "templates": [
            {"id": "parecer_sobrio_v1", "name": "Parecer Sóbrio", "description": "Tom formal e técnico"},
            {"id": "peticao_persuasiva", "name": "Petição Persuasiva", "description": "Tom persuasivo e enfático"},
            {"id": "contrato_padrao", "name": "Contrato Padrão", "description": "Linguagem contratual precisa"},
        ]
    }

@app.get("/modes")
async def list_modes():
    """Lista modos/tipos de peça disponíveis"""
    return {"modes": list(PROMPT_MAP.keys())}

# =============================================================================
# HEALTH CHECK
# =============================================================================

@app.get("/health")
async def health_check():
    return {"status": "ok", "version": "2.1", "persistence": "sqlite"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
