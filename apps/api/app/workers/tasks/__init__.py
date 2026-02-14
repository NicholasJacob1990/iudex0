"""
Tasks Celery
"""

from app.workers.tasks.document_tasks import (
    process_document_task,
    ocr_document_task,
    transcribe_audio_task,
    extract_document_text_task,
    generate_document_preview_task,
    transcription_job_task,
    generate_podcast_task,
    generate_diagram_task,
    visual_index_task,
)
from app.workers.tasks.ai_tasks import (
    generate_document_task,
    generate_summary_task,
)
from app.workers.tasks.extraction_tasks import (
    process_extraction_job_task,
    start_extraction_job_task,
    extraction_worker,
    process_job_background,
)
from app.workers.tasks.skill_tasks import (
    detect_skill_patterns_task,
)
from app.workers.tasks.graph_risk_tasks import (
    graph_risk_cleanup_task,
)
from app.workers.tasks.workflow_tasks import (
    run_scheduled_workflow,
    run_webhook_workflow,
    run_triggered_workflow,
    run_builtin_workflow,
    sync_workflow_schedules,
    renew_graph_subscriptions,
)

__all__ = [
    "process_document_task",
    "ocr_document_task",
    "transcribe_audio_task",
    "extract_document_text_task",
    "generate_document_preview_task",
    "transcription_job_task",
    "generate_podcast_task",
    "generate_diagram_task",
    "visual_index_task",
    "generate_document_task",
    "generate_summary_task",
    "process_extraction_job_task",
    "start_extraction_job_task",
    "extraction_worker",
    "process_job_background",
    "detect_skill_patterns_task",
    "graph_risk_cleanup_task",
    "run_scheduled_workflow",
    "run_webhook_workflow",
    "run_triggered_workflow",
    "run_builtin_workflow",
    "sync_workflow_schedules",
    "renew_graph_subscriptions",
]
