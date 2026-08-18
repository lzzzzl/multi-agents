"""add uq constraint on run_events (run_id, sequence)

Revision ID: g0a1b2c3d4e5
Revises: f8a9b0c1d2e3
Create Date: 2026-08-18 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op

revision: str = 'g0a1b2c3d4e5'
down_revision: Union[str, None] = 'f8a9b0c1d2e3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# 清理历史重复 sequence:按 (sequence, created_at, id) 保序重排为连续行号
_DEDUP_SQL = """
WITH ordered AS (
    SELECT id,
           ROW_NUMBER() OVER (PARTITION BY run_id ORDER BY sequence, created_at, id) AS rn
    FROM run_events
)
UPDATE run_events AS e
SET sequence = o.rn
FROM ordered AS o
WHERE e.id = o.id AND e.sequence <> o.rn
"""


def upgrade() -> None:
    op.execute(_DEDUP_SQL)
    # 旧普通索引被唯一约束自带的索引取代(列相同,避免冗余)
    op.drop_index("ix_run_events_run_sequence", table_name="run_events")
    op.create_unique_constraint(
        "uq_run_events_run_sequence", "run_events", ["run_id", "sequence"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_run_events_run_sequence", "run_events", type_="unique")
    op.create_index("ix_run_events_run_sequence", "run_events", ["run_id", "sequence"])
