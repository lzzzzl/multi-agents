"""ResearcherAgent:通过 ReAct 循环调用工具为 Writer 准备报告初稿(Step 3.1)。

思考 → 声明工具 → 经 workflow 的 ToolRunner 执行(记录到 tool_calls 表与事件流)
→ 观察结果 → 再思考,直至无需更多工具或达到轮次上限。
"""

import json
import logging

from app.agents._json import load_json
from app.agents.base import AgentContext, BaseAgent
from app.core.config import settings
from app.llms import LLMError

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一位资料调研 Agent(Researcher)。
你的职责:通过「思考 → 调用工具 → 观察结果 → 再思考」的循环,为报告撰写准备初稿素材。
当前可用工具:
- generate_report(title, outline): 根据标题与大纲生成结构化 Markdown 报告初稿。
- current_time(): 返回当前 UTC 时间,可用于补充报告的时间信息。
- send_notification(channel, message): 向管理员发送执行通知(高风险,调用前需人工审批,默认不要使用)。

每一轮只输出一个 JSON 对象,不要任何多余文字或 Markdown 代码块标记。格式:
- 需要调用工具:{"tool_use": {"name": "<工具名>", "args": {...}}}
- 无需更多工具:{"tool_use": null, "summary": "<调研结论摘要>"}

要求:
- 首轮调用 generate_report 生成初稿:title 使用任务标题,outline 依据任务目标给出 3~5 个章节。
- 收到工具观察后,判断是否需要补充其他信息(如 current_time);不需要时输出 {"tool_use": null} 结束。
- 除非任务明确要求发送通知,否则不要调用 send_notification。"""


class ResearcherAgent(BaseAgent):
    agent_id = "agent_researcher"
    name = "Researcher"
    system_prompt = SYSTEM_PROMPT
    # Step 3.1:启用 ReAct 工具循环,轮次上限由配置控制
    max_tool_rounds = settings.AGENT_MAX_TOOL_ROUNDS

    def extract_tool_use(self, output: dict) -> dict | None:
        """从输出中提取工具声明;{"tool_use": null} 表示显式终止循环。"""
        return output.get("tool_use")

    def build_user_prompt(self, ctx: AgentContext) -> str:
        task = ctx.task
        lines = [f"任务标题: {task.title}"]
        if task.description:
            lines.append(f"任务描述: {task.description}")
        if ctx.input:
            lines.append(f"任务输入: {json.dumps(ctx.input, ensure_ascii=False)}")

        plan = ctx.bus.latest("agent_planner") or {}
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
            # 显式终止:无需更多工具,保留 summary 作为调研结论
            return {"tool_use": None, "summary": data.get("summary")}
        if not isinstance(tool_use, dict):
            raise LLMError("Researcher 输出 tool_use 字段非法", code="LLM_JSON_PARSE")
        name = str(tool_use.get("name") or "")
        args = tool_use.get("args") or {}
        if not name:
            raise LLMError("Researcher 输出缺少 tool_use.name", code="LLM_JSON_PARSE")
        if not isinstance(args, dict):
            raise LLMError("Researcher 输出 tool_use.args 不是对象", code="LLM_JSON_PARSE")
        return {"tool_use": {"name": name, "args": args}}
