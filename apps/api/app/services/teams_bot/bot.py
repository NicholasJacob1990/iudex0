"""
IudexBot — Main Teams bot logic.
Classifies intent and dispatches to appropriate handler.
"""

import logging

from botbuilder.core import ActivityHandler, TurnContext

from app.services.teams_bot.handlers import (
    handle_search_command,
    handle_analyze_command,
    handle_workflow_command,
    handle_status_command,
    handle_help_command,
    handle_free_chat,
    handle_card_action,
)

logger = logging.getLogger(__name__)


class IudexBot(ActivityHandler):
    """Teams bot for Iudex/Vorbium."""

    async def on_message_activity(self, turn_context: TurnContext):
        text = (turn_context.activity.text or "").strip()

        # Handle Adaptive Card action submissions
        if turn_context.activity.value:
            await handle_card_action(turn_context)
            return

        # Route commands
        if text.startswith("/pesquisar") or text.startswith("pesquisar"):
            query = text.replace("/pesquisar", "").replace("pesquisar", "").strip()
            await handle_search_command(turn_context, query)
        elif text.startswith("/analisar") or text.startswith("analisar"):
            content = text.replace("/analisar", "").replace("analisar", "").strip()
            await handle_analyze_command(turn_context, content)
        elif text.startswith("/workflow") or text.startswith("workflow"):
            name = text.replace("/workflow", "").replace("workflow", "").strip()
            await handle_workflow_command(turn_context, name)
        elif text.startswith("/status") or text.startswith("status"):
            run_id = text.replace("/status", "").replace("status", "").strip()
            await handle_status_command(turn_context, run_id)
        elif text.startswith("/ajuda") or text.startswith("ajuda"):
            await handle_help_command(turn_context)
        else:
            await handle_free_chat(turn_context, text)

    async def on_members_added_activity(self, members_added, turn_context: TurnContext):
        for member in members_added:
            if member.id != turn_context.activity.recipient.id:
                await turn_context.send_activity(
                    "Ola! Sou o Vorbium, seu assistente juridico com IA. "
                    "Digite /ajuda para ver os comandos disponiveis."
                )
