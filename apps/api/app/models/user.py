"""
Modelo de Usuário
"""

from datetime import datetime
from app.core.time_utils import utcnow
from typing import Optional
from sqlalchemy import String, DateTime, ForeignKey, JSON, Enum as SQLEnum, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.core.database import Base


class UserRole(str, enum.Enum):
    USER = "USER"
    PREMIUM = "PREMIUM"
    ADMIN = "ADMIN"


class UserPlan(str, enum.Enum):
    FREE = "FREE"
    INDIVIDUAL = "INDIVIDUAL"
    PROFESSIONAL = "PROFESSIONAL"
    ENTERPRISE = "ENTERPRISE"


class AccountType(str, enum.Enum):
    """Tipo de conta: individual (pessoa física) ou institucional (pessoa jurídica)"""
    INDIVIDUAL = "INDIVIDUAL"
    INSTITUTIONAL = "INSTITUTIONAL"


class User(Base):
    __tablename__ = "users"
    
    id: Mapped[str] = mapped_column(String, primary_key=True)
    email: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    
    # Tipo de conta e plano
    account_type: Mapped[AccountType] = mapped_column(
        SQLEnum(AccountType),
        default=AccountType.INDIVIDUAL,
        nullable=False
    )
    role: Mapped[UserRole] = mapped_column(
        SQLEnum(UserRole),
        default=UserRole.USER,
        nullable=False
    )
    plan: Mapped[UserPlan] = mapped_column(
        SQLEnum(UserPlan),
        default=UserPlan.FREE,
        nullable=False
    )
    
    # Dados pessoais (Individual)
    avatar: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    cpf: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    oab: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    oab_state: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    # Dados institucionais (Institutional)
    institution_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    cnpj: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    position: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    department: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    institution_address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    institution_phone: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    # Assinatura (base64 ou URL)
    signature_image: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    signature_text: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    # Organização ativa (nullable — retrocompatível com single-user)
    organization_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("organizations.id"), nullable=True, index=True
    )

    # Preferências e metadados
    preferences: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(default=False, nullable=False)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow,
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow,
        onupdate=utcnow,
        nullable=False
    )

    cases = relationship("Case", back_populates="user", cascade="all, delete-orphan")
    watchlist_items = relationship("ProcessWatchlist", back_populates="user", cascade="all, delete-orphan")
    oab_watchlist_items = relationship("DjenOabWatchlist", back_populates="user", cascade="all, delete-orphan")
    djen_intimations = relationship("DjenIntimation", back_populates="user", cascade="all, delete-orphan")
    org_memberships = relationship("OrganizationMember", back_populates="user", cascade="all, delete-orphan")
    team_memberships = relationship("TeamMember", back_populates="user", cascade="all, delete-orphan")
    
    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email}, name={self.name}, type={self.account_type})>"
    
    @property
    def full_signature_data(self) -> dict:
        """Retorna dados completos para assinatura de documentos"""
        if self.account_type == AccountType.INDIVIDUAL:
            return {
                "type": "individual",
                "name": self.name,
                "oab": self.oab,
                "oab_state": self.oab_state,
                "cpf": self.cpf,
                "email": self.email,
                "phone": self.phone,
                "signature_image": self.signature_image,
                "signature_text": self.signature_text or f"{self.name}\nOAB/{self.oab_state} {self.oab}" if self.oab else self.name
            }
        else:
            return {
                "type": "institutional",
                "name": self.name,
                "position": self.position,
                "department": self.department,
                "institution_name": self.institution_name,
                "cnpj": self.cnpj,
                "institution_address": self.institution_address,
                "institution_phone": self.institution_phone,
                "email": self.email,
                "signature_image": self.signature_image,
                "signature_text": self.signature_text or f"{self.name}\n{self.position}\n{self.institution_name}"
            }
