"""Add playbook tables for contract review rules

Revision ID: k1l2m3n4o5p6
Revises: j0k1l2m3n4o5
Create Date: 2026-02-02
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "k1l2m3n4o5p6"
down_revision: Union[str, None] = "j0k1l2m3n4o5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Playbooks table
    op.create_table(
        "playbooks",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("organization_id", sa.String(), sa.ForeignKey("organizations.id"), nullable=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("area", sa.String(100), nullable=True),
        sa.Column("rules", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("is_template", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("scope", sa.String(20), server_default="personal", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("parent_id", sa.String(), sa.ForeignKey("playbooks.id"), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_playbooks_user_id", "playbooks", ["user_id"])
    op.create_index("ix_playbooks_organization_id", "playbooks", ["organization_id"])
    op.create_index("ix_playbooks_area", "playbooks", ["area"])
    op.create_index("ix_playbooks_scope", "playbooks", ["scope"])
    op.create_index("ix_playbooks_user_active", "playbooks", ["user_id", "is_active"])

    # Playbook rules table
    op.create_table(
        "playbook_rules",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("playbook_id", sa.String(), sa.ForeignKey("playbooks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("clause_type", sa.String(100), nullable=False),
        sa.Column("rule_name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("preferred_position", sa.Text(), nullable=False),
        sa.Column("fallback_positions", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("rejected_positions", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("action_on_reject", sa.String(20), server_default="flag", nullable=False),
        sa.Column("severity", sa.String(20), server_default="medium", nullable=False),
        sa.Column("guidance_notes", sa.Text(), nullable=True),
        sa.Column("order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_playbook_rules_playbook_id", "playbook_rules", ["playbook_id"])
    op.create_index("ix_playbook_rules_clause_type", "playbook_rules", ["clause_type"])
    op.create_index("ix_playbook_rules_order", "playbook_rules", ["playbook_id", "order"])

    # Playbook shares table
    op.create_table(
        "playbook_shares",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("playbook_id", sa.String(), sa.ForeignKey("playbooks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("shared_with_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("shared_with_org_id", sa.String(), sa.ForeignKey("organizations.id"), nullable=True),
        sa.Column("permission", sa.String(20), server_default="view", nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_playbook_shares_playbook_id", "playbook_shares", ["playbook_id"])
    op.create_index("ix_playbook_shares_user_id", "playbook_shares", ["shared_with_user_id"])
    op.create_index("ix_playbook_shares_org_id", "playbook_shares", ["shared_with_org_id"])
    op.create_index("ix_playbook_shares_lookup", "playbook_shares", ["playbook_id", "shared_with_user_id"])


def downgrade() -> None:
    op.drop_table("playbook_shares")
    op.drop_table("playbook_rules")
    op.drop_table("playbooks")
