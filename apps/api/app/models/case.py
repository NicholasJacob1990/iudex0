from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
import uuid
from app.core.time_utils import utcnow
import enum

from app.core.database import Base

class CaseStatus(str, enum.Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    CLOSED = "closed"

class Case(Base):
    __tablename__ = "cases"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    
    title = Column(String, nullable=False)
    client_name = Column(String, nullable=True)
    process_number = Column(String, nullable=True)
    
    # Metadados Jurídicos
    court = Column(String, nullable=True) # Tribunal/Comarca
    area = Column(String, nullable=True)  # Cível, Trabalhista, etc.
    
    # Conteúdo Base
    description = Column(Text, nullable=True) # Resumo dos fatos
    thesis = Column(Text, nullable=True)      # Tese central
    
    status = Column(String, default=CaseStatus.ACTIVE)
    
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    # Relacionamentos
    user = relationship("User", back_populates="cases")
    watchlist_items = relationship("ProcessWatchlist", back_populates="case")
