"""
Service layer for Outlook Add-in operations.

Handles email summarization, classification, and deadline extraction
using the existing AI infrastructure (agent_clients).
"""

import json
import logging
from datetime import timedelta
from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.time_utils import utcnow
from app.models.email_analysis_cache import EmailAnalysisCache
from app.schemas.outlook_addin_schemas import (
    ClassifyEmailResponse,
    ExtractDeadlinesResponse,
    DeadlineItem,
)

logger = logging.getLogger(__name__)

# Cache TTL: 24 hours
CACHE_TTL_HOURS = 24


class OutlookAddinService:
    """Service for Outlook Add-in email analysis."""

    async def get_cached_analysis(
        self,
        db: AsyncSession,
        user_id: str,
        message_id: str,
        analysis_type: str,
    ) -> Optional[dict]:
        """Check cache for previous analysis result."""
        stmt = select(EmailAnalysisCache).where(
            EmailAnalysisCache.user_id == user_id,
            EmailAnalysisCache.internet_message_id == message_id,
            EmailAnalysisCache.analysis_type == analysis_type,
            EmailAnalysisCache.expires_at > utcnow(),
        )
        result = await db.execute(stmt)
        cached = result.scalar_one_or_none()
        if cached:
            return cached.result
        return None

    async def _save_cache(
        self,
        db: AsyncSession,
        user_id: str,
        message_id: str,
        analysis_type: str,
        result: dict,
    ) -> None:
        """Save analysis result to cache."""
        cache_entry = EmailAnalysisCache(
            user_id=user_id,
            internet_message_id=message_id,
            analysis_type=analysis_type,
            result=result,
            expires_at=utcnow() + timedelta(hours=CACHE_TTL_HOURS),
        )
        db.add(cache_entry)
        try:
            await db.commit()
        except Exception:
            await db.rollback()

    async def summarize_email(
        self,
        subject: str,
        from_address: str,
        to_addresses: list[str],
        body: str,
        body_type: str,
        attachment_names: list[str],
        user_id: str,
        db: AsyncSession,
    ) -> AsyncGenerator[dict, None]:
        """
        Summarize email using AI with SSE streaming.
        Yields SSE events: thinking, content, done, error.
        """
        prompt = self._build_summarize_prompt(
            subject=subject,
            from_address=from_address,
            to_addresses=to_addresses,
            body=body,
            attachment_names=attachment_names,
        )

        system_prompt = self._get_system_prompt("summarize")
        accumulated_content = ""

        try:
            from app.services.ai.agent_clients import (
                stream_vertex_gemini_async,
                init_vertex_client,
            )
            from app.services.ai.model_registry import get_api_model_name

            client = init_vertex_client()

            yield {"type": "thinking", "data": "Analisando e-mail..."}

            # Stream the response using Gemini
            async for chunk_type, chunk_data in stream_vertex_gemini_async(
                client=client,
                prompt=prompt,
                model=get_api_model_name("gemini-3-flash"),
                system_instruction=system_prompt,
            ):
                if chunk_type == "thinking":
                    yield {"type": "thinking", "data": chunk_data}
                elif chunk_type == "text":
                    accumulated_content += chunk_data
                    yield {"type": "content", "data": chunk_data}
                elif chunk_type == "error":
                    yield {"type": "error", "data": chunk_data}
                    return

            # Parse the accumulated content into structured result
            try:
                result = json.loads(accumulated_content)
            except json.JSONDecodeError:
                result = {
                    "tipo_juridico": "Nao classificado",
                    "confianca": 0.0,
                    "resumo": accumulated_content,
                    "partes": [],
                    "prazos": [],
                    "acoes_sugeridas": [],
                    "workflows_recomendados": [],
                }

            yield {"type": "done", "data": result}

        except Exception as e:
            logger.error(f"Summarize email error: {e}")
            yield {"type": "error", "data": str(e)}

    async def classify_email(
        self,
        subject: str,
        from_address: str,
        body: str,
        body_type: str,
        user_id: str,
        db: AsyncSession,
    ) -> ClassifyEmailResponse:
        """Classify email legal type."""
        from app.services.ai.agent_clients import (
            call_vertex_gemini_async,
            init_vertex_client,
        )
        from app.services.ai.model_registry import get_api_model_name

        client = init_vertex_client()

        prompt = self._build_classify_prompt(subject, from_address, body)
        system_prompt = self._get_system_prompt("classify")

        response = await call_vertex_gemini_async(
            client=client,
            prompt=prompt,
            model=get_api_model_name("gemini-3-flash"),
            system_instruction=system_prompt,
        )

        try:
            data = json.loads(response or "{}")
            return ClassifyEmailResponse(**data)
        except (json.JSONDecodeError, ValueError):
            return ClassifyEmailResponse(
                tipo_juridico="Nao classificado",
                confianca=0.0,
                tags=[],
            )

    async def extract_deadlines(
        self,
        subject: str,
        body: str,
        body_type: str,
        user_id: str,
        db: AsyncSession,
    ) -> ExtractDeadlinesResponse:
        """Extract deadlines from email."""
        from app.services.ai.agent_clients import (
            call_vertex_gemini_async,
            init_vertex_client,
        )
        from app.services.ai.model_registry import get_api_model_name

        client = init_vertex_client()

        prompt = self._build_deadlines_prompt(subject, body)
        system_prompt = self._get_system_prompt("deadlines")

        response = await call_vertex_gemini_async(
            client=client,
            prompt=prompt,
            model=get_api_model_name("gemini-3-flash"),
            system_instruction=system_prompt,
        )

        try:
            data = json.loads(response or "{}")
            prazos = [DeadlineItem(**p) for p in data.get("prazos", [])]
            return ExtractDeadlinesResponse(prazos=prazos, total=len(prazos))
        except (json.JSONDecodeError, ValueError):
            return ExtractDeadlinesResponse(prazos=[], total=0)

    def _build_summarize_prompt(
        self,
        subject: str,
        from_address: str,
        to_addresses: list[str],
        body: str,
        attachment_names: list[str],
    ) -> str:
        attachments_str = ", ".join(attachment_names) if attachment_names else "Nenhum"
        return f"""Analise o seguinte e-mail juridico e retorne um JSON com:
- tipo_juridico: tipo do documento/comunicacao juridica
- confianca: nivel de confianca da classificacao (0.0 a 1.0)
- resumo: resumo estruturado do conteudo
- partes: lista de partes envolvidas
- prazos: lista de prazos (cada um com data, descricao, urgencia)
- acoes_sugeridas: lista de acoes recomendadas
- workflows_recomendados: lista de workflows relevantes (id, name, relevance)

ASSUNTO: {subject}
DE: {from_address}
PARA: {', '.join(to_addresses)}
ANEXOS: {attachments_str}

CORPO:
{body[:50000]}"""

    def _build_classify_prompt(self, subject: str, from_address: str, body: str) -> str:
        return f"""Classifique o tipo juridico deste e-mail. Retorne JSON com:
- tipo_juridico: classificacao principal (ex: "Notificacao Extrajudicial", "Contrato", "Peticao", "Parecer", "Comunicacao Interna", etc.)
- subtipo: subclassificacao se aplicavel
- confianca: nivel de confianca (0.0 a 1.0)
- tags: lista de tags relevantes

ASSUNTO: {subject}
DE: {from_address}
CORPO (primeiros 5000 chars):
{body[:5000]}"""

    def _build_deadlines_prompt(self, subject: str, body: str) -> str:
        return f"""Extraia todos os prazos e datas relevantes deste e-mail juridico.
Retorne JSON com:
- prazos: lista de objetos com (data, descricao, urgencia, tipo)
  - data: no formato ISO 8601 ou descritivo
  - descricao: o que deve ser feito
  - urgencia: "alta", "media" ou "baixa"
  - tipo: "prazo_fatal", "prazo_ordinario", "reuniao", "vencimento", "outro"

ASSUNTO: {subject}
CORPO:
{body[:30000]}"""

    def _get_system_prompt(self, task: str) -> str:
        base = (
            "Voce e um assistente juridico especializado em analise de e-mails. "
            "Voce trabalha para o Vorbium, uma plataforma juridica com IA. "
            "Responda SEMPRE em portugues brasileiro. "
            "Retorne APENAS JSON valido, sem markdown ou explicacoes."
        )

        if task == "summarize":
            return base + " Voce deve analisar e-mails juridicos de forma completa, identificando tipo, partes, prazos e acoes."
        elif task == "classify":
            return base + " Voce deve classificar o tipo juridico do e-mail com alta precisao."
        elif task == "deadlines":
            return base + " Voce deve extrair todos os prazos e datas relevantes do e-mail."
        return base


# Singleton
outlook_addin_service = OutlookAddinService()
