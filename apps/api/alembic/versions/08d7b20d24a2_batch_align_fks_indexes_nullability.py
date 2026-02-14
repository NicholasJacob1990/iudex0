"""batch_align_fks_indexes_nullability

Usa batch_alter_table do SQLite para alinhar FKs, nullable e índices
que não podem ser alterados com ALTER TABLE simples.

Revision ID: 08d7b20d24a2
Revises: ca2f2765f64d
Create Date: 2026-02-10 09:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '08d7b20d24a2'
down_revision: Union[str, None] = 'ca2f2765f64d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Renomear índices antigos (idx_ → ix_) e adicionar FKs via batch ──

    # cases: add FK organization_id → organizations.id
    with op.batch_alter_table('cases', schema=None) as batch_op:
        batch_op.create_foreign_key('fk_cases_organization_id', 'organizations', ['organization_id'], ['id'])

    # chats: rename index + add FK
    op.drop_index('idx_chats_org_id', table_name='chats')
    op.create_index(op.f('ix_chats_organization_id'), 'chats', ['organization_id'])
    with op.batch_alter_table('chats', schema=None) as batch_op:
        batch_op.create_foreign_key('fk_chats_organization_id', 'organizations', ['organization_id'], ['id'])

    # documents: rename index + add FKs + new indexes
    op.drop_index('idx_documents_org_id', table_name='documents')
    op.create_index(op.f('ix_documents_organization_id'), 'documents', ['organization_id'])
    op.create_index(op.f('ix_documents_case_id'), 'documents', ['case_id'])
    with op.batch_alter_table('documents', schema=None) as batch_op:
        batch_op.create_foreign_key('fk_documents_organization_id', 'organizations', ['organization_id'], ['id'])
        batch_op.create_foreign_key('fk_documents_case_id', 'cases', ['case_id'], ['id'])

    # users: rename index + add FK
    op.drop_index('idx_users_org_id', table_name='users')
    op.create_index(op.f('ix_users_organization_id'), 'users', ['organization_id'])
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.create_foreign_key('fk_users_organization_id', 'organizations', ['organization_id'], ['id'])

    # djen_intimations: add FK for oab_watchlist_id + fix unique constraint
    with op.batch_alter_table('djen_intimations', schema=None) as batch_op:
        batch_op.create_foreign_key('fk_djen_intimations_oab_watchlist', 'djen_oab_watchlist', ['oab_watchlist_id'], ['id'])

    # table_chat_messages: add missing index
    op.create_index(op.f('ix_table_chat_messages_review_table_id'), 'table_chat_messages', ['review_table_id'])

    # redline_states: add unique constraint via index
    op.create_index('uq_run_redline', 'redline_states', ['playbook_run_id', 'redline_id'], unique=True)

    # review_table_templates: drop orphaned index (model doesn't define it)
    # Keeping it — it exists and is harmless, removing would be destructive


def downgrade() -> None:
    # redline_states
    op.drop_index('uq_run_redline', table_name='redline_states')

    # table_chat_messages
    op.drop_index(op.f('ix_table_chat_messages_review_table_id'), table_name='table_chat_messages')

    # djen_intimations: drop FK
    with op.batch_alter_table('djen_intimations', schema=None) as batch_op:
        batch_op.drop_constraint('fk_djen_intimations_oab_watchlist', type_='foreignkey')

    # users: restore old index name, drop FK
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_constraint('fk_users_organization_id', type_='foreignkey')
    op.drop_index(op.f('ix_users_organization_id'), table_name='users')
    op.create_index('idx_users_org_id', 'users', ['organization_id'])

    # documents: restore old index, drop FKs
    with op.batch_alter_table('documents', schema=None) as batch_op:
        batch_op.drop_constraint('fk_documents_case_id', type_='foreignkey')
        batch_op.drop_constraint('fk_documents_organization_id', type_='foreignkey')
    op.drop_index(op.f('ix_documents_case_id'), table_name='documents')
    op.drop_index(op.f('ix_documents_organization_id'), table_name='documents')
    op.create_index('idx_documents_org_id', 'documents', ['organization_id'])

    # chats: restore old index, drop FK
    with op.batch_alter_table('chats', schema=None) as batch_op:
        batch_op.drop_constraint('fk_chats_organization_id', type_='foreignkey')
    op.drop_index(op.f('ix_chats_organization_id'), table_name='chats')
    op.create_index('idx_chats_org_id', 'chats', ['organization_id'])

    # cases: drop FK
    with op.batch_alter_table('cases', schema=None) as batch_op:
        batch_op.drop_constraint('fk_cases_organization_id', type_='foreignkey')
