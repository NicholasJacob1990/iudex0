from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Enum, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
import uuid
from app.core.time_utils import utcnow
import enum
import re

from app.core.database import Base


class CaseStatus(str, enum.Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    CLOSED = "closed"


class Case(Base):
    __tablename__ = "cases"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    organization_id = Column(String, ForeignKey("organizations.id"), nullable=True, index=True)

    title = Column(String, nullable=False)
    client_name = Column(String, nullable=True)

    # ===== IDENTIFICAÇÃO PROCESSUAL =====
    # Número do processo (formato livre, legado)
    process_number = Column(String, nullable=True, index=True)
    # Número CNJ normalizado (NNNNNNN-DD.AAAA.J.TR.OOOO)
    cnj_number = Column(String, nullable=True, index=True)

    # ===== METADADOS JURÍDICOS =====
    court = Column(String, nullable=True)      # Tribunal/Comarca (ex: TJSP, TRF3)
    area = Column(String, nullable=True)       # Área (Cível, Trabalhista, Criminal, etc.)
    classe = Column(String, nullable=True)     # Classe processual (Ação Civil Pública, Mandado de Segurança)
    assunto = Column(String, nullable=True)    # Assunto principal (ex: "Indenização por Dano Moral")

    # ===== PARTES PROCESSUAIS =====
    # Estrutura: {"autor": [...], "reu": [...], "terceiros": [...], "advogados": {...}}
    # SQLite (test env) does not support Postgres JSONB; use a portable JSON type there.
    _JSON_COMPAT = JSON().with_variant(JSONB, "postgresql")
    partes = Column(_JSON_COMPAT, default=dict)

    # ===== CONTEÚDO BASE =====
    description = Column(Text, nullable=True)  # Resumo dos fatos
    thesis = Column(Text, nullable=True)       # Tese central

    # ===== STATUS =====
    status = Column(String, default=CaseStatus.ACTIVE)

    # ===== TIMESTAMPS =====
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    # Relacionamentos
    user = relationship("User", back_populates="cases")
    watchlist_items = relationship("ProcessWatchlist", back_populates="case")

    @staticmethod
    def normalize_cnj(numero: str) -> str | None:
        """
        Normaliza número de processo para padrão CNJ.
        Formato: NNNNNNN-DD.AAAA.J.TR.OOOO

        Onde:
        - NNNNNNN: Número sequencial (7 dígitos)
        - DD: Dígito verificador (2 dígitos)
        - AAAA: Ano de ajuizamento (4 dígitos)
        - J: Segmento de justiça (1 dígito)
        - TR: Tribunal (2 dígitos)
        - OOOO: Origem (4 dígitos)
        """
        if not numero:
            return None

        # Remove caracteres não numéricos
        digits = re.sub(r'\D', '', numero)

        # Deve ter exatamente 20 dígitos
        if len(digits) != 20:
            return None

        # Formata no padrão CNJ
        return f"{digits[:7]}-{digits[7:9]}.{digits[9:13]}.{digits[13]}.{digits[14:16]}.{digits[16:20]}"

    def set_cnj_number(self, numero: str) -> bool:
        """
        Define o número CNJ, normalizando automaticamente.
        Retorna True se o número foi válido e definido.
        """
        normalized = self.normalize_cnj(numero)
        if normalized:
            self.cnj_number = normalized
            # Também atualiza process_number para compatibilidade
            if not self.process_number:
                self.process_number = normalized
            return True
        return False

    def add_parte(self, polo: str, nome: str, tipo: str = "pessoa_fisica", documento: str = None, advogados: list = None):
        """
        Adiciona uma parte ao processo.

        Args:
            polo: "autor", "reu", "terceiro", "interessado"
            nome: Nome da parte
            tipo: "pessoa_fisica", "pessoa_juridica", "orgao_publico"
            documento: CPF/CNPJ
            advogados: Lista de advogados da parte
        """
        if self.partes is None:
            self.partes = {}

        if polo not in self.partes:
            self.partes[polo] = []

        parte = {
            "nome": nome,
            "tipo": tipo,
        }
        if documento:
            parte["documento"] = documento
        if advogados:
            parte["advogados"] = advogados

        self.partes[polo].append(parte)

    def get_partes_resumo(self) -> str:
        """Retorna resumo das partes para exibição."""
        if not self.partes:
            return "Partes não informadas"

        partes = []
        if "autor" in self.partes and self.partes["autor"]:
            autores = ", ".join(p.get("nome", "") for p in self.partes["autor"][:2])
            if len(self.partes["autor"]) > 2:
                autores += f" e outros ({len(self.partes['autor'])})"
            partes.append(f"Autor: {autores}")

        if "reu" in self.partes and self.partes["reu"]:
            reus = ", ".join(p.get("nome", "") for p in self.partes["reu"][:2])
            if len(self.partes["reu"]) > 2:
                reus += f" e outros ({len(self.partes['reu'])})"
            partes.append(f"Réu: {reus}")

        return " x ".join(partes) if partes else "Partes não informadas"
