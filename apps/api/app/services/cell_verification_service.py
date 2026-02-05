"""
CellVerificationService — Verificacao e validacao de celulas extraidas em Review Tables.

Inspirado no Harvey AI "verified cells" toggle, permite:
- Marcar celulas como verificadas ou rejeitadas
- Corrigir valores extraidos incorretamente
- Verificacao em lote
- Estatisticas de verificacao por tabela
- Identificar celulas de baixa confianca para revisao
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time_utils import utcnow
from app.models.dynamic_column import CellExtraction, VerificationStatus, DynamicColumn
from app.models.review_table import ReviewTable, ReviewTableTemplate
from app.models.audit_log import AuditLog

logger = logging.getLogger("CellVerificationService")


# ---------------------------------------------------------------------------
# Data classes para respostas estruturadas
# ---------------------------------------------------------------------------


@dataclass
class VerificationStats:
    """Estatisticas de verificacao de uma Review Table."""
    total_cells: int
    verified: int
    rejected: int
    corrected: int
    pending: int
    average_confidence: float
    low_confidence_count: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_cells": self.total_cells,
            "verified": self.verified,
            "rejected": self.rejected,
            "corrected": self.corrected,
            "pending": self.pending,
            "average_confidence": round(self.average_confidence, 3),
            "low_confidence_count": self.low_confidence_count,
        }


# ---------------------------------------------------------------------------
# Funcoes de calculo de confianca
# ---------------------------------------------------------------------------


def calculate_confidence(
    extraction_result: Dict[str, Any],
    column_type: str,
    source_snippet: Optional[str] = None,
) -> float:
    """Calcula score de confianca baseado em multiplos fatores.

    Args:
        extraction_result: Resultado da extracao (deve conter 'value' e opcionalmente 'confidence', 'reasoning')
        column_type: Tipo da coluna (text, date, currency, boolean, etc.)
        source_snippet: Trecho do documento usado na extracao

    Returns:
        Score de confianca entre 0.0 e 1.0
    """
    # Base confidence from LLM response
    base_confidence = float(extraction_result.get("confidence", 0.5))

    # Ensure base is within bounds
    base_confidence = max(0.1, min(0.95, base_confidence))

    adjustments = 0.0

    # 1. Source snippet quality boost
    if source_snippet:
        snippet_len = len(source_snippet)
        if snippet_len > 150:
            adjustments += 0.1  # Substantial source text
        elif snippet_len > 50:
            adjustments += 0.05
        elif snippet_len < 20:
            adjustments -= 0.05  # Very short source is suspicious

    # 2. Type-specific validation
    value = extraction_result.get("value", "")
    if value and value.lower() not in ("nao encontrado", "erro", ""):
        if _validates_type(value, column_type):
            adjustments += 0.1  # Value matches expected type pattern
        else:
            adjustments -= 0.1  # Type mismatch

    # 3. Uncertainty detection in reasoning
    reasoning = extraction_result.get("reasoning", "")
    uncertainty_markers = [
        "incerto", "uncertain", "unclear", "ambiguo", "ambiguous",
        "possivelmente", "possibly", "talvez", "maybe", "provavel",
        "nao tenho certeza", "not sure", "parece ser", "appears to be"
    ]
    reasoning_lower = reasoning.lower() if reasoning else ""
    if any(marker in reasoning_lower for marker in uncertainty_markers):
        adjustments -= 0.15  # LLM expressed uncertainty

    # 4. Empty/error value penalty
    if not value or value.lower() in ("nao encontrado", "erro", "erro na extracao"):
        adjustments -= 0.2

    # Calculate final confidence
    final_confidence = base_confidence + adjustments

    # Clamp to valid range
    return max(0.0, min(1.0, final_confidence))


def _validates_type(value: str, column_type: str) -> bool:
    """Verifica se o valor corresponde ao padrao esperado do tipo."""
    if not value:
        return False

    value_lower = value.lower().strip()

    if column_type in ("boolean", "yes_no_classification"):
        return value_lower in ("sim", "nao", "yes", "no", "true", "false", "s", "n")

    if column_type in ("date", "date_extraction"):
        # Check for date-like patterns
        import re
        date_patterns = [
            r"\d{2}/\d{2}/\d{4}",  # DD/MM/YYYY
            r"\d{4}-\d{2}-\d{2}",  # YYYY-MM-DD
            r"\d{2}\.\d{2}\.\d{4}",  # DD.MM.YYYY
        ]
        return any(re.search(p, value) for p in date_patterns)

    if column_type in ("currency", "number"):
        # Check for numeric patterns
        import re
        # Remove currency symbols and thousands separators for validation
        cleaned = re.sub(r"[R$€£¥,.]", "", value)
        cleaned = cleaned.replace(" ", "").replace("-", "")
        return cleaned.isdigit() or bool(re.match(r"^-?\d+([.,]\d+)?$", value))

    if column_type == "risk_rating":
        return value_lower in (
            "baixo", "low", "medio", "medium", "alto", "high", "critico", "critical"
        )

    if column_type == "compliance_check":
        return any(kw in value_lower for kw in (
            "conforme", "compliant", "nao conforme", "non-compliant", "parcialmente"
        ))

    # For text types, we accept any non-empty value
    return True


# ---------------------------------------------------------------------------
# CellVerificationService
# ---------------------------------------------------------------------------


class CellVerificationService:
    """Servico para verificacao e validacao de celulas extraidas."""

    async def verify_cell(
        self,
        cell_id: str,
        user_id: str,
        verified: bool,
        correction: Optional[str] = None,
        note: Optional[str] = None,
        db: AsyncSession = None,
    ) -> CellExtraction:
        """Marca uma celula como verificada, rejeitada ou corrigida.

        Args:
            cell_id: ID da celula a verificar.
            user_id: ID do usuario que esta verificando.
            verified: True para verificar/aceitar, False para rejeitar.
            correction: Valor corrigido (se houver).
            note: Nota explicativa da correcao/rejeicao.
            db: Sessao do banco de dados.

        Returns:
            A CellExtraction atualizada.

        Raises:
            ValueError: Se a celula nao for encontrada.
        """
        cell = await db.get(CellExtraction, cell_id)
        if not cell:
            raise ValueError(f"Celula {cell_id} nao encontrada")

        now = utcnow()

        if correction is not None and correction.strip():
            # Correcao fornecida — marcar como corrigida
            cell.verification_status = VerificationStatus.CORRECTED.value
            cell.corrected_value = correction.strip()
            cell.correction_note = note
            cell.verification_note = note
        elif verified:
            # Verificada como correta
            cell.verification_status = VerificationStatus.VERIFIED.value
            cell.corrected_value = None
            cell.verification_note = note
        else:
            # Rejeitada como incorreta
            cell.verification_status = VerificationStatus.REJECTED.value
            cell.verification_note = note

        cell.verified_by = user_id
        cell.verified_at = now
        cell.updated_at = now

        await db.commit()
        await db.refresh(cell)

        # Audit log
        await self._log_verification_action(
            db=db,
            user_id=user_id,
            cell=cell,
            action="verify_cell",
            details={
                "verified": verified,
                "correction": correction,
                "note": note,
            },
        )

        logger.info(
            "Celula verificada: id=%s, status=%s, by=%s",
            cell_id, cell.verification_status, user_id,
        )

        return cell

    async def bulk_verify(
        self,
        cell_ids: List[str],
        user_id: str,
        verified: bool,
        db: AsyncSession,
    ) -> int:
        """Verifica ou rejeita multiplas celulas de uma vez.

        Args:
            cell_ids: Lista de IDs de celulas.
            user_id: ID do usuario verificando.
            verified: True para verificar, False para rejeitar.
            db: Sessao do banco de dados.

        Returns:
            Quantidade de celulas atualizadas.
        """
        if not cell_ids:
            return 0

        now = utcnow()
        new_status = (
            VerificationStatus.VERIFIED.value if verified
            else VerificationStatus.REJECTED.value
        )

        stmt = (
            update(CellExtraction)
            .where(CellExtraction.id.in_(cell_ids))
            .values(
                verification_status=new_status,
                verified_by=user_id,
                verified_at=now,
                updated_at=now,
            )
        )

        result = await db.execute(stmt)
        await db.commit()

        count = result.rowcount

        logger.info(
            "Bulk verify: %d celulas atualizadas para status=%s, by=%s",
            count, new_status, user_id,
        )

        return count

    async def get_verification_stats(
        self,
        review_table_id: str,
        db: AsyncSession,
    ) -> VerificationStats:
        """Retorna estatisticas de verificacao de uma Review Table.

        Args:
            review_table_id: ID da Review Table.
            db: Sessao do banco de dados.

        Returns:
            VerificationStats com totais e medias.
        """
        LOW_CONFIDENCE_THRESHOLD = 0.7

        # Query agregada
        base_query = select(CellExtraction).where(
            CellExtraction.review_table_id == review_table_id
        )

        # Total
        total_result = await db.execute(
            select(func.count(CellExtraction.id)).where(
                CellExtraction.review_table_id == review_table_id
            )
        )
        total_cells = total_result.scalar() or 0

        if total_cells == 0:
            return VerificationStats(
                total_cells=0,
                verified=0,
                rejected=0,
                corrected=0,
                pending=0,
                average_confidence=0.0,
                low_confidence_count=0,
            )

        # Contagens por status
        status_counts = await db.execute(
            select(
                CellExtraction.verification_status,
                func.count(CellExtraction.id)
            )
            .where(CellExtraction.review_table_id == review_table_id)
            .group_by(CellExtraction.verification_status)
        )

        counts_by_status = {row[0]: row[1] for row in status_counts.fetchall()}

        verified = counts_by_status.get(VerificationStatus.VERIFIED.value, 0)
        rejected = counts_by_status.get(VerificationStatus.REJECTED.value, 0)
        corrected = counts_by_status.get(VerificationStatus.CORRECTED.value, 0)
        pending = counts_by_status.get(VerificationStatus.PENDING.value, 0)

        # Media de confianca
        avg_result = await db.execute(
            select(func.avg(CellExtraction.confidence)).where(
                CellExtraction.review_table_id == review_table_id
            )
        )
        average_confidence = avg_result.scalar() or 0.0

        # Celulas de baixa confianca
        low_conf_result = await db.execute(
            select(func.count(CellExtraction.id)).where(
                and_(
                    CellExtraction.review_table_id == review_table_id,
                    CellExtraction.confidence < LOW_CONFIDENCE_THRESHOLD,
                )
            )
        )
        low_confidence_count = low_conf_result.scalar() or 0

        return VerificationStats(
            total_cells=total_cells,
            verified=verified,
            rejected=rejected,
            corrected=corrected,
            pending=pending,
            average_confidence=float(average_confidence),
            low_confidence_count=low_confidence_count,
        )

    async def get_low_confidence_cells(
        self,
        review_table_id: str,
        threshold: float = 0.7,
        db: AsyncSession = None,
        limit: int = 100,
    ) -> List[CellExtraction]:
        """Retorna celulas abaixo do threshold de confianca para revisao.

        Args:
            review_table_id: ID da Review Table.
            threshold: Limite de confianca (padrao 0.7).
            db: Sessao do banco de dados.
            limit: Maximo de celulas a retornar.

        Returns:
            Lista de CellExtraction ordenada por confianca crescente.
        """
        stmt = (
            select(CellExtraction)
            .where(
                and_(
                    CellExtraction.review_table_id == review_table_id,
                    CellExtraction.confidence < threshold,
                    CellExtraction.verification_status == VerificationStatus.PENDING.value,
                )
            )
            .order_by(CellExtraction.confidence.asc())
            .limit(limit)
        )

        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def get_cell_by_position(
        self,
        review_table_id: str,
        document_id: str,
        column_name: Optional[str] = None,
        dynamic_column_id: Optional[str] = None,
        db: AsyncSession = None,
    ) -> Optional[CellExtraction]:
        """Busca uma celula especifica por posicao.

        Args:
            review_table_id: ID da Review Table.
            document_id: ID do documento.
            column_name: Nome da coluna (para colunas de template).
            dynamic_column_id: ID da coluna dinamica.
            db: Sessao do banco de dados.

        Returns:
            CellExtraction ou None se nao encontrada.
        """
        conditions = [
            CellExtraction.review_table_id == review_table_id,
            CellExtraction.document_id == document_id,
        ]

        if dynamic_column_id:
            conditions.append(CellExtraction.dynamic_column_id == dynamic_column_id)
        elif column_name:
            conditions.append(CellExtraction.column_name == column_name)
        else:
            raise ValueError("Deve fornecer column_name ou dynamic_column_id")

        stmt = select(CellExtraction).where(and_(*conditions))
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_cells_by_dynamic_column(
        self,
        dynamic_column_id: str,
        db: AsyncSession,
        status_filter: Optional[str] = None,
    ) -> List[CellExtraction]:
        """Retorna todas as celulas de uma coluna dinamica.

        Args:
            dynamic_column_id: ID da coluna dinamica.
            db: Sessao do banco de dados.
            status_filter: Filtrar por status de verificacao.

        Returns:
            Lista de CellExtraction.
        """
        conditions = [CellExtraction.dynamic_column_id == dynamic_column_id]

        if status_filter:
            conditions.append(CellExtraction.verification_status == status_filter)

        stmt = (
            select(CellExtraction)
            .where(and_(*conditions))
            .order_by(CellExtraction.document_id)
        )

        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def get_cells_for_document(
        self,
        review_table_id: str,
        document_id: str,
        db: AsyncSession,
    ) -> List[CellExtraction]:
        """Retorna todas as celulas de um documento em uma Review Table.

        Args:
            review_table_id: ID da Review Table.
            document_id: ID do documento.
            db: Sessao do banco de dados.

        Returns:
            Lista de CellExtraction.
        """
        stmt = (
            select(CellExtraction)
            .where(
                and_(
                    CellExtraction.review_table_id == review_table_id,
                    CellExtraction.document_id == document_id,
                )
            )
            .order_by(CellExtraction.column_name)
        )

        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def get_cells_for_review_table(
        self,
        review_table_id: str,
        db: AsyncSession,
        status_filter: Optional[str] = None,
        min_confidence: Optional[float] = None,
        max_confidence: Optional[float] = None,
    ) -> List[CellExtraction]:
        """Retorna todas as celulas de uma Review Table com filtros opcionais.

        Args:
            review_table_id: ID da Review Table.
            db: Sessao do banco de dados.
            status_filter: Filtrar por status de verificacao.
            min_confidence: Confianca minima.
            max_confidence: Confianca maxima.

        Returns:
            Lista de CellExtraction.
        """
        conditions = [CellExtraction.review_table_id == review_table_id]

        if status_filter:
            conditions.append(CellExtraction.verification_status == status_filter)

        if min_confidence is not None:
            conditions.append(CellExtraction.confidence >= min_confidence)

        if max_confidence is not None:
            conditions.append(CellExtraction.confidence <= max_confidence)

        stmt = (
            select(CellExtraction)
            .where(and_(*conditions))
            .order_by(
                CellExtraction.document_id,
                CellExtraction.column_name,
            )
        )

        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def recalculate_confidence(
        self,
        cell_id: str,
        db: AsyncSession,
    ) -> float:
        """Re-calcula a confianca de uma celula com base nos dados atuais.

        Util apos atualizacoes no documento ou melhorias no algoritmo de calculo.

        Args:
            cell_id: ID da celula.
            db: Sessao do banco de dados.

        Returns:
            Novo score de confianca.

        Raises:
            ValueError: Se a celula nao for encontrada.
        """
        cell = await db.get(CellExtraction, cell_id)
        if not cell:
            raise ValueError(f"Celula {cell_id} nao encontrada")

        # Montar extraction_result a partir dos dados da celula
        extraction_result = {
            "value": cell.extracted_value,
            "confidence": cell.confidence,
            "reasoning": cell.extraction_reasoning or "",
        }

        # Buscar tipo da coluna
        column_type = "text"  # default

        # Se tem dynamic_column_id, buscar da dynamic column
        if cell.dynamic_column_id:
            dynamic_col = await db.get(DynamicColumn, cell.dynamic_column_id)
            if dynamic_col:
                column_type = dynamic_col.extraction_type or "text"
        elif cell.column_name:
            # Senao, buscar do template da review table
            review_table = await db.get(ReviewTable, cell.review_table_id)
            if review_table:
                template = await db.get(ReviewTableTemplate, review_table.template_id)
                if template:
                    template_columns = template.columns or []
                    for col in template_columns:
                        if col.get("name") == cell.column_name:
                            column_type = col.get("type", "text")
                            break

        # Recalcular
        new_confidence = calculate_confidence(
            extraction_result=extraction_result,
            column_type=column_type,
            source_snippet=cell.source_snippet,
        )

        cell.confidence = new_confidence
        cell.updated_at = utcnow()

        await db.commit()
        await db.refresh(cell)

        logger.info(
            "Confianca recalculada: cell=%s, old=%.3f, new=%.3f",
            cell_id, extraction_result["confidence"], new_confidence,
        )

        return new_confidence

    async def _log_verification_action(
        self,
        db: AsyncSession,
        user_id: str,
        cell: CellExtraction,
        action: str,
        details: Dict[str, Any],
    ) -> None:
        """Registra acao de verificacao no audit log."""
        try:
            log = AuditLog(
                user_id=user_id,
                action=action,
                resource_type="cell_extraction",
                resource_id=cell.id,
                details={
                    "review_table_id": cell.review_table_id,
                    "document_id": cell.document_id,
                    "column_name": cell.column_name,
                    "verification_status": cell.verification_status,
                    **details,
                },
            )
            db.add(log)
            # Commit sera feito pelo caller
        except Exception as e:
            logger.warning("Erro ao registrar audit log: %s", e)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

cell_verification_service = CellVerificationService()
