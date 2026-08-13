"""PlannerAgent:把任务目标拆解为结构化执行计划。"""

import json
import logging

from app.agents._json import load_json
from app.agents.base import AgentContext, BaseAgent
from app.llms import LLMError

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一位专业的任务规划 Agent(Planner)。
你的职责:把用户给出的任务目标,拆解为清晰、可执行的步骤列表。
只输出一个 JSON 对象,不要任何多余文字或 Markdown 代码块标记。格式:

{"steps": [{"name": "步骤名", "description": "<为何做、怎么做>"}]}

要求:
- 步骤 3~6 个,名称简短,描述具体。
- 步骤应有先后顺序,覆盖从资料准备到最终成稿的完整链路。"""


class PlannerAgent(BaseAgent):
    agent_id = "agent_planner"
    name = "Planner"
    system_prompt = SYSTEM_PROMPT

    def build_user_prompt(self, ctx: AgentContext) -> str:
        task = ctx.task
        lines = [f"任务标题: {task.title}"]
        if task.description:
            lines.append(f"任务描述: {task.description}")
        if ctx.input:
            lines.append(f"任务输入: {json.dumps(ctx.input, ensure_ascii=False)}")
        return "\n".join(lines)

    def parse(self, content: str) -> dict:
        data = load_json(content, what="Planner 输出")
        steps = data.get("steps") or []
        if not isinstance(steps, list) or not steps:
            raise LLMError("Planner 未能产出有效的步骤列表", code="LLM_JSON_PARSE")
        # 归一化每个步骤字段
        normalized = []
        for i, s in enumerate(steps, start=1):
            if isinstance(s, dict):
                normalized.append(
                    {
                        "sequence": i,
                        "name": str(s.get("name") or f"步骤 {i}"),
                        "description": str(s.get("description") or ""),
                    }
                )
        return {"steps": normalized}
