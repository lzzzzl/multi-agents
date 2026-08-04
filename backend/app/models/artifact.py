"""Artifact 模型:运行生成的结果文件或结构化结果。"""

from typing import Any

from sqlalchemy import BigInteger, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.db.ids import generate_id


class Artifact(Base, TimestampMixin):
    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: generate_id("artifact")
    )
    run_id: Mapped[str] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    step_id: Mapped[str | None] = mapped_column(
        ForeignKey("run_steps.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_by_agent_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)

    # markdown / json / text / html / image / file / report
    type: Mapped[str] = mapped_column(String, nullable=False, default="markdown")
    name: Mapped[str] = mapped_column(String, nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String, nullable=True)

    # 小型内容直接存 content,大文件存 storage_url
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    storage_url: Mapped[str | None] = mapped_column(String, nullable=True)

    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    checksum: Mapped[str | None] = mapped_column(String, nullable=True)

    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB, nullable=True)

    run: Mapped["Run"] = relationship(back_populates="artifacts")  # type: ignore[name-defined]  # noqa: F821

    def __repr__(self) -> str:
        return f"<Artifact {self.id} type={self.type} name={self.name}>"
