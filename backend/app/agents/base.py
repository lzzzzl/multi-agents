"""Agent 抽象基类与上下文。

Agent 负责:
- 构造放入 LLM 的 prompt(系统提示 + 用户输入)
- 调用 LLM
- 解析输出为结构化结果
- (可选)ReAct 工具循环:声明工具 → 执行 → 观察 → 再思考(Step 3.1)

步骤生命周期(创建 RunStep、写事件)由上层 workflow 统一管理,Agent 保持纯粹:
工具执行经 tool_executor 回调上抛给 workflow(由 ToolRunner 持久化与审计)。
"""

import json
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.agents.message_bus import MessageBus
from app.llms import LLMMessage, LLMUsage, get_llm_provider
from app.models import Run, Task

# 工具执行回调:接收 tool_use 声明 {"name": ..., "args": ...},返回观察结果 dict
ToolExecutor = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass
class AgentContext:
    """一次 Agent 执行所需的上下文。

    上游输出经 bus 传递(Step 3.2):ctx.bus.latest("<agent_id>") 取最新,
    ctx.bus.history("<agent_id>") 取全部(如 Writer 重写回看上一稿)。
    """

    run: Run
    task: Task
    input: dict[str, Any]  # 该 run 的输入快照
    bus: MessageBus = field(default_factory=MessageBus)


@dataclass
class AgentResult:
    """Agent 执行结果,workflow 据此写事件与汇总成本。"""

    agent_id: str
    name: str
    message: str  # 展示给用户的总结文本
    output: dict[str, Any]
    usage: LLMUsage = field(default_factory=LLMUsage)
    latency_ms: int = 0
    # ReAct 循环中实际执行的工具轮次(Step 3.1)
    tool_rounds: int = 0


class BaseAgent(ABC):
    agent_id: str
    name: str
    system_prompt: str
    # Step 2.3:为 True 时,上层传入的 on_token 回调会被启用,
    # LLM 输出以 token 增量推送(如 Writer 逐字输出);默认关闭避免噪音。
    stream_output: bool = False
    # Step 3.1:ReAct 工具循环的最大工具执行轮次;0 表示不启用(单次调用行为不变)。
    max_tool_rounds: int = 0

    @abstractmethod
    def build_user_prompt(self, ctx: AgentContext) -> str:
        """构造这条 user 消息。"""
        raise NotImplementedError

    def parse(self, content: str) -> dict[str, Any]:
        """把 LLM 原始输出解析为结构化 output。默认原样包裹。"""
        return {"content": content}

    def extract_tool_use(self, output: dict[str, Any]) -> dict[str, Any] | None:
        """从 parse 后的输出中提取工具调用声明。

        返回 None 表示本轮无需调用工具(ReAct 循环终止)。默认不启用工具循环。
        """
        return None

    def build_observation_prompt(
        self, tool_use: dict[str, Any], observation: dict[str, Any]
    ) -> str:
        """把工具执行结果构造为下一轮的 user 消息(观察)。"""
        return (
            f"[工具观察] {tool_use.get('name')} 调用结果:\n"
            f"{json.dumps(observation, ensure_ascii=False, default=str)}\n"
            '请根据观察决定下一步:继续调用其他工具,或输出 {"tool_use": null} 给出最终结论。'
        )

    def run(
        self,
        ctx: AgentContext,
        *,
        on_token: Callable[[str], None] | None = None,
        tool_executor: ToolExecutor | None = None,
    ) -> AgentResult:
        """执行 Agent;启用 ReAct 时进行「思考→工具→观察→再思考」循环。

        循环终止条件(满足其一):
        - LLM 输出不再声明工具(extract_tool_use 返回 None,显式终止)
        - 已执行轮次达到 max_tool_rounds(轮次上限,硬终止)
        - 未提供 tool_executor(等价于单次调用)

        多轮 LLM 调用的 usage 累加;latency 取整个循环的墙钟时间。
        """
        llm = get_llm_provider()
        messages = [
            LLMMessage(role="system", content=self.system_prompt),
            LLMMessage(role="user", content=self.build_user_prompt(ctx)),
        ]
        callback = on_token if (self.stream_output and on_token is not None) else None

        total_usage = LLMUsage()
        rounds = 0
        started_at = time.monotonic()
        while True:
            result = llm.chat(messages, on_token=callback)
            total_usage.input_tokens += result.usage.input_tokens
            total_usage.output_tokens += result.usage.output_tokens
            total_usage.model = result.usage.model or total_usage.model

            output = self.parse(result.content)
            tool_use = (
                self.extract_tool_use(output)
                if (tool_executor is not None and self.max_tool_rounds > 0)
                else None
            )
            if tool_use is None or rounds >= self.max_tool_rounds:
                break

            rounds += 1
            observation = tool_executor(tool_use)
            # 追加本轮对话:assistant 的工具声明 + user 的观察结果
            messages.append(LLMMessage(role="assistant", content=result.content))
            messages.append(
                LLMMessage(role="user", content=self.build_observation_prompt(tool_use, observation))
            )

        return AgentResult(
            agent_id=self.agent_id,
            name=self.name,
            message=result.content,
            output=output,
            usage=total_usage,
            latency_ms=int((time.monotonic() - started_at) * 1000),
            tool_rounds=rounds,
        )