"""LlmSpan 模型:一次 LLM 调用的轻量 trace 记录。

层级:run_id → step_id → agent_id → llm_call。
为 DAG/ReAct 提供调试底座,与 RunEvent 的 llm_call 事件互补:
事件用于前端实时展示,span 用于结构化查询与统计。
"""

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.db.ids import generate_id


class LlmSpan(Base, TimestampMixin):
    __tablename__ = "llm_spans"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: generate_id("span")
    )
    run_id: Mapped[str] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    step_id: Mapped[str | None] = mapped_column(
        ForeignKey("run_steps.id", ondelete="SET NULL"), nullable=True, index=True
    )
    agent_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)

    model: Mapped[str] = mapped_column(String, nullable=False, default="")
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # success / failed
    status: Mapped[str] = mapped_column(String, nullable=False, default="success", index=True)
    # 失败归因分类(ErrorCode 值),成功时为 NULL
    error_code: Mapped[str | None] = mapped_column(String, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 该 step 内第几次调用(重试时每次尝试各记一条)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    run: Mapped["Run"] = relationship(back_populates="llm_spans")  # type: ignore[name-defined]  # noqa: F821

    def __repr__(self) -> str:
        return f"<LlmSpan {self.id} agent={self.agent_id} status={self.status}>"
