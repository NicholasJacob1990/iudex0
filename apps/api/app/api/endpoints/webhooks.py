"""
Endpoints para receber webhooks de serviços externos

Fornece handlers para:
- Notificações do serviço de tribunais
- Outros webhooks futuros
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request, status
from loguru import logger

from app.core.config import settings
from app.schemas.tribunais import WebhookEvent, WebhookResponse

router = APIRouter()


# =============================================================================
# Webhook do Serviço de Tribunais
# =============================================================================


async def _process_tribunais_webhook(event: WebhookEvent) -> None:
    """
    Processa evento de webhook do serviço de tribunais em background.

    Args:
        event: Evento recebido do serviço de tribunais
    """
    try:
        logger.info(
            f"Processando webhook tribunais: job={event.job_id}, "
            f"status={event.status}, operation={event.operation}"
        )

        # TODO: Implementar lógica de processamento baseada no tipo de evento
        # Exemplos:
        # - Notificar usuário via WebSocket
        # - Atualizar status no banco de dados
        # - Enviar email de confirmação
        # - Disparar próximas ações do workflow

        if event.status.value == "completed":
            logger.info(f"Operação {event.job_id} concluída com sucesso")
            # TODO: Notificar usuário de sucesso
            # await notify_user(event.user_id, {
            #     "type": "tribunais_operation_completed",
            #     "job_id": event.job_id,
            #     "operation": event.operation,
            #     "result": event.result,
            # })

        elif event.status.value == "failed":
            logger.error(f"Operação {event.job_id} falhou: {event.error}")
            # TODO: Notificar usuário de erro
            # await notify_user(event.user_id, {
            #     "type": "tribunais_operation_failed",
            #     "job_id": event.job_id,
            #     "operation": event.operation,
            #     "error": event.error,
            # })

        elif event.status.value == "waiting_sign":
            logger.info(f"Operação {event.job_id} aguardando assinatura")
            # TODO: Notificar usuário que precisa assinar
            # await notify_user(event.user_id, {
            #     "type": "tribunais_signature_required",
            #     "job_id": event.job_id,
            #     "operation": event.operation,
            # })

    except Exception as e:
        logger.error(f"Erro ao processar webhook tribunais: {e}")
        # Não propagar exceção para não causar retry do webhook


@router.post(
    "/tribunais",
    response_model=WebhookResponse,
    summary="Webhook do serviço de tribunais",
    description="Recebe notificações de operações concluídas do serviço de tribunais",
    responses={
        200: {"description": "Webhook recebido com sucesso"},
        400: {"description": "Payload inválido"},
        401: {"description": "Não autorizado"},
    },
)
async def tribunais_webhook(
    event: WebhookEvent,
    background_tasks: BackgroundTasks,
    x_webhook_secret: Optional[str] = Header(None, alias="X-Webhook-Secret"),
):
    """
    Recebe notificações do serviço de tribunais.

    Este endpoint é chamado pelo serviço de tribunais quando uma operação
    é concluída (sucesso ou falha).

    Eventos suportados:
    - **completed**: Operação concluída com sucesso
    - **failed**: Operação falhou
    - **waiting_sign**: Aguardando assinatura do usuário (A3)

    O processamento é feito em background para não bloquear a resposta.
    """
    # Validate webhook secret
    expected_secret = getattr(settings, "TRIBUNAIS_WEBHOOK_SECRET", None)
    if expected_secret:
        if x_webhook_secret != expected_secret:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid webhook secret",
            )
    else:
        logger.warning(
            "TRIBUNAIS_WEBHOOK_SECRET not configured. "
            "Webhook requests are not being validated. "
            "Set TRIBUNAIS_WEBHOOK_SECRET in production."
        )

    logger.info(
        f"Webhook tribunais recebido: job={event.job_id}, "
        f"user={event.user_id}, status={event.status}"
    )

    # Processar em background
    background_tasks.add_task(_process_tribunais_webhook, event)

    return WebhookResponse(
        received=True,
        message=f"Webhook received for job {event.job_id}",
    )


@router.post(
    "/tribunais/test",
    response_model=WebhookResponse,
    summary="Testar webhook de tribunais",
    description="Endpoint para testar configuração de webhooks",
    include_in_schema=False,  # Não mostrar na documentação pública
)
async def tribunais_webhook_test(request: Request):
    """
    Endpoint para testar configuração de webhooks.

    Útil para verificar conectividade e formato de payloads.
    """
    body = await request.json()
    logger.info(f"Webhook test recebido: {body}")

    return WebhookResponse(
        received=True,
        message="Test webhook received successfully",
    )


# =============================================================================
# Webhook Genérico (para outros serviços futuros)
# =============================================================================


@router.post(
    "/generic/{service}",
    response_model=WebhookResponse,
    summary="Webhook genérico",
    description="Recebe webhooks de serviços externos",
)
async def generic_webhook(
    service: str,
    request: Request,
    background_tasks: BackgroundTasks,
    x_webhook_secret: Optional[str] = Header(None, alias="X-Webhook-Secret"),
):
    """
    Endpoint genérico para receber webhooks de diferentes serviços.

    O parâmetro `service` identifica o serviço de origem e é usado
    para rotear o processamento.
    """
    try:
        body = await request.json()
    except Exception:
        body = {"raw": await request.body()}

    logger.info(f"Webhook genérico recebido de {service}: {body}")

    # TODO: Implementar roteamento baseado no serviço
    # if service == "stripe":
    #     await process_stripe_webhook(body)
    # elif service == "sendgrid":
    #     await process_sendgrid_webhook(body)

    return WebhookResponse(
        received=True,
        message=f"Webhook from {service} received",
    )
