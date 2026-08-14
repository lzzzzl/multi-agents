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
from app.workflows.base import Workflow
from app.workflows.checkpoint import WorkflowCheckpoint, WorkflowSuspended
from app.workflows.dag import DAG, DAGNode

logger = logging.getLogger(__name__)


class SequentialWorkflow(Workflow):
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

    def _new_context(self) -> dict[str, Any]:
        return {
            "previous": {},
            "stats": {
                "sequence": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "steps": 0,
            },
            "cancelled": False,
            "quality": "revision",
            "rewrites": 0,
            "final_content": "",
        }

    def _summary(self, context: dict[str, Any]) -> dict[str, Any]:
        return {
            "artifact_id": context["finalize"]["artifact_id"],
            "steps": context["stats"]["steps"],
            "rewrites": context["rewrites"],
            "quality": context["quality"],
            "input_tokens": context["stats"]["input_tokens"],
            "output_tokens": context["stats"]["output_tokens"],
            "estimated_cost": _estimate_cost(
                context["stats"]["input_tokens"], context["stats"]["output_tokens"]
            ),
        }

    def _save_checkpoint(
        self, db: Session, run_id: str, checkpoint: WorkflowCheckpoint
    ) -> None:
        run = db.get(Run, run_id)
        metadata = dict(run.metadata_ or {})
        metadata["checkpoint"] = checkpoint.to_dict()
        run.metadata_ = metadata
        db.commit()

    def _load_checkpoint(self, run: Run) -> WorkflowCheckpoint:
        metadata = run.metadata_ or {}
        raw = metadata.get("checkpoint")
        if not raw:
            raise ValueError(f"Run {run.id} 没有可恢复的 checkpoint")
        return WorkflowCheckpoint.from_dict(raw)

    def _build_dag(
        self,
        db: Session,
        run_id: str,
        run: Run,
        task: Task,
        context: dict[str, Any],
        skip: set[str],
    ) -> tuple[DAG, list[str]]:
        """构建 DAG。skip 中的节点视为已完成,不构建且依赖被过滤。"""
        completed: list[str] = []

        def _guard(ctx: dict[str, Any]) -> bool:
            if ctx["cancelled"] or self._check_cancelled(db, run_id):
                ctx["cancelled"] = True
                return True
            return False

        def _accumulate(ctx: dict[str, Any], result: Any) -> None:
            ctx["stats"]["input_tokens"] += result.usage.input_tokens
            ctx["stats"]["output_tokens"] += result.usage.output_tokens
            ctx["stats"]["steps"] += 1

        def plan(ctx: dict[str, Any]) -> Any:
            if _guard(ctx):
                return None
            ctx["stats"]["sequence"] += 1
            result = self._run_agent_step(
                db,
                run_id,
                self._planner,
                self._make_context(run, task, ctx["previous"]),
                sequence=ctx["stats"]["sequence"],
            )
            ctx["previous"]["agent_planner"] = result.output
            _accumulate(ctx, result)
            completed.append("plan")
            return result.output

        def research(ctx: dict[str, Any]) -> Any:
            if _guard(ctx):
                return None
            ctx["stats"]["sequence"] += 1
            result = self._run_agent_step(
                db,
                run_id,
                self._researcher,
                self._make_context(run, task, ctx["previous"]),
                sequence=ctx["stats"]["sequence"],
            )
            ctx["previous"]["agent_researcher"] = result.output
            _accumulate(ctx, result)
            completed.append("research")
            return result.output

        def execute_tool(ctx: dict[str, Any]) -> Any:
            if _guard(ctx):
                return None
            step_id = self._latest_step_id(db, run_id)
            tool_result = self._execute_tool(
                db,
                run_id,
                task,
                (ctx["previous"].get("agent_researcher") or {}).get("tool_use"),
                step_id=step_id,
            )
            ctx["previous"]["tool_result"] = tool_result
            completed.append("execute_tool")
            return tool_result

        def compose(ctx: dict[str, Any]) -> Any:
            for round_no in range(self._max_rewrites + 1):
                if _guard(ctx):
                    return None

                suffix = "" if round_no == 0 else f"·修改{round_no}"

                ctx["stats"]["sequence"] += 1
                writer_result = self._run_agent_step(
                    db,
                    run_id,
                    self._writer,
                    self._make_context(run, task, ctx["previous"]),
                    sequence=ctx["stats"]["sequence"],
                    name_suffix=suffix,
                )
                ctx["previous"]["agent_writer"] = writer_result.output
                _accumulate(ctx, writer_result)

                ctx["stats"]["sequence"] += 1
                reviewer_result = self._run_agent_step(
                    db,
                    run_id,
                    self._reviewer,
                    self._make_context(run, task, ctx["previous"]),
                    sequence=ctx["stats"]["sequence"],
                    name_suffix=suffix,
                )
                ctx["previous"]["agent_reviewer"] = reviewer_result.output
                _accumulate(ctx, reviewer_result)

                ctx["quality"] = reviewer_result.output.get("quality") or "revision"
                ctx["final_content"] = (
                    reviewer_result.output.get("final_content")
                    or writer_result.output.get("markdown")
                    or writer_result.output.get("content")
                    or ""
                )
                if ctx["quality"] == "pass":
                    break
                if round_no >= self._max_rewrites:
                    logger.warning(
                        "Run %s reached max rewrites (%s), stopping with quality=%s",
                        run_id,
                        self._max_rewrites,
                        ctx["quality"],
                    )
                    break

            ctx["rewrites"] = round_no
            completed.append("compose")
            return {
                "quality": ctx["quality"],
                "final_content": ctx["final_content"],
                "rewrites": ctx["rewrites"],
            }

        def finalize(ctx: dict[str, Any]) -> Any:
            if _guard(ctx):
                return None

            final_content = ctx["final_content"]
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

            plan_output = ctx["previous"].get("agent_planner") or {}
            json_content = {
                "task": {"id": task.id, "title": task.title},
                "workflow": self.name,
                "plan": plan_output.get("steps") or [],
                "quality": ctx["quality"],
                "rewrites": ctx["rewrites"],
                "cost_summary": {
                    "input_tokens": ctx["stats"]["input_tokens"],
                    "output_tokens": ctx["stats"]["output_tokens"],
                    "estimated_cost": _estimate_cost(
                        ctx["stats"]["input_tokens"], ctx["stats"]["output_tokens"]
                    ),
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

            completed.append("finalize")
            return {"artifact_id": artifact.id}

        spec = [
            ("plan", plan, []),
            ("research", research, ["plan"]),
            ("execute_tool", execute_tool, ["research"]),
            ("compose", compose, ["execute_tool"]),
            ("finalize", finalize, ["compose"]),
        ]
        nodes = [
            DAGNode(name, executor, depends_on=[d for d in deps if d not in skip])
            for name, executor, deps in spec
            if name not in skip
        ]
        return DAG(nodes), completed

    def execute(self, db: Session, run_id: str) -> dict[str, Any]:
        """执行整个 workflow;节点挂起时持久化 checkpoint 并返回 suspended。"""
        run = db.get(Run, run_id)
        task = db.get(Task, run.task_id) if run else None
        if not run or not task:
            raise ValueError(f"Run {run_id} 或对应 Task 不存在")

        context = self._new_context()
        dag, completed = self._build_dag(db, run_id, run, task, context, skip=set())
        try:
            dag.run(context, parallel=False)
        except WorkflowSuspended as exc:
            checkpoint = WorkflowCheckpoint(
                workflow_name=self.name,
                completed_nodes=list(completed),
                context=context,
                suspended_node=exc.node,
                reason=exc.reason,
            )
            self._save_checkpoint(db, run_id, checkpoint)
            return {"suspended": True, "node": exc.node, "reason": exc.reason}

        if context["cancelled"]:
            return {"cancelled": True}

        return self._summary(context)

    def resume(self, db: Session, run_id: str) -> dict[str, Any]:
        """从 checkpoint 恢复执行,跳过已完成节点,不重复执行。"""
        run = db.get(Run, run_id)
        task = db.get(Task, run.task_id) if run else None
        if not run or not task:
            raise ValueError(f"Run {run_id} 或对应 Task 不存在")

        checkpoint = self._load_checkpoint(run)
        context = checkpoint.context
        dag, _ = self._build_dag(
            db, run_id, run, task, context, skip=set(checkpoint.completed_nodes)
        )
        dag.run(context, parallel=False)

        if context["cancelled"]:
            return {"cancelled": True}

        return self._summary(context)


def _estimate_cost(input_tokens: int, output_tokens: int) -> float:
    """简化的成本估算(元),不同模型价格不同,这里用固定单价。"""
    return round(input_tokens / 1_000_000 * 0.5 + output_tokens / 1_000_000 * 2.0, 4)
