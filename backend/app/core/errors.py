"""业务层异常。携带错误码,供 API 层映射为统一响应。"""

from enum import StrEnum

from app.llms.types import LLMError
from app.tools.base import ToolError


class AppError(Exception):
    """业务错误基类。"""

    code: str = "INTERNAL_ERROR"
    status_code: int = 500

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFoundError(AppError):
    code = "NOT_FOUND"
    status_code = 404


class ValidationError(AppError):
    code = "VALIDATION_ERROR"
    status_code = 422


class ConflictError(AppError):
    code = "CONFLICT"
    status_code = 409


class TaskNotFound(NotFoundError):
    code = "TASK_NOT_FOUND"


class RunNotFound(NotFoundError):
    code = "RUN_NOT_FOUND"


class ArtifactNotFound(NotFoundError):
    code = "ARTIFACT_NOT_FOUND"


class WorkflowNotFound(NotFoundError):
    code = "WORKFLOW_NOT_FOUND"


class ErrorCode(StrEnum):
    """Run 失败的归因分类,用于可观测性与熔断统计。"""

    LLM_TIMEOUT = "LLM_TIMEOUT"
    LLM_JSON_PARSE = "LLM_JSON_PARSE"
    LLM_HTTP_ERROR = "LLM_HTTP_ERROR"
    TOOL_FAILED = "TOOL_FAILED"
    TOOL_APPROVAL_TIMEOUT = "TOOL_APPROVAL_TIMEOUT"
    RUN_CANCELLED = "RUN_CANCELLED"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    UNKNOWN = "UNKNOWN"


# 临时性错误,可在 per-step 重试时安全重试;确定性错误(如 JSON 解析)不重试。
RETRYABLE_ERROR_CODES = frozenset(
    {
        ErrorCode.LLM_TIMEOUT.value,
        ErrorCode.LLM_HTTP_ERROR.value,
    }
)


def classify_error(exc: BaseException) -> str:
    """把异常归类为 ErrorCode 值,用于写入 run.error_code。

    优先取异常自带的 code(如 LLMError.code、ToolError.code),若其值恰好是
    合法 ErrorCode 则直接复用;否则按异常类型兜底。
    """
    code = getattr(exc, "code", None)
    if isinstance(code, str):
        try:
            return ErrorCode(code).value
        except ValueError:
            pass

    if isinstance(exc, ToolError):
        return ErrorCode.TOOL_FAILED.value

    return ErrorCode.UNKNOWN.value


def is_retryable_error(exc: BaseException) -> bool:
    """判断异常是否属于可安全重试的临时性错误。"""
    return classify_error(exc) in RETRYABLE_ERROR_CODES
