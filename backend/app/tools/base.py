"""Tool 抽象。

Tool 是 Agent 可调用的外部能力。Tool 的契约(名称、描述、输入 schema、
风险等级、执行器)由代码注册,可通过 Registry 查找。调用过程统一由
ToolRunner 记录到 tool_calls 表并写入事件。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

# 风险等级
SAFE = "safe"
SENSITIVE = "sensitive"
DANGEROUS = "dangerous"


class ToolError(RuntimeError):
    """工具执行失败。"""

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


@dataclass
class ToolResult:
    """工具执行结果。"""

    output: dict[str, Any]
    # 若工具产生可展示的文本结果,放在这里(如 markdown 内容)
    display: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class Tool(ABC):
    """工具基类。子类实现 name / description / input_schema / execute。"""

    name: str
    description: str = ""
    # safe / sensitive / dangerous
    risk_level: str = SAFE
    # 标记工具调用是否需要按幂等键去重。有外部副作用的工具(如发送通知)
    # 应设为 True,由 ToolRunner 保证相同输入只真正执行一次。
    deduplicate: bool = False
    # JSON Schema 描述输入参数
    input_schema: dict[str, Any] = {}
    timeout_seconds: float = 30.0

    @abstractmethod
    def execute(self, args: dict[str, Any]) -> ToolResult:
        """执行工具。args 应已通过 schema 校验。"""
        raise NotImplementedError

    def __repr__(self) -> str:
        return f"<Tool {self.name} risk={self.risk_level}>"
