"""Run Worker。

消费 runs 队列,加载 run 并执行真实 workflow:
  -> 标记 run running
  -> 按 workflow_name 从 registry 取 workflow 并执行
  -> 生成 Markdown artifact
  -> 标记 run completed / failed

Step 2.1 审批异步化:
  -> execute_run 遇到 suspended 摘要时直接返回,释放 worker
     (run 保持 waiting_for_approval,checkpoint 已持久化);
  -> 审批决策后由 RunService.approve 入队 resume_run,
     从 checkpoint 续跑,不重复执行已完成节点。
"""

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.errors import classify_error
from app.db.session import SessionLocal
from app.models import Run, RunEvent
from app.services.eventing import append_event
from app.workflows import get_registry

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _append_event(
    db: Session,
    run_id: str,
    *,
    type: str,
    payload: dict | None = None,
) -> RunEvent:
    return append_event(db, run_id, type=type, payload=payload)


def _finish(db: Session, run: Run, summary: dict) -> None:
    """按 workflow 摘要收尾:写完成事件、回填 run 终态。"""
    _append_event(
        db,
        run.id,
        type="run_completed",
        payload={"artifact_id": summary["artifact_id"]},
    )
    run.status = "completed"
    run.completed_at = _now()
    run.output_summary = {
        "artifact_id": summary["artifact_id"],
        "steps": summary["steps"],
    }
    run.cost_summary = {
        "input_tokens": summary["input_tokens"],
        "output_tokens": summary["output_tokens"],
        "estimated_cost": summary["estimated_cost"],
    }
    db.commit()
    logger.info("Run %s completed", run.id)


def _fail(db: Session, run: Run, exc: Exception) -> None:
    logger.exception("Run %s failed: %s", run.id, exc)
    run = db.get(Run, run.id) or run
    run.status = "failed"
    run.failed_at = _now()
    run.error_message = str(exc)
    run.error_code = classify_error(exc)
    db.commit()
    _append_event(
        db,
        run.id,
        type="run_failed",
        payload={"error": str(exc), "error_code": run.error_code},
    )


def execute_run(run_id: str) -> None:
    """RQ job 入口:执行一个 run。"""
    db = SessionLocal()
    try:
        run = db.get(Run, run_id)
        if not run:
            logger.error("Run %s not found", run_id)
            return
        if run.status == "cancelled":
            logger.info("Run %s already cancelled, skip", run_id)
            return

        # 1. 标记 running
        run.status = "running"
        run.started_at = _now()
        db.commit()

        # 2. 按 run.workflow_name 从 registry 取 workflow 并执行
        try:
            workflow_cls = get_registry().get(run.workflow_name)
            workflow = workflow_cls()
            summary = workflow.execute(db, run_id)
            if summary.get("suspended"):
                # 审批挂起:checkpoint 已持久化,释放 worker 等待 resume
                logger.info("Run %s suspended at %r", run_id, summary.get("node"))
                return
            if summary.get("cancelled"):
                return
            _finish(db, run, summary)
        except Exception as exc:
            _fail(db, run, exc)

    finally:
        db.close()


def resume_run(run_id: str) -> None:
    """RQ job 入口:审批决策后从 checkpoint 恢复执行 run。"""
    db = SessionLocal()
    try:
        run = db.get(Run, run_id)
        if not run:
            logger.error("Run %s not found", run_id)
            return
        if run.status == "cancelled":
            logger.info("Run %s already cancelled, skip resume", run_id)
            return
        if run.status not in {"waiting_for_approval", "running"}:
            logger.info("Run %s in status %r, skip resume", run_id, run.status)
            return

        # 审批接口可能已把 run 置回 running;此处兜底保证状态一致
        if run.status == "waiting_for_approval":
            run.status = "running"
            db.commit()

        try:
            workflow_cls = get_registry().get(run.workflow_name)
            workflow = workflow_cls()
            summary = workflow.resume(db, run_id)
            if summary.get("suspended"):
                # 恢复途中再次挂起(如后续又一高风险工具)
                logger.info("Run %s suspended again at %r", run_id, summary.get("node"))
                return
            if summary.get("cancelled"):
                return
            _finish(db, run, summary)
        except Exception as exc:
            _fail(db, run, exc)

    finally:
        db.close()
