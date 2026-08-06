"""ToolCall 模型:一次具体工具调用记录,用于审计与可观测。"""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.db.ids import generate_id


class ToolCall(Base, TimestampMixin):
    __tablename__ = "tool_calls"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: generate_id("toolcall")
    )
    run_id: Mapped[str] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    step_id: Mapped[str | None] = mapped_column(
        ForeignKey("run_steps.id", ondelete="SET NULL"), nullable=True, index=True
    )
    agent_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)

    # 工具名(Tool 由代码 registry 注册,不依赖 DB 表)
    tool_name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    # safe / sensitive / dangerous
    risk_level: Mapped[str] = mapped_column(String, nullable=False, default="safe")

    # pending / waiting_for_approval / running / completed / failed / cancelled / rejected
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending", index=True)

    input: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    output: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    approval_id: Mapped[str | None] = mapped_column(String, nullable=True)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB, nullable=True)

    run: Mapped["Run"] = relationship(back_populates="tool_calls")  # type: ignore[name-defined]  # noqa: F821

    def __repr__(self) -> str:
        return f"<ToolCall {self.id} tool={self.tool_name} status={self.status}>"