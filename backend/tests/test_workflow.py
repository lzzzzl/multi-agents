"""SequentialWorkflow 重写循环测试(使用 Mock LLM 与 fake session,不依赖数据库)。"""

from unittest.mock import MagicMock, patch

from app.llms.mock import MockLLMProvider
from app.models import Run, Task
from app.workflows import SequentialWorkflow


def _make_fake_db(run: Run, task: Task) -> MagicMock:
    db = MagicMock()
    db.get.side_effect = lambda model, id_: run if model is Run else (task if model is Task else None)
    db.scalar.return_value = None  # 事件 sequence 基线

    def _fake_refresh(obj) -> None:
        # 模拟 flush 后主键由 default 生成
        pk = type(obj).__table__.primary_key.columns[0].key
        if getattr(obj, pk, None) is None:
            setattr(obj, pk, f"fake_{type(obj).__name__.lower()}")

    db.refresh.side_effect = _fake_refresh
    return db


@patch("app.agents.base.get_llm_provider", return_value=MockLLMProvider(latency_ms=0))
def test_rewrite_loop_passes(_mock) -> None:
    run = Run(id="run_x", task_id="task_x", input_snapshot={})
    task = Task(id="task_x", title="测试任务", description=None)
    db = _make_fake_db(run, task)

    summary = SequentialWorkflow(max_rewrites=2).execute(db, "run_x")

    # Planner + 首次(Writer,Reviewer) + 重写(Writer,Reviewer) = 5 步
    assert summary["steps"] == 5
    assert summary["rewrites"] == 1
    assert summary["quality"] == "pass"
    assert summary["artifact_id"]


@patch("app.agents.base.get_llm_provider", return_value=MockLLMProvider(latency_ms=0))
def test_no_rewrite_allowed_stops_on_revision(_mock) -> None:
    run = Run(id="run_y", task_id="task_y", input_snapshot={})
    task = Task(id="task_y", title="测试任务", description=None)
    db = _make_fake_db(run, task)

    summary = SequentialWorkflow(max_rewrites=0).execute(db, "run_y")

    # 首次评审即 revision,且不允许重写 -> 仅 Planner + Writer + Reviewer = 3 步
    assert summary["steps"] == 3
    assert summary["rewrites"] == 0
    assert summary["quality"] == "revision"
    assert summary["artifact_id"]