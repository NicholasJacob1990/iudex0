"""Marketplace models for public sharing of templates, workflows, and prompts."""
import enum
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, Float, ForeignKey, Index,
    Integer, JSON, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class MarketplaceCategory(str, enum.Enum):
    MINUTAS = "minutas"
    WORKFLOWS = "workflows"
    PROMPTS = "prompts"
    CLAUSULAS = "clausulas"
    AGENTS = "agents"
    PARECERES = "pareceres"


class MarketplaceItem(Base):
    __tablename__ = "marketplace_items"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    publisher_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    resource_type: Mapped[str] = mapped_column(
        String(30), nullable=False, doc="library_item, workflow, librarian"
    )
    resource_id: Mapped[str] = mapped_column(
        String(36), nullable=False, doc="ID of the original resource"
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(
        String(30), nullable=False, default=MarketplaceCategory.MINUTAS
    )
    tags: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    is_published: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    download_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    avg_rating: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    rating_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    preview_data: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True, doc="Preview/summary of the resource content"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    publisher = relationship("User", backref="marketplace_items")
    reviews = relationship(
        "MarketplaceReview", back_populates="item", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_marketplace_category", "category"),
        Index("ix_marketplace_publisher", "publisher_id"),
        Index("ix_marketplace_published", "is_published"),
        UniqueConstraint("resource_type", "resource_id", name="uq_marketplace_resource"),
    )


class MarketplaceReview(Base):
    __tablename__ = "marketplace_reviews"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    item_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("marketplace_items.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    rating: Mapped[int] = mapped_column(Integer, nullable=False, doc="1-5 stars")
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    item = relationship("MarketplaceItem", back_populates="reviews")
    user = relationship("User", backref="marketplace_reviews")

    __table_args__ = (
        UniqueConstraint("item_id", "user_id", name="uq_review_per_user"),
        Index("ix_reviews_item", "item_id"),
    )
