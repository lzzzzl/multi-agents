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

        if "质量评审 Agent" in system_text or "reviewer" in system_text.lower():
            # 若被评审内容含 Writer 的修订标记,视为已重写并通过;
            # 否则首次评审判定为需修改,以触发一次重写循环。
            if "已按评审意见修订" in user_text:
                return (
                    "{\n"
                    '  "quality": "pass",\n'
                    '  "score": 9,\n'
                    '  "feedback": "修改后结构完整、内容准确,达到交付标准。",\n'
                    '  "final_content": ' + _json_quote(f"# {task_title}\n\n## 概述\n\n本报告由 multi-agent 工作台生成。\n\n## 正文\n\n已根据评审意见完善。\n\n## 结论\n\n经过 Planner、Writer、Reviewer 三阶段协作,已完成交付。") + "\n}"
                )
            return (
                "{\n"
                '  "quality": "revision",\n'
                '  "score": 5,\n'
                '  "feedback": "正文内容单薄,缺少数据支撑与细分小节,请扩充并补充结论。",\n'
                '  "final_content": ""\n'
                "}"
            )
        if "报告撰写 Agent" in system_text or "writer" in system_text.lower():
            # 若 Writer 收到评审意见(重写轮),输出带修订标记的稿子
            if "评审意见" in user_text:
                return (
                    f"# {task_title}\n\n"
                    "## 概述\n\n本报告由 multi-agent 工作台生成。\n\n"
                    "## 正文\n\n已按评审意见修订,补充了数据支撑与结论。\n\n"
                    "## 结论\n\n完成。"
                )
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