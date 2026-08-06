"""Run 模型:一次任务执行记录。"""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.db.ids import generate_id


class Run(Base, TimestampMixin):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: generate_id("run")
    )
    task_id: Mapped[str] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )

    workflow_name: Mapped[str] = mapped_column(String, nullable=False, default="sequential_report")
    workflow_version: Mapped[str] = mapped_column(String, nullable=False, default="1.0.0")

    # queued / running / waiting_for_approval / completed / failed / cancelled
    status: Mapped[str] = mapped_column(String, nullable=False, default="queued", index=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 运行开始时快照任务输入,保证历史回放不受任务后续修改影响
    input_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    output_summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    cost_summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB, nullable=True)

    source_run_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)

    task: Mapped["Task"] = relationship(back_populates="runs")  # type: ignore[name-defined]  # noqa: F821
    steps: Mapped[list["RunStep"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        back_populates="run", cascade="all, delete-orphan", order_by="RunStep.sequence"
    )
    events: Mapped[list["RunEvent"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        back_populates="run", cascade="all, delete-orphan", order_by="RunEvent.sequence"
    )
    artifacts: Mapped[list["Artifact"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        back_populates="run", cascade="all, delete-orphan"
    )
    tool_calls: Mapped[list["ToolCall"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        back_populates="run", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Run {self.id} status={self.status}>"
