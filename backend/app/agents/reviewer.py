"""ReviewerAgent:评审 Writer 产出,决定通过或要求修改。"""

import json

from app.agents._json import load_json
from app.agents.base import AgentContext, BaseAgent
from app.llms import LLMError

SYSTEM_PROMPT = """你是一位严谨的质量评审 Agent(Reviewer)。
你的职责:审查 Writer 产出的报告,判断是否达到交付标准。
只输出一个 JSON 对象,不要任何多余文字或 Markdown 代码块标记。格式:

{"quality": "pass|revision", "score": 0-10, "feedback": "<评审意见>", "final_content": "<定稿内容,与原文一致或修正后>"}

要求:
- 若质量达标,quality 为 pass,feedback 简述通过理由。
- 若需修改,quality 为 revision,feedback 给出具体修改意见。
- final_content 始终给出最终交付内容。"""


class ReviewerAgent(BaseAgent):
    agent_id = "agent_reviewer"
    name = "Reviewer"
    system_prompt = SYSTEM_PROMPT

    def build_user_prompt(self, ctx: AgentContext) -> str:
        task = ctx.task
        lines = [f"任务标题: {task.title}"]
        if task.description:
            lines.append(f"任务描述: {task.description}")
        if ctx.input:
            lines.append(f"任务输入: {json.dumps(ctx.input, ensure_ascii=False)}")

        writer = ctx.previous.get("agent_writer") or {}
        draft = writer.get("markdown") or writer.get("content") or ""
        lines.append("待评审报告:")
        lines.append(draft or "(无正文)")

        return "\n".join(lines)

    def parse(self, content: str) -> dict:
        data = load_json(content, what="Reviewer 输出")
        quality = str(data.get("quality") or "pass").strip().lower()
        if quality not in {"pass", "revision"}:
            raise LLMError("Reviewer 输出 quality 字段非法", code="LLM_JSON_PARSE")
        return {
            "quality": quality,
            "score": data.get("score", 0),
            "feedback": str(data.get("feedback") or ""),
            "final_content": str(data.get("final_content") or ""),
        }
