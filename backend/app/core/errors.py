"""业务层异常。携带错误码,供 API 层映射为统一响应。"""


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
