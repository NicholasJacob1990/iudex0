"""
Serviço para operações do Word Add-in.

Reutiliza serviços existentes (playbook, chat) adaptados para o contexto
do Office Add-in, onde o conteúdo vem inline (não de um documento salvo).
"""

import json
import logging
from typing import AsyncGenerator, Optional

from app.core.config import settings
from app.schemas.word_addin import (
    ClauseAnalysisResult,
    InlineAnalyzeResponse,
)

logger = logging.getLogger(__name__)


class WordAddinService:
    """Serviço para operações específicas do Word Add-in."""

    async def analyze_inline_content(
        self,
        playbook_id: str,
        document_content: str,
        document_format: str,
        user_id: str,
        db=None,
    ) -> InlineAnalyzeResponse:
        """
        Analisa conteúdo inline com um playbook.

        Reutiliza a lógica do PlaybookService mas aceita texto direto
        em vez de requerer um documento salvo no banco.
        """
        from app.services.playbook_service import PlaybookService

        playbook_service = PlaybookService()

        try:
            result = await playbook_service.analyze_document_content(
                playbook_id=playbook_id,
                content=document_content,
                user_id=user_id,
                db=db,
            )

            clauses = []
            for item in result.get("analyses", []):
                clauses.append(ClauseAnalysisResult(
                    id=item.get("id", ""),
                    text=item.get("text", ""),
                    classification=item.get("classification", "parcial"),
                    severity=item.get("severity", "info"),
                    rule_id=item.get("rule_id", ""),
                    rule_name=item.get("rule_name", ""),
                    explanation=item.get("explanation", ""),
                    suggested_redline=item.get("suggested_redline"),
                ))

            compliant = sum(1 for c in clauses if c.classification == "conforme")
            non_compliant = sum(1 for c in clauses if c.classification == "nao_conforme")

            return InlineAnalyzeResponse(
                playbook_id=playbook_id,
                clauses=clauses,
                summary=result.get("summary", ""),
                total_rules=result.get("total_rules", len(clauses)),
                compliant=compliant,
                non_compliant=non_compliant,
            )
        except Exception as e:
            logger.error(f"Erro na análise inline: {e}")
            raise

    async def edit_content_stream(
        self,
        content: str,
        instruction: str,
        model: Optional[str] = None,
        context: Optional[str] = None,
        user_id: str = "",
    ) -> AsyncGenerator[str, None]:
        """
        Edita conteúdo com IA via streaming SSE.

        Retorna eventos SSE com o conteúdo editado.
        """
        from app.services.ai.providers import get_llm_provider

        model_id = model or "gemini-3-flash"

        system_prompt = (
            "Você é um assistente jurídico especializado em edição de documentos legais brasileiros. "
            "Edite o texto conforme a instrução do usuário. "
            "Retorne APENAS o texto editado, sem explicações adicionais. "
            "Mantenha a formatação e o estilo do original quando possível."
        )

        user_prompt = f"""## Instrução de edição
{instruction}

## Texto original
{content}"""

        if context:
            user_prompt += f"\n\n## Contexto adicional\n{context}"

        try:
            provider = get_llm_provider(model_id)

            # Emit thinking event
            yield f'data: {json.dumps({"type": "thinking", "data": "Analisando e editando o texto..."})}\n\n'

            # Stream the response
            full_response = ""
            async for chunk in provider.stream_chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                model=model_id,
            ):
                full_response += chunk
                yield f'data: {json.dumps({"type": "content", "data": chunk})}\n\n'

            # Emit done event
            yield f'data: {json.dumps({"type": "done", "data": full_response})}\n\n'

        except Exception as e:
            logger.error(f"Erro no stream de edição: {e}")
            yield f'data: {json.dumps({"type": "error", "data": str(e)})}\n\n'

    async def translate_content_stream(
        self,
        content: str,
        source_lang: str = "pt",
        target_lang: str = "en",
        user_id: str = "",
    ) -> AsyncGenerator[str, None]:
        """Traduz conteúdo via streaming SSE."""
        from app.services.ai.providers import get_llm_provider

        lang_names = {
            "pt": "português brasileiro",
            "en": "inglês",
            "es": "espanhol",
            "fr": "francês",
            "de": "alemão",
            "it": "italiano",
        }

        source_name = lang_names.get(source_lang, source_lang)
        target_name = lang_names.get(target_lang, target_lang)

        system_prompt = (
            f"Traduza o texto de {source_name} para {target_name}. "
            "Mantenha a formatação, termos técnicos jurídicos e referências legais. "
            "Retorne APENAS a tradução."
        )

        try:
            provider = get_llm_provider("gemini-3-flash")

            yield f'data: {json.dumps({"type": "thinking", "data": f"Traduzindo de {source_name} para {target_name}..."})}\n\n'

            full_response = ""
            async for chunk in provider.stream_chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": content},
                ],
                model="gemini-3-flash",
            ):
                full_response += chunk
                yield f'data: {json.dumps({"type": "content", "data": chunk})}\n\n'

            yield f'data: {json.dumps({"type": "done", "data": full_response})}\n\n'

        except Exception as e:
            logger.error(f"Erro na tradução: {e}")
            yield f'data: {json.dumps({"type": "error", "data": str(e)})}\n\n'

    async def anonymize_content(
        self,
        content: str,
        entities_to_anonymize: list[str],
        user_id: str = "",
    ) -> dict:
        """Anonimiza conteúdo identificando e substituindo PII."""
        from app.services.ai.providers import get_llm_provider

        system_prompt = (
            "Você é um especialista em proteção de dados (LGPD). "
            "Identifique e substitua todas as informações pessoais no texto. "
            "Use placeholders no formato [TIPO_N] (ex: [NOME_1], [CPF_1]). "
            "Retorne um JSON com: anonymized_content (texto anonimizado), "
            "entities_found (lista de {type, original, replacement}), "
            "mapping (dict replacement -> original)."
        )

        user_prompt = (
            f"Entidades para anonimizar: {', '.join(entities_to_anonymize)}\n\n"
            f"Texto:\n{content}"
        )

        try:
            provider = get_llm_provider("gemini-3-flash")

            response = await provider.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                model="gemini-3-flash",
                response_format={"type": "json_object"},
            )

            result = json.loads(response)
            return {
                "anonymized_content": result.get("anonymized_content", content),
                "entities_found": result.get("entities_found", []),
                "mapping": result.get("mapping", {}),
            }

        except Exception as e:
            logger.error(f"Erro na anonimização: {e}")
            raise


# Singleton
word_addin_service = WordAddinService()
