"""Step 2.1 异步审批测试(使用 fake session,不依赖数据库与队列)。

覆盖:
- 首次调用高风险工具:创建 waiting_for_approval 的 ToolCall 并抛 ApprovalRequired,
  run 置为 waiting_for_approval(worker 被释放,不再阻塞轮询)。
- resume 后已批准:复用同一条 ToolCall 执行,不重复创建。
- resume 后被拒绝:抛 ToolError(TOOL_REJECTED)。
- deduplicate 工具在等待审批期间重复调用:不得绕过审批直接返回。
- approve 决策后入队 resume job;取消挂起中的 run 会同步取消待审批 ToolCall。
"""

from unittest.mock import MagicMock, patch

import pytest

from app.core.errors import ConflictError
from app.models import Run, Task, ToolCall
from app.services.run_service import RunService
from app.tools.base import ApprovalRequired, ToolError
from app.tools.builtin import SendNotificationTool
from app.tools.runner import ToolRunner


def _make_fake_db(run: Run) -> MagicMock:
    db = MagicMock()
    db.get.side_effect = lambda model, id_: run if model is Run else None
    db.scalar.return_value = None

    def _fake_refresh(obj) -> None:
        pk = type(obj).__table__.primary_key.columns[0].key
        if getattr(obj, pk, None) is None:
            setattr(obj, pk, f"fake_{type(obj).__name__.lower()}")

    db.refresh.side_effect = _fake_refresh
    return db


def _added_tool_calls(db: MagicMock) -> list[ToolCall]:
    return [c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], ToolCall)]


def _scalar_returns(existing: ToolCall | None):
    """fake db 的 scalar 分流:tool_calls 查询返回 existing,其余(如 max sequence)返回 None。"""

    def _scalar(stmt):
        if existing is not None and "tool_calls" in str(stmt):
            return existing
        return None

    return _scalar


def test_sensitive_tool_suspends_with_approval_required() -> None:
    """首次调用高风险工具应抛 ApprovalRequired 并挂起 run,而不是阻塞等待。"""
    run = Run(id="run_a", task_id="task_a", input_snapshot={}, status="running")
    db = _make_fake_db(run)
    runner = ToolRunner(db)

    with pytest.raises(ApprovalRequired) as exc_info:
        runner.run(
            run_id="run_a",
            tool_name="send_notification",
            args={"message": "hi"},
            agent_id="agent_researcher",
        )

    # run 挂起为 waiting_for_approval,ToolCall 同样等待审批
    assert run.status == "waiting_for_approval"
    calls = _added_tool_calls(db)
    assert len(calls) == 1
    assert calls[0].status == "waiting_for_approval"
    assert calls[0].tool_name == "send_notification"
    assert exc_info.value.tool_call_id == calls[0].id


def test_sensitive_tool_suspends_again_while_still_waiting() -> None:
    """resume 时审批仍未决:幂等地再次抛 ApprovalRequired。"""
    run = Run(id="run_a2", task_id="task_a", input_snapshot={}, status="waiting_for_approval")
    db = _make_fake_db(run)
    existing = ToolCall(
        id="tc_wait",
        run_id="run_a2",
        tool_name="send_notification",
        status="waiting_for_approval",
    )
    db.scalar.return_value = existing
    runner = ToolRunner(db)

    with pytest.raises(ApprovalRequired):
        runner.run(
            run_id="run_a2",
            tool_name="send_notification",
            args={"message": "hi"},
            agent_id="agent_researcher",
        )
    # 未创建新的 ToolCall
    assert _added_tool_calls(db) == []


def test_approved_tool_executes_once_on_resume() -> None:
    """获批后 resume:复用同一条 ToolCall 执行,副作用只发生一次。"""
    run = Run(id="run_b", task_id="task_b", input_snapshot={}, status="running")
    db = _make_fake_db(run)
    runner = ToolRunner(db)

    # 第一次:挂起
    with pytest.raises(ApprovalRequired):
        runner.run(
            run_id="run_b",
            tool_name="send_notification",
            args={"message": "hi"},
            agent_id="agent_researcher",
        )
    first = _added_tool_calls(db)[0]

    # 模拟审批通过
    first.status = "approved"
    db.scalar.side_effect = _scalar_returns(first)

    # resume:再次以相同参数调用,应复用记录并执行
    call = runner.run(
        run_id="run_b",
        tool_name="send_notification",
        args={"message": "hi"},
        agent_id="agent_researcher",
    )

    assert run.status == "running"
    assert call.status == "completed"
    assert call.id == first.id  # 同一条记录,未重复创建
    assert call.output and call.output["sent"] is True
    assert len(_added_tool_calls(db)) == 1


def test_rejected_tool_raises_on_resume() -> None:
    """被拒后 resume:抛 ToolError(TOOL_REJECTED),由 workflow 决定后续。"""
    run = Run(id="run_c", task_id="task_c", input_snapshot={}, status="waiting_for_approval")
    db = _make_fake_db(run)
    rejected = ToolCall(
        id="tc_rej",
        run_id="run_c",
        tool_name="send_notification",
        status="rejected",
    )
    db.scalar.return_value = rejected
    runner = ToolRunner(db)

    with pytest.raises(ToolError) as exc_info:
        runner.run(
            run_id="run_c",
            tool_name="send_notification",
            args={"message": "hi"},
            agent_id="agent_researcher",
        )
    assert exc_info.value.code == "TOOL_REJECTED"
    # 不创建新的审批请求
    assert _added_tool_calls(db) == []


def test_waiting_call_not_returned_via_dedup_bypass() -> None:
    """send_notification(deduplicate=True)等待审批期间重复调用不得绕过审批。"""
    run = Run(id="run_d", task_id="task_d", input_snapshot={}, status="waiting_for_approval")
    db = _make_fake_db(run)
    waiting = ToolCall(
        id="tc_wait2",
        run_id="run_d",
        tool_name="send_notification",
        status="waiting_for_approval",
    )
    db.scalar.return_value = waiting
    runner = ToolRunner(db)
    tool = SendNotificationTool()
    assert tool.deduplicate is True

    # 高风险工具必须走审批路径:仍处于等待时再次挂起,而不是直接返回 waiting 记录
    with pytest.raises(ApprovalRequired):
        runner.run(
            run_id="run_d",
            tool_name="send_notification",
            args={"message": "hi"},
            agent_id="agent_researcher",
        )


def _make_approve_db(run: Run, call: ToolCall) -> MagicMock:
    db = MagicMock()
    db.get.side_effect = lambda model, id_: run if model is Run else None
    db.scalar.side_effect = _scalar_returns(call)
    db.refresh.side_effect = lambda obj: None
    return db


@patch("app.workers.queue.get_queue")
def test_approve_enqueues_resume_job(mock_get_queue) -> None:
    """审批决策后应把 resume_run 重新入队,让 worker 从 checkpoint 续跑。"""
    run = Run(id="run_e", task_id="task_e", input_snapshot={}, status="waiting_for_approval")
    call = ToolCall(
        id="tc_e",
        run_id="run_e",
        tool_name="send_notification",
        status="waiting_for_approval",
    )
    db = _make_approve_db(run, call)

    RunService(db).approve("run_e", decision="approve")

    assert call.status == "approved"
    assert run.status == "running"
    mock_get_queue.return_value.enqueue.assert_called_once()
    enqueued_func = mock_get_queue.return_value.enqueue.call_args.args[0]
    assert enqueued_func.__name__ == "resume_run"


@patch("app.workers.queue.get_queue")
def test_reject_also_enqueues_resume_job(mock_get_queue) -> None:
    """拒绝同样入队 resume:由 workflow 捕获 ToolError 后继续后续节点。"""
    run = Run(id="run_f", task_id="task_f", input_snapshot={}, status="waiting_for_approval")
    call = ToolCall(
        id="tc_f",
        run_id="run_f",
        tool_name="send_notification",
        status="waiting_for_approval",
    )
    db = _make_approve_db(run, call)

    RunService(db).approve("run_f", decision="reject")

    assert call.status == "rejected"
    assert run.status == "running"
    assert mock_get_queue.return_value.enqueue.called


def test_cancel_while_waiting_cancels_pending_tool_call() -> None:
    """取消挂起中的 run 时,待审批的 ToolCall 一并取消并留痕。"""
    run = Run(id="run_g", task_id="task_g", input_snapshot={}, status="waiting_for_approval")
    call = ToolCall(
        id="tc_g",
        run_id="run_g",
        tool_name="send_notification",
        status="waiting_for_approval",
    )
    db = MagicMock()
    db.get.side_effect = lambda model, id_: run if model is Run else None
    db.scalars.return_value = iter([call])
    db.refresh.side_effect = lambda obj: None

    RunService(db).cancel("run_g")

    assert run.status == "cancelled"
    assert call.status == "cancelled"
    assert call.completed_at is not None


def test_retry_creates_new_run_from_source() -> None:
    source = Run(
        id="run_h",
        task_id="task_h",
        workflow_name="sequential_report",
        input_snapshot={"x": 1},
        status="failed",
    )
    task = Task(id="task_h", title="t", description=None)
    db = MagicMock()
    db.get.side_effect = lambda model, id_: source if model is Run else (task if model is Task else None)
    db.scalar.return_value = None
    db.refresh.side_effect = lambda obj: None

    new_run = RunService(db).retry("run_h")

    assert new_run.status == "queued"
    assert new_run.source_run_id == "run_h"
    assert new_run.input_snapshot == {"x": 1}
    assert new_run.workflow_name == "sequential_report"


def test_retry_rejects_running_run() -> None:
    run = Run(id="run_i", task_id="task_i", input_snapshot={}, status="running")
    db = MagicMock()
    db.get.side_effect = lambda model, id_: run if model is Run else None

    with pytest.raises(ConflictError):
        RunService(db).retry("run_i")
