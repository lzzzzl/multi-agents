"""统一响应格式与分页结构。

所有 API 返回:
    {"data": ..., "error": null}
失败时:
    {"data": null, "error": {"code": "...", "message": "...", "details": {}}}
"""

from typing import Any, Generic, TypeVar

from pydantic import BaseModel


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None


class ApiResponse(BaseModel, Generic[TypeVar("T")]):
    data: Any = None
    error: ErrorDetail | None = None

    @classmethod
    def ok(cls, data: Any = None) -> "ApiResponse":
        return cls(data=data, error=None)

    @classmethod
    def fail(cls, code: str, message: str, details: dict[str, Any] | None = None) -> "ApiResponse":
        return cls(data=None, error=ErrorDetail(code=code, message=message, details=details))


class PageMeta(BaseModel):
    """游标分页元信息。"""

    next_cursor: str | None = None
    has_more: bool = False


class Page(BaseModel, Generic[TypeVar("T")]):
    items: list[Any]
    next_cursor: str | None = None


class HealthResponse(BaseModel):
    status: str
