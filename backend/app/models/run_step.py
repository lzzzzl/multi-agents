"""RunStep 模型:一次 run 中的执行步骤。"""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.db.ids import generate_id


class RunStep(Base, TimestampMixin):
    __tablename__ = "run_steps"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: generate_id("step")
    )
    run_id: Mapped[str] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    parent_step_id: Mapped[str | None] = mapped_column(
        ForeignKey("run_steps.id", ondelete="SET NULL"), nullable=True
    )
    agent_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)

    name: Mapped[str] = mapped_column(String, nullable=False)
    # agent / tool / workflow / approval / system
    type: Mapped[str] = mapped_column(String, nullable=False, default="agent")
    # pending / running / waiting_for_approval / completed / failed / skipped / cancelled
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending", index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    depends_on: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    input: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    output: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB, nullable=True)

    run: Mapped["Run"] = relationship(back_populates="steps")  # type: ignore[name-defined]  # noqa: F821

    def __repr__(self) -> str:
        return f"<RunStep {self.id} type={self.type} status={self.status}>"
