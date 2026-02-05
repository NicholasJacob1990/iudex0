"""
Configuração do Celery para processamento assíncrono
"""

import os

from celery import Celery
from celery.schedules import crontab
from loguru import logger

from app.core.config import settings

# Roteamento (permite worker dedicado para jobs longos)
_TRANSCRIPTION_QUEUE = os.getenv("IUDEX_CELERY_TRANSCRIPTION_QUEUE", "transcription")

# Criar aplicação Celery
celery_app = Celery(
    "iudex",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

# Configuração
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="America/Sao_Paulo",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,  # 1 hora
    task_soft_time_limit=3300,  # 55 minutos
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
    task_routes={
        # Worker dedicado recomendado para transcrição (jobs longos)
        "transcription_job": {"queue": _TRANSCRIPTION_QUEUE},
    },
)

# Agenda diária (requer celery beat)
celery_app.conf.beat_schedule = {
    "djen-daily-sync": {
        "task": "djen_daily_sync",
        "schedule": crontab(hour=6, minute=0),
    },
    "workflow-schedule-sync": {
        "task": "sync_workflow_schedules",
        "schedule": crontab(minute="*/5"),
    },
}

# Autodiscover tasks
celery_app.autodiscover_tasks(["app.workers.tasks"])

logger.info("Celery configurado")
