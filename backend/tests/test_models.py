"""数据模型测试:ID 生成与默认值。不依赖数据库连接。"""

from app.db.ids import generate_id
from app.models import Artifact, Run, RunEvent, RunStep, Task, ToolCall


def test_generate_id_prefixed() -> None:
    assert generate_id("run").startswith("run_")
    assert generate_id("task").startswith("task_")
    # 长度: 前缀 + 下划线 + 24 位 hex
    assert len(generate_id("run")) == 4 + 24


def test_run_defaults() -> None:
    run = Run(task_id="task_x")
    # id 与 status 等 default 由 SQLAlchemy 在 flush 时应用,实例化时为 None
    assert run.id is None
    assert run.status is None
    # 但 schema 声明的默认值必须存在
    cols = Run.__table__.c
    assert cols.status.default.arg == "queued"
    assert cols.workflow_name.default.arg == "sequential_report"
    assert callable(cols.id.default.arg)


def test_task_defaults() -> None:
    task = Task(title="调研 AI 趋势")
    assert task.id is None
    cols = Task.__table__.c
    assert cols.status.default.arg == "draft"
    assert callable(cols.id.default.arg)


def test_tool_call_defaults() -> None:
    tc = ToolCall(run_id="run_x", tool_name="current_time")
    assert tc.id is None
    assert tc.started_at is None
    cols = ToolCall.__table__.c
    assert cols.status.default.arg == "pending"
    assert cols.risk_level.default.arg == "safe"
    assert callable(cols.id.default.arg)


def test_run_event_sequence() -> None:
    ev = RunEvent(run_id="run_x", type="run_started", sequence=1)
    assert ev.sequence == 1
    assert ev.agent_id is None


def test_artifact_defaults_mime() -> None:
    art = Artifact(run_id="run_x", name="a.md", content="# hi")
    assert art.id is None
    assert art.size_bytes is None
    # type 默认 markdown,size_bytes 由调用方显式传入
    assert Artifact.__table__.c.type.default.arg == "markdown"


def test_relationships_collections() -> None:
    run = Run(task_id="task_x")
    run.steps.append(RunStep(run_id=run.id, name="s", type="agent", sequence=1))
    run.events.append(RunEvent(run_id=run.id, type="run_started"))
    run.artifacts.append(Artifact(run_id=run.id, name="a", content="c"))
    run.tool_calls.append(ToolCall(run_id=run.id, tool_name="t"))
    assert len(run.steps) == 1
    assert len(run.events) == 1
    assert len(run.artifacts) == 1
    assert len(run.tool_calls) == 1