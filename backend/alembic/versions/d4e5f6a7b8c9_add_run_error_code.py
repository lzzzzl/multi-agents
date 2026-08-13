"""add run error_code

Revision ID: d4e5f6a7b8c9
Revises: bf4a7ce789b8
Create Date: 2026-08-13 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'bf4a7ce789b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('runs', sa.Column('error_code', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('runs', 'error_code')
