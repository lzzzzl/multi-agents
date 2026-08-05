"""Mock LLM Provider。

用于无 API Key 时的本地兜底与自动化测试。
根据 user prompt 中的关键词,返回贴合各 Agent 角色的模拟输出,
从而让 Agent 流程可以在不依赖真实模型的情况下端到端跑通。
"""

import re
import time

from app.llms.base import LLMProvider
from app.llms.types import LLMMessage, LLMResult, LLMUsage


class MockLLMProvider(LLMProvider):
    model = "mock-model"

    def __init__(self, *, latency_ms: int = 50) -> None:
        self.latency_ms = latency_ms

    def chat(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> LLMResult:
        # 依据 system prompt 判断调用方角色,user 文本仅用于提取任务标题
        system_text = " ".join(m.content for m in messages if m.role == "system")
        user_text = " ".join(m.content for m in messages if m.role == "user")
        content = self._respond(system_text, user_text)

        started = time.monotonic()
        time.sleep(self.latency_ms / 1000)

        return LLMResult(
            content=content,
            usage=LLMUsage(input_tokens=120, output_tokens=len(content) // 4, model=self.model),
            latency_ms=self.latency_ms,
        )

    def _respond(self, system_text: str, user_text: str) -> str:
        task_title = _extract_title(user_text)

        if "评审" in system_text or "review" in system_text.lower():
            return (
                "{\n"
                '  "quality": "pass",\n'
                '  "score": 9,\n'
                '  "feedback": "报告结构完整、内容准确,达到交付标准。",\n'
                '  "final_content": ' + _json_quote(f"# {task_title}\n\n## 概述\n\n本报告由 multi-agent 工作台生成。\n\n## 结论\n\n经过 Planner、Writer、Reviewer 三阶段协作,已完成交付。") + "\n}"
            )
        if "撰写" in system_text or "write" in system_text.lower() or "markdown 报告" in system_text:
            return (
                f"# {task_title}\n\n"
                "## 概述\n\n本报告由 multi-agent 工作台生成。\n\n"
                "## 正文\n\n根据计划展开撰写,内容如下。\n\n"
                "## 结论\n\n完成。"
            )
        # 默认按 Planner 输出计划
        return (
            "{\n"
            '  "steps": [\n'
            f'    {{"name": "资料收集", "description": "围绕「{task_title}」收集资料"}},\n'
            f'    {{"name": "内容撰写", "description": "根据资料撰写报告正文"}},\n'
            f'    {{"name": "质量检查", "description": "校验报告完整性"}}\n'
            "  ]\n"
            "}"
        )


def _extract_title(text: str) -> str:
    m = re.search(r"任务标题[:：]\s*(.+)", text) or re.search(r"标题[:：]\s*(.+)", text)
    if m:
        return m.group(1).strip()
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return lines[0].strip()[:40] if lines else "未命名任务"


def _json_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'