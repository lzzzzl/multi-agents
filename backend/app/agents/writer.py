"""WriterAgent:依据计划撰写 Markdown 报告正文。"""

import json

from app.agents.base import AgentContext, BaseAgent

SYSTEM_PROMPT = """你是一位专业的报告撰写 Agent(Writer)。
你的职责:根据给定的执行计划,撰写一份结构完整、内容详实的 Markdown 报告。
若收到评审意见,请针对意见修改后重新输出完整正文。
直接输出 Markdown 正文,不要输出 ``` 代码块或任何多余说明。"""


class WriterAgent(BaseAgent):
    agent_id = "agent_writer"
    name = "Writer"
    system_prompt = SYSTEM_PROMPT
    # 正文撰写开启 token 流式,前端可逐字看到 Writer 输出(Step 2.3)
    stream_output = True

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

        # 若 Researcher 通过工具生成了初稿,作为撰写素材
        tool_result = ctx.previous.get("tool_result") or {}
        draft = tool_result.get("draft")
        if draft:
            lines.append("下面是通过工具生成的报告初稿,请据此润色、补全并重写为完整定稿:")
            lines.append(draft)

        # 若上一稿被 Reviewer 打回,携带反馈与上一稿内容要求重写
        review = ctx.previous.get("agent_reviewer") or {}
        if review.get("quality") == "revision":
            feedback = review.get("feedback") or ""
            lines.append("上一稿评审意见(请据此修改):")
            lines.append(feedback or "(无具体意见,请自行改进)")

            prev_writer = ctx.previous.get("agent_writer") or {}
            prev_draft = prev_writer.get("markdown") or prev_writer.get("content") or ""
            if prev_draft:
                lines.append("上一稿内容:")
                lines.append(prev_draft)

            lines.append("请保留有价值的内容,针对评审意见修改后重新输出完整 Markdown 正文。")

        return "\n".join(lines)

    def parse(self, content: str) -> dict:
        text = content.strip()
        if text.startswith("```"):
            text = text[text.find("\n") + 1 :]
            if text.endswith("```"):
                text = text[:-3].strip()
        return {"markdown": text}