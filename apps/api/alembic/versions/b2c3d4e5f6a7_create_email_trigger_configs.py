"""create_email_trigger_configs

Create email_trigger_configs table for per-user email command trigger rules.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-02-10 18:01:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Table may already exist if created by init_db auto-create
    from sqlalchemy import inspect as sa_inspect
    bind = op.get_bind()
    inspector = sa_inspect(bind)
    if 'email_trigger_configs' not in inspector.get_table_names():
        op.create_table(
            'email_trigger_configs',
            sa.Column('id', sa.String(), nullable=False),
            sa.Column('user_id', sa.String(), nullable=False),
            sa.Column('name', sa.String(length=255), nullable=False),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
            sa.Column('command_prefix', sa.String(length=50), nullable=True),
            sa.Column('command', sa.String(length=100), nullable=True),
            sa.Column('sender_filter', sa.String(length=255), nullable=True),
            sa.Column('subject_contains', sa.String(length=255), nullable=True),
            sa.Column('require_attachment', sa.Boolean(), nullable=False, server_default='0'),
            sa.Column('authorized_senders', sa.JSON(), nullable=False, server_default='[]'),
            sa.Column('workflow_id', sa.String(), nullable=False),
            sa.Column('workflow_parameters', sa.JSON(), nullable=False, server_default='{}'),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
        )

    # Create indexes if they don't exist (safe for idempotency)
    existing_indexes = {idx['name'] for idx in inspector.get_indexes('email_trigger_configs')} if 'email_trigger_configs' in inspector.get_table_names() else set()
    if 'ix_email_trigger_configs_user_id' not in existing_indexes:
        op.create_index('ix_email_trigger_configs_user_id', 'email_trigger_configs', ['user_id'])
    if 'ix_email_trigger_configs_active' not in existing_indexes:
        op.create_index('ix_email_trigger_configs_active', 'email_trigger_configs', ['user_id', 'is_active'])


def downgrade() -> None:
    op.drop_index('ix_email_trigger_configs_active', table_name='email_trigger_configs')
    op.drop_index('ix_email_trigger_configs_user_id', table_name='email_trigger_configs')
    op.drop_table('email_trigger_configs')
