"""
TableChatService — Chat interface for Review Table data queries.

Allows users to ask natural language questions about extracted data in Review Tables.
Inspired by Harvey AI's "Ask Harvey" feature for data interrogation.

Supports:
- Filter queries: "Which documents have X?"
- Aggregation queries: "How many documents have X?"
- Comparison queries: "Compare X across documents"
- Summary queries: "Summarize the findings"
- Specific queries: "What does document Y say about X?"
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time_utils import utcnow
from app.models.review_table import ReviewTable, ReviewTableTemplate
from app.models.table_chat import MessageRole, QueryType, TableChatMessage
from app.services.ai.agent_clients import (
    call_anthropic_async,
    call_vertex_gemini_async,
    get_claude_client,
    get_gemini_client,
)

logger = logging.getLogger("TableChatService")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_MODEL = "gemini-3-flash"
AI_TIMEOUT = 60
MAX_HISTORY_MESSAGES = 20
MAX_TABLE_CONTEXT_LENGTH = 30000


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

TABLE_CHAT_SYSTEM_PROMPT = """Voce e um assistente juridico analitico especializado em analise de dados extraidos de documentos.
Voce tem acesso a uma Review Table contendo dados estruturados extraidos de multiplos documentos.

Suas responsabilidades:
1. Responder perguntas sobre os dados da tabela de forma precisa e objetiva
2. Citar documentos especificos que fundamentam suas respostas
3. Realizar calculos e agregacoes quando solicitado
4. Identificar padroes e comparar dados entre documentos
5. Fornecer resumos e insights quando apropriado

Sempre responda em portugues brasileiro de forma clara e profissional."""


TABLE_CHAT_PROMPT = """## CONTEXTO DA REVIEW TABLE

### Tabela: "{table_name}"
### Colunas Disponiveis: {column_names}
### Total de Documentos: {doc_count}

{table_context}

## HISTORICO DA CONVERSA
{history}

## PERGUNTA DO USUARIO
{question}

## INSTRUCOES PARA RESPOSTA

1. Analise a pergunta e os dados da tabela
2. Identifique o tipo de query:
   - FILTER: perguntas do tipo "quais documentos tem X?"
   - AGGREGATION: perguntas do tipo "quantos/qual porcentagem tem X?"
   - COMPARISON: perguntas do tipo "compare X entre documentos"
   - SUMMARY: perguntas do tipo "resuma os achados"
   - SPECIFIC: perguntas sobre um documento especifico
   - GENERAL: perguntas gerais sobre a tabela

3. Responda de forma clara e objetiva em portugues
4. Cite os documentos especificos que fundamentam sua resposta
5. Para queries quantitativas, faca calculos precisos
6. Sugira uma visualizacao quando apropriado (bar_chart, pie_chart, table, list)

Responda em JSON valido com o seguinte formato:
```json
{{
  "answer": "<resposta detalhada em portugues>",
  "query_type": "<filter|aggregation|comparison|summary|specific|general>",
  "documents_referenced": [
    {{"id": "<doc_id>", "name": "<doc_name>", "relevance": "<por que este documento e relevante>"}}
  ],
  "structured_data": {{
    "type": "<count|percentage|list|comparison|null>",
    "data": "<dados estruturados ou null>"
  }},
  "visualization_hint": "<bar_chart|pie_chart|table|list|null>"
}}
```

Responda APENAS com o JSON, sem texto adicional."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_json_parse(text: str) -> Any:
    """Tenta parsear JSON mesmo com markdown code fences."""
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        cleaned = "\n".join(lines)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None


async def _call_ai(
    prompt: str,
    system_instruction: Optional[str] = None,
    model: str = DEFAULT_MODEL,
    max_tokens: int = 4000,
    temperature: float = 0.2,
) -> Optional[str]:
    """Chama modelo de IA com fallback Gemini -> Claude."""
    gemini_client = get_gemini_client()
    if gemini_client:
        try:
            result = await call_vertex_gemini_async(
                client=gemini_client,
                prompt=prompt,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                timeout=AI_TIMEOUT,
                system_instruction=system_instruction,
            )
            if result:
                return result
        except Exception as e:
            logger.warning("Gemini falhou para table chat, tentando Claude: %s", e)

    claude_client = get_claude_client()
    if claude_client:
        try:
            result = await call_anthropic_async(
                client=claude_client,
                prompt=prompt,
                model="claude-4.5-sonnet",
                max_tokens=max_tokens,
                temperature=temperature,
                timeout=AI_TIMEOUT,
                system_instruction=system_instruction,
            )
            if result:
                return result
        except Exception as e:
            logger.error("Claude tambem falhou para table chat: %s", e)

    return None


# ---------------------------------------------------------------------------
# TableChatService
# ---------------------------------------------------------------------------


class TableChatService:
    """Servico de chat para consultas em Review Tables."""

    # -----------------------------------------------------------------------
    # ask_table — Main entry point
    # -----------------------------------------------------------------------

    async def ask_table(
        self,
        review_table_id: str,
        question: str,
        user_id: str,
        db: AsyncSession,
        include_history: bool = True,
    ) -> Dict[str, Any]:
        """Processa uma pergunta sobre os dados de uma Review Table.

        Args:
            review_table_id: ID da review table.
            question: Pergunta do usuario em linguagem natural.
            user_id: ID do usuario.
            db: Sessao do banco de dados.
            include_history: Se deve incluir historico da conversa.

        Returns:
            Dict com: answer, documents, data, visualization_hint, message_id
        """
        # 1. Carregar review table
        review = await db.get(ReviewTable, review_table_id)
        if not review:
            raise ValueError(f"Review table {review_table_id} nao encontrada")

        # 2. Carregar template para obter definicoes das colunas
        template = await db.get(ReviewTableTemplate, review.template_id)
        if not template:
            raise ValueError(f"Template {review.template_id} nao encontrado")

        # 3. Construir contexto da tabela
        table_context = self._build_table_context(
            review=review,
            columns=template.columns or [],
        )

        # 4. Carregar historico de mensagens (se habilitado)
        history_text = ""
        if include_history:
            history_messages = await self._get_recent_history(
                review_table_id=review_table_id,
                db=db,
                limit=MAX_HISTORY_MESSAGES,
            )
            history_text = self._format_history(history_messages)

        # 5. Construir prompt
        column_names = [c["name"] for c in (template.columns or [])]
        prompt = TABLE_CHAT_PROMPT.format(
            table_name=review.name,
            column_names=", ".join(column_names),
            doc_count=len(review.results or []),
            table_context=table_context,
            history=history_text if history_text else "(sem historico)",
            question=question,
        )

        # 6. Salvar mensagem do usuario
        user_message = TableChatMessage(
            id=str(uuid.uuid4()),
            review_table_id=review_table_id,
            user_id=user_id,
            role=MessageRole.USER.value,
            content=question,
            documents_referenced=[],
        )
        db.add(user_message)
        await db.commit()

        # 7. Chamar IA
        start_time = datetime.now()
        response = await _call_ai(
            prompt=prompt,
            system_instruction=TABLE_CHAT_SYSTEM_PROMPT,
            max_tokens=4000,
            temperature=0.2,
        )
        latency_ms = int((datetime.now() - start_time).total_seconds() * 1000)

        # 8. Parsear resposta
        parsed = _safe_json_parse(response) if response else None

        if not parsed or not isinstance(parsed, dict):
            # Fallback: usar resposta bruta
            answer = response.strip() if response else "Nao foi possivel processar a pergunta."
            parsed = {
                "answer": answer,
                "query_type": "general",
                "documents_referenced": [],
                "structured_data": None,
                "visualization_hint": None,
            }

        # 9. Extrair dados da resposta
        answer = parsed.get("answer", "")
        query_type_str = parsed.get("query_type", "general")
        docs_referenced = parsed.get("documents_referenced", [])
        structured_data = parsed.get("structured_data")
        viz_hint = parsed.get("visualization_hint")

        # Normalizar query_type
        try:
            query_type = QueryType(query_type_str)
        except ValueError:
            query_type = QueryType.GENERAL

        # Extrair IDs dos documentos
        doc_ids = [d.get("id", "") for d in docs_referenced if isinstance(d, dict)]

        # 10. Salvar mensagem do assistente
        assistant_message = TableChatMessage(
            id=str(uuid.uuid4()),
            review_table_id=review_table_id,
            user_id=user_id,
            role=MessageRole.ASSISTANT.value,
            content=answer,
            query_type=query_type.value,
            query_result=structured_data,
            documents_referenced=doc_ids,
            visualization_hint=viz_hint,
            msg_metadata={
                "model": DEFAULT_MODEL,
                "latency_ms": latency_ms,
            },
        )
        db.add(assistant_message)
        await db.commit()
        await db.refresh(assistant_message)

        logger.info(
            "Table chat: table=%s, query_type=%s, docs_ref=%d, latency=%dms",
            review_table_id,
            query_type.value,
            len(doc_ids),
            latency_ms,
        )

        # 11. Retornar resposta formatada
        return {
            "answer": answer,
            "query_type": query_type.value,
            "documents": docs_referenced,
            "data": structured_data,
            "visualization_hint": viz_hint,
            "message_id": assistant_message.id,
        }

    # -----------------------------------------------------------------------
    # build_table_context
    # -----------------------------------------------------------------------

    def _build_table_context(
        self,
        review: ReviewTable,
        columns: List[Dict[str, Any]],
    ) -> str:
        """Constroi contexto textual da tabela para o LLM.

        Inclui:
        - Nome e descricao das colunas
        - Dados extraidos de cada documento
        - Estatisticas resumidas
        """
        if not review.results:
            return "(tabela vazia - sem dados extraidos)"

        lines: List[str] = []

        # Definicoes das colunas
        lines.append("### COLUNAS DEFINIDAS")
        for col in columns:
            col_name = col.get("name", "")
            col_type = col.get("type", "text")
            col_prompt = col.get("extraction_prompt", "")
            lines.append(f"- **{col_name}** ({col_type}): {col_prompt}")
        lines.append("")

        # Dados extraidos
        lines.append("### DADOS EXTRAIDOS")
        col_names = [c["name"] for c in columns]

        for i, row in enumerate(review.results, 1):
            doc_name = row.get("document_name", "Desconhecido")
            doc_id = row.get("document_id", "")
            cols = row.get("columns", {})

            lines.append(f"#### Documento {i}: {doc_name} (id: {doc_id})")
            for col_name in col_names:
                val = cols.get(col_name, "-")
                lines.append(f"  - {col_name}: {val}")
            lines.append("")

        # Truncar se muito longo
        context = "\n".join(lines)
        if len(context) > MAX_TABLE_CONTEXT_LENGTH:
            context = context[:MAX_TABLE_CONTEXT_LENGTH] + "\n\n[... dados truncados por tamanho]"

        return context

    # -----------------------------------------------------------------------
    # get_chat_history
    # -----------------------------------------------------------------------

    async def get_chat_history(
        self,
        review_table_id: str,
        db: AsyncSession,
        limit: int = 50,
        offset: int = 0,
    ) -> List[TableChatMessage]:
        """Retorna historico de mensagens de uma review table."""
        stmt = (
            select(TableChatMessage)
            .where(TableChatMessage.review_table_id == review_table_id)
            .order_by(TableChatMessage.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await db.execute(stmt)
        messages = result.scalars().all()
        # Retornar em ordem cronologica
        return list(reversed(messages))

    async def _get_recent_history(
        self,
        review_table_id: str,
        db: AsyncSession,
        limit: int = MAX_HISTORY_MESSAGES,
    ) -> List[TableChatMessage]:
        """Retorna as mensagens mais recentes para contexto."""
        return await self.get_chat_history(
            review_table_id=review_table_id,
            db=db,
            limit=limit,
        )

    def _format_history(self, messages: List[TableChatMessage]) -> str:
        """Formata historico de mensagens para o prompt."""
        if not messages:
            return ""

        lines: List[str] = []
        for msg in messages:
            role = "Usuario" if msg.role == MessageRole.USER.value else "Assistente"
            lines.append(f"**{role}**: {msg.content}")
            lines.append("")

        return "\n".join(lines)

    # -----------------------------------------------------------------------
    # clear_chat_history
    # -----------------------------------------------------------------------

    async def clear_chat_history(
        self,
        review_table_id: str,
        db: AsyncSession,
    ) -> int:
        """Limpa historico de chat de uma review table.

        Returns:
            Numero de mensagens deletadas.
        """
        stmt = select(TableChatMessage).where(
            TableChatMessage.review_table_id == review_table_id
        )
        result = await db.execute(stmt)
        messages = result.scalars().all()

        count = len(messages)
        for msg in messages:
            await db.delete(msg)

        await db.commit()

        logger.info(
            "Chat history cleared: table=%s, messages_deleted=%d",
            review_table_id,
            count,
        )

        return count

    # -----------------------------------------------------------------------
    # execute_data_query — Structured query execution
    # -----------------------------------------------------------------------

    async def execute_data_query(
        self,
        review: ReviewTable,
        query_type: QueryType,
        filter_column: Optional[str] = None,
        filter_value: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Executa uma query estruturada sobre os dados da tabela.

        Para queries que podem ser resolvidas sem chamar a IA.

        Args:
            review: Review table com os dados.
            query_type: Tipo de query.
            filter_column: Coluna para filtrar (opcional).
            filter_value: Valor para filtrar (opcional).

        Returns:
            Dict com resultados estruturados.
        """
        results = review.results or []

        if query_type == QueryType.FILTER and filter_column and filter_value:
            # Filtrar documentos que contem o valor na coluna
            filtered = []
            for row in results:
                cols = row.get("columns", {})
                val = str(cols.get(filter_column, "")).lower()
                if filter_value.lower() in val:
                    filtered.append({
                        "document_id": row.get("document_id", ""),
                        "document_name": row.get("document_name", ""),
                        "value": cols.get(filter_column, ""),
                    })
            return {
                "type": "list",
                "count": len(filtered),
                "data": filtered,
            }

        if query_type == QueryType.AGGREGATION and filter_column:
            # Contar ocorrencias de valores distintos
            value_counts: Dict[str, int] = {}
            for row in results:
                cols = row.get("columns", {})
                val = str(cols.get(filter_column, "N/A"))
                value_counts[val] = value_counts.get(val, 0) + 1

            total = len(results)
            percentages = {
                k: round(v / total * 100, 1) if total > 0 else 0
                for k, v in value_counts.items()
            }
            return {
                "type": "aggregation",
                "total": total,
                "counts": value_counts,
                "percentages": percentages,
            }

        return {"type": "none", "data": None}

    # -----------------------------------------------------------------------
    # get_table_statistics
    # -----------------------------------------------------------------------

    async def get_table_statistics(
        self,
        review: ReviewTable,
        template: ReviewTableTemplate,
    ) -> Dict[str, Any]:
        """Calcula estatisticas resumidas da tabela.

        Util para fornecer contexto inicial ao usuario.
        """
        results = review.results or []
        columns = template.columns or []
        col_names = [c["name"] for c in columns]

        stats: Dict[str, Any] = {
            "total_documents": len(results),
            "columns": len(col_names),
            "column_stats": {},
        }

        for col_name in col_names:
            filled = 0
            not_found = 0
            unique_values: set = set()

            for row in results:
                val = row.get("columns", {}).get(col_name, "")
                val_lower = str(val).lower().strip()

                if val_lower in ("nao encontrado", "erro", "", "erro na extracao") or val_lower.startswith("erro:"):
                    not_found += 1
                else:
                    filled += 1
                    unique_values.add(val_lower)

            stats["column_stats"][col_name] = {
                "filled": filled,
                "not_found": not_found,
                "unique_values": len(unique_values),
                "fill_rate": round(filled / len(results) * 100, 1) if results else 0,
            }

        return stats


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

table_chat_service = TableChatService()
