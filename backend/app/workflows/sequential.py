"""SequentialWorkflow:按顺序编排 Planner -> Writer -> Reviewer。"""

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents import AgentContext, BaseAgent, PlannerAgent, ReviewerAgent, WriterAgent
from app.models import Run, RunEvent, RunStep, Task
from app.models.artifact import Artifact

logger = logging.getLogger(__name__)


class SequentialWorkflow:
    """串行编排一组 Agent,每个 Agent 产出写入 RunStep 与事件流。"""

    name = "sequential_report"
    version = "1.0.0"

    def __init__(self) -> None:
        self._agents: list[BaseAgent] = [
            PlannerAgent(),
            WriterAgent(),
            ReviewerAgent(),
        ]

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
        current_max = db.scalar(
            select(func.max(RunEvent.sequence)).where(RunEvent.run_id == run_id)
        )
        next_seq = (current_max or 0) + 1
        event = RunEvent(
            run_id=run_id,
            step_id=step_id,
            agent_id=agent_id,
            type=type,
            sequence=next_seq,
            payload=payload,
        )
        db.add(event)
        db.commit()
        db.refresh(event)
        return event

    def _check_cancelled(self, db: Session, run_id: str) -> bool:
        run = db.get(Run, run_id)
        return run is not None and run.status == "cancelled"

    def execute(self, db: Session, run_id: str) -> dict[str, Any]:
        """执行整个 workflow,返回汇总结果。"""
        run = db.get(Run, run_id)
        task = db.get(Task, run.task_id) if run else None
        if not run or not task:
            raise ValueError(f"Run {run_id} 或对应 Task 不存在")

        ctx = AgentContext(
            run=run,
            task=task,
            input=run.input_snapshot or {},
        )

        total_input = 0
        total_output = 0
        steps_done = 0

        for idx, agent in enumerate(self._agents, start=1):
            if self._check_cancelled(db, run_id):
                logger.info("Run %s cancelled at agent %s", run_id, agent.name)
                return {"cancelled": True}

            step = RunStep(
                run_id=run_id,
                agent_id=agent.agent_id,
                name=agent.name,
                type="agent",
                status="running",
                sequence=idx,
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

            result = agent.run(ctx)
            ctx.previous[agent.agent_id] = result.output

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

            total_input += result.usage.input_tokens
            total_output += result.usage.output_tokens
            steps_done += 1

        # 取 Reviewer 的定稿作为最终 artifact
        reviewer_output = ctx.previous.get("agent_reviewer", {})
        final_content = reviewer_output.get("final_content") or ""
        if not final_content:
            writer_output = ctx.previous.get("agent_writer", {})
            final_content = writer_output.get("markdown") or writer_output.get("content") or ""

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

        return {
            "artifact_id": artifact.id,
            "steps": steps_done,
            "input_tokens": total_input,
            "output_tokens": total_output,
            "estimated_cost": _estimate_cost(total_input, total_output),
        }


def _estimate_cost(input_tokens: int, output_tokens: int) -> float:
    """简化的成本估算(元),不同模型价格不同,这里用固定单价。"""
    return round(input_tokens / 1_000_000 * 0.5 + output_tokens / 1_000_000 * 2.0, 4)