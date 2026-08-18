"""add llm_spans table

Revision ID: f8a9b0c1d2e3
Revises: e6f7a8b9c0d1
Create Date: 2026-08-18 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'f8a9b0c1d2e3'
down_revision: Union[str, None] = 'e6f7a8b9c0d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'llm_spans',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column(
            'run_id',
            sa.String(),
            sa.ForeignKey('runs.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'step_id',
            sa.String(),
            sa.ForeignKey('run_steps.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column('agent_id', sa.String(), nullable=True),
        sa.Column('model', sa.String(), nullable=False),
        sa.Column('input_tokens', sa.Integer(), nullable=False),
        sa.Column('output_tokens', sa.Integer(), nullable=False),
        sa.Column('latency_ms', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('error_code', sa.String(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('attempt', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(op.f('ix_llm_spans_run_id'), 'llm_spans', ['run_id'])
    op.create_index(op.f('ix_llm_spans_step_id'), 'llm_spans', ['step_id'])
    op.create_index(op.f('ix_llm_spans_agent_id'), 'llm_spans', ['agent_id'])
    op.create_index(op.f('ix_llm_spans_status'), 'llm_spans', ['status'])


def downgrade() -> None:
    op.drop_index(op.f('ix_llm_spans_status'), table_name='llm_spans')
    op.drop_index(op.f('ix_llm_spans_agent_id'), table_name='llm_spans')
    op.drop_index(op.f('ix_llm_spans_step_id'), table_name='llm_spans')
    op.drop_index(op.f('ix_llm_spans_run_id'), table_name='llm_spans')
    op.drop_table('llm_spans')
