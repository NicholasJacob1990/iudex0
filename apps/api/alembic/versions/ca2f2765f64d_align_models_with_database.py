"""align_models_with_database

Migração de alinhamento: adiciona colunas, índices e constraints
que existem nos models mas faltam no banco SQLite.

Revision ID: ca2f2765f64d
Revises: a866b468b088
Create Date: 2026-02-10 09:42:13.583109

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ca2f2765f64d'
down_revision: Union[str, None] = 'a866b468b088'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── cell_extractions: 7 colunas faltantes ──
    op.add_column('cell_extractions', sa.Column('correction_note', sa.Text(), nullable=True))
    op.add_column('cell_extractions', sa.Column('source_char_start', sa.Integer(), nullable=True))
    op.add_column('cell_extractions', sa.Column('source_char_end', sa.Integer(), nullable=True))
    op.add_column('cell_extractions', sa.Column('extraction_model', sa.String(length=100), nullable=True))
    op.add_column('cell_extractions', sa.Column('extraction_reasoning', sa.Text(), nullable=True))
    op.add_column('cell_extractions', sa.Column('column_name', sa.String(length=255), nullable=True))
    op.add_column('cell_extractions', sa.Column('created_at', sa.DateTime(), nullable=True))

    # ── corpus_project_documents: folder_path + índices ──
    op.add_column('corpus_project_documents', sa.Column('folder_path', sa.String(length=1024), nullable=True))
    op.create_index('ix_corpus_project_docs_folder', 'corpus_project_documents', ['project_id', 'folder_path'])
    op.create_index(op.f('ix_corpus_project_documents_folder_path'), 'corpus_project_documents', ['folder_path'])

    # ── dms_integrations: 2 colunas ──
    op.add_column('dms_integrations', sa.Column('connection_status', sa.String(length=20), server_default='connected', nullable=True))
    op.add_column('dms_integrations', sa.Column('provider_metadata', sa.JSON(), nullable=True))

    # ── organization_members: workflow_role ──
    op.add_column('organization_members', sa.Column('workflow_role', sa.String(length=30), nullable=True))

    # ── review_tables: cell_history ──
    op.add_column('review_tables', sa.Column('cell_history', sa.JSON(), nullable=True, server_default='[]'))

    # ── workflows: índices faltantes ──
    op.create_index(op.f('ix_workflows_category'), 'workflows', ['category'])
    op.create_index(op.f('ix_workflows_published_slug'), 'workflows', ['published_slug'], unique=True)

    # ── extraction_job_documents: índices faltantes ──
    op.create_index(op.f('ix_extraction_job_documents_job_id'), 'extraction_job_documents', ['job_id'])
    op.create_index('ix_extraction_job_documents_queue', 'extraction_job_documents', ['job_id', 'queue_position'])
    op.create_index('uix_extraction_job_document', 'extraction_job_documents', ['job_id', 'document_id'], unique=True)

    # ── djen_intimations: trocar unique de hash-only para (user_id, hash) ──
    op.drop_index('ix_djen_intimations_hash', table_name='djen_intimations')
    op.create_index(op.f('ix_djen_intimations_hash'), 'djen_intimations', ['hash'])
    # SQLite: unique constraint via unique index (equivalente)
    op.create_index('uq_djen_intimations_user_hash', 'djen_intimations', ['user_id', 'hash'], unique=True)


def downgrade() -> None:
    # ── djen_intimations: restaurar unique em hash-only ──
    op.drop_index('uq_djen_intimations_user_hash', table_name='djen_intimations')
    op.drop_index(op.f('ix_djen_intimations_hash'), table_name='djen_intimations')
    op.create_index('ix_djen_intimations_hash', 'djen_intimations', ['hash'], unique=True)

    # ── extraction_job_documents: drop índices ──
    op.drop_index('uix_extraction_job_document', table_name='extraction_job_documents')
    op.drop_index('ix_extraction_job_documents_queue', table_name='extraction_job_documents')
    op.drop_index(op.f('ix_extraction_job_documents_job_id'), table_name='extraction_job_documents')

    # ── workflows: drop índices ──
    op.drop_index(op.f('ix_workflows_published_slug'), table_name='workflows')
    op.drop_index(op.f('ix_workflows_category'), table_name='workflows')

    # ── review_tables ──
    op.drop_column('review_tables', 'cell_history')

    # ── organization_members ──
    op.drop_column('organization_members', 'workflow_role')

    # ── dms_integrations ──
    op.drop_column('dms_integrations', 'provider_metadata')
    op.drop_column('dms_integrations', 'connection_status')

    # ── corpus_project_documents ──
    op.drop_index(op.f('ix_corpus_project_documents_folder_path'), table_name='corpus_project_documents')
    op.drop_index('ix_corpus_project_docs_folder', table_name='corpus_project_documents')
    op.drop_column('corpus_project_documents', 'folder_path')

    # ── cell_extractions ──
    op.drop_column('cell_extractions', 'created_at')
    op.drop_column('cell_extractions', 'column_name')
    op.drop_column('cell_extractions', 'extraction_reasoning')
    op.drop_column('cell_extractions', 'extraction_model')
    op.drop_column('cell_extractions', 'source_char_end')
    op.drop_column('cell_extractions', 'source_char_start')
    op.drop_column('cell_extractions', 'correction_note')
