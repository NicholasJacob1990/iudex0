"""
Serviço de Audit Logging.

Fornece função helper para registrar ações no audit log
e middleware para captura automática de chamadas API.
"""

from __future__ import annotations

import uuid
from typing import Any, Optional

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time_utils import utcnow
from app.models.audit_log import AuditLog


async def log_audit(
    db: AsyncSession,
    user_id: str,
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    details: Optional[dict[str, Any]] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> AuditLog:
    """
    Registra uma entrada no audit log.

    Args:
        db: Sessão do banco de dados
        user_id: ID do usuário que executou a ação
        action: Tipo de ação (create, read, update, delete, export, share, login, analyze)
        resource_type: Tipo do recurso afetado
        resource_id: ID do recurso (opcional)
        details: Detalhes extras em JSON (opcional)
        ip_address: IP do cliente (opcional)
        user_agent: User-Agent do cliente (opcional)

    Returns:
        AuditLog criado
    """
    entry = AuditLog(
        id=str(uuid.uuid4()),
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
        ip_address=ip_address,
        user_agent=user_agent,
        created_at=utcnow(),
    )
    db.add(entry)
    # Não fazemos commit aqui — o caller ou o middleware de DB controla a transação
    try:
        await db.flush()
    except Exception as e:
        logger.warning(f"Falha ao registrar audit log: {e}")
    return entry


def extract_client_ip(request) -> Optional[str]:
    """Extrai IP do cliente do request FastAPI, considerando proxies."""
    if hasattr(request, "headers"):
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip
    if hasattr(request, "client") and request.client:
        return request.client.host
    return None
