"""add_claude_agent_tables

Revision ID: f6c7d8e9a0b1
Revises: e5b6c7d8f9a0
Create Date: 2026-01-26 23:00:00

Adds:
- tool_permissions: Controle granular de permissões de ferramentas por usuário
- conversation_summaries: Compressão de contexto para conversas longas
- checkpoints: Snapshots de estado para HIL e recuperação de workflows
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f6c7d8e9a0b1"
down_revision: Union[str, None] = "e5b6c7d8f9a0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # ===== TOOL_PERMISSIONS TABLE =====
    # Alinhado com o model em app/models/tool_permission.py
    if not inspector.has_table("tool_permissions"):
        op.create_table(
            "tool_permissions",
            # Primary key
            sa.Column("id", sa.String(), primary_key=True),

            # Foreign key to users
            sa.Column("user_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),

            # Identificação da ferramenta (pode usar wildcards como "search_*")
            sa.Column("tool_name", sa.String(100), nullable=False),

            # Padrão glob para matching do input (ex: "*sensivel*")
            sa.Column("pattern", sa.String(500), nullable=True),

            # Modo: 'allow', 'deny', 'ask' (usando Enum no Postgres)
            sa.Column("mode", sa.Enum('allow', 'deny', 'ask', name='permissionmode'), nullable=False),

            # Escopo: 'session', 'project', 'global'
            sa.Column("scope", sa.Enum('session', 'project', 'global', name='permissionscope'), nullable=False),

            # Referências opcionais para escopos específicos
            sa.Column("session_id", sa.String(), sa.ForeignKey("workflow_states.id", ondelete="CASCADE"), nullable=True),
            sa.Column("project_id", sa.String(), nullable=True),

            # Metadados adicionais (alinhado com o model)
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("created_by", sa.String(), nullable=True),  # 'user' ou 'system'

            # Timestamps
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        )

        # Indexes for tool_permissions (alinhados com __table_args__ do model)
        op.create_index("ix_tool_permissions_user_id", "tool_permissions", ["user_id"])
        op.create_index("idx_tool_permissions_lookup", "tool_permissions", ["user_id", "tool_name", "scope"])
        op.create_index("idx_tool_permissions_session", "tool_permissions", ["session_id"])
        op.create_index("idx_tool_permissions_project", "tool_permissions", ["project_id"])

    # ===== CONVERSATION_SUMMARIES TABLE =====
    if not inspector.has_table("conversation_summaries"):
        op.create_table(
            "conversation_summaries",
            # Primary key
            sa.Column("id", sa.String(), primary_key=True),

            # Foreign keys
            sa.Column("chat_id", sa.String(), sa.ForeignKey("chats.id", ondelete="CASCADE"), nullable=False),
            sa.Column("from_message_id", sa.String(), sa.ForeignKey("chat_messages.id"), nullable=False),
            sa.Column("to_message_id", sa.String(), sa.ForeignKey("chat_messages.id"), nullable=False),

            # Summary content
            sa.Column("summary_text", sa.Text(), nullable=False),

            # Token metrics
            sa.Column("tokens_original", sa.Integer(), nullable=False),
            sa.Column("tokens_compressed", sa.Integer(), nullable=False),

            # Timestamps
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )

        # Indexes for conversation_summaries
        op.create_index("ix_conversation_summaries_chat_id", "conversation_summaries", ["chat_id"])
        op.create_index(
            "ix_conversation_summaries_chat_created",
            "conversation_summaries",
            ["chat_id", "created_at"]
        )

    # ===== CHECKPOINTS TABLE =====
    if not inspector.has_table("checkpoints"):
        op.create_table(
            "checkpoints",
            # Primary key
            sa.Column("id", sa.String(), primary_key=True),

            # Foreign key to workflow_states (job)
            sa.Column("job_id", sa.String(), sa.ForeignKey("workflow_states.id", ondelete="CASCADE"), nullable=False),

            # Turn identifier (optional)
            sa.Column("turn_id", sa.String(), nullable=True),

            # Snapshot metadata
            sa.Column("snapshot_type", sa.String(20), nullable=False),  # 'auto', 'manual', 'hil'
            sa.Column("description", sa.String(500), nullable=True),

            # Snapshot data
            sa.Column("state_snapshot", sa.JSON(), nullable=False),
            sa.Column("files_snapshot_uri", sa.String(1000), nullable=True),

            # Restorable flag
            sa.Column("is_restorable", sa.Boolean(), nullable=False, server_default="true"),

            # Timestamps
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),

            # Constraints
            sa.CheckConstraint("snapshot_type IN ('auto', 'manual', 'hil')", name="ck_checkpoints_snapshot_type"),
        )

        # Indexes for checkpoints
        op.create_index("ix_checkpoints_job_id", "checkpoints", ["job_id"])
        op.create_index("ix_checkpoints_snapshot_type", "checkpoints", ["snapshot_type"])
        op.create_index("ix_checkpoints_job_created", "checkpoints", ["job_id", "created_at"])
        op.create_index(
            "ix_checkpoints_restorable",
            "checkpoints",
            ["job_id", "is_restorable"],
            postgresql_where=sa.text("is_restorable = true")
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Drop checkpoints table and indexes
    if inspector.has_table("checkpoints"):
        op.drop_index("ix_checkpoints_restorable", table_name="checkpoints")
        op.drop_index("ix_checkpoints_job_created", table_name="checkpoints")
        op.drop_index("ix_checkpoints_snapshot_type", table_name="checkpoints")
        op.drop_index("ix_checkpoints_job_id", table_name="checkpoints")
        op.drop_table("checkpoints")

    # Drop conversation_summaries table and indexes
    if inspector.has_table("conversation_summaries"):
        op.drop_index("ix_conversation_summaries_chat_created", table_name="conversation_summaries")
        op.drop_index("ix_conversation_summaries_chat_id", table_name="conversation_summaries")
        op.drop_table("conversation_summaries")

    # Drop tool_permissions table and indexes
    if inspector.has_table("tool_permissions"):
        op.drop_index("idx_tool_permissions_project", table_name="tool_permissions")
        op.drop_index("idx_tool_permissions_session", table_name="tool_permissions")
        op.drop_index("idx_tool_permissions_lookup", table_name="tool_permissions")
        op.drop_index("ix_tool_permissions_user_id", table_name="tool_permissions")
        op.drop_table("tool_permissions")

        # Drop enum types
        sa.Enum(name='permissionmode').drop(bind, checkfirst=True)
        sa.Enum(name='permissionscope').drop(bind, checkfirst=True)
