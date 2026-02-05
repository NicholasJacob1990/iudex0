"""
ColumnBuilderService - Construtor de colunas dinamicas via linguagem natural.

Permite que usuarios criem colunas de extracao perguntando em linguagem natural,
similar ao Harvey AI Column Builder. O servico:

1. Analisa o prompt do usuario para determinar o tipo de extracao
2. Gera um nome sugestivo para a coluna
3. Cria a DynamicColumn no banco
4. Extrai valores de todos os documentos da review table

Exemplo de uso:
    service = ColumnBuilderService()
    column = await service.create_column_from_prompt(
        review_table_id="...",
        prompt="What type of registration rights are granted?",
        user_id="..."
    )
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time_utils import utcnow
from app.models.document import Document
from app.models.dynamic_column import (
    CellExtraction,
    DynamicColumn,
    ExtractionType,
    VerificationStatus,
)
from app.models.review_table import ReviewTable
from app.services.ai.agent_clients import (
    call_anthropic_async,
    call_vertex_gemini_async,
    get_claude_client,
    get_gemini_client,
)

logger = logging.getLogger("ColumnBuilderService")

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

DEFAULT_MODEL = "gemini-2.0-flash"
AI_TIMEOUT = 90
MAX_DOC_TEXT_LENGTH = 25000
MAX_CONCURRENT_EXTRACTIONS = 5


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

SCHEMA_INFERENCE_PROMPT = """Voce e um especialista em analise de documentos juridicos.

Analise a pergunta abaixo e determine o tipo de dados mais adequado para a resposta.

## PERGUNTA
{prompt}

## TIPOS DISPONIVEIS
- "text": Texto livre, resumo ou descricao (para perguntas abertas)
- "boolean": Sim/Nao (para perguntas que podem ser respondidas com sim ou nao)
- "number": Valor numerico (para quantidades, contagens)
- "date": Data (para perguntas sobre datas especificas)
- "currency": Valor monetario (para valores em dinheiro)
- "enum": Opcoes pre-definidas (para classificacoes com opcoes conhecidas)
- "list": Lista de itens (para multiplos valores)
- "verbatim": Transcricao literal (quando precisa do texto exato do documento)
- "risk_rating": Classificacao de risco (Baixo/Medio/Alto/Critico)
- "compliance_check": Conformidade (Conforme/Nao Conforme/Parcialmente Conforme)

## INSTRUCOES
1. Analise a pergunta e identifique o tipo de resposta esperada
2. Se for uma pergunta de classificacao com opcoes obvias, use "enum" e sugira opcoes
3. Se for uma pergunta de sim/nao, use "boolean"
4. Se for sobre riscos ou conformidade, use os tipos especializados
5. Na duvida, use "text"
6. Sugira um nome curto e descritivo para a coluna (max 50 chars)

Responda em JSON:
```json
{{
  "extraction_type": "<tipo>",
  "column_name": "<nome sugerido para coluna>",
  "enum_options": ["opcao1", "opcao2"] ou null,
  "reasoning": "<breve explicacao da escolha>"
}}
```

Responda APENAS com o JSON, sem texto adicional."""


EXTRACTION_PROMPT = """Voce e um assistente juridico especializado em extracao de dados de documentos.

## TAREFA
Extraia a resposta para a pergunta abaixo a partir do documento fornecido.

## PERGUNTA
{prompt}

## TIPO DE RESPOSTA ESPERADA
{extraction_type_description}

{enum_options_section}

{instructions_section}

## DOCUMENTO
{document_text}

## INSTRUCOES DE EXTRACAO
1. Leia o documento completo com atencao
2. Encontre a informacao que responde a pergunta
3. Extraia EXATAMENTE o que foi pedido
4. Se a informacao NAO estiver no documento, responda: "Nao encontrado"
5. Cite o trecho do documento que fundamenta sua resposta
6. Atribua um score de confianca de 0.0 a 1.0:
   - 1.0: Informacao explicita e clara no documento
   - 0.7-0.9: Informacao presente mas requer interpretacao
   - 0.4-0.6: Informacao inferida ou parcialmente presente
   - 0.1-0.3: Baixa confianca, informacao ambigua
   - 0.0: Informacao nao encontrada

Responda em JSON:
```json
{{
  "value": "<valor extraido>",
  "confidence": <float 0.0 a 1.0>,
  "source_snippet": "<trecho do documento (max 300 chars)>",
  "source_page": <numero da pagina ou null>
}}
```

Responda APENAS com o JSON, sem texto adicional."""


EXTRACTION_TYPE_DESCRIPTIONS: Dict[str, str] = {
    "text": "Texto livre ou resumo conciso (2-3 frases)",
    "boolean": "Responda APENAS 'Sim' ou 'Nao'",
    "number": "Valor numerico (apenas o numero, sem unidades)",
    "date": "Data no formato DD/MM/AAAA",
    "currency": "Valor monetario (formato: 1000.00, sem simbolo de moeda)",
    "enum": "Escolha UMA das opcoes fornecidas",
    "list": "Lista de itens separados por ponto-e-virgula",
    "verbatim": "Transcricao literal do trecho relevante do documento",
    "risk_rating": "Classificacao: 'Baixo', 'Medio', 'Alto' ou 'Critico'",
    "compliance_check": "Classificacao: 'Conforme', 'Nao Conforme' ou 'Parcialmente Conforme'",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_json_parse(text: str) -> Optional[Dict[str, Any]]:
    """Tenta parsear JSON mesmo com markdown code fences."""
    if not text:
        return None
    cleaned = text.strip()
    # Remover code fences
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        cleaned = "\n".join(lines)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Tentar encontrar JSON no texto
        match = re.search(r'\{[^{}]*\}', cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return None


async def _call_ai(
    prompt: str,
    system_instruction: Optional[str] = None,
    model: str = DEFAULT_MODEL,
    max_tokens: int = 2000,
    temperature: float = 0.1,
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
            logger.warning("Gemini falhou para column builder, tentando Claude: %s", e)

    claude_client = get_claude_client()
    if claude_client:
        try:
            result = await call_anthropic_async(
                client=claude_client,
                prompt=prompt,
                model="claude-sonnet-4-20250514",
                max_tokens=max_tokens,
                temperature=temperature,
                timeout=AI_TIMEOUT,
                system_instruction=system_instruction,
            )
            if result:
                return result
        except Exception as e:
            logger.error("Claude tambem falhou para column builder: %s", e)

    return None


# ---------------------------------------------------------------------------
# ColumnBuilderService
# ---------------------------------------------------------------------------


class ColumnBuilderService:
    """Servico para criacao de colunas dinamicas via linguagem natural."""

    # -----------------------------------------------------------------------
    # infer_column_schema - Inferir tipo e nome da coluna
    # -----------------------------------------------------------------------

    async def infer_column_schema(
        self,
        prompt: str,
    ) -> Dict[str, Any]:
        """Usa LLM para analisar a pergunta e determinar o schema da coluna.

        Args:
            prompt: Pergunta em linguagem natural

        Returns:
            Dict com extraction_type, column_name, enum_options, reasoning
        """
        if not prompt or len(prompt.strip()) < 5:
            raise ValueError("O prompt deve ter no minimo 5 caracteres")

        inference_prompt = SCHEMA_INFERENCE_PROMPT.format(prompt=prompt)

        response = await _call_ai(
            prompt=inference_prompt,
            system_instruction=(
                "Voce e um especialista em analise de dados e extracao de informacoes. "
                "Determine o tipo de dado mais adequado para a pergunta fornecida. "
                "Responda APENAS em JSON valido."
            ),
            max_tokens=1000,
            temperature=0.2,
        )

        if not response:
            # Fallback: tipo texto com nome gerado do prompt
            return {
                "extraction_type": "text",
                "column_name": self._generate_column_name(prompt),
                "enum_options": None,
                "reasoning": "Fallback para tipo texto (IA indisponivel)",
            }

        parsed = _safe_json_parse(response)
        if not parsed:
            return {
                "extraction_type": "text",
                "column_name": self._generate_column_name(prompt),
                "enum_options": None,
                "reasoning": "Fallback para tipo texto (resposta invalida)",
            }

        # Validar tipo
        extraction_type = parsed.get("extraction_type", "text")
        valid_types = {t.value for t in ExtractionType}
        if extraction_type not in valid_types:
            extraction_type = "text"

        # Validar enum_options
        enum_options = parsed.get("enum_options")
        if extraction_type != "enum":
            enum_options = None
        elif enum_options and not isinstance(enum_options, list):
            enum_options = None

        return {
            "extraction_type": extraction_type,
            "column_name": parsed.get("column_name") or self._generate_column_name(prompt),
            "enum_options": enum_options,
            "reasoning": parsed.get("reasoning", ""),
        }

    def _generate_column_name(self, prompt: str) -> str:
        """Gera nome de coluna a partir do prompt."""
        # Remover palavras interrogativas e truncar
        words = prompt.lower().split()
        skip_words = {"what", "which", "who", "when", "where", "how", "is", "are", "does", "do",
                      "qual", "quais", "quem", "quando", "onde", "como", "e", "sao", "tem", "ha"}
        filtered = [w for w in words if w not in skip_words and len(w) > 2]
        name = " ".join(filtered[:5]).title()
        return name[:50] if name else "Coluna"

    # -----------------------------------------------------------------------
    # create_column_from_prompt - Criar coluna a partir de prompt
    # -----------------------------------------------------------------------

    async def create_column_from_prompt(
        self,
        review_table_id: str,
        prompt: str,
        user_id: str,
        db: AsyncSession,
        name: Optional[str] = None,
        extraction_type: Optional[str] = None,
        enum_options: Optional[List[str]] = None,
        extraction_instructions: Optional[str] = None,
    ) -> DynamicColumn:
        """Cria uma coluna dinamica a partir de um prompt em linguagem natural.

        Args:
            review_table_id: ID da review table
            prompt: Pergunta que define a extracao
            user_id: ID do usuario criador
            db: Sessao do banco
            name: Nome da coluna (opcional, sera inferido)
            extraction_type: Tipo de extracao (opcional, sera inferido)
            enum_options: Opcoes para tipo enum (opcional)
            extraction_instructions: Instrucoes adicionais (opcional)

        Returns:
            DynamicColumn criada

        Raises:
            ValueError: Se review table nao existe ou prompt invalido
        """
        # Validar review table
        review_table = await db.get(ReviewTable, review_table_id)
        if not review_table:
            raise ValueError(f"Review table {review_table_id} nao encontrada")

        if not prompt or len(prompt.strip()) < 5:
            raise ValueError("O prompt deve ter no minimo 5 caracteres")

        # Inferir schema se nao fornecido
        if not extraction_type or not name:
            schema = await self.infer_column_schema(prompt)
            if not extraction_type:
                extraction_type = schema["extraction_type"]
            if not name:
                name = schema["column_name"]
            if not enum_options and schema.get("enum_options"):
                enum_options = schema["enum_options"]

            logger.info(
                "Schema inferido para coluna: type=%s, name=%s, reasoning=%s",
                extraction_type, name, schema.get("reasoning", "")
            )

        # Determinar ordem (ultima coluna + 1)
        stmt = select(DynamicColumn).where(
            DynamicColumn.review_table_id == review_table_id,
            DynamicColumn.is_active == True,  # noqa: E712
        ).order_by(DynamicColumn.order.desc())
        result = await db.execute(stmt)
        last_column = result.scalar_one_or_none()
        next_order = (last_column.order + 1) if last_column else 0

        # Criar coluna
        column = DynamicColumn(
            id=str(uuid.uuid4()),
            review_table_id=review_table_id,
            name=name,
            prompt=prompt,
            extraction_type=extraction_type,
            enum_options=enum_options,
            extraction_instructions=extraction_instructions,
            order=next_order,
            is_active=True,
            created_by=user_id,
        )
        db.add(column)
        await db.commit()
        await db.refresh(column)

        logger.info(
            "Coluna dinamica criada: id=%s, name=%s, type=%s, table=%s",
            column.id, column.name, column.extraction_type, review_table_id
        )

        return column

    # -----------------------------------------------------------------------
    # extract_for_document - Extrair valor de um documento
    # -----------------------------------------------------------------------

    async def extract_for_document(
        self,
        column: DynamicColumn,
        document_id: str,
        document_content: str,
        db: AsyncSession,
    ) -> CellExtraction:
        """Extrai valor de um documento para uma coluna dinamica.

        Args:
            column: Coluna dinamica
            document_id: ID do documento
            document_content: Texto do documento
            db: Sessao do banco

        Returns:
            CellExtraction com valor extraido
        """
        # Verificar se ja existe extracao
        stmt = select(CellExtraction).where(
            CellExtraction.dynamic_column_id == column.id,
            CellExtraction.document_id == document_id,
        )
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()

        # Truncar documento
        doc_text = document_content[:MAX_DOC_TEXT_LENGTH]

        # Preparar prompt de extracao
        extraction_type_desc = EXTRACTION_TYPE_DESCRIPTIONS.get(
            column.extraction_type, "Texto livre"
        )

        enum_options_section = ""
        if column.extraction_type == "enum" and column.enum_options:
            enum_options_section = f"## OPCOES VALIDAS\n{', '.join(column.enum_options)}\n\nEscolha UMA das opcoes acima."

        instructions_section = ""
        if column.extraction_instructions:
            instructions_section = f"## INSTRUCOES ADICIONAIS\n{column.extraction_instructions}"

        prompt = EXTRACTION_PROMPT.format(
            prompt=column.prompt,
            extraction_type_description=extraction_type_desc,
            enum_options_section=enum_options_section,
            instructions_section=instructions_section,
            document_text=doc_text,
        )

        response = await _call_ai(
            prompt=prompt,
            system_instruction=(
                "Voce e um assistente juridico especializado em extracao "
                "precisa de dados de documentos. Responda em JSON valido."
            ),
            max_tokens=1500,
            temperature=0.1,
        )

        # Parsear resposta
        parsed = _safe_json_parse(response) if response else None

        if parsed and isinstance(parsed, dict):
            value = str(parsed.get("value", "Nao encontrado"))
            confidence = min(max(float(parsed.get("confidence", 0.5)), 0.0), 1.0)
            source_snippet = str(parsed.get("source_snippet", ""))[:500]
            source_page = parsed.get("source_page")
            if source_page is not None:
                try:
                    source_page = int(source_page)
                except (ValueError, TypeError):
                    source_page = None
        else:
            # Fallback
            value = response.strip() if response else "Erro na extracao"
            confidence = 0.3
            source_snippet = ""
            source_page = None

        # Criar ou atualizar CellExtraction
        if existing:
            existing.extracted_value = value
            existing.raw_value = response
            existing.confidence = confidence
            existing.source_snippet = source_snippet
            existing.source_page = source_page
            existing.verification_status = VerificationStatus.PENDING
            existing.verified_by = None
            existing.verified_at = None
            existing.corrected_value = None
            existing.correction_note = None
            existing.extraction_model = DEFAULT_MODEL
            existing.extracted_at = utcnow()
            extraction = existing
        else:
            extraction = CellExtraction(
                id=str(uuid.uuid4()),
                dynamic_column_id=column.id,
                document_id=document_id,
                review_table_id=column.review_table_id,
                column_name=column.name,  # Armazenar nome da coluna para referencia
                extracted_value=value,
                raw_value=response,
                confidence=confidence,
                source_snippet=source_snippet,
                source_page=source_page,
                verification_status=VerificationStatus.PENDING,
                extraction_model=DEFAULT_MODEL,
            )
            db.add(extraction)

        await db.commit()
        await db.refresh(extraction)

        return extraction

    # -----------------------------------------------------------------------
    # extract_column_for_all_documents - Processar todos os docs
    # -----------------------------------------------------------------------

    async def extract_column_for_all_documents(
        self,
        column: DynamicColumn,
        db: AsyncSession,
    ) -> List[CellExtraction]:
        """Extrai valores da coluna para todos os documentos da review table.

        Processa documentos em paralelo com limite de concorrencia.

        Args:
            column: Coluna dinamica
            db: Sessao do banco

        Returns:
            Lista de CellExtractions criadas
        """
        # Carregar review table
        review_table = await db.get(ReviewTable, column.review_table_id)
        if not review_table:
            raise ValueError(f"Review table {column.review_table_id} nao encontrada")

        document_ids = review_table.document_ids or []
        if not document_ids:
            logger.warning("Review table %s nao possui documentos", column.review_table_id)
            return []

        semaphore = asyncio.Semaphore(MAX_CONCURRENT_EXTRACTIONS)
        extractions: List[CellExtraction] = []

        async def process_document(doc_id: str) -> Optional[CellExtraction]:
            async with semaphore:
                # Carregar documento
                doc = await db.get(Document, doc_id)
                if not doc:
                    logger.warning("Documento %s nao encontrado", doc_id)
                    return None

                doc_text = doc.extracted_text or doc.content or ""
                if not doc_text.strip():
                    logger.warning("Documento %s sem texto extraido", doc_id)
                    # Criar extracao com erro
                    extraction = CellExtraction(
                        id=str(uuid.uuid4()),
                        dynamic_column_id=column.id,
                        document_id=doc_id,
                        review_table_id=column.review_table_id,
                        extracted_value="Erro: documento sem texto",
                        confidence=0.0,
                        verification_status=VerificationStatus.PENDING,
                    )
                    db.add(extraction)
                    return extraction

                try:
                    return await self.extract_for_document(
                        column=column,
                        document_id=doc_id,
                        document_content=doc_text,
                        db=db,
                    )
                except Exception as e:
                    logger.error(
                        "Erro ao extrair documento %s para coluna %s: %s",
                        doc_id, column.id, e
                    )
                    return None

        # Processar em paralelo
        tasks = [process_document(doc_id) for doc_id in document_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, CellExtraction):
                extractions.append(result)
            elif isinstance(result, Exception):
                logger.error("Erro no processamento de documento: %s", result)

        await db.commit()

        logger.info(
            "Extracao concluida: coluna=%s, documentos=%d, extracoes=%d",
            column.id, len(document_ids), len(extractions)
        )

        return extractions

    # -----------------------------------------------------------------------
    # reprocess_column - Reprocessar coluna
    # -----------------------------------------------------------------------

    async def reprocess_column(
        self,
        column_id: str,
        db: AsyncSession,
        document_ids: Optional[List[str]] = None,
    ) -> List[CellExtraction]:
        """Reprocessa extracoes de uma coluna (todas ou documentos especificos).

        Args:
            column_id: ID da coluna
            db: Sessao do banco
            document_ids: Lista opcional de IDs de documentos para reprocessar

        Returns:
            Lista de CellExtractions atualizadas
        """
        column = await db.get(DynamicColumn, column_id)
        if not column:
            raise ValueError(f"Coluna {column_id} nao encontrada")

        if document_ids:
            # Reprocessar apenas documentos especificos
            review_table = await db.get(ReviewTable, column.review_table_id)
            if not review_table:
                raise ValueError(f"Review table nao encontrada")

            # Filtrar para documentos que existem na review table
            valid_doc_ids = [
                d for d in document_ids
                if d in (review_table.document_ids or [])
            ]

            extractions = []
            for doc_id in valid_doc_ids:
                doc = await db.get(Document, doc_id)
                if doc:
                    doc_text = doc.extracted_text or doc.content or ""
                    if doc_text.strip():
                        extraction = await self.extract_for_document(
                            column=column,
                            document_id=doc_id,
                            document_content=doc_text,
                            db=db,
                        )
                        extractions.append(extraction)

            return extractions
        else:
            # Reprocessar todos
            return await self.extract_column_for_all_documents(column=column, db=db)

    # -----------------------------------------------------------------------
    # get_column_extractions - Obter extracoes de uma coluna
    # -----------------------------------------------------------------------

    async def get_column_extractions(
        self,
        column_id: str,
        db: AsyncSession,
        verification_status: Optional[VerificationStatus] = None,
    ) -> List[CellExtraction]:
        """Obtem todas as extracoes de uma coluna.

        Args:
            column_id: ID da coluna
            db: Sessao do banco
            verification_status: Filtrar por status de verificacao

        Returns:
            Lista de CellExtractions
        """
        stmt = select(CellExtraction).where(
            CellExtraction.dynamic_column_id == column_id
        )

        if verification_status:
            stmt = stmt.where(
                CellExtraction.verification_status == verification_status
            )

        stmt = stmt.order_by(CellExtraction.extracted_at.desc())

        result = await db.execute(stmt)
        return list(result.scalars().all())

    # -----------------------------------------------------------------------
    # verify_cell - Verificar/corrigir uma celula
    # -----------------------------------------------------------------------

    async def verify_cell(
        self,
        cell_id: str,
        user_id: str,
        db: AsyncSession,
        status: VerificationStatus,
        corrected_value: Optional[str] = None,
        note: Optional[str] = None,
    ) -> CellExtraction:
        """Verifica ou corrige uma celula extraida.

        Args:
            cell_id: ID da CellExtraction
            user_id: ID do usuario verificador
            db: Sessao do banco
            status: Novo status de verificacao
            corrected_value: Valor corrigido (se aplicavel)
            note: Nota do revisor

        Returns:
            CellExtraction atualizada
        """
        cell = await db.get(CellExtraction, cell_id)
        if not cell:
            raise ValueError(f"Celula {cell_id} nao encontrada")

        cell.verification_status = status
        cell.verified_by = user_id
        cell.verified_at = utcnow()
        cell.verification_note = note

        if corrected_value is not None:
            cell.corrected_value = corrected_value
            if status != VerificationStatus.CORRECTED:
                cell.verification_status = VerificationStatus.CORRECTED

        await db.commit()
        await db.refresh(cell)

        logger.info(
            "Celula verificada: id=%s, status=%s, by=%s",
            cell_id, status, user_id
        )

        return cell


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

column_builder_service = ColumnBuilderService()
