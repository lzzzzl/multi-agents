"""SequentialWorkflow:按顺序编排 Planner -> Writer -> Reviewer。

Writer 出稿后经 Reviewer 评审:
- 若通过(quality=pass),结束并生成 artifact。
- 若不通过(quality=revision),把评审反馈连同上一稿回传给 Writer 重写,
  循环直至通过或达到 WORKFLOW_MAX_REWRITES 上限。
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import (
    AgentContext,
    BaseAgent,
    PlannerAgent,
    ResearcherAgent,
    ReviewerAgent,
    WriterAgent,
)
from app.core.config import settings
from app.core.errors import classify_error
from app.models import Run, RunEvent, RunStep, Task
from app.models.artifact import Artifact
from app.services.eventing import append_event
from app.tools.runner import ToolRunner

logger = logging.getLogger(__name__)


class SequentialWorkflow:
    """串行编排 Agent,并在 Reviewer 不通过时自动触发重写循环。"""

    name = "sequential_report"
    version = "1.1.0"

    def __init__(self, *, max_rewrites: int | None = None) -> None:
        self._planner = PlannerAgent()
        self._researcher = ResearcherAgent()
        self._writer = WriterAgent()
        self._reviewer = ReviewerAgent()
        # 最大重写轮次(不含首次出稿)
        self._max_rewrites = max_rewrites if max_rewrites is not None else settings.WORKFLOW_MAX_REWRITES

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def _append_event(
        self,
        db: Session,
        run_id: str,
        *,
        type: str,
        payload: dict | None = None,
        step_id: str | None = None,
        agent_id: str | None = None,
    ) -> RunEvent:
        return append_event(
            db,
            run_id,
            type=type,
            payload=payload,
            step_id=step_id,
            agent_id=agent_id,
        )

    def _check_cancelled(self, db: Session, run_id: str) -> bool:
        run = db.get(Run, run_id)
        return run is not None and run.status == "cancelled"

    def _run_agent_step(
        self,
        db: Session,
        run_id: str,
        agent: BaseAgent,
        ctx: AgentContext,
        *,
        sequence: int,
        name_suffix: str = "",
    ) -> Any:
        """执行单个 Agent,创建 RunStep 并写事件,返回 AgentResult。"""
        step = RunStep(
            run_id=run_id,
            agent_id=agent.agent_id,
            name=f"{agent.name}{name_suffix}",
            type="agent",
            status="running",
            sequence=sequence,
            started_at=self._now(),
        )
        db.add(step)
        db.commit()
        db.refresh(step)

        self._append_event(
            db,
            run_id,
            type="step_started",
            step_id=step.id,
            agent_id=agent.agent_id,
            payload={"name": step.name, "sequence": step.sequence},
        )

        try:
            result = agent.run(ctx)
        except Exception as exc:  # noqa: BLE001
            error_code = classify_error(exc)
            step.status = "failed"
            step.failed_at = self._now()
            step.error_message = str(exc)
            step.metadata_ = {"error_code": error_code}
            db.commit()

            self._append_event(
                db,
                run_id,
                type="llm_call",
                step_id=step.id,
                agent_id=agent.agent_id,
                payload={"status": "failed", "error_code": error_code, "error": str(exc)},
            )
            self._append_event(
                db,
                run_id,
                type="step_failed",
                step_id=step.id,
                agent_id=agent.agent_id,
                payload={"name": step.name, "error": str(exc), "error_code": error_code},
            )
            raise

        step.status = "completed"
        step.completed_at = self._now()
        step.output = result.output
        step.metadata_ = {
            "input_tokens": result.usage.input_tokens,
            "output_tokens": result.usage.output_tokens,
            "model": result.usage.model,
            "latency_ms": result.latency_ms,
        }
        db.commit()

        self._append_event(
            db,
            run_id,
            type="llm_call",
            step_id=step.id,
            agent_id=agent.agent_id,
            payload={
                "model": result.usage.model,
                "input_tokens": result.usage.input_tokens,
                "output_tokens": result.usage.output_tokens,
                "latency_ms": result.latency_ms,
                "status": "success",
            },
        )
        self._append_event(
            db,
            run_id,
            type="agent_message",
            step_id=step.id,
            agent_id=agent.agent_id,
            payload={
                "content": result.message,
                "agent": result.name,
                "output": result.output,
            },
        )
        self._append_event(
            db,
            run_id,
            type="step_completed",
            step_id=step.id,
            agent_id=agent.agent_id,
            payload={"name": step.name},
        )
        return result

    def _make_context(
        self, run: Run, task: Task, previous: dict[str, dict[str, Any]] | None = None
    ) -> AgentContext:
        return AgentContext(
            run=run,
            task=task,
            input=run.input_snapshot or {},
            previous=previous or {},
        )

    def _latest_step_id(self, db: Session, run_id: str) -> str | None:
        step = db.scalar(
            select(RunStep)
            .where(RunStep.run_id == run_id)
            .order_by(RunStep.sequence.desc())
            .limit(1)
        )
        return step.id if step else None

    def _execute_tool(
        self,
        db: Session,
        run_id: str,
        task: Task,
        tool_use: dict[str, Any] | None,
        *,
        step_id: str | None,
    ) -> dict[str, Any]:
        """执行工具调用,返回结果 dict。

        优先使用 Agent 声明的 tool_use;若缺失或非法,回退到 generate_report
        依据任务标题生成初稿,保证工具调用链路始终可观测。工具失败时记录错误,
        不中断 workflow。
        """
        tool_name = "generate_report"
        args: dict[str, Any] = {"title": task.title, "outline": []}
        if isinstance(tool_use, dict) and tool_use.get("name"):
            tool_name = str(tool_use["name"])
            declared_args = tool_use.get("args")
            if isinstance(declared_args, dict):
                args = dict(declared_args)
            args.setdefault("title", task.title)

        runner = ToolRunner(db)
        try:
            call = runner.run(
                run_id=run_id,
                tool_name=tool_name,
                args=args,
                step_id=step_id,
                agent_id="agent_researcher",
            )
            return {
                "tool_name": tool_name,
                "tool_call_id": call.id,
                "output": call.output or {},
                "draft": (call.output or {}).get("_display"),
                "error": call.error_message,
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning("Tool %s failed for run %s: %s", tool_name, run_id, exc)
            return {"tool_name": tool_name, "output": {}, "error": str(exc)}

    def execute(self, db: Session, run_id: str) -> dict[str, Any]:
        """执行整个 workflow,返回汇总结果。"""
        run = db.get(Run, run_id)
        task = db.get(Task, run.task_id) if run else None
        if not run or not task:
            raise ValueError(f"Run {run_id} 或对应 Task 不存在")

        previous: dict[str, dict[str, Any]] = {}
        total_input = 0
        total_output = 0
        steps_done = 0
        sequence = 0

        # 1. Planner
        if self._check_cancelled(db, run_id):
            return {"cancelled": True}
        sequence += 1
        plan_result = self._run_agent_step(
            db, run_id, self._planner, self._make_context(run, task, previous), sequence=sequence
        )
        previous["agent_planner"] = plan_result.output
        total_input += plan_result.usage.input_tokens
        total_output += plan_result.usage.output_tokens
        steps_done += 1

        # 2. Researcher:声明并执行工具调用,为 Writer 准备初稿素材
        if self._check_cancelled(db, run_id):
            return {"cancelled": True}
        sequence += 1
        researcher_result = self._run_agent_step(
            db, run_id, self._researcher, self._make_context(run, task, previous), sequence=sequence
        )
        previous["agent_researcher"] = researcher_result.output
        total_input += researcher_result.usage.input_tokens
        total_output += researcher_result.usage.output_tokens
        steps_done += 1

        # 执行 Researcher 声明的工具调用,结果注入上下文供 Writer 参考
        step_id = self._latest_step_id(db, run_id)
        previous["tool_result"] = self._execute_tool(
            db, run_id, task, researcher_result.output.get("tool_use"), step_id=step_id
        )

        # 3. Writer -> Reviewer 循环
        quality = "revision"
        final_content = ""
        rewrites = 0
        for round_no in range(self._max_rewrites + 1):
            if self._check_cancelled(db, run_id):
                logger.info("Run %s cancelled around round %s", run_id, round_no)
                return {"cancelled": True}

            suffix = "" if round_no == 0 else f"·修改{round_no}"

            sequence += 1
            writer_result = self._run_agent_step(
                db,
                run_id,
                self._writer,
                self._make_context(run, task, previous),
                sequence=sequence,
                name_suffix=suffix,
            )
            previous["agent_writer"] = writer_result.output
            total_input += writer_result.usage.input_tokens
            total_output += writer_result.usage.output_tokens
            steps_done += 1

            sequence += 1
            reviewer_result = self._run_agent_step(
                db,
                run_id,
                self._reviewer,
                self._make_context(run, task, previous),
                sequence=sequence,
                name_suffix=suffix,
            )
            previous["agent_reviewer"] = reviewer_result.output
            total_input += reviewer_result.usage.input_tokens
            total_output += reviewer_result.usage.output_tokens
            steps_done += 1

            quality = reviewer_result.output.get("quality") or "revision"
            final_content = (
                reviewer_result.output.get("final_content")
                or writer_result.output.get("markdown")
                or writer_result.output.get("content")
                or ""
            )
            if quality == "pass":
                break

            if round_no >= self._max_rewrites:
                logger.warning(
                    "Run %s reached max rewrites (%s), stopping with quality=%s",
                    run_id,
                    self._max_rewrites,
                    quality,
                )
                break

        rewrites = round_no  # 实际发生的重写轮次(首轮不计)

        # 4. 生成最终 Markdown artifact
        artifact = Artifact(
            run_id=run_id,
            created_by_agent_id="agent_writer",
            type="markdown",
            name=f"{task.title}.md",
            mime_type="text/markdown",
            content=final_content,
            size_bytes=len(final_content.encode("utf-8")),
        )
        db.add(artifact)
        db.commit()
        db.refresh(artifact)

        self._append_event(
            db,
            run_id,
            type="artifact_created",
            payload={"artifact_id": artifact.id, "name": artifact.name},
        )

        # 4. 生成执行摘要 JSON artifact(计划 + 成本 + 质量)
        plan = previous.get("agent_planner") or {}
        json_content = {
            "task": {"id": task.id, "title": task.title},
            "workflow": self.name,
            "plan": plan.get("steps") or [],
            "quality": quality,
            "rewrites": rewrites,
            "cost_summary": {
                "input_tokens": total_input,
                "output_tokens": total_output,
                "estimated_cost": _estimate_cost(total_input, total_output),
            },
        }
        json_text = json.dumps(json_content, ensure_ascii=False, indent=2)
        summary_artifact = Artifact(
            run_id=run_id,
            created_by_agent_id="agent_reviewer",
            type="json",
            name="execution-summary.json",
            mime_type="application/json",
            content=json_text,
            size_bytes=len(json_text.encode("utf-8")),
        )
        db.add(summary_artifact)
        db.commit()
        db.refresh(summary_artifact)

        self._append_event(
            db,
            run_id,
            type="artifact_created",
            payload={"artifact_id": summary_artifact.id, "name": summary_artifact.name},
        )

        return {
            "artifact_id": artifact.id,
            "steps": steps_done,
            "rewrites": rewrites,  # 重写轮次(Writer+Reviewer 配对,减首次出稿)
            "quality": quality,
            "input_tokens": total_input,
            "output_tokens": total_output,
            "estimated_cost": _estimate_cost(total_input, total_output),
        }


def _estimate_cost(input_tokens: int, output_tokens: int) -> float:
    """简化的成本估算(元),不同模型价格不同,这里用固定单价。"""
    return round(input_tokens / 1_000_000 * 0.5 + output_tokens / 1_000_000 * 2.0, 4)
