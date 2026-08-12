"""Tool 系统测试:Registry / 内置工具 / ToolRunner。
使用 fake session,不依赖数据库。"""

from unittest.mock import MagicMock

import pytest

from app.models import Run, RunEvent, Task, ToolCall
from app.tools.base import SAFE, ToolError
from app.tools.builtin import CurrentTimeTool, GenerateReportTool, SendNotificationTool
from app.tools.registry import ToolRegistry, get_registry
from app.tools.runner import ToolRunner


class _FakeTool(CurrentTimeTool):
    """仅用于 registry 重复注册测试的匿名工具。"""

    name = "fake_probe"


def _make_fake_db(run: Run | None = None) -> MagicMock:
    db = MagicMock()
    db.get.side_effect = lambda model, id_: run if model is Run else None
    db.scalar.return_value = None  # 事件 sequence 基线

    def _fake_refresh(obj) -> None:
        pk = type(obj).__table__.primary_key.columns[0].key
        if getattr(obj, pk, None) is None:
            setattr(obj, pk, f"fake_{type(obj).__name__.lower()}")

    db.refresh.side_effect = _fake_refresh
    return db


# ---------- Registry ----------


def test_registry_register_and_get() -> None:
    reg = ToolRegistry()
    reg.register(CurrentTimeTool())
    assert reg.has("current_time")
    assert reg.get("current_time").name == "current_time"
    assert "current_time" in [t.name for t in reg.list()]


def test_registry_duplicate_raises() -> None:
    reg = ToolRegistry()
    reg.register(CurrentTimeTool())
    with pytest.raises(ValueError):
        reg.register(CurrentTimeTool())


def test_registry_unknown_raises_tool_error() -> None:
    reg = ToolRegistry()
    with pytest.raises(ToolError) as exc:
        reg.get("nope")
    assert exc.value.code == "TOOL_NOT_FOUND"


def test_global_registry_has_builtins() -> None:
    reg = get_registry()
    for name in ("current_time", "generate_report", "send_notification"):
        assert reg.has(name)


# ---------- 内置工具 ----------


def test_current_time_tool() -> None:
    result = CurrentTimeTool().execute({})
    assert "iso" in result.output
    assert result.display is not None


def test_generate_report_tool() -> None:
    result = GenerateReportTool().execute({"title": "AI 报告", "outline": ["市场", "趋势"]})
    assert result.output["title"] == "AI 报告"
    assert result.output["sections"] == 2
    assert result.display.startswith("# AI 报告")


def test_generate_report_rejects_non_list_outline() -> None:
    with pytest.raises(ToolError) as exc:
        GenerateReportTool().execute({"title": "t", "outline": "not-a-list"})
    assert exc.value.code == "INVALID_INPUT"


def test_send_notification_tool_risk() -> None:
    tool = SendNotificationTool()
    assert tool.risk_level != SAFE
    result = tool.execute({"message": "hi", "channel": "email"})
    assert result.output["sent"] is True


# ---------- ToolRunner ----------


def test_runner_executes_safe_tool() -> None:
    db = _make_fake_db()
    call = ToolRunner(db).run(
        run_id="run_x",
        tool_name="current_time",
        args={},
        step_id=None,
        agent_id="agent_researcher",
    )
    assert call.status == "completed"
    assert call.risk_level == SAFE
    assert call.output and "iso" in call.output
    # 事件写入: started + completed
    events = [c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], RunEvent)]
    types = [e.type for e in events]
    assert "tool_call_started" in types
    assert "tool_call_completed" in types


def test_runner_unknown_tool_raises() -> None:
    db = _make_fake_db()
    with pytest.raises(ToolError) as exc:
        ToolRunner(db).run(
            run_id="run_x", tool_name="nope", args={}, step_id=None, agent_id=None
        )
    assert exc.value.code == "TOOL_NOT_FOUND"