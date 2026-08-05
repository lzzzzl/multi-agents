"""WriterAgent:依据计划撰写 Markdown 报告正文。"""

import json

from app.agents.base import AgentContext, BaseAgent

SYSTEM_PROMPT = """你是一位专业的报告撰写 Agent(Writer)。
你的职责:根据给定的执行计划,撰写一份结构完整、内容详实的 Markdown 报告。
直接输出 Markdown 正文,不要输出 ``` 代码块或任何多余说明。"""


class WriterAgent(BaseAgent):
    agent_id = "agent_writer"
    name = "Writer"
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
        text = content.strip()
        if text.startswith("```"):
            text = text[text.find("\n") + 1 :]
            if text.endswith("```"):
                text = text[:-3].strip()
        return {"markdown": text}