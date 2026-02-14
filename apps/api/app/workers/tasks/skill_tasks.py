"""Celery tasks for dynamic skill pattern detection."""

from __future__ import annotations

import asyncio
from typing import Any, Dict

from loguru import logger

from app.core.database import AsyncSessionLocal
from app.services.ai.skills.pattern_detector import detect_all_users_skill_patterns
from app.workers.celery_app import celery_app


@celery_app.task(name="detect_skill_patterns")
def detect_skill_patterns_task(
    lookback_days: int = 30,
    min_occurrences: int = 3,
    per_user_limit: int = 5,
) -> Dict[str, Any]:
    return asyncio.run(
        _run_detect_skill_patterns(
            lookback_days=lookback_days,
            min_occurrences=min_occurrences,
            per_user_limit=per_user_limit,
        )
    )


async def _run_detect_skill_patterns(
    *,
    lookback_days: int,
    min_occurrences: int,
    per_user_limit: int,
) -> Dict[str, Any]:
    async with AsyncSessionLocal() as db:
        findings = await detect_all_users_skill_patterns(
            db=db,
            lookback_days=lookback_days,
            min_occurrences=min_occurrences,
            per_user_limit=per_user_limit,
        )

    total_users = len(findings)
    total_patterns = sum(len(patterns) for patterns in findings.values())
    logger.info(
        "[TASK] detect_skill_patterns: users=%s patterns=%s lookback_days=%s min_occurrences=%s",
        total_users,
        total_patterns,
        lookback_days,
        min_occurrences,
    )

    payload = {
        "success": True,
        "users_analyzed": total_users,
        "patterns_found": total_patterns,
        "lookback_days": lookback_days,
        "min_occurrences": min_occurrences,
        "per_user_limit": per_user_limit,
        "findings": {
            user_id: [
                {
                    "pattern_key": item.pattern_key,
                    "occurrences": item.occurrences,
                    "confidence": item.confidence,
                    "suggested_skill_name": item.suggested_skill_name,
                    "suggested_triggers": item.suggested_triggers,
                    "suggested_tools": item.suggested_tools,
                    "sample_prompts": item.sample_prompts,
                }
                for item in items
            ]
            for user_id, items in findings.items()
        },
    }
    return payload

