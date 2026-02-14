"""
Configuração do Celery para processamento assíncrono
"""

import os
import platform

from celery import Celery
from celery.schedules import crontab
from kombu import Queue
from loguru import logger

from app.core.config import settings

# Roteamento (permite worker dedicado para jobs longos)
_TRANSCRIPTION_QUEUE = os.getenv("IUDEX_CELERY_TRANSCRIPTION_QUEUE", "transcription")
_IS_DARWIN = platform.system().lower() == "darwin"
_DEFAULT_WORKER_POOL = "solo" if _IS_DARWIN else "prefork"
_DEFAULT_WORKER_CONCURRENCY = 1 if _IS_DARWIN else None

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
    # Se nao declarar as queues explicitamente, o worker por padrao tende a
    # consumir apenas a queue default ("celery"), e jobs roteados (ex: transcription)
    # ficam parados ate iniciar worker com `--queues`.
    task_queues=(
        Queue("celery"),
        Queue(_TRANSCRIPTION_QUEUE),
    ),
    task_track_started=True,
    task_time_limit=3600,  # 1 hora
    task_soft_time_limit=3300,  # 55 minutos
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
    worker_pool=os.getenv("IUDEX_CELERY_WORKER_POOL", _DEFAULT_WORKER_POOL),
    worker_concurrency=int(os.getenv("IUDEX_CELERY_WORKER_CONCURRENCY", str(_DEFAULT_WORKER_CONCURRENCY)))
    if _DEFAULT_WORKER_CONCURRENCY is not None
    else None,
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
    "djen-scheduled-sync": {
        "task": "djen_scheduled_sync",
        "schedule": crontab(minute="*/5"),
    },
    "detect-skill-patterns": {
        "task": "detect_skill_patterns",
        "schedule": crontab(hour="*/6", minute=15),
    },
    "workflow-schedule-sync": {
        "task": "sync_workflow_schedules",
        "schedule": crontab(minute="*/5"),
    },
    "graph-risk-cleanup": {
        "task": "graph_risk_cleanup",
        "schedule": crontab(hour=3, minute=20),
    },
    "graph-subscription-renewal": {
        "task": "renew_graph_subscriptions",
        "schedule": crontab(hour="*/6", minute=30),
    },
}

# Autodiscover tasks
#
# Celery's autodiscovery imports `<package>.tasks` (related_name="tasks" by default).
# We want it to import `app.workers.tasks` (a package) which in turn imports all task modules.
celery_app.autodiscover_tasks(["app.workers"])

logger.info("Celery configurado")
if _IS_DARWIN:
    logger.warning(
        "Celery em macOS: usando pool '{}' e concorrência {} (override via IUDEX_CELERY_WORKER_POOL/IUDEX_CELERY_WORKER_CONCURRENCY)",
        celery_app.conf.worker_pool,
        celery_app.conf.worker_concurrency,
    )
