"""
Builtin workflows for the Outlook Add-in.

These are lightweight workflows that execute via direct AI calls (no LangGraph)
and are identified by slug instead of UUID.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


BUILTIN_WORKFLOWS = {
    "extract-deadlines": {
        "name": "Extrair Prazos",
        "description": "Extrai prazos e datas do e-mail e retorna lista estruturada",
    },
    "draft-reply": {
        "name": "Minutar Resposta",
        "description": "Gera rascunho de resposta juridica ao e-mail",
    },
    "create-calendar-events": {
        "name": "Criar Eventos no Calendario",
        "description": "Extrai prazos do e-mail e cria eventos no calendario do Outlook",
    },
    "classify-archive": {
        "name": "Classificar e Arquivar",
        "description": "Classifica o tipo juridico do e-mail e sugere pasta de arquivamento",
    },
}


def is_builtin(workflow_id: str) -> bool:
    return workflow_id in BUILTIN_WORKFLOWS


def get_builtin_name(workflow_id: str) -> Optional[str]:
    info = BUILTIN_WORKFLOWS.get(workflow_id)
    return info["name"] if info else None


async def execute(
    workflow_id: str,
    email_data: dict,
    parameters: dict | None,
    user_id: str,
    db: AsyncSession,
) -> dict:
    """Execute a builtin workflow and return structured output."""
    handler = _HANDLERS.get(workflow_id)
    if not handler:
        raise ValueError(f"Unknown builtin workflow: {workflow_id}")
    return await handler(email_data, parameters or {}, user_id, db)


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


async def _extract_deadlines(
    email_data: dict, parameters: dict, user_id: str, db: AsyncSession
) -> dict:
    """Reutiliza lógica de outlook_addin_service.extract_deadlines."""
    from app.services.outlook_addin_service import outlook_addin_service

    result = await outlook_addin_service.extract_deadlines(
        subject=email_data.get("subject", ""),
        body=email_data.get("body", ""),
        body_type="html",
        user_id=user_id,
        db=db,
    )
    return {"prazos": [p.model_dump() for p in result.prazos], "total": result.total}


async def _draft_reply(
    email_data: dict, parameters: dict, user_id: str, db: AsyncSession
) -> dict:
    """Gera rascunho de resposta juridica via Gemini."""
    from app.services.ai.agent_clients import call_vertex_gemini_async, init_vertex_client
    from app.services.ai.model_registry import get_api_model_name

    client = init_vertex_client()

    tone = parameters.get("tone", "formal")
    instructions = parameters.get("instructions", "")

    prompt = f"""Elabore um rascunho de resposta juridica ao seguinte e-mail.
Tom: {tone}
{f'Instrucoes adicionais: {instructions}' if instructions else ''}

ASSUNTO: {email_data.get('subject', '')}
DE: {email_data.get('sender', '')}
PARA: {', '.join(email_data.get('recipients', []))}

CORPO:
{email_data.get('body', '')[:30000]}

Retorne JSON com:
- assunto: assunto da resposta
- corpo_html: corpo da resposta em HTML
- observacoes: lista de observacoes para o advogado revisar"""

    system_prompt = (
        "Voce e um assistente juridico especializado em redacao de respostas a e-mails. "
        "Responda SEMPRE em portugues brasileiro. "
        "Retorne APENAS JSON valido, sem markdown ou explicacoes."
    )

    response = await call_vertex_gemini_async(
        client=client,
        prompt=prompt,
        model=get_api_model_name("gemini-3-flash"),
        system_instruction=system_prompt,
    )

    try:
        result = json.loads(response or "{}")
    except json.JSONDecodeError:
        result = {"assunto": "Re: " + email_data.get("subject", ""), "corpo_html": response or "", "observacoes": []}

    # Optionally send via Graph if parameters.send_draft is True
    if parameters.get("send_draft"):
        try:
            from app.services.graph_email import send_email

            sender = email_data.get("sender", "")
            if sender:
                await send_email(
                    user_id=user_id,
                    to=[sender],
                    subject=result.get("assunto", ""),
                    body_html=result.get("corpo_html", ""),
                    db=db,
                )
                result["draft_sent"] = True
        except Exception as e:
            logger.warning(f"Failed to send draft reply: {e}")
            result["draft_sent"] = False
            result["draft_error"] = str(e)

    return result


async def _create_calendar_events(
    email_data: dict, parameters: dict, user_id: str, db: AsyncSession
) -> dict:
    """Extrai prazos e cria eventos no calendario."""
    from app.services.graph_calendar import create_event

    # Step 1: Extract deadlines
    deadlines_result = await _extract_deadlines(email_data, parameters, user_id, db)
    prazos = deadlines_result.get("prazos", [])

    if not prazos:
        return {"events_created": 0, "prazos": [], "message": "Nenhum prazo encontrado no e-mail"}

    # Step 2: Create calendar events for each deadline
    events_created = []
    for prazo in prazos:
        try:
            data_str = prazo.get("data", "")
            descricao = prazo.get("descricao", "Prazo juridico")
            urgencia = prazo.get("urgencia", "media")

            # Parse date — accept ISO format or descriptive
            try:
                start = datetime.fromisoformat(data_str.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                logger.warning(f"Could not parse date '{data_str}', skipping event")
                continue

            # Default 1h event for deadlines
            end = start + timedelta(hours=1)

            # Set reminder based on urgency
            reminder = {"alta": 1440, "media": 60, "baixa": 15}.get(urgencia, 60)

            subject_prefix = email_data.get("subject", "E-mail")
            event = await create_event(
                user_id=user_id,
                subject=f"[Prazo] {descricao} — {subject_prefix}",
                body_html=f"<p>Prazo extraido automaticamente do e-mail: <b>{subject_prefix}</b></p>"
                          f"<p>Urgencia: {urgencia}</p><p>Tipo: {prazo.get('tipo', 'N/A')}</p>",
                start=start,
                end=end,
                db=db,
                reminder_minutes=reminder,
            )
            events_created.append({
                "prazo": prazo,
                "event_id": event.get("id"),
                "status": "created",
            })
        except Exception as e:
            logger.warning(f"Failed to create calendar event for prazo: {e}")
            events_created.append({
                "prazo": prazo,
                "status": "error",
                "error": str(e),
            })

    return {
        "events_created": len([e for e in events_created if e["status"] == "created"]),
        "events": events_created,
    }


async def _classify_archive(
    email_data: dict, parameters: dict, user_id: str, db: AsyncSession
) -> dict:
    """Classifica tipo juridico e sugere pasta de arquivamento."""
    from app.services.outlook_addin_service import outlook_addin_service
    from app.services.ai.agent_clients import call_vertex_gemini_async, init_vertex_client
    from app.services.ai.model_registry import get_api_model_name

    # Step 1: Classify
    classify_result = await outlook_addin_service.classify_email(
        subject=email_data.get("subject", ""),
        from_address=email_data.get("sender", ""),
        body=email_data.get("body", ""),
        body_type="html",
        user_id=user_id,
        db=db,
    )

    # Step 2: Suggest archive folder via AI
    client = init_vertex_client()

    prompt = f"""Com base na classificacao juridica abaixo, sugira a pasta de arquivamento mais adequada.

Tipo: {classify_result.tipo_juridico}
Subtipo: {classify_result.subtipo or 'N/A'}
Tags: {', '.join(classify_result.tags)}
Assunto: {email_data.get('subject', '')}
Remetente: {email_data.get('sender', '')}

Retorne JSON com:
- pasta_sugerida: caminho da pasta sugerida (ex: "Contratos/Locacao", "Processos/Trabalhista")
- confianca: confianca na sugestao (0.0 a 1.0)
- alternativas: lista de pastas alternativas"""

    response = await call_vertex_gemini_async(
        client=client,
        prompt=prompt,
        model=get_api_model_name("gemini-3-flash"),
        system_instruction=(
            "Voce e um assistente juridico especializado em organizacao de documentos. "
            "Retorne APENAS JSON valido."
        ),
    )

    try:
        folder_suggestion = json.loads(response or "{}")
    except json.JSONDecodeError:
        folder_suggestion = {"pasta_sugerida": "Geral", "confianca": 0.0, "alternativas": []}

    return {
        "classificacao": classify_result.model_dump(),
        "arquivamento": folder_suggestion,
    }


_HANDLERS = {
    "extract-deadlines": _extract_deadlines,
    "draft-reply": _draft_reply,
    "create-calendar-events": _create_calendar_events,
    "classify-archive": _classify_archive,
}
