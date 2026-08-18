"""SQLAlchemy 声明性基类与公共字段混入。"""

from datetime import datetime

from sqlalchemy import JSON, DateTime, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """所有 ORM 模型的基类。"""


# 生产用 PostgreSQL JSONB;SQLite(测试真引擎)回退到通用 JSON
JSONVariant = JSONB().with_variant(JSON(), "sqlite")


class TimestampMixin:
    """公共时间戳字段。"""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
