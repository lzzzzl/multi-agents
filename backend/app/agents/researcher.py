"""ResearcherAgent:通过调用工具为 Writer 准备报告初稿。

Researcher 负责声明一次工具调用(当前使用本地 safe 工具 generate_report),
由 workflow 统一经 ToolRunner 执行并记录到 tool_calls 表与事件流。
"""

import json
import logging

from app.agents._json import load_json
from app.agents.base import AgentContext, BaseAgent
from app.llms import LLMError

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一位资料调研 Agent(Researcher)。
你的职责:调用工具为报告撰写准备初稿素材。当前可用工具:
- generate_report(title, outline): 根据标题与大纲生成结构化 Markdown 报告初稿。
- send_notification(channel, message): 向管理员发送执行通知(高风险,调用前需人工审批,默认不要使用)。

只输出一个 JSON 对象,不要任何多余文字或 Markdown 代码块标记。格式:
{"tool_use": {"name": "generate_report", "args": {"title": "<报告标题>", "outline": ["<大纲项>", ...]}}}

要求:
- title 使用任务标题。
- outline 依据任务目标给出 3~5 个章节大纲。
- 默认使用 generate_report;除非任务明确要求发送通知,否则不要调用 send_notification。
- 若你认为无需调用工具,可输出 {"tool_use": null}。"""


class ResearcherAgent(BaseAgent):
    agent_id = "agent_researcher"
    name = "Researcher"
    system_prompt = SYSTEM_PROMPT

    def build_user_prompt(self, ctx: AgentContext) -> str:
        task = ctx.task
        lines = [f"任务标题: {task.title}"]
        if task.description:
            lines.append(f"任务描述: {task.description}")
        if ctx.input:
            lines.append(f"任务输入: {json.dumps(ctx.input, ensure_ascii=False)}")

        plan = ctx.previous.get("agent_planner") or {}
        steps = plan.get("steps") or []
        if steps:
            lines.append("执行计划:")
            for s in steps:
                name = s.get("name") or ""
                desc = s.get("description") or ""
                lines.append(f"- {name}: {desc}")
        return "\n".join(lines)

    def parse(self, content: str) -> dict:
        data = load_json(content, what="Researcher 输出")
        tool_use = data.get("tool_use")
        if tool_use is None:
            return {"tool_use": None}
        if not isinstance(tool_use, dict):
            raise LLMError("Researcher 输出 tool_use 字段非法")
        name = str(tool_use.get("name") or "")
        args = tool_use.get("args") or {}
        if not name:
            raise LLMError("Researcher 输出缺少 tool_use.name")
        if not isinstance(args, dict):
            raise LLMError("Researcher 输出 tool_use.args 不是对象")
        return {"tool_use": {"name": name, "args": args}}