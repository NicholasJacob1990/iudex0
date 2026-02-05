"""add marketplace tables

Revision ID: i9j0k1l2m3n4
Revises: h8i9j0k1l2m3
Create Date: 2026-02-02
"""
from alembic import op
import sqlalchemy as sa

revision = "i9j0k1l2m3n4"
down_revision = "h8i9j0k1l2m3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "marketplace_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("publisher_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("resource_type", sa.String(30), nullable=False),
        sa.Column("resource_id", sa.String(36), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("category", sa.String(30), nullable=False, server_default="minutas"),
        sa.Column("tags", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("is_published", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("download_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("avg_rating", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("rating_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("preview_data", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.UniqueConstraint("resource_type", "resource_id", name="uq_marketplace_resource"),
    )
    op.create_index("ix_marketplace_category", "marketplace_items", ["category"])
    op.create_index("ix_marketplace_publisher", "marketplace_items", ["publisher_id"])
    op.create_index("ix_marketplace_published", "marketplace_items", ["is_published"])

    op.create_table(
        "marketplace_reviews",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("item_id", sa.String(36), sa.ForeignKey("marketplace_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rating", sa.Integer, nullable=False),
        sa.Column("comment", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("item_id", "user_id", name="uq_review_per_user"),
    )
    op.create_index("ix_reviews_item", "marketplace_reviews", ["item_id"])


def downgrade() -> None:
    op.drop_table("marketplace_reviews")
    op.drop_table("marketplace_items")
