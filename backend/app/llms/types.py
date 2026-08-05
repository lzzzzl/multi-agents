"""LLM 调用相关的轻量类型定义(不依赖具体 SDK)。"""

from dataclasses import dataclass, field


@dataclass
class LLMMessage:
    """一条对话消息。role 取 system / user / assistant。"""

    role: str
    content: str


@dataclass
class LLMUsage:
    """单次调用的用量与模型标识。"""

    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""


@dataclass
class LLMResult:
    """单次调用的结果。"""

    content: str
    usage: LLMUsage = field(default_factory=LLMUsage)
    latency_ms: int = 0
    raw: dict | None = None


class LLMError(RuntimeError):
    """LLM 调用失败。"""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code