"""Run 业务服务。

Phase 1:创建 run、查询 run、记录事件。
注意:实际 Agent 执行在后台 worker 中进行(见 app/workers),
API 层只负责创建 run 并入队,不在 HTTP 请求内执行 workflow。
"""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import RunNotFound, TaskNotFound
from app.models import Run, RunEvent, RunStep, Task
from app.schemas.run import RunCreate


class RunService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, payload: RunCreate) -> Run:
        task = self.db.get(Task, payload.task_id)
        if not task:
            raise TaskNotFound(f"Task {payload.task_id} not found")

        # 快照任务输入,保证历史回放不受任务后续修改影响
        input_snapshot = payload.input_override or task.input or {}

        run = Run(
            task_id=task.id,
            workflow_name=payload.workflow_name,
            status="queued",
            input_snapshot=input_snapshot,
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)

        # 写入首个事件。Worker 接管后会继续写入后续事件。
        self.append_event(run.id, type="run_started", payload={"workflow": run.workflow_name})

        # 投递后台 job 给 worker,不在 HTTP 请求内执行 workflow。
        # 用 try/except 保护:入队失败不应阻塞 run 创建,worker 也可手动补跑。
        try:
            from app.workers.queue import get_queue
            from app.workers.run_worker import execute_run

            get_queue().enqueue(execute_run, run.id, job_timeout=600)
        except Exception:
            # 入队失败时记录,run 保持 queued 状态便于排查/重投
            import logging

            logging.getLogger(__name__).warning(
                "Failed to enqueue run %s, will stay queued", run.id, exc_info=True
            )
        return run

    def get(self, run_id: str) -> Run:
        run = self.db.get(Run, run_id)
        if not run:
            raise RunNotFound(f"Run {run_id} not found")
        return run

    def get_detail(self, run_id: str) -> Run:
        run = self.get(run_id)
        # 预加载 steps,按 sequence 排序
        stmt = select(RunStep).where(RunStep.run_id == run_id).order_by(RunStep.sequence)
        run.steps = list(self.db.scalars(stmt))
        return run

    def list_events(
        self,
        run_id: str,
        after_sequence: int | None = None,
        limit: int = 100,
    ) -> list[RunEvent]:
        stmt = (
            select(RunEvent)
            .where(RunEvent.run_id == run_id)
            .order_by(RunEvent.sequence.asc())
            .limit(limit)
        )
        if after_sequence is not None:
            stmt = stmt.where(RunEvent.sequence > after_sequence)
        return list(self.db.scalars(stmt))

    def append_event(
        self,
        run_id: str,
        *,
        type: str,
        payload: dict[str, Any] | None = None,
        step_id: str | None = None,
        agent_id: str | None = None,
        tool_call_id: str | None = None,
    ) -> RunEvent:
        """向 run 追加一个事件,sequence 在该 run 内单调递增。"""
        current_max = self.db.scalar(
            select(func.max(RunEvent.sequence)).where(RunEvent.run_id == run_id)
        )
        next_seq = (current_max or 0) + 1

        event = RunEvent(
            run_id=run_id,
            step_id=step_id,
            agent_id=agent_id,
            tool_call_id=tool_call_id,
            type=type,
            sequence=next_seq,
            payload=payload,
        )
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)
        return event

    def cancel(self, run_id: str, reason: str | None = None) -> Run:
        run = self.get(run_id)
        if run.status in {"completed", "failed", "cancelled"}:
            # 已终态,返回当前状态
            return run
        run.status = "cancelled"
        run.cancelled_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(run)
        self.append_event(
            run.id, type="run_cancelled", payload={"reason": reason or "用户手动取消"}
        )
        return run
