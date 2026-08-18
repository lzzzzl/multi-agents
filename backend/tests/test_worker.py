"""Worker 测试:execute_run / resume_run 的完成、取消、挂起、失败路径。
通过 patch SessionLocal 与 get_registry,不依赖真实 DB 与队列。"""

from unittest.mock import MagicMock, patch

from app.models import Run, RunEvent
from app.workers.run_worker import execute_run, resume_run


def _make_db(run: Run) -> MagicMock:
    db = MagicMock()
    db.get.side_effect = lambda model, id_: run if model is Run else None
    db.scalar.return_value = None  # 事件 sequence 基线

    def _refresh(obj) -> None:
        pk = type(obj).__table__.primary_key.columns[0].key
        if getattr(obj, pk, None) is None:
            setattr(obj, pk, f"fake_{type(obj).__name__.lower()}")

    db.refresh.side_effect = _refresh
    return db


def _event_types(db: MagicMock) -> list[str]:
    return [
        c.args[0].type
        for c in db.add.call_args_list
        if isinstance(c.args[0], RunEvent)
    ]


def _make_workflow_cls(
    summary: dict | None = None,
    exc: Exception | None = None,
    *,
    resume_summary: dict | None = None,
) -> MagicMock:
    """构造一个假的 workflow 类,实例化后 execute/resume 返回 summary 或抛 exc。"""
    workflow_cls = MagicMock()
    instance = workflow_cls.return_value
    if exc is not None:
        instance.execute.side_effect = exc
        instance.resume.side_effect = exc
    else:
        instance.execute.return_value = summary
        instance.resume.return_value = resume_summary if resume_summary is not None else summary
    return workflow_cls


def _patch_registry(mock_get_registry: MagicMock, workflow_cls: MagicMock) -> None:
    registry = MagicMock()
    registry.get.return_value = workflow_cls
    mock_get_registry.return_value = registry


@patch("app.workers.run_worker.SessionLocal")
@patch("app.workers.run_worker.get_registry")
def test_execute_run_completed(mock_get_registry, mock_sl) -> None:
    run = Run(id="run_a", task_id="task_a", status="queued")
    db = _make_db(run)
    mock_sl.return_value = db
    _patch_registry(
        mock_get_registry,
        _make_workflow_cls(
            summary={
                "artifact_id": "artifact_x",
                "steps": 4,
                "input_tokens": 10,
                "output_tokens": 20,
                "estimated_cost": 0.0001,
            }
        ),
    )

    execute_run("run_a")

    assert run.status == "completed"
    assert run.completed_at is not None
    assert run.output_summary["artifact_id"] == "artifact_x"
    assert run.cost_summary["input_tokens"] == 10
    assert "run_completed" in _event_types(db)
    db.close.assert_called_once()


@patch("app.workers.run_worker.SessionLocal")
@patch("app.workers.run_worker.get_registry")
def test_execute_run_cancelled(mock_get_registry, mock_sl) -> None:
    run = Run(id="run_b", task_id="task_b", status="running")
    db = _make_db(run)
    mock_sl.return_value = db
    _patch_registry(mock_get_registry, _make_workflow_cls(summary={"cancelled": True}))

    execute_run("run_b")

    # 取消时提前返回,run 不置为 completed,也不写 run_completed
    assert run.status == "running"
    assert "run_completed" not in _event_types(db)


@patch("app.workers.run_worker.SessionLocal")
@patch("app.workers.run_worker.get_registry")
def test_execute_run_failed(mock_get_registry, mock_sl) -> None:
    run = Run(id="run_c", task_id="task_c", status="running")
    db = _make_db(run)
    mock_sl.return_value = db
    _patch_registry(mock_get_registry, _make_workflow_cls(exc=RuntimeError("boom")))

    execute_run("run_c")

    assert run.status == "failed"
    assert run.failed_at is not None
    assert run.error_message == "boom"
    assert run.error_code == "UNKNOWN"
    assert "run_failed" in _event_types(db)


def test_execute_run_missing_skips() -> None:
    db = MagicMock()
    db.get.return_value = None
    with patch("app.workers.run_worker.SessionLocal", return_value=db):
        execute_run("run_missing")
    # 未找到 run 时直接返回,不写任何事件
    assert db.add.call_count == 0


@patch("app.workers.run_worker.SessionLocal")
@patch("app.workers.run_worker.get_registry")
def test_execute_run_suspended_releases_worker(mock_get_registry, mock_sl) -> None:
    """Step 2.1:workflow 挂起时 worker 直接返回,不置 completed/failed。"""
    run = Run(id="run_s", task_id="task_s", status="queued")
    db = _make_db(run)
    mock_sl.return_value = db
    _patch_registry(
        mock_get_registry,
        _make_workflow_cls(summary={"suspended": True, "node": "execute_tool"}),
    )

    execute_run("run_s")

    # worker 不改终态(生产中 run 已由 ToolRunner 置为 waiting_for_approval)
    assert run.status != "completed"
    assert run.status != "failed"
    assert run.completed_at is None
    assert "run_completed" not in _event_types(db)
    assert "run_failed" not in _event_types(db)
    db.close.assert_called_once()


@patch("app.workers.run_worker.SessionLocal")
@patch("app.workers.run_worker.get_registry")
def test_resume_run_completes(mock_get_registry, mock_sl) -> None:
    """审批后 resume:workflow.resume 返回摘要,worker 正常收尾为 completed。"""
    run = Run(id="run_r", task_id="task_r", status="running", started_at=_now_stub())
    db = _make_db(run)
    mock_sl.return_value = db
    workflow_cls = _make_workflow_cls(
        summary=None,
        resume_summary={
            "artifact_id": "artifact_r",
            "steps": 4,
            "input_tokens": 10,
            "output_tokens": 20,
            "estimated_cost": 0.0001,
        },
    )
    _patch_registry(mock_get_registry, workflow_cls)

    resume_run("run_r")

    workflow_cls.return_value.resume.assert_called_once()
    assert run.status == "completed"
    assert run.output_summary["artifact_id"] == "artifact_r"
    assert "run_completed" in _event_types(db)


def _now_stub():
    from datetime import datetime, timezone

    return datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc)


@patch("app.workers.run_worker.SessionLocal")
@patch("app.workers.run_worker.get_registry")
def test_resume_run_suspended_again(mock_get_registry, mock_sl) -> None:
    """resume 途中再次挂起(又一高风险工具):worker 释放,不写终态。"""
    run = Run(id="run_s2", task_id="task_s2", status="running")
    db = _make_db(run)
    mock_sl.return_value = db
    _patch_registry(
        mock_get_registry,
        _make_workflow_cls(summary=None, resume_summary={"suspended": True, "node": "execute_tool"}),
    )

    resume_run("run_s2")

    assert run.status != "completed"
    assert "run_completed" not in _event_types(db)


@patch("app.workers.run_worker.SessionLocal")
@patch("app.workers.run_worker.get_registry")
def test_resume_run_skips_terminal_run(mock_get_registry, mock_sl) -> None:
    """已终态(如取消)的 run 不再恢复执行。"""
    run = Run(id="run_c2", task_id="task_c2", status="cancelled")
    db = _make_db(run)
    mock_sl.return_value = db
    workflow_cls = _make_workflow_cls(summary={"artifact_id": "x", "steps": 1})
    _patch_registry(mock_get_registry, workflow_cls)

    resume_run("run_c2")

    workflow_cls.return_value.resume.assert_not_called()
    assert run.status == "cancelled"


@patch("app.workers.run_worker.SessionLocal")
@patch("app.workers.run_worker.get_registry")
def test_resume_run_failed(mock_get_registry, mock_sl) -> None:
    """resume 抛异常:run 置 failed 并写 run_failed 事件。"""
    run = Run(id="run_f2", task_id="task_f2", status="running")
    db = _make_db(run)
    mock_sl.return_value = db
    _patch_registry(mock_get_registry, _make_workflow_cls(exc=RuntimeError("resume boom")))

    resume_run("run_f2")

    assert run.status == "failed"
    assert run.error_message == "resume boom"
    assert "run_failed" in _event_types(db)
