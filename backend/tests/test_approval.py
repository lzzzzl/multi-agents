"""Step 11 审批与重试测试(使用 fake session,不依赖数据库)。"""

from unittest.mock import MagicMock, patch

from app.core.errors import ConflictError
from app.models import Run, Task, ToolCall
from app.services.run_service import RunService
from app.tools.base import ToolError
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


def test_sensitive_tool_requires_approval_then_executes() -> None:
    run = Run(id="run_a", task_id="task_a", input_snapshot={}, status="running")
    db = _make_fake_db(run)
    runner = ToolRunner(db)
    tool = SendNotificationTool()

    with patch.object(runner, "_wait_for_approval", return_value="approved"):
        call = runner._run_with_approval(
            "run_a", tool, {"message": "hi"}, step_id=None, agent_id="agent_researcher"
        )

    # 审批期间 run 挂起;获批后恢复 running 并执行工具
    assert run.status == "running"
    assert call.status == "completed"
    assert call.tool_name == "send_notification"
    assert call.risk_level == "sensitive"
    assert call.output and call.output["sent"] is True


def test_sensitive_tool_rejected_raises() -> None:
    run = Run(id="run_b", task_id="task_b", input_snapshot={}, status="running")
    db = _make_fake_db(run)
    runner = ToolRunner(db)
    tool = SendNotificationTool()

    with patch.object(runner, "_wait_for_approval", return_value="rejected"):
        try:
            runner._run_with_approval(
                "run_b", tool, {"message": "hi"}, step_id=None, agent_id="agent_researcher"
            )
        except ToolError as exc:
            assert exc.code == "TOOL_REJECTED"
        else:
            raise AssertionError("应当抛 ToolError")

    call = db.get(ToolCall, "fake_toolcall")
    # 被拒的工具调用状态为 rejected,且不会真正执行
    added = [c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], ToolCall)]
    assert added and added[-1].status == "rejected"
    assert added[-1].error_message == "工具调用被人工拒绝"


def test_retry_creates_new_run_from_source() -> None:
    source = Run(
        id="run_c",
        task_id="task_c",
        workflow_name="sequential_report",
        input_snapshot={"x": 1},
        status="failed",
    )
    task = Task(id="task_c", title="t", description=None)
    db = MagicMock()
    db.get.side_effect = lambda model, id_: source if model is Run else (task if model is Task else None)
    db.scalar.return_value = None
    db.refresh.side_effect = lambda obj: None

    new_run = RunService(db).retry("run_c")

    assert new_run.status == "queued"
    assert new_run.source_run_id == "run_c"
    assert new_run.input_snapshot == {"x": 1}
    assert new_run.workflow_name == "sequential_report"


def test_retry_rejects_running_run() -> None:
    run = Run(id="run_d", task_id="task_d", input_snapshot={}, status="running")
    db = MagicMock()
    db.get.side_effect = lambda model, id_: run if model is Run else None

    import pytest

    with pytest.raises(ConflictError):
        RunService(db).retry("run_d")