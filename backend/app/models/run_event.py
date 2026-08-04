"""RunEvent 模型:运行过程事件流,可观察性与实时推送的核心。"""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.ids import generate_id


class RunEvent(Base):
    __tablename__ = "run_events"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: generate_id("evt")
    )
    run_id: Mapped[str] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    step_id: Mapped[str | None] = mapped_column(
        ForeignKey("run_steps.id", ondelete="SET NULL"), nullable=True, index=True
    )
    agent_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    tool_call_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)

    type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    # 在单个 run 内单调递增,SSE 用作游标
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    run: Mapped["Run"] = relationship(back_populates="events")  # type: ignore[name-defined]  # noqa: F821

    __table_args__ = (
        # SSE 按 (run_id, sequence) 游标查询,核心索引
        Index("ix_run_events_run_sequence", "run_id", "sequence"),
        Index("ix_run_events_run_created", "run_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<RunEvent {self.id} type={self.type} seq={self.sequence}>"
