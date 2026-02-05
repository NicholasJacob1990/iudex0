"""add_missing_model_tables

Revision ID: t2u3v4w5x6y7
Revises: t1u2v3w4x5y6
Create Date: 2026-02-02

Creates tables for models that had no corresponding migrations:
- rag_eval_metrics
- rag_ingestion_events
- rag_trace_events
- rag_access_policies
- api_call_usage
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "t2u3v4w5x6y7"
down_revision: Union[str, None] = "t1u2v3w4x5y6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # rag_eval_metrics (from app/models/rag_eval.py)
    op.create_table(
        "rag_eval_metrics",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("dataset", sa.String(), nullable=False),
        sa.Column("context_precision", sa.Float(), nullable=True),
        sa.Column("context_recall", sa.Float(), nullable=True),
        sa.Column("faithfulness", sa.Float(), nullable=True),
        sa.Column("answer_relevancy", sa.Float(), nullable=True),
        sa.Column("metrics", sa.JSON(), nullable=False, server_default="{}"),
    )

    # rag_ingestion_events (from app/models/rag_ingestion.py)
    op.create_table(
        "rag_ingestion_events",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("scope", sa.String(), nullable=False),
        sa.Column("scope_id", sa.String(), nullable=True),
        sa.Column("tenant_id", sa.String(), nullable=True),
        sa.Column("group_id", sa.String(), nullable=True),
        sa.Column("collection", sa.String(), nullable=False),
        sa.Column("source_type", sa.String(), nullable=False),
        sa.Column("doc_hash", sa.String(), nullable=True),
        sa.Column("doc_version", sa.Integer(), nullable=True),
        sa.Column("chunk_count", sa.Integer(), nullable=True),
        sa.Column("skipped_count", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.create_index("ix_rag_ingestion_events_scope", "rag_ingestion_events", ["scope"])
    op.create_index("ix_rag_ingestion_events_scope_id", "rag_ingestion_events", ["scope_id"])
    op.create_index("ix_rag_ingestion_events_tenant_id", "rag_ingestion_events", ["tenant_id"])
    op.create_index("ix_rag_ingestion_events_group_id", "rag_ingestion_events", ["group_id"])
    op.create_index("ix_rag_ingestion_events_collection", "rag_ingestion_events", ["collection"])
    op.create_index("ix_rag_ingestion_events_source_type", "rag_ingestion_events", ["source_type"])
    op.create_index("ix_rag_ingestion_events_doc_hash", "rag_ingestion_events", ["doc_hash"])
    op.create_index("ix_rag_ingestion_events_status", "rag_ingestion_events", ["status"])

    # rag_trace_events (from app/models/rag_trace.py)
    op.create_table(
        "rag_trace_events",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("request_id", sa.String(), nullable=False),
        sa.Column("event", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("tenant_id", sa.String(), nullable=True),
        sa.Column("conversation_id", sa.String(), nullable=True),
        sa.Column("message_id", sa.String(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.create_index("ix_rag_trace_events_request_id", "rag_trace_events", ["request_id"])
    op.create_index("ix_rag_trace_events_user_id", "rag_trace_events", ["user_id"])
    op.create_index("ix_rag_trace_events_tenant_id", "rag_trace_events", ["tenant_id"])
    op.create_index("ix_rag_trace_events_conversation_id", "rag_trace_events", ["conversation_id"])
    op.create_index("ix_rag_trace_events_message_id", "rag_trace_events", ["message_id"])

    # rag_access_policies (from app/models/rag_policy.py)
    op.create_table(
        "rag_access_policies",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("allow_global", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("allow_groups", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("group_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_rag_access_policies_tenant_id", "rag_access_policies", ["tenant_id"])
    op.create_index("ix_rag_access_policies_user_id", "rag_access_policies", ["user_id"])

    # api_call_usage (from app/models/api_usage.py)
    op.create_table(
        "api_call_usage",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("scope_type", sa.String(), nullable=False),
        sa.Column("scope_id", sa.String(), nullable=False),
        sa.Column("turn_id", sa.String(), nullable=True),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=True),
        sa.Column("cached", sa.Boolean(), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_api_call_usage_scope_type", "api_call_usage", ["scope_type"])
    op.create_index("ix_api_call_usage_scope_id", "api_call_usage", ["scope_id"])
    op.create_index("ix_api_call_usage_turn_id", "api_call_usage", ["turn_id"])
    op.create_index("ix_api_call_usage_user_id", "api_call_usage", ["user_id"])
    op.create_index("idx_api_call_usage_scope", "api_call_usage", ["scope_type", "scope_id"])


def downgrade() -> None:
    op.drop_index("idx_api_call_usage_scope", table_name="api_call_usage")
    op.drop_index("ix_api_call_usage_user_id", table_name="api_call_usage")
    op.drop_index("ix_api_call_usage_turn_id", table_name="api_call_usage")
    op.drop_index("ix_api_call_usage_scope_id", table_name="api_call_usage")
    op.drop_index("ix_api_call_usage_scope_type", table_name="api_call_usage")
    op.drop_table("api_call_usage")

    op.drop_index("ix_rag_access_policies_user_id", table_name="rag_access_policies")
    op.drop_index("ix_rag_access_policies_tenant_id", table_name="rag_access_policies")
    op.drop_table("rag_access_policies")

    op.drop_index("ix_rag_trace_events_message_id", table_name="rag_trace_events")
    op.drop_index("ix_rag_trace_events_conversation_id", table_name="rag_trace_events")
    op.drop_index("ix_rag_trace_events_tenant_id", table_name="rag_trace_events")
    op.drop_index("ix_rag_trace_events_user_id", table_name="rag_trace_events")
    op.drop_index("ix_rag_trace_events_request_id", table_name="rag_trace_events")
    op.drop_table("rag_trace_events")

    op.drop_index("ix_rag_ingestion_events_status", table_name="rag_ingestion_events")
    op.drop_index("ix_rag_ingestion_events_doc_hash", table_name="rag_ingestion_events")
    op.drop_index("ix_rag_ingestion_events_source_type", table_name="rag_ingestion_events")
    op.drop_index("ix_rag_ingestion_events_collection", table_name="rag_ingestion_events")
    op.drop_index("ix_rag_ingestion_events_group_id", table_name="rag_ingestion_events")
    op.drop_index("ix_rag_ingestion_events_tenant_id", table_name="rag_ingestion_events")
    op.drop_index("ix_rag_ingestion_events_scope_id", table_name="rag_ingestion_events")
    op.drop_index("ix_rag_ingestion_events_scope", table_name="rag_ingestion_events")
    op.drop_table("rag_ingestion_events")

    op.drop_table("rag_eval_metrics")
