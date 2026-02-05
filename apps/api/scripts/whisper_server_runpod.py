#!/usr/bin/env python3
"""
Whisper Server para RunPod (GPU)

Este arquivo implementa um servidor FastAPI para transcrição via Whisper
em GPU no RunPod. Suporta processamento assíncrono com job_id e polling.

=== DEPLOY NO RUNPOD ===

1. Criar um Pod com GPU (recomendado: RTX 4090 ou A100)
2. Usar imagem: runpod/pytorch:2.1.0-py3.10-cuda11.8.0-devel-ubuntu22.04
3. Instalar dependências:
   pip install fastapi uvicorn faster-whisper python-multipart aiofiles

4. Rodar servidor:
   uvicorn whisper_server_runpod:app --host 0.0.0.0 --port 8080

5. Configurar no Iudex:
   WHISPER_SERVER_URL=https://your-pod-id-8080.proxy.runpod.net
   WHISPER_SERVER_API_KEY=your-secret-key

=== API ENDPOINTS ===

POST /transcribe
  - Multipart form: file, language, model, beam_size, word_timestamps, diarize
  - Returns: {"job_id": "xxx"}

GET /status/{job_id}
  - Returns: {"status": "queued|processing|completed|error", "progress": 0-100}

GET /result/{job_id}
  - Returns: {"text": "...", "segments": [...], "words": [...]}

DELETE /job/{job_id}
  - Cancela e limpa job

GET /health
  - Health check

=== CONFIGURAÇÃO ===

Variáveis de ambiente:
- WHISPER_API_KEY: API key para autenticação (obrigatório)
- WHISPER_MODEL: Modelo padrão (default: large-v3)
- WHISPER_DEVICE: Device (default: cuda)
- WHISPER_COMPUTE_TYPE: Tipo de computação (default: float16)
- MAX_CONCURRENT_JOBS: Máximo de jobs simultâneos (default: 2)
- JOB_RETENTION_HOURS: Tempo para manter jobs completos (default: 24)
"""

import os
import uuid
import asyncio
import logging
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from enum import Enum
from dataclasses import dataclass, field
import threading

from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Depends, BackgroundTasks
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Configuração de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURAÇÃO
# =============================================================================

API_KEY = os.environ.get("WHISPER_API_KEY", "change-me-in-production")
DEFAULT_MODEL = os.environ.get("WHISPER_MODEL", "large-v3")
DEVICE = os.environ.get("WHISPER_DEVICE", "cuda")
COMPUTE_TYPE = os.environ.get("WHISPER_COMPUTE_TYPE", "float16")
MAX_CONCURRENT_JOBS = int(os.environ.get("MAX_CONCURRENT_JOBS", "2"))
JOB_RETENTION_HOURS = int(os.environ.get("JOB_RETENTION_HOURS", "24"))

# Diretório para arquivos temporários
TEMP_DIR = Path(tempfile.gettempdir()) / "whisper_server"
TEMP_DIR.mkdir(parents=True, exist_ok=True)

# =============================================================================
# MODELOS DE DADOS
# =============================================================================

class JobStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    ERROR = "error"
    CANCELLED = "cancelled"


@dataclass
class TranscriptionJob:
    job_id: str
    status: JobStatus = JobStatus.QUEUED
    progress: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    audio_path: Optional[str] = None
    config: Dict[str, Any] = field(default_factory=dict)


# Armazenamento em memória dos jobs
jobs: Dict[str, TranscriptionJob] = {}
jobs_lock = threading.Lock()

# Semáforo para limitar jobs concorrentes
job_semaphore = asyncio.Semaphore(MAX_CONCURRENT_JOBS)

# =============================================================================
# WHISPER MODEL (Lazy Loading)
# =============================================================================

_whisper_model = None
_model_lock = threading.Lock()


def get_whisper_model():
    """Carrega o modelo Whisper (lazy loading, thread-safe)."""
    global _whisper_model

    if _whisper_model is None:
        with _model_lock:
            if _whisper_model is None:
                logger.info(f"🚀 Carregando Whisper {DEFAULT_MODEL} em {DEVICE}...")
                try:
                    from faster_whisper import WhisperModel
                    _whisper_model = WhisperModel(
                        DEFAULT_MODEL,
                        device=DEVICE,
                        compute_type=COMPUTE_TYPE,
                    )
                    logger.info(f"✅ Whisper carregado com sucesso")
                except Exception as e:
                    logger.error(f"❌ Falha ao carregar Whisper: {e}")
                    raise

    return _whisper_model


# =============================================================================
# AUTENTICAÇÃO
# =============================================================================

security = HTTPBearer()


async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Verifica API key."""
    if credentials.credentials != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return credentials.credentials


# =============================================================================
# APLICAÇÃO FASTAPI
# =============================================================================

app = FastAPI(
    title="Whisper Server (RunPod)",
    description="Servidor de transcrição Whisper em GPU para o Iudex",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# ENDPOINTS
# =============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "model": DEFAULT_MODEL,
        "device": DEVICE,
        "active_jobs": len([j for j in jobs.values() if j.status == JobStatus.PROCESSING]),
        "queued_jobs": len([j for j in jobs.values() if j.status == JobStatus.QUEUED]),
    }


@app.post("/transcribe")
async def submit_transcription(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    language: str = Form("pt"),
    model: str = Form(DEFAULT_MODEL),
    beam_size: int = Form(5),
    word_timestamps: str = Form("true"),
    diarize: str = Form("true"),
    _: str = Depends(verify_token),
):
    """
    Submete arquivo para transcrição.
    Retorna job_id para polling.
    """
    # Gerar job_id
    job_id = str(uuid.uuid4())

    # Salvar arquivo temporariamente
    audio_path = TEMP_DIR / f"{job_id}_{file.filename}"
    try:
        with open(audio_path, "wb") as f:
            content = await file.read()
            f.write(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {e}")

    # Criar job
    job = TranscriptionJob(
        job_id=job_id,
        audio_path=str(audio_path),
        config={
            "language": language,
            "model": model,
            "beam_size": beam_size,
            "word_timestamps": word_timestamps.lower() == "true",
            "diarize": diarize.lower() == "true",
        },
    )

    with jobs_lock:
        jobs[job_id] = job

    logger.info(f"📋 Job criado: {job_id} ({file.filename})")

    # Agendar processamento em background
    background_tasks.add_task(process_transcription, job_id)

    return {"job_id": job_id}


@app.get("/status/{job_id}")
async def get_job_status(job_id: str, _: str = Depends(verify_token)):
    """Retorna status do job."""
    with jobs_lock:
        job = jobs.get(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        "job_id": job_id,
        "status": job.status.value,
        "progress": job.progress,
        "error": job.error,
        "created_at": job.created_at.isoformat(),
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


@app.get("/result/{job_id}")
async def get_job_result(job_id: str, _: str = Depends(verify_token)):
    """Retorna resultado da transcrição."""
    with jobs_lock:
        job = jobs.get(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status != JobStatus.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail=f"Job not completed. Status: {job.status.value}"
        )

    return job.result


@app.delete("/job/{job_id}")
async def cancel_job(job_id: str, _: str = Depends(verify_token)):
    """Cancela e limpa job."""
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        # Marcar como cancelado
        job.status = JobStatus.CANCELLED

        # Limpar arquivo
        if job.audio_path and os.path.exists(job.audio_path):
            try:
                os.remove(job.audio_path)
            except Exception:
                pass

        # Remover do dict
        del jobs[job_id]

    return {"status": "cancelled", "job_id": job_id}


# =============================================================================
# PROCESSAMENTO
# =============================================================================

async def process_transcription(job_id: str):
    """Processa transcrição em background."""
    async with job_semaphore:
        with jobs_lock:
            job = jobs.get(job_id)
            if not job or job.status == JobStatus.CANCELLED:
                return
            job.status = JobStatus.PROCESSING
            job.started_at = datetime.utcnow()

        logger.info(f"🎙️ Iniciando transcrição: {job_id}")

        try:
            # Carregar modelo (lazy)
            model = get_whisper_model()

            # Transcrever
            config = job.config
            segments_list = []
            words_list = []
            full_text = []

            # Callback de progresso
            def update_progress(progress: int):
                with jobs_lock:
                    if job_id in jobs:
                        jobs[job_id].progress = progress

            # Executar transcrição
            segments, info = model.transcribe(
                job.audio_path,
                language=config.get("language", "pt"),
                beam_size=config.get("beam_size", 5),
                word_timestamps=config.get("word_timestamps", True),
                vad_filter=True,
            )

            # Processar segmentos
            total_duration = info.duration if hasattr(info, "duration") else 0

            for segment in segments:
                # Atualizar progresso
                if total_duration > 0:
                    progress = min(95, int((segment.end / total_duration) * 100))
                    update_progress(progress)

                seg_data = {
                    "start": segment.start,
                    "end": segment.end,
                    "text": segment.text.strip(),
                    "speaker": "A",  # Sem diarização por enquanto
                }
                segments_list.append(seg_data)
                full_text.append(segment.text.strip())

                # Words
                if config.get("word_timestamps") and segment.words:
                    for word in segment.words:
                        words_list.append({
                            "start": word.start,
                            "end": word.end,
                            "word": word.word,
                            "probability": word.probability,
                        })

            # Resultado final
            result = {
                "text": " ".join(full_text),
                "segments": segments_list,
                "words": words_list,
                "language": info.language if hasattr(info, "language") else config.get("language"),
                "duration": total_duration,
            }

            # Atualizar job
            with jobs_lock:
                if job_id in jobs:
                    jobs[job_id].status = JobStatus.COMPLETED
                    jobs[job_id].progress = 100
                    jobs[job_id].completed_at = datetime.utcnow()
                    jobs[job_id].result = result

            logger.info(f"✅ Transcrição completa: {job_id} ({len(segments_list)} segments)")

        except Exception as e:
            logger.error(f"❌ Erro na transcrição {job_id}: {e}")
            with jobs_lock:
                if job_id in jobs:
                    jobs[job_id].status = JobStatus.ERROR
                    jobs[job_id].error = str(e)
                    jobs[job_id].completed_at = datetime.utcnow()

        finally:
            # Limpar arquivo temporário após processamento
            with jobs_lock:
                job = jobs.get(job_id)
                if job and job.audio_path and os.path.exists(job.audio_path):
                    try:
                        os.remove(job.audio_path)
                        job.audio_path = None
                    except Exception:
                        pass


# =============================================================================
# LIMPEZA DE JOBS ANTIGOS
# =============================================================================

async def cleanup_old_jobs():
    """Remove jobs antigos periodicamente."""
    while True:
        await asyncio.sleep(3600)  # A cada hora

        cutoff = datetime.utcnow() - timedelta(hours=JOB_RETENTION_HOURS)

        with jobs_lock:
            to_remove = [
                job_id for job_id, job in jobs.items()
                if job.completed_at and job.completed_at < cutoff
            ]

            for job_id in to_remove:
                job = jobs.pop(job_id, None)
                if job and job.audio_path and os.path.exists(job.audio_path):
                    try:
                        os.remove(job.audio_path)
                    except Exception:
                        pass

        if to_remove:
            logger.info(f"🧹 Limpeza: {len(to_remove)} jobs antigos removidos")


@app.on_event("startup")
async def startup_event():
    """Inicia tarefas de background."""
    asyncio.create_task(cleanup_old_jobs())
    logger.info(f"🚀 Whisper Server iniciado")
    logger.info(f"   Model: {DEFAULT_MODEL}")
    logger.info(f"   Device: {DEVICE}")
    logger.info(f"   Max concurrent jobs: {MAX_CONCURRENT_JOBS}")


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    uvicorn.run(
        "whisper_server_runpod:app",
        host="0.0.0.0",
        port=8080,
        reload=False,
        workers=1,  # Whisper não é thread-safe
    )
