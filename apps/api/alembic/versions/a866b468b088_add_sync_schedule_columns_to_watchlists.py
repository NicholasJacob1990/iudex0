"""add_sync_schedule_columns_to_watchlists

Revision ID: a866b468b088
Revises: y7z8a9b0c1d2
Create Date: 2026-02-10 04:09:48.946302

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a866b468b088'
down_revision: Union[str, None] = 'y7z8a9b0c1d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # process_watchlist: add sync schedule columns
    op.add_column('process_watchlist', sa.Column('sync_frequency', sa.String(), nullable=False, server_default='daily'))
    op.add_column('process_watchlist', sa.Column('sync_time', sa.String(), nullable=False, server_default='06:00'))
    op.add_column('process_watchlist', sa.Column('sync_cron', sa.String(), nullable=True))
    op.add_column('process_watchlist', sa.Column('sync_timezone', sa.String(), nullable=False, server_default='America/Sao_Paulo'))
    op.add_column('process_watchlist', sa.Column('next_sync_at', sa.DateTime(), nullable=True))

    # djen_oab_watchlist: add sync schedule columns
    op.add_column('djen_oab_watchlist', sa.Column('sync_frequency', sa.String(), nullable=False, server_default='daily'))
    op.add_column('djen_oab_watchlist', sa.Column('sync_time', sa.String(), nullable=False, server_default='06:00'))
    op.add_column('djen_oab_watchlist', sa.Column('sync_cron', sa.String(), nullable=True))
    op.add_column('djen_oab_watchlist', sa.Column('sync_timezone', sa.String(), nullable=False, server_default='America/Sao_Paulo'))
    op.add_column('djen_oab_watchlist', sa.Column('next_sync_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('process_watchlist', 'next_sync_at')
    op.drop_column('process_watchlist', 'sync_timezone')
    op.drop_column('process_watchlist', 'sync_cron')
    op.drop_column('process_watchlist', 'sync_time')
    op.drop_column('process_watchlist', 'sync_frequency')

    op.drop_column('djen_oab_watchlist', 'next_sync_at')
    op.drop_column('djen_oab_watchlist', 'sync_timezone')
    op.drop_column('djen_oab_watchlist', 'sync_cron')
    op.drop_column('djen_oab_watchlist', 'sync_time')
    op.drop_column('djen_oab_watchlist', 'sync_frequency')
