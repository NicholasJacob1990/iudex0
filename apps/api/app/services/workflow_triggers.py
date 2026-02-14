"""
Workflow Trigger Registry — finds and dispatches workflows by trigger type.

When an external event arrives (Teams command, Outlook email, DJEN movement, etc.),
the TriggerRegistry finds matching workflows and enqueues them for async execution.

Email command support:
  Users can send emails with a command prefix to trigger specific workflows.
  Example: "IUDEX: minutar contrato de locação"
  The subject is parsed into: command="minutar", command_args="contrato de locação"
"""

import json
import logging
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workflow import Workflow

logger = logging.getLogger(__name__)

# Default prefixes recognised as email commands (case-insensitive).
# Users can override via trigger_config.command_prefix.
_DEFAULT_COMMAND_PREFIXES = ["iudex:", "vorbium:", "[iudex]", "[vorbium]"]


def parse_email_command(subject: str, custom_prefix: str | None = None) -> dict | None:
    """Parse a structured command from an email subject line.

    Recognised patterns:
      - "IUDEX: minutar contrato de locação"
      - "[IUDEX] pesquisar jurisprudência STF"
      - Custom prefix: "MEUBOT: analisar documento"

    Returns dict with keys ``prefix``, ``command``, ``command_args`` or None.
    """
    text = subject.strip()
    text_lower = text.lower()

    prefixes = list(_DEFAULT_COMMAND_PREFIXES)
    if custom_prefix:
        prefixes.insert(0, custom_prefix.lower().rstrip(":") + ":")
        prefixes.insert(1, custom_prefix.lower())

    for prefix in prefixes:
        if text_lower.startswith(prefix):
            remainder = text[len(prefix):].strip()
            parts = remainder.split(None, 1)
            command = parts[0].lower() if parts else ""
            command_args = parts[1] if len(parts) > 1 else ""
            return {
                "prefix": prefix.strip("[]").rstrip(":"),
                "command": command,
                "command_args": command_args,
            }

    return None


def _extract_trigger_nodes(graph_json: dict) -> list[dict]:
    """Extract trigger nodes from a workflow graph_json."""
    nodes = graph_json.get("nodes", [])
    return [
        n.get("data", {})
        for n in nodes
        if n.get("type") == "trigger" or n.get("data", {}).get("type") == "trigger"
    ]


def _matches_trigger(trigger_data: dict, trigger_type: str, event_data: dict) -> bool:
    """Check if a trigger node config matches the incoming event."""
    node_trigger_type = trigger_data.get("trigger_type", "")
    if node_trigger_type != trigger_type:
        return False

    config = trigger_data.get("trigger_config", {})

    if trigger_type == "teams_command":
        # Match by command name or keywords
        command = event_data.get("command", "").lower()
        expected_command = config.get("command", "").lower()
        keywords = [k.lower() for k in config.get("keywords", [])]

        if expected_command and command == expected_command:
            return True
        if keywords:
            text = event_data.get("text", "").lower()
            return any(kw in text for kw in keywords)
        return False

    elif trigger_type == "outlook_email":
        # Match by sender, subject contains, has_attachment, keywords, body, command
        sender_filter = config.get("sender_filter", "").lower()
        subject_contains = config.get("subject_contains", "").lower()
        body_contains = config.get("body_contains", "").lower()
        require_attachment = config.get("require_attachment", False)
        keywords = [k.lower() for k in config.get("keywords", [])]
        expected_command = config.get("command", "").lower()
        command_prefix = config.get("command_prefix", "")

        sender = event_data.get("sender", "").lower()
        subject = event_data.get("subject", "").lower()
        body = event_data.get("body", "").lower()
        has_attachment = event_data.get("has_attachment", False)

        # Hard filters — must pass all that are configured
        if sender_filter and sender_filter not in sender:
            return False
        if require_attachment and not has_attachment:
            return False

        # Subject contains (existing)
        if subject_contains and subject_contains not in subject:
            return False

        # Body contains
        if body_contains and body_contains not in body:
            return False

        # Keywords — at least one must appear in subject OR body
        if keywords:
            combined = subject + " " + body
            if not any(kw in combined for kw in keywords):
                return False

        # Command matching — parse subject for "IUDEX: <command> <args>"
        if expected_command:
            parsed = event_data.get("parsed_command", {})
            if not parsed:
                parsed = parse_email_command(
                    event_data.get("subject", ""), custom_prefix=command_prefix
                ) or {}
            if parsed.get("command", "").lower() != expected_command:
                return False

        return True

    elif trigger_type == "djen_movement":
        # Match by NPU, OAB, movement type
        npu_filter = config.get("npu", "")
        oab_filter = config.get("oab", "")
        movement_types = [t.lower() for t in config.get("movement_types", [])]

        npu = event_data.get("npu", "")
        tipo = event_data.get("tipo", "").lower()

        if npu_filter and npu_filter != npu:
            return False
        if oab_filter and oab_filter != event_data.get("oab", ""):
            return False
        if movement_types and tipo not in movement_types:
            return False
        return True

    elif trigger_type == "webhook":
        # Webhooks always match if the trigger type matches
        return True

    elif trigger_type == "schedule":
        # Schedules are handled by Celery Beat, not by event dispatch
        return True

    return False


class TriggerRegistry:
    """Finds matching workflows for incoming trigger events and dispatches them."""

    async def find_workflows_for_trigger(
        self,
        trigger_type: str,
        event_data: dict,
        db: AsyncSession,
        user_id: str | None = None,
    ) -> list[Workflow]:
        """Find active workflows whose trigger nodes match the incoming event."""
        query = select(Workflow).where(
            Workflow.is_active == True,  # noqa: E712
        )
        if user_id:
            query = query.where(Workflow.user_id == user_id)

        result = await db.execute(query)
        workflows = result.scalars().all()

        matching = []
        for wf in workflows:
            trigger_nodes = _extract_trigger_nodes(wf.graph_json or {})
            for trigger_data in trigger_nodes:
                if _matches_trigger(trigger_data, trigger_type, event_data):
                    matching.append(wf)
                    break  # One match per workflow is enough

        logger.info(
            f"TriggerRegistry: {len(matching)}/{len(workflows)} workflows match "
            f"trigger_type={trigger_type}"
        )
        return matching

    async def dispatch_event(
        self,
        trigger_type: str,
        event_data: dict,
        user_id: str,
        db: AsyncSession,
    ) -> list[str]:
        """Find matching workflows and enqueue them for async execution.

        Returns list of enqueued run task IDs.
        """
        from app.workers.celery_app import celery_app

        workflows = await self.find_workflows_for_trigger(
            trigger_type, event_data, db, user_id=user_id
        )

        task_ids = []
        for wf in workflows:
            task = celery_app.send_task(
                "run_triggered_workflow",
                kwargs={
                    "workflow_id": wf.id,
                    "user_id": user_id,
                    "trigger_type": trigger_type,
                    "event_data": event_data,
                },
            )
            task_ids.append(task.id)
            logger.info(
                f"Dispatched workflow {wf.id} ({wf.name}) for "
                f"trigger={trigger_type}, celery_task={task.id}"
            )

        return task_ids


# Singleton
trigger_registry = TriggerRegistry()
