"""Mock LLM Provider。

用于无 API Key 时的本地兜底与自动化测试。
根据 user prompt 中的关键词,返回贴合各 Agent 角色的模拟输出,
从而让 Agent 流程可以在不依赖真实模型的情况下端到端跑通。
"""

import json
import re
import time
from collections.abc import Callable

from app.llms.base import LLMProvider
from app.llms.types import LLMMessage, LLMResult, LLMUsage


class MockLLMProvider(LLMProvider):
    model = "mock-model"

    def __init__(self, *, latency_ms: int = 50, stream_chunk_chars: int = 12) -> None:
        self.latency_ms = latency_ms
        # 流式回调时每个 chunk 的目标长度(字符)
        self.stream_chunk_chars = stream_chunk_chars

    def chat(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        on_token: Callable[[str], None] | None = None,
    ) -> LLMResult:
        # 依据 system prompt 判断调用方角色,user 文本仅用于提取任务标题
        system_text = " ".join(m.content for m in messages if m.role == "system")
        user_text = " ".join(m.content for m in messages if m.role == "user")
        content = self._respond(system_text, user_text)

        started = time.monotonic()
        if on_token is not None:
            # 把总延迟均摊到各 chunk,模拟逐字输出节奏(latency_ms=0 时不休眠,测试友好)
            chunks = _chunk_text(content, self.stream_chunk_chars)
            per_chunk_sleep = (self.latency_ms / 1000) / max(len(chunks), 1)
            for piece in chunks:
                time.sleep(per_chunk_sleep)
                on_token(piece)
        else:
            time.sleep(self.latency_ms / 1000)

        latency_ms = max(int((time.monotonic() - started) * 1000), self.latency_ms)
        return LLMResult(
            content=content,
            usage=LLMUsage(input_tokens=120, output_tokens=len(content) // 4, model=self.model),
            latency_ms=latency_ms,
        )

    def _respond(self, system_text: str, user_text: str) -> str:
        task_title = _extract_title(user_text)

        if "资料调研 Agent" in system_text or "researcher" in system_text.lower():
            # ReAct 循环演示(Step 3.1):首轮声明 generate_report,
            # 观察一次后补充 current_time,再观察后显式终止(tool_use: null)
            observations = user_text.count("[工具观察]")
            if observations == 0:
                return json.dumps(
                    {
                        "tool_use": {
                            "name": "generate_report",
                            "args": {
                                "title": task_title,
                                "outline": ["背景", "现状分析", "结论"],
                            },
                        }
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            if observations == 1:
                return json.dumps(
                    {"tool_use": {"name": "current_time", "args": {}}},
                    ensure_ascii=False,
                    indent=2,
                )
            return json.dumps(
                {
                    "tool_use": None,
                    "summary": "已完成资料调研:报告初稿已生成,并补充了当前时间信息。",
                },
                ensure_ascii=False,
                indent=2,
            )
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


def _chunk_text(text: str, size: int) -> list[str]:
    """把文本切成固定长度的 chunk(至少 1 字符,避免空回调)。"""
    if size <= 0:
        size = 12
    return [text[i : i + size] for i in range(0, len(text), size)] or [""]


def _extract_title(text: str) -> str:
    m = re.search(r"任务标题[:：]\s*(.+)", text) or re.search(r"标题[:：]\s*(.+)", text)
    if m:
        return m.group(1).strip()
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return lines[0].strip()[:40] if lines else "未命名任务"


def _json_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'