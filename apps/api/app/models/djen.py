"""
Modelos de banco de dados para integração DJEN
"""

from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Boolean, Date, Integer, UniqueConstraint
from sqlalchemy.orm import relationship
import uuid

from app.core.database import Base
from app.core.time_utils import utcnow


class ProcessWatchlist(Base):
    """
    Lista de processos monitorados por usuário.
    Usado para monitoramento ativo via DataJud + DJEN.
    """
    __tablename__ = "process_watchlist"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    case_id = Column(String, ForeignKey("cases.id"), nullable=True, index=True)
    
    # Identificação do processo
    npu = Column(String, nullable=False, index=True)  # Apenas dígitos
    npu_formatted = Column(String, nullable=True)      # Com máscara para exibição
    tribunal_sigla = Column(String, nullable=False)    # TJMG (Comunica)
    tribunal_alias = Column(String, nullable=False)    # tjmg (DataJud)
    
    # Controle de sincronização
    last_datajud_check = Column(DateTime, nullable=True)
    last_mov_datetime = Column(String, nullable=True)  # Último movimento visto
    
    # Status
    is_active = Column(Boolean, default=True)
    
    # Timestamps
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    # Relacionamentos
    user = relationship("User", back_populates="watchlist_items")
    case = relationship("Case", back_populates="watchlist_items")
    intimations = relationship("DjenIntimation", back_populates="watchlist_item")


class DjenOabWatchlist(Base):
    """
    Lista de OABs monitoradas por usuário.
    Usado para rastreamento diário de publicações via DJEN.
    """
    __tablename__ = "djen_oab_watchlist"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)

    # Identificação da OAB
    numero_oab = Column(String, nullable=False)
    uf_oab = Column(String, nullable=False)
    sigla_tribunal = Column(String, nullable=True)
    meio = Column(String, nullable=True, default="D")
    max_pages = Column(Integer, nullable=True, default=3)

    # Controle de sincronização
    last_sync_date = Column(Date, nullable=True)

    # Status
    is_active = Column(Boolean, default=True)

    # Timestamps
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    # Relacionamentos
    user = relationship("User", back_populates="oab_watchlist_items")
    intimations = relationship("DjenIntimation", back_populates="oab_watchlist_item")


class DjenIntimation(Base):
    """
    Intimações capturadas do DJEN.
    Hash é único por usuário para deduplicação.
    """
    __tablename__ = "djen_intimations"
    __table_args__ = (
        UniqueConstraint("user_id", "hash", name="uq_djen_intimations_user_hash"),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    watchlist_id = Column(String, ForeignKey("process_watchlist.id"), nullable=True, index=True)
    oab_watchlist_id = Column(String, ForeignKey("djen_oab_watchlist.id"), nullable=True, index=True)
    
    # Dados da API Comunica - Hash é GLOBAL para deduplicação
    hash = Column(String, nullable=False, index=True)
    comunicacao_id = Column(Integer, nullable=True)  # ID original da API
    
    # Dados do processo
    numero_processo = Column(String, nullable=False, index=True)
    numero_processo_mascara = Column(String, nullable=True)
    tribunal_sigla = Column(String, nullable=False)
    
    # Conteúdo da intimação
    tipo_comunicacao = Column(String, nullable=True)
    nome_orgao = Column(String, nullable=True)
    texto = Column(Text, nullable=True)
    
    # Metadados
    data_disponibilizacao = Column(Date, nullable=True)
    meio = Column(String, nullable=True)  # D ou E
    link = Column(String, nullable=True)
    tipo_documento = Column(String, nullable=True)
    nome_classe = Column(String, nullable=True)
    numero_comunicacao = Column(Integer, nullable=True)
    ativo = Column(Boolean, default=True)
    
    # Timestamps
    created_at = Column(DateTime, default=utcnow)

    # Relacionamentos
    user = relationship("User", back_populates="djen_intimations")
    watchlist_item = relationship("ProcessWatchlist", back_populates="intimations")
    oab_watchlist_item = relationship("DjenOabWatchlist", back_populates="intimations")
