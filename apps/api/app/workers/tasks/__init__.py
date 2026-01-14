"""
Tasks Celery
"""

from app.workers.tasks.document_tasks import (
    process_document_task,
    ocr_document_task,
    transcribe_audio_task,
    generate_podcast_task,
    generate_diagram_task,
)
from app.workers.tasks.ai_tasks import (
    generate_document_task,
    generate_summary_task,
)

__all__ = [
    "process_document_task",
    "ocr_document_task",
    "transcribe_audio_task",
    "generate_podcast_task",
    "generate_diagram_task",
    "generate_document_task",
    "generate_summary_task",
]
