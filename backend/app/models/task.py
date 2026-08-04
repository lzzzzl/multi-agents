"""Task 模型:用户提交的任务目标。"""

from typing import Any

from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.db.ids import generate_id


class Task(Base, TimestampMixin):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: generate_id("task")
    )
    project_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    created_by: Mapped[str | None] = mapped_column(String, nullable=True, index=True)

    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # draft / queued / running / completed / failed / cancelled / archived
    status: Mapped[str] = mapped_column(String, nullable=False, default="draft", index=True)
    priority: Mapped[str] = mapped_column(String, nullable=False, default="normal")

    input: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB, nullable=True)

    runs: Mapped[list["Run"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        back_populates="task", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Task {self.id} status={self.status}>"
