"""RunEvent 模型:运行过程事件流,可观察性与实时推送的核心。"""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, JSONVariant
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
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONVariant, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    run: Mapped["Run"] = relationship(back_populates="events")  # type: ignore[name-defined]  # noqa: F821

    __table_args__ = (
        # Step 2.2:(run_id, sequence) 唯一,数据库层兜底防并发撞号;
        # 唯一约束自带 (run_id, sequence) 索引,SSE 游标查询同样命中
        UniqueConstraint("run_id", "sequence", name="uq_run_events_run_sequence"),
        Index("ix_run_events_run_created", "run_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<RunEvent {self.id} type={self.type} seq={self.sequence}>"
