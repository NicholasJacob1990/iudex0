"""
Bot command handlers — process each command type and respond.
"""

import json
import logging

import httpx
from botbuilder.core import TurnContext
from botbuilder.schema import Activity, ActivityTypes, Attachment

from app.services.teams_bot.cards import (
    build_search_results_card,
    build_help_card,
    build_workflow_started_card,
    build_workflow_status_card,
    build_hil_notification_card,
)

logger = logging.getLogger(__name__)

API_BASE = "http://localhost:8000/api"


async def _get_user_token(turn_context: TurnContext) -> str:
    """Get or create user token from AAD info."""
    aad_id = turn_context.activity.from_property.aad_object_id
    if not aad_id:
        return ""
    # TODO: Look up cached Iudex JWT by AAD ID from Redis
    return ""


def _make_card_attachment(card: dict) -> Attachment:
    """Wrap an Adaptive Card dict as a Bot Framework Attachment."""
    return Attachment(
        content_type="application/vnd.microsoft.card.adaptive",
        content=card,
    )


async def handle_search_command(turn_context: TurnContext, query: str):
    """Handle /pesquisar command — search corpus."""
    if not query:
        await turn_context.send_activity("Por favor, informe o que deseja pesquisar. Ex: /pesquisar dano moral")
        return

    await turn_context.send_activity(Activity(type=ActivityTypes.typing))

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{API_BASE}/corpus/search",
                json={"query": query, "limit": 5},
                headers={"Authorization": f"Bearer {await _get_user_token(turn_context)}"},
            )
            if response.status_code == 200:
                data = response.json()
                results = data.get("results", [])
                card = build_search_results_card(query, results)
                await turn_context.send_activity(
                    Activity(
                        type=ActivityTypes.message,
                        attachments=[_make_card_attachment(card)],
                    )
                )
            else:
                await turn_context.send_activity(f"Erro na pesquisa: {response.status_code}")
    except Exception as e:
        logger.error(f"Search command error: {e}")
        await turn_context.send_activity("Erro ao realizar pesquisa. Tente novamente.")


async def handle_analyze_command(turn_context: TurnContext, content: str):
    """Handle /analisar command — analyze text with AI."""
    if not content:
        await turn_context.send_activity("Por favor, inclua o texto para analisar. Ex: /analisar [texto]")
        return

    await turn_context.send_activity(Activity(type=ActivityTypes.typing))
    # TODO: Call AI orchestrator for analysis
    await turn_context.send_activity(f"Analise do texto recebida ({len(content)} caracteres). Processando...")


async def handle_workflow_command(turn_context: TurnContext, name: str):
    """Handle /workflow command — start a workflow via TriggerRegistry."""
    if not name:
        await turn_context.send_activity("Por favor, informe o nome do workflow. Ex: /workflow due-diligence")
        return

    await turn_context.send_activity(Activity(type=ActivityTypes.typing))

    # Dispatch via TriggerRegistry for event-driven workflows
    try:
        from app.core.database import AsyncSessionLocal
        from app.services.workflow_triggers import trigger_registry

        event_data = {
            "command": name.split()[0] if name else "",
            "text": name,
            "user_aad_id": turn_context.activity.from_property.aad_object_id or "",
            "conversation_id": turn_context.activity.conversation.id if turn_context.activity.conversation else "",
            "channel": "teams",
        }

        token = await _get_user_token(turn_context)
        user_id = token or event_data["user_aad_id"]

        async with AsyncSessionLocal() as db:
            task_ids = await trigger_registry.dispatch_event(
                trigger_type="teams_command",
                event_data=event_data,
                user_id=user_id,
                db=db,
            )

        if task_ids:
            card = build_workflow_started_card(name, "running")
        else:
            card = build_workflow_started_card(name, "pending")
    except Exception as e:
        logger.error(f"Workflow trigger dispatch error: {e}")
        card = build_workflow_started_card(name, "pending")

    await turn_context.send_activity(
        Activity(
            type=ActivityTypes.message,
            attachments=[_make_card_attachment(card)],
        )
    )


async def handle_status_command(turn_context: TurnContext, run_id: str):
    """Handle /status command — check workflow status."""
    if not run_id:
        await turn_context.send_activity("Por favor, informe o ID do workflow. Ex: /status abc123")
        return

    await turn_context.send_activity(Activity(type=ActivityTypes.typing))
    card = build_workflow_status_card(run_id, "running", "Processando...")
    await turn_context.send_activity(
        Activity(
            type=ActivityTypes.message,
            attachments=[_make_card_attachment(card)],
        )
    )


async def handle_help_command(turn_context: TurnContext):
    """Handle /ajuda command — show available commands."""
    card = build_help_card()
    await turn_context.send_activity(
        Activity(
            type=ActivityTypes.message,
            attachments=[_make_card_attachment(card)],
        )
    )


async def handle_free_chat(turn_context: TurnContext, text: str):
    """Handle free-form chat — send to LLM."""
    if not text:
        return

    await turn_context.send_activity(Activity(type=ActivityTypes.typing))
    # TODO: Create chat session and stream LLM response
    await turn_context.send_activity(
        f"Recebi sua mensagem. A funcionalidade de chat livre sera implementada em breve."
    )


async def handle_card_action(turn_context: TurnContext):
    """Handle Adaptive Card action submissions (e.g., HIL approve/reject)."""
    value = turn_context.activity.value
    if not value:
        return

    action = value.get("action")

    if action == "hil_approve":
        run_id = value.get("run_id")
        node = value.get("node")
        comment = value.get("comment", "")
        # TODO: Call workflow HIL endpoint
        await turn_context.send_activity(f"Workflow aprovado! Run: {run_id}, Node: {node}")

    elif action == "hil_reject":
        run_id = value.get("run_id")
        node = value.get("node")
        comment = value.get("comment", "")
        await turn_context.send_activity(f"Workflow rejeitado. Run: {run_id}, Node: {node}")

    else:
        logger.warning(f"Unknown card action: {action}")
