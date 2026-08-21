"""Planner / Writer / Reviewer 三个 Agent 的单元测试(使用 Mock LLM,不依赖真实 API 与数据库)。"""

from unittest.mock import patch

from app.agents import PlannerAgent, ReviewerAgent, WriterAgent
from app.agents.base import AgentContext
from app.agents.message_bus import MessageBus
from app.llms.mock import MockLLMProvider
from app.models import Run, Task


def _make_context(
    input_: dict | None = None, messages: dict[str, list[dict]] | None = None
) -> AgentContext:
    """构造测试上下文;messages 为预置到 bus 的上游消息(topic -> 消息列表)。"""
    task = Task(id="task_1", title="编写一份 AI 行业报告", description="覆盖市场与趋势")
    run = Run(id="run_1", task_id="task_1")
    bus = MessageBus()
    for topic, msgs in (messages or {}).items():
        for msg in msgs:
            bus.publish(topic, msg)
    return AgentContext(
        run=run,
        task=task,
        input=input_ or {},
        bus=bus,
    )


@patch("app.agents.base.get_llm_provider", return_value=MockLLMProvider(latency_ms=0))
def test_planner_produces_steps(_mock) -> None:
    result = PlannerAgent().run(_make_context())
    steps = result.output["steps"]
    assert isinstance(steps, list) and len(steps) >= 1
    assert all("name" in s and "description" in s for s in steps)
    assert result.agent_id == "agent_planner"


@patch("app.agents.base.get_llm_provider", return_value=MockLLMProvider(latency_ms=0))
def test_writer_produces_markdown(_mock) -> None:
    plan = {
        "steps": [
            {"sequence": 1, "name": "资料收集", "description": "收集资料"},
            {"sequence": 2, "name": "撰写", "description": "撰写正文"},
        ]
    }
    ctx = _make_context(messages={"agent_planner": [plan]})
    result = WriterAgent().run(ctx)
    assert result.output["markdown"].startswith("#")
    assert result.agent_id == "agent_writer"


@patch("app.agents.base.get_llm_provider", return_value=MockLLMProvider(latency_ms=0))
def test_reviewer_passes(_mock) -> None:
    ctx = _make_context(
        messages={"agent_writer": [{"markdown": "# 草稿\n\n内容"}]}
    )
    result = ReviewerAgent().run(ctx)
    assert result.output["quality"] in {"pass", "revision"}
    assert result.agent_id == "agent_reviewer"


def test_planner_parse_rejects_invalid() -> None:
    agent = PlannerAgent()
    try:
        agent.parse("not json at all")
    except Exception as exc:  # noqa: BLE001
        assert exc.__class__.__name__ == "LLMError"
    else:  # pragma: no cover
        raise AssertionError("应当抛出 LLMError")


def test_planner_parse_tolerates_json_fence() -> None:
    agent = PlannerAgent()
    content = '```json\n{"steps": [{"name": "A", "description": "B"}]}\n```'
    result = agent.parse(content)
    assert result["steps"][0]["name"] == "A"


def test_load_json_second_parse_failure_raises_llm_error() -> None:
    from app.agents._json import load_json

    try:
        load_json('{"a": }')
    except Exception as exc:  # noqa: BLE001
        assert exc.__class__.__name__ == "LLMError"
        assert exc.code == "LLM_JSON_PARSE"
    else:  # pragma: no cover
        raise AssertionError("应当抛出 LLMError")
