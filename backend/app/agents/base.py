"""Agent 抽象基类与上下文。

Agent 负责:
- 构造放入 LLM 的 prompt(系统提示 + 用户输入)
- 调用 LLM
- 解析输出为结构化结果

步骤生命周期(创建 RunStep、写事件)由上层 workflow 统一管理,Agent 保持纯粹。
"""

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.llms import LLMMessage, LLMUsage, get_llm_provider
from app.models import Run, Task


@dataclass
class AgentContext:
    """一次 Agent 执行所需的上下文。"""

    run: Run
    task: Task
    input: dict[str, Any]  # 该 run 的输入快照
    previous: dict[str, dict[str, Any]] = field(default_factory=dict)  # agent_id -> output


@dataclass
class AgentResult:
    """Agent 执行结果,workflow 据此写事件与汇总成本。"""

    agent_id: str
    name: str
    message: str  # 展示给用户的总结文本
    output: dict[str, Any]
    usage: LLMUsage = field(default_factory=LLMUsage)
    latency_ms: int = 0


class BaseAgent(ABC):
    agent_id: str
    name: str
    system_prompt: str
    # Step 2.3:为 True 时,上层传入的 on_token 回调会被启用,
    # LLM 输出以 token 增量推送(如 Writer 逐字输出);默认关闭避免噪音。
    stream_output: bool = False

    @abstractmethod
    def build_user_prompt(self, ctx: AgentContext) -> str:
        """构造这条 user 消息。"""
        raise NotImplementedError

    def parse(self, content: str) -> dict[str, Any]:
        """把 LLM 原始输出解析为结构化 output。默认原样包裹。"""
        return {"content": content}

    def run(
        self, ctx: AgentContext, *, on_token: Callable[[str], None] | None = None
    ) -> AgentResult:
        llm = get_llm_provider()
        messages = [
            LLMMessage(role="system", content=self.system_prompt),
            LLMMessage(role="user", content=self.build_user_prompt(ctx)),
        ]
        callback = on_token if (self.stream_output and on_token is not None) else None
        result = llm.chat(messages, on_token=callback)
        return AgentResult(
            agent_id=self.agent_id,
            name=self.name,
            message=result.content,
            output=self.parse(result.content),
            usage=result.usage,
            latency_ms=result.latency_ms,
        )