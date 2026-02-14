"""
Adaptive Card builders for Teams Bot responses.
All builders return plain dicts (JSON-serializable).
Uses Adaptive Cards schema v1.5 (mobile-compatible elements use v1.2).
"""

import logging
from typing import Any

from botbuilder.schema import Attachment

logger = logging.getLogger(__name__)


def _card_attachment(card: dict) -> Attachment:
    """Wrap an Adaptive Card dict as a Bot Framework Attachment."""
    return Attachment(
        content_type="application/vnd.microsoft.card.adaptive",
        content=card,
    )


def build_search_results_card(query: str, results: list[dict]) -> dict:
    """Build Adaptive Card showing search results from corpus."""
    body: list[dict] = [
        {
            "type": "TextBlock",
            "text": "Resultados da Pesquisa",
            "weight": "Bolder",
            "size": "Large",
            "wrap": True,
        },
        {
            "type": "TextBlock",
            "text": f"Pesquisa: \"{query}\"",
            "isSubtle": True,
            "wrap": True,
        },
    ]

    if not results:
        body.append({
            "type": "TextBlock",
            "text": "Nenhum resultado encontrado.",
            "wrap": True,
        })
    else:
        for i, result in enumerate(results[:5], 1):
            title = result.get("title", result.get("name", f"Resultado {i}"))
            snippet = result.get("snippet", result.get("content", ""))[:200]
            score = result.get("score", 0)

            body.append({
                "type": "Container",
                "separator": True,
                "items": [
                    {
                        "type": "TextBlock",
                        "text": f"**{i}. {title}**",
                        "wrap": True,
                    },
                    {
                        "type": "TextBlock",
                        "text": snippet,
                        "wrap": True,
                        "isSubtle": True,
                        "maxLines": 3,
                    },
                    {
                        "type": "TextBlock",
                        "text": f"Relevancia: {score:.0%}" if isinstance(score, float) else f"Relevancia: {score}",
                        "wrap": True,
                        "size": "Small",
                        "color": "Accent",
                    },
                ],
            })

    body.append({
        "type": "TextBlock",
        "text": f"Total: {len(results)} resultado(s)",
        "wrap": True,
        "size": "Small",
        "isSubtle": True,
    })

    return {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.5",
        "body": body,
    }


def build_hil_notification_card(
    workflow_name: str,
    run_id: str,
    node_name: str,
    summary: str,
) -> dict:
    """Build Adaptive Card for Human-in-the-Loop approval request."""
    return {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.5",
        "body": [
            {
                "type": "TextBlock",
                "text": "Aprovacao Necessaria",
                "weight": "Bolder",
                "size": "Large",
                "color": "Warning",
                "wrap": True,
            },
            {
                "type": "FactSet",
                "facts": [
                    {"title": "Workflow", "value": workflow_name},
                    {"title": "Etapa", "value": node_name},
                    {"title": "Run ID", "value": run_id[:8] + "..."},
                ],
            },
            {
                "type": "TextBlock",
                "text": "Resumo:",
                "weight": "Bolder",
                "wrap": True,
            },
            {
                "type": "TextBlock",
                "text": summary,
                "wrap": True,
            },
            {
                "type": "Input.Text",
                "id": "comment",
                "placeholder": "Comentario (opcional)",
                "isMultiline": True,
            },
        ],
        "actions": [
            {
                "type": "Action.Submit",
                "title": "Aprovar",
                "style": "positive",
                "data": {
                    "action": "hil_approve",
                    "run_id": run_id,
                    "node": node_name,
                },
            },
            {
                "type": "Action.Submit",
                "title": "Rejeitar",
                "style": "destructive",
                "data": {
                    "action": "hil_reject",
                    "run_id": run_id,
                    "node": node_name,
                },
            },
        ],
    }


def build_notification_card(notification: dict) -> Attachment:
    """
    Dispatcher: build appropriate card based on notification type.
    Returns a Bot Framework Attachment.
    """
    notif_type = notification.get("type", "generic")

    if notif_type == "hil":
        card = build_hil_notification_card(
            workflow_name=notification.get("workflow_name", ""),
            run_id=notification.get("run_id", ""),
            node_name=notification.get("node_name", ""),
            summary=notification.get("summary", ""),
        )
    elif notif_type == "completion":
        card = build_completion_card(
            workflow_name=notification.get("workflow_name", ""),
            run_id=notification.get("run_id", ""),
            summary=notification.get("summary", ""),
        )
    else:
        # Generic notification card
        card = {
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "type": "AdaptiveCard",
            "version": "1.5",
            "body": [
                {
                    "type": "TextBlock",
                    "text": notification.get("title", "Notificacao"),
                    "weight": "Bolder",
                    "size": "Large",
                    "wrap": True,
                },
                {
                    "type": "TextBlock",
                    "text": notification.get("message", ""),
                    "wrap": True,
                },
            ],
        }

    return _card_attachment(card)


def build_help_card() -> dict:
    """Build Adaptive Card showing available bot commands."""
    return {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.5",
        "body": [
            {
                "type": "TextBlock",
                "text": "Vorbium — Comandos Disponiveis",
                "weight": "Bolder",
                "size": "Large",
                "wrap": True,
            },
            {
                "type": "TextBlock",
                "text": "Seu assistente juridico com IA no Teams.",
                "isSubtle": True,
                "wrap": True,
            },
            {
                "type": "Container",
                "separator": True,
                "items": [
                    {
                        "type": "FactSet",
                        "facts": [
                            {
                                "title": "/pesquisar [termo]",
                                "value": "Pesquisar no corpus de documentos",
                            },
                            {
                                "title": "/analisar [texto]",
                                "value": "Analisar texto com IA",
                            },
                            {
                                "title": "/workflow [nome]",
                                "value": "Iniciar um workflow automatizado",
                            },
                            {
                                "title": "/status [id]",
                                "value": "Verificar status de um workflow",
                            },
                            {
                                "title": "/ajuda",
                                "value": "Exibir esta mensagem de ajuda",
                            },
                        ],
                    },
                ],
            },
            {
                "type": "TextBlock",
                "text": "Voce tambem pode enviar mensagens livres para conversar com a IA.",
                "wrap": True,
                "isSubtle": True,
                "size": "Small",
            },
        ],
    }


def build_workflow_started_card(name: str, status: str) -> dict:
    """Build Adaptive Card confirming workflow initiation."""
    status_color = "Good" if status == "running" else "Accent"

    return {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.5",
        "body": [
            {
                "type": "TextBlock",
                "text": "Workflow Iniciado",
                "weight": "Bolder",
                "size": "Large",
                "wrap": True,
            },
            {
                "type": "FactSet",
                "facts": [
                    {"title": "Nome", "value": name},
                    {"title": "Status", "value": status},
                ],
            },
            {
                "type": "TextBlock",
                "text": "O workflow foi iniciado com sucesso. "
                        "Voce sera notificado quando houver atualizacoes.",
                "wrap": True,
                "isSubtle": True,
            },
        ],
    }


def build_workflow_status_card(run_id: str, status: str, summary: str) -> dict:
    """Build Adaptive Card showing workflow run status."""
    status_colors = {
        "running": "Accent",
        "completed": "Good",
        "error": "Attention",
        "waiting_hil": "Warning",
    }
    color = status_colors.get(status, "Default")

    status_labels = {
        "running": "Em execucao",
        "completed": "Concluido",
        "error": "Erro",
        "waiting_hil": "Aguardando aprovacao",
        "pending": "Pendente",
    }
    status_label = status_labels.get(status, status)

    return {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.5",
        "body": [
            {
                "type": "TextBlock",
                "text": "Status do Workflow",
                "weight": "Bolder",
                "size": "Large",
                "wrap": True,
            },
            {
                "type": "FactSet",
                "facts": [
                    {"title": "Run ID", "value": run_id[:8] + "..." if len(run_id) > 8 else run_id},
                    {"title": "Status", "value": status_label},
                ],
            },
            {
                "type": "TextBlock",
                "text": summary,
                "wrap": True,
            },
        ],
    }


def build_completion_card(workflow_name: str, run_id: str, summary: str) -> dict:
    """Build Adaptive Card for workflow completion notification."""
    return {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.5",
        "body": [
            {
                "type": "TextBlock",
                "text": "Workflow Concluido",
                "weight": "Bolder",
                "size": "Large",
                "color": "Good",
                "wrap": True,
            },
            {
                "type": "FactSet",
                "facts": [
                    {"title": "Workflow", "value": workflow_name},
                    {"title": "Run ID", "value": run_id[:8] + "..." if len(run_id) > 8 else run_id},
                    {"title": "Status", "value": "Concluido"},
                ],
            },
            {
                "type": "TextBlock",
                "text": "Resumo:",
                "weight": "Bolder",
                "wrap": True,
            },
            {
                "type": "TextBlock",
                "text": summary,
                "wrap": True,
            },
        ],
    }
