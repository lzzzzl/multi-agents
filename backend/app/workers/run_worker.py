"""Run Worker。

消费 runs 队列,加载 run 并模拟执行:
  -> 标记 run running
  -> 依次创建 RunStep(Planner / Writer / Reviewer)并写事件
  -> 每个 step: started -> 写 agent_message -> completed
  -> 标记 run completed,生成 Markdown artifact

Phase 1 用模拟执行打通端到端链路;
Phase 2 将替换为真实 LLM Provider + Agent Runtime。
"""

import logging
import time
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import Run, RunEvent, RunStep, Task
from app.models.artifact import Artifact

logger = logging.getLogger(__name__)

# 模拟 workflow 的三个步骤。Phase 2 替换为真实 Agent。
SIMULATED_STEPS = [
    {
        "name": "Planner",
        "type": "agent",
        "agent_id": "agent_planner",
        "message": "已将任务拆解为 3 个执行步骤:资料收集、内容撰写、质量检查。",
        "output": {"steps": ["research", "write", "review"]},
    },
    {
        "name": "Writer",
        "type": "agent",
        "agent_id": "agent_writer",
        "message": "已根据计划生成报告草稿。",
        "output": {"draft": "# 报告草稿\n\n这是模拟生成的内容。"},
    },
    {
        "name": "Reviewer",
        "type": "agent",
        "agent_id": "agent_reviewer",
        "message": "质量检查通过,可以输出最终结果。",
        "output": {"quality": "pass"},
    },
]

# 每个 step 模拟耗时(秒),让 SSE 流能看到事件增量
STEP_DELAY_SECONDS = 1.0


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _append_event(
    db: Session,
    run_id: str,
    *,
    type: str,
    payload: dict | None = None,
    step_id: str | None = None,
    agent_id: str | None = None,
) -> RunEvent:
    from sqlalchemy import func, select

    current_max = db.scalar(select(func.max(RunEvent.sequence)).where(RunEvent.run_id == run_id))
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


def _check_cancelled(db: Session, run_id: str) -> bool:
    """API 取消 run 时会改状态。Worker 在 step 边界检查。"""
    run = db.get(Run, run_id)
    return run is not None and run.status == "cancelled"


def execute_run(run_id: str) -> None:
    """RQ job 入口:模拟执行一个 run。"""
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

        task = db.get(Task, run.task_id)
        task_title = task.title if task else "未命名任务"

        try:
            # 2. 依次执行模拟步骤
            for idx, step_def in enumerate(SIMULATED_STEPS):
                if _check_cancelled(db, run_id):
                    logger.info("Run %s cancelled at step %s", run_id, step_def["name"])
                    return

                step = RunStep(
                    run_id=run_id,
                    agent_id=step_def["agent_id"],
                    name=step_def["name"],
                    type=step_def["type"],
                    status="running",
                    sequence=idx + 1,
                    started_at=_now(),
                )
                db.add(step)
                db.commit()
                db.refresh(step)

                _append_event(
                    db,
                    run_id,
                    type="step_started",
                    step_id=step.id,
                    agent_id=step.agent_id,
                    payload={"name": step.name, "sequence": step.sequence},
                )
                _append_event(
                    db,
                    run_id,
                    type="agent_started",
                    step_id=step.id,
                    agent_id=step.agent_id,
                    payload={"agent": step.name},
                )

                # 模拟 LLM 思考耗时
                time.sleep(STEP_DELAY_SECONDS)

                if _check_cancelled(db, run_id):
                    step.status = "cancelled"
                    db.commit()
                    return

                # Agent 产出的消息事件
                _append_event(
                    db,
                    run_id,
                    type="agent_message",
                    step_id=step.id,
                    agent_id=step.agent_id,
                    payload={"content": step_def["message"]},
                )

                step.status = "completed"
                step.completed_at = _now()
                step.output = step_def["output"]
                db.commit()

                _append_event(
                    db,
                    run_id,
                    type="step_completed",
                    step_id=step.id,
                    agent_id=step.agent_id,
                    payload={"name": step.name},
                )

            # 3. 生成最终 artifact
            content = (
                f"# {task_title}\n\n"
                f"## 概述\n\n本报告由 multi-agent 工作台自动生成(模拟)。\n\n"
                f"## 执行步骤\n\n"
                + "\n".join(
                    f"{i+1}. **{s['name']}** — {s['message']}"
                    for i, s in enumerate(SIMULATED_STEPS)
                )
                + "\n"
            )
            artifact = Artifact(
                run_id=run_id,
                created_by_agent_id="agent_writer",
                type="markdown",
                name=f"{task_title}.md",
                mime_type="text/markdown",
                content=content,
                size_bytes=len(content.encode("utf-8")),
            )
            db.add(artifact)
            db.commit()
            db.refresh(artifact)

            _append_event(
                db,
                run_id,
                type="artifact_created",
                payload={"artifact_id": artifact.id, "name": artifact.name},
            )

            # 4. 标记完成
            run.status = "completed"
            run.completed_at = _now()
            run.output_summary = {"artifact_id": artifact.id, "steps": len(SIMULATED_STEPS)}
            run.cost_summary = {
                "input_tokens": 1200,
                "output_tokens": 800,
                "estimated_cost": 0.02,
            }
            db.commit()

            _append_event(
                db,
                run_id,
                type="run_completed",
                payload={"artifact_id": artifact.id},
            )
            logger.info("Run %s completed", run_id)

        except Exception as exc:
            logger.exception("Run %s failed: %s", run_id, exc)
            run.status = "failed"
            run.failed_at = _now()
            run.error_message = str(exc)
            db.commit()
            _append_event(
                db,
                run_id,
                type="run_failed",
                payload={"error": str(exc)},
            )

    finally:
        db.close()
