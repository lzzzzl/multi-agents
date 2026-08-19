"""SequentialWorkflow 重写循环测试(使用 Mock LLM 与 fake session,不依赖数据库)。"""

from unittest.mock import MagicMock, patch

from app.llms.mock import MockLLMProvider
from app.models import Run, Task, ToolCall
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

    # Planner + Researcher + 首次(Writer,Reviewer) + 重写(Writer,Reviewer) = 6 步
    assert summary["steps"] == 6
    assert summary["rewrites"] == 1
    assert summary["quality"] == "pass"
    assert summary["artifact_id"]


@patch("app.agents.base.get_llm_provider", return_value=MockLLMProvider(latency_ms=0))
def test_no_rewrite_allowed_stops_on_revision(_mock) -> None:
    run = Run(id="run_y", task_id="task_y", input_snapshot={})
    task = Task(id="task_y", title="测试任务", description=None)
    db = _make_fake_db(run, task)

    summary = SequentialWorkflow(max_rewrites=0).execute(db, "run_y")

    # 首次评审即 revision,且不允许重写 -> Planner + Researcher + Writer + Reviewer = 4 步
    assert summary["steps"] == 4
    assert summary["rewrites"] == 0
    assert summary["quality"] == "revision"
    assert summary["artifact_id"]


def _collect_tool_calls(db: MagicMock) -> list[ToolCall]:
    """从 fake db 的 add 调用中提取被持久化的 ToolCall 对象。"""
    calls: list[ToolCall] = []
    for call in db.add.call_args_list:
        obj = call.args[0]
        if isinstance(obj, ToolCall):
            calls.append(obj)
    return calls


@patch("app.agents.base.get_llm_provider", return_value=MockLLMProvider(latency_ms=0))
def test_workflow_executes_tool_call(_mock) -> None:
    """Step 3.1:Researcher 以 ReAct 循环连续调用多个工具,均记录 ToolCall 可审计。"""
    run = Run(id="run_z", task_id="task_z", input_snapshot={})
    task = Task(id="task_z", title="测试任务", description=None)
    db = _make_fake_db(run, task)

    summary = SequentialWorkflow(max_rewrites=0).execute(db, "run_z")

    # mock Researcher 的 ReAct 轨迹:generate_report -> current_time -> 结束
    tool_calls = _collect_tool_calls(db)
    assert [tc.tool_name for tc in tool_calls] == ["generate_report", "current_time"]
    tc = tool_calls[0]
    assert tc.risk_level == "safe"
    assert tc.status == "completed"
    assert tc.agent_id == "agent_researcher"
    assert tc.input and tc.input["title"] == "测试任务"
    # 工具生成的可展示初稿被写入 output._display,供 Writer 使用
    assert tc.output and tc.output.get("_display")
    assert summary["steps"] == 4


class _NoToolLLM(MockLLMProvider):
    """Researcher 一开始就判定无需工具的 LLM,验证 workflow 的兜底工具调用。"""

    def _respond(self, system_text: str, user_text: str) -> str:
        if "资料调研" in system_text or "researcher" in system_text.lower():
            return '{"tool_use": null, "summary": "无需工具"}'
        return super()._respond(system_text, user_text)


@patch("app.agents.base.get_llm_provider", return_value=_NoToolLLM(latency_ms=0))
def test_workflow_falls_back_to_default_tool_when_none_declared(_mock) -> None:
    """ReAct 循环未执行任何工具时,workflow 仍兜底执行 generate_report 保持链路可观测。"""
    run = Run(id="run_z2", task_id="task_z2", input_snapshot={})
    task = Task(id="task_z2", title="测试任务", description=None)
    db = _make_fake_db(run, task)

    summary = SequentialWorkflow(max_rewrites=0).execute(db, "run_z2")

    tool_calls = _collect_tool_calls(db)
    assert len(tool_calls) == 1
    assert tool_calls[0].tool_name == "generate_report"
    assert tool_calls[0].status == "completed"
    assert summary["steps"] == 4