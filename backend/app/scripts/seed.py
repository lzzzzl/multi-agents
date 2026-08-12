"""演示种子数据。

用法(在 backend/ 下):
    python -m app.scripts.seed                 # 幂等插入,已存在则跳过
    python -m app.scripts.seed --force         # 先删除本脚本创建的行再重建
    python -m app.scripts.seed --clear         # 仅删除本脚本创建的行

通过固定 ID(`seed_*` 前缀)保证幂等,不污染真实用户数据。
"""

import argparse
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import Artifact, Run, RunEvent, RunStep, Task, ToolCall

# 固定 ID 前缀,便于识别与清理
TASK_IDS = {
    "completed": "seed_task_completed",
    "approval": "seed_task_approval",
    "failed": "seed_task_failed",
    "cancelled": "seed_task_cancelled",
    "draft": "seed_task_draft",
}
RUN_IDS = {
    "completed": "seed_run_completed",
    "approval": "seed_run_approval",
    "failed": "seed_run_failed",
    "cancelled": "seed_run_cancelled",
}

now = datetime.now(timezone.utc)


def _ago(**kw: float) -> datetime:
    return now - timedelta(**kw)


def _task(task_id: str, title: str, description: str, status: str, priority: str = "medium") -> Task:
    return Task(
        id=task_id,
        title=title,
        description=description,
        status=status,
        priority=priority,
        input={"topic": title},
    )


def _run(run_id: str, task_id: str, status: str, **kw) -> Run:
    topic = kw.pop("topic", "")
    return Run(
        id=run_id,
        task_id=task_id,
        status=status,
        workflow_name="sequential_report",
        workflow_version="1.0.0",
        input_snapshot={"topic": topic},
        **kw,
    )


def _events(db: Session, run_id: str, types: list[tuple[str, dict | None]]) -> None:
    """按给定顺序写入事件,sequence 自动递增。"""
    for i, (etype, payload) in enumerate(types, start=1):
        db.add(RunEvent(run_id=run_id, type=etype, sequence=i, payload=payload))


def seed_completed(db: Session) -> Task:
    """已完成任务:含完整步骤、事件、工具调用与两种 artifact。"""
    task = _task(
        TASK_IDS["completed"],
        "AI 智能体协作框架调研报告",
        "调研主流多智能体协作框架的架构与适用场景。",
        "completed",
    )
    run = _run(
        RUN_IDS["completed"],
        task.id,
        "completed",
        topic="AI 智能体协作框架",
        started_at=_ago(hours=2),
        completed_at=_ago(hours=1.7),
        output_summary={
            "artifact_id": f"seed_artifact_{task.id}",
            "steps": 4,
            "input_tokens": 3200,
            "output_tokens": 1800,
            "estimated_cost": 0.012,
        },
        cost_summary={"input_tokens": 3200, "output_tokens": 1800, "estimated_cost": 0.012},
    )
    db.add_all([task, run])

    steps = [
        RunStep(run_id=run.id, agent_id="agent_planner", name="制定计划", type="agent", status="completed", sequence=1,
                started_at=_ago(hours=2), completed_at=_ago(hours=1.95), output={"plan": "调研并撰写报告"}),
        RunStep(run_id=run.id, agent_id="agent_researcher", name="研究分析", type="agent", status="completed", sequence=2,
                started_at=_ago(hours=1.95), completed_at=_ago(hours=1.85), output={"findings": "AutoGen / CrewAI / LangGraph"}),
        RunStep(run_id=run.id, agent_id="agent_researcher", name="生成初稿工具", type="tool", status="completed", sequence=3,
                started_at=_ago(hours=1.85), completed_at=_ago(hours=1.8), output={"draft": "报告初稿"}),
        RunStep(run_id=run.id, agent_id="agent_writer", name="撰写正文", type="agent", status="completed", sequence=4,
                started_at=_ago(hours=1.8), completed_at=_ago(hours=1.75), output={"content": "正文完成"}),
        RunStep(run_id=run.id, agent_id="agent_reviewer", name="质量审查", type="agent", status="completed", sequence=5,
                started_at=_ago(hours=1.75), completed_at=_ago(hours=1.7), output={"passed": True, "score": 0.9}),
    ]
    db.add_all(steps)

    _events(db, run.id, [
        ("run_started", {"message": "运行开始"}),
        ("agent_started", {"agent_id": "agent_planner", "name": "制定计划"}),
        ("agent_completed", {"agent_id": "agent_planner", "name": "制定计划"}),
        ("agent_started", {"agent_id": "agent_researcher", "name": "研究分析"}),
        ("tool_call_started", {"tool_call_id": "seed_toolcall_completed_time", "tool_name": "current_time"}),
        ("tool_call_completed", {"tool_call_id": "seed_toolcall_completed_time", "tool_name": "current_time"}),
        ("tool_call_started", {"tool_call_id": "seed_toolcall_completed_report", "tool_name": "generate_report"}),
        ("tool_call_completed", {"tool_call_id": "seed_toolcall_completed_report", "tool_name": "generate_report"}),
        ("agent_completed", {"agent_id": "agent_researcher", "name": "研究分析"}),
        ("agent_started", {"agent_id": "agent_writer", "name": "撰写正文"}),
        ("agent_completed", {"agent_id": "agent_writer", "name": "撰写正文"}),
        ("artifact_created", {"artifact_id": f"seed_artifact_{task.id}", "name": f"{task.title}.md"}),
        ("agent_started", {"agent_id": "agent_reviewer", "name": "质量审查"}),
        ("agent_completed", {"agent_id": "agent_reviewer", "name": "质量审查"}),
        ("run_completed", {"message": "运行完成"}),
    ])

    db.add_all([
        ToolCall(id="seed_toolcall_completed_time", run_id=run.id, tool_name="current_time", risk_level="safe",
                 status="completed", input={}, output={"iso": _ago(hours=1.9).isoformat()},
                 started_at=_ago(hours=1.9), completed_at=_ago(hours=1.9), duration_ms=120),
        ToolCall(id="seed_toolcall_completed_report", run_id=run.id, tool_name="generate_report", risk_level="safe",
                 status="completed",
                 input={"title": task.title, "outline": ["架构", "对比", "选型"]},
                 output={"title": task.title, "sections": 3, "_display": f"# {task.title}\n\n## 架构\n...\n"},
                 started_at=_ago(hours=1.85), completed_at=_ago(hours=1.8), duration_ms=3000),
    ])

    md_content = (
        f"# {task.title}\n\n"
        "## 摘要\n\n"
        "本报告调研了 AutoGen、CrewAI、LangGraph 三类多智能体协作框架。\n\n"
        "## 架构对比\n\n"
        "- **AutoGen**: 对话式编排,适合多角色对话。\n"
        "- **CrewAI**: 角色 + 任务驱动,配置友好。\n"
        "- **LangGraph**: 状态图表达工作流,可控性强。\n\n"
        "## 选型建议\n\n"
        "根据团队技术栈与可控性需求,推荐 LangGraph 作为首选。\n"
    )
    db.add_all([
        Artifact(id=f"seed_artifact_{task.id}", run_id=run.id, type="markdown", name=f"{task.title}.md",
                 mime_type="text/markdown", content=md_content, size_bytes=len(md_content.encode("utf-8")),
                 created_by_agent_id="agent_writer"),
        Artifact(id=f"seed_artifact_summary_{task.id}", run_id=run.id, type="json", name="execution-summary.json",
                 mime_type="application/json",
                 content='{"plan":"调研并撰写报告","quality_score":0.9,"rewrites":0,"cost_usd":0.012}',
                 size_bytes=76, created_by_agent_id="agent_reviewer"),
    ])
    return task


def seed_approval(db: Session) -> Task:
    """等待审批任务:含一个待审批的敏感工具调用,用于演示审批面板。"""
    task = _task(
        TASK_IDS["approval"],
        "客户关怀邮件批量发送",
        "向 50 位客户发送个性化关怀邮件(需审批)。",
        "running",
    )
    run = _run(
        RUN_IDS["approval"],
        task.id,
        "waiting_for_approval",
        topic="客户关怀邮件",
        started_at=_ago(minutes=20),
    )
    db.add_all([task, run])

    db.add_all([
        RunStep(run_id=run.id, agent_id="agent_planner", name="制定计划", type="agent", status="completed", sequence=1,
                started_at=_ago(minutes=20), completed_at=_ago(minutes=15)),
        RunStep(run_id=run.id, agent_id="agent_researcher", name="研究分析", type="agent", status="completed", sequence=2,
                started_at=_ago(minutes=15), completed_at=_ago(minutes=10)),
        RunStep(run_id=run.id, agent_id="agent_researcher", name="发送通知", type="approval", status="waiting_for_approval", sequence=3,
                started_at=_ago(minutes=10)),
    ])

    _events(db, run.id, [
        ("run_started", {"message": "运行开始"}),
        ("agent_started", {"agent_id": "agent_planner", "name": "制定计划"}),
        ("agent_completed", {"agent_id": "agent_planner", "name": "制定计划"}),
        ("agent_started", {"agent_id": "agent_researcher", "name": "研究分析"}),
        ("agent_completed", {"agent_id": "agent_researcher", "name": "研究分析"}),
        ("tool_call_waiting_for_approval", {"tool_call_id": "seed_toolcall_waiting", "tool_name": "send_notification"}),
        ("run_waiting_for_approval", {"message": "等待人工审批"}),
    ])

    db.add(ToolCall(
        id="seed_toolcall_waiting", run_id=run.id, tool_name="send_notification", risk_level="sensitive",
        status="waiting_for_approval", input={"message": "感谢您的支持!", "channel": "email", "recipients": 50},
        started_at=_ago(minutes=10),
    ))
    return task


def seed_failed(db: Session) -> Task:
    """失败任务:用于演示重试。"""
    task = _task(
        TASK_IDS["failed"],
        "竞品价格分析",
        "分析竞品定价并生成对比表(执行失败)。",
        "failed",
    )
    run = _run(
        RUN_IDS["failed"],
        task.id,
        "failed",
        topic="竞品价格分析",
        started_at=_ago(hours=5),
        failed_at=_ago(hours=4.8),
        error_message="Writer 生成正文时模型返回超时:LLM provider timeout",
    )
    db.add_all([task, run])

    db.add_all([
        RunStep(run_id=run.id, agent_id="agent_planner", name="制定计划", type="agent", status="completed", sequence=1,
                started_at=_ago(hours=5), completed_at=_ago(hours=4.95)),
        RunStep(run_id=run.id, agent_id="agent_researcher", name="研究分析", type="agent", status="completed", sequence=2,
                started_at=_ago(hours=4.95), completed_at=_ago(hours=4.85)),
        RunStep(run_id=run.id, agent_id="agent_writer", name="撰写正文", type="agent", status="failed", sequence=3,
                started_at=_ago(hours=4.85), failed_at=_ago(hours=4.8),
                error_message="LLM provider timeout"),
    ])

    _events(db, run.id, [
        ("run_started", {"message": "运行开始"}),
        ("agent_started", {"agent_id": "agent_planner", "name": "制定计划"}),
        ("agent_completed", {"agent_id": "agent_planner", "name": "制定计划"}),
        ("agent_started", {"agent_id": "agent_researcher", "name": "研究分析"}),
        ("agent_completed", {"agent_id": "agent_researcher", "name": "研究分析"}),
        ("agent_started", {"agent_id": "agent_writer", "name": "撰写正文"}),
        ("agent_failed", {"agent_id": "agent_writer", "name": "撰写正文", "error": "LLM provider timeout"}),
        ("run_failed", {"message": "运行失败", "error": "LLM provider timeout"}),
    ])
    return task


def seed_cancelled(db: Session) -> Task:
    """已取消任务:用于演示取消后重试。"""
    task = _task(
        TASK_IDS["cancelled"],
        "行业趋势周报",
        "生成本周行业趋势摘要(已被用户取消)。",
        "cancelled",
    )
    run = _run(
        RUN_IDS["cancelled"],
        task.id,
        "cancelled",
        topic="行业趋势周报",
        started_at=_ago(hours=1),
        cancelled_at=_ago(minutes=40),
    )
    db.add_all([task, run])

    db.add_all([
        RunStep(run_id=run.id, agent_id="agent_planner", name="制定计划", type="agent", status="completed", sequence=1,
                started_at=_ago(hours=1), completed_at=_ago(minutes=55)),
        RunStep(run_id=run.id, agent_id="agent_researcher", name="研究分析", type="agent", status="cancelled", sequence=2,
                started_at=_ago(minutes=55), completed_at=_ago(minutes=40)),
    ])

    _events(db, run.id, [
        ("run_started", {"message": "运行开始"}),
        ("agent_started", {"agent_id": "agent_planner", "name": "制定计划"}),
        ("agent_completed", {"agent_id": "agent_planner", "name": "制定计划"}),
        ("agent_started", {"agent_id": "agent_researcher", "name": "研究分析"}),
        ("run_cancelled", {"message": "用户主动取消"}),
    ])
    return task


def seed_draft(db: Session) -> Task:
    """草稿任务:无 run,供用户发起首次运行。"""
    task = _task(
        TASK_IDS["draft"],
        "新技术选型评估:向量数据库",
        "评估 Milvus / Qdrant / pgvector 的适用场景并给出建议。",
        "draft",
        priority="high",
    )
    db.add(task)
    return task


def run_seed(db: Session, *, force: bool = False, clear: bool = False) -> int:
    # 删除 Task 即可利用 FK ON DELETE CASCADE 级联清理其下的 Run / 事件 / 步骤 / 工具调用 / artifact
    if clear or force:
        db.query(Task).filter(Task.id.in_(list(TASK_IDS.values()))).delete(synchronize_session=False)
        db.commit()
        if clear:
            print("已清理 seed 数据。")
            return 0

    existing = set(db.scalars(select(Task.id).where(Task.id.in_(list(TASK_IDS.values())))))
    if existing:
        print("seed 数据已存在,跳过(使用 --force 重建或 --clear 清理)。")
        return 0

    seed_completed(db)
    seed_approval(db)
    seed_failed(db)
    seed_cancelled(db)
    seed_draft(db)
    db.commit()
    print("seed 完成:completed / approval / failed / cancelled / draft 各 1 条。")
    return 1


def main() -> None:
    parser = argparse.ArgumentParser(description="演示种子数据")
    parser.add_argument("--force", action="store_true", help="先清理再重建")
    parser.add_argument("--clear", action="store_true", help="仅清理 seed 数据")
    args = parser.parse_args()

    db: Session = SessionLocal()
    try:
        run_seed(db, force=args.force, clear=args.clear)
    finally:
        db.close()


if __name__ == "__main__":
    main()