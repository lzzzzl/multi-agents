"""Run Worker。

消费 runs 队列,加载 run 并执行真实 workflow:
  -> 标记 run running
  -> SequentialWorkflow 编排 Planner -> Writer -> Reviewer,写事件与步骤
  -> 生成 Markdown artifact
  -> 标记 run completed / failed
"""

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.errors import classify_error
from app.db.session import SessionLocal
from app.models import Run, RunEvent
from app.services.eventing import append_event
from app.workflows import SequentialWorkflow

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

        # 2. 执行真实 workflow
        workflow = SequentialWorkflow()
        try:
            summary = workflow.execute(db, run_id)
            if summary.get("cancelled"):
                return

            _append_event(
                db,
                run_id,
                type="run_completed",
                payload={"artifact_id": summary["artifact_id"]},
            )

            # 3. 标记完成
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
            logger.info("Run %s completed", run_id)

        except Exception as exc:
            logger.exception("Run %s failed: %s", run_id, exc)
            run = db.get(Run, run_id) or run
            run.status = "failed"
            run.failed_at = _now()
            run.error_message = str(exc)
            run.error_code = classify_error(exc)
            db.commit()
            _append_event(
                db,
                run_id,
                type="run_failed",
                payload={"error": str(exc), "error_code": run.error_code},
            )

    finally:
        db.close()
