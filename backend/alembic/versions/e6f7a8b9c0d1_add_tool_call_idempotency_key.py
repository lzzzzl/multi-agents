"""add tool_call idempotency_key

Revision ID: e6f7a8b9c0d1
Revises: d4e5f6a7b8c9
Create Date: 2026-08-17 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'e6f7a8b9c0d1'
down_revision: Union[str, None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('tool_calls', sa.Column('idempotency_key', sa.String(), nullable=True))
    op.create_index(
        op.f('ix_tool_calls_idempotency_key'),
        'tool_calls',
        ['idempotency_key'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_tool_calls_idempotency_key'), table_name='tool_calls')
    op.drop_column('tool_calls', 'idempotency_key')
