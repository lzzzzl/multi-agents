"""Step 3.1 ReAct 工具循环测试。

覆盖:
- BaseAgent.run 的 tool loop:思考 → 声明工具 → 执行 → 观察 → 再思考,连续多工具;
- 显式终止({"tool_use": null})与轮次上限两种终止条件;
- 未启用(max_tool_rounds=0)或未传入 tool_executor 时保持单次调用行为;
- 多轮 usage 累加、step metadata 记录 tool_rounds;
- 工作流端到端:Researcher 在一次 run 内连续调用多个工具。

审批挂起/恢复在 ReAct 循环中的行为由 test_workflow_resume.py 覆盖。
"""

from unittest.mock import MagicMock, patch

from app.agents import ResearcherAgent
from app.agents.base import AgentContext
from app.llms.mock import MockLLMProvider
from app.models import Run, RunStep, Task
from app.workflows import SequentialWorkflow


def _make_ctx() -> AgentContext:
    run = Run(id="run_react", task_id="task_react", input_snapshot={})
    task = Task(id="task_react", title="ReAct 测试", description=None)
    return AgentContext(run=run, task=task, input={})


class _Recorder:
    """记录每轮工具声明的 tool_executor。"""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def __call__(self, tool_use: dict) -> dict:
        self.calls.append(tool_use)
        return {"tool_name": tool_use["name"], "output": {"ok": True}, "draft": "初稿"}


# ---- Agent 层 ----


@patch("app.agents.base.get_llm_provider", return_value=MockLLMProvider(latency_ms=0))
def test_react_loop_executes_consecutive_tools(_mock) -> None:
    """思考→工具→观察→再思考:Researcher 连续调用两个工具后显式终止。"""
    agent = ResearcherAgent()
    recorder = _Recorder()
    result = agent.run(_make_ctx(), tool_executor=recorder)

    # mock 轨迹:generate_report -> (观察) -> current_time -> (观察) -> tool_use null
    assert [c["name"] for c in recorder.calls] == ["generate_report", "current_time"]
    assert result.tool_rounds == 2
    # 显式终止:最终输出不再声明工具
    assert result.output["tool_use"] is None
    assert result.output["summary"]
    # 多轮 LLM 调用的 usage 累加(3 次调用 x 每次 120 input tokens)
    assert result.usage.input_tokens == 3 * 120


@patch("app.agents.base.get_llm_provider", return_value=MockLLMProvider(latency_ms=0))
def test_react_loop_respects_round_limit(_mock) -> None:
    """轮次上限生效:达到上限后即使 LLM 仍声明工具也不再执行。"""
    agent = ResearcherAgent()
    agent.max_tool_rounds = 1
    recorder = _Recorder()
    result = agent.run(_make_ctx(), tool_executor=recorder)

    # 仅执行第一轮;第二轮声明(current_time)因上限不再执行
    assert [c["name"] for c in recorder.calls] == ["generate_report"]
    assert result.tool_rounds == 1
    # 最后一次 LLM 输出保留(含未执行的声明),循环硬终止
    assert result.output["tool_use"]["name"] == "current_time"


@patch("app.agents.base.get_llm_provider", return_value=MockLLMProvider(latency_ms=0))
def test_react_disabled_when_rounds_zero(_mock) -> None:
    """max_tool_rounds=0 时不启用循环,保持单次调用行为。"""
    agent = ResearcherAgent()
    agent.max_tool_rounds = 0
    recorder = _Recorder()
    result = agent.run(_make_ctx(), tool_executor=recorder)

    assert recorder.calls == []
    assert result.tool_rounds == 0
    assert result.usage.input_tokens == 120  # 单次 LLM 调用


@patch("app.agents.base.get_llm_provider", return_value=MockLLMProvider(latency_ms=0))
def test_react_without_executor_single_call(_mock) -> None:
    """未传入 tool_executor 时即使声明了工具也不循环(等价单次调用)。"""
    agent = ResearcherAgent()
    result = agent.run(_make_ctx())

    assert result.tool_rounds == 0
    assert result.usage.input_tokens == 120
    # 首轮声明原样返回,由上层决定是否执行(workflow 兜底路径)
    assert result.output["tool_use"]["name"] == "generate_report"


@patch("app.agents.base.get_llm_provider", return_value=MockLLMProvider(latency_ms=0))
def test_react_observation_feeds_next_round(_mock) -> None:
    """工具执行结果应作为观察回传 LLM:观察中包含工具输出内容。"""
    captured_messages: list[list] = []
    provider = MockLLMProvider(latency_ms=0)
    original_chat = provider.chat

    def _spy_chat(messages, **kwargs):
        captured_messages.append([m.content for m in messages])
        return original_chat(messages, **kwargs)

    provider.chat = _spy_chat
    with patch("app.agents.base.get_llm_provider", return_value=provider):
        agent = ResearcherAgent()
        result = agent.run(_make_ctx(), tool_executor=lambda tu: {"output": {"mark": "OBS-42"}})

    assert result.tool_rounds == 2
    # 最后一轮对话包含观察消息,且观察内容已注入
    final_messages = captured_messages[-1]
    assert any("OBS-42" in content for content in final_messages)
    # ReAct 轨迹:system + user + (assistant 声明 + user 观察) x 2 = 6 条
    assert len(final_messages) == 6


# ---- Workflow 层 ----


def _make_fake_db(run: Run, task: Task) -> MagicMock:
    db = MagicMock()
    db.get.side_effect = lambda model, id_: run if model is Run else (task if model is Task else None)
    db.scalar.return_value = None

    def _fake_refresh(obj) -> None:
        pk = type(obj).__table__.primary_key.columns[0].key
        if getattr(obj, pk, None) is None:
            setattr(obj, pk, f"fake_{type(obj).__name__.lower()}")

    db.refresh.side_effect = _fake_refresh
    return db


@patch("app.agents.base.get_llm_provider", return_value=MockLLMProvider(latency_ms=0))
def test_workflow_react_step_records_tool_rounds(_mock) -> None:
    """research 步骤的 metadata 记录 ReAct 轮次,可在 UI/trace 中观测。"""
    run = Run(id="run_meta", task_id="task_meta", input_snapshot={})
    task = Task(id="task_meta", title="ReAct 工作流", description=None)
    db = _make_fake_db(run, task)

    summary = SequentialWorkflow(max_rewrites=0).execute(db, "run_meta")

    assert summary["artifact_id"]
    steps = [c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], RunStep)]
    research_steps = [s for s in steps if s.agent_id == "agent_researcher"]
    assert len(research_steps) == 1
    assert research_steps[0].metadata_["tool_rounds"] == 2
    assert research_steps[0].status == "completed"
