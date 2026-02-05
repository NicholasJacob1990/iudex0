"""
Tasks Celery
"""

from app.workers.tasks.document_tasks import (
    process_document_task,
    ocr_document_task,
    transcribe_audio_task,
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

__all__ = [
    "process_document_task",
    "ocr_document_task",
    "transcribe_audio_task",
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
]
