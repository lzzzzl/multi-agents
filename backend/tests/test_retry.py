"""per-step 重试测试。"""

from unittest.mock import MagicMock, patch

import pytest

from app.agents.base import AgentContext
from app.llms.mock import MockLLMProvider
from app.llms.types import LLMError
from app.models import Run, RunStep, Task
from app.workflows import SequentialWorkflow


class FlakyLLMProvider:
    """前 fail_times 次抛指定 LLMError,之后委托给 MockLLMProvider。"""

    model = "flaky"

    def __init__(self, fail_times: int, fail_code: str = "LLM_TIMEOUT") -> None:
        self.fail_times = fail_times
        self.fail_code = fail_code
        self.calls = 0
        self._real = MockLLMProvider(latency_ms=0)

    def chat(self, messages, *, temperature=0.7, max_tokens=None):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise LLMError("boom", code=self.fail_code)
        return self._real.chat(messages, temperature=temperature, max_tokens=max_tokens)


class AlwaysFailingProvider:
    model = "always_fail"

    def __init__(self, code: str) -> None:
        self.code = code
        self.calls = 0

    def chat(self, messages, *, temperature=0.7, max_tokens=None):
        self.calls += 1
        raise LLMError("boom", code=self.code)


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


def _make_step_args():
    run = Run(id="run_x", task_id="task_x", input_snapshot={})
    task = Task(id="task_x", title="测试任务", description=None)
    db = _make_fake_db(run, task)
    ctx = AgentContext(run=run, task=task, input={}, previous={})
    return run, task, db, ctx


def _added_steps(db: MagicMock) -> list[RunStep]:
    return [c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], RunStep)]


@patch("app.agents.base.get_llm_provider")
def test_agent_step_retries_retryable_error(mock_provider) -> None:
    flaky = FlakyLLMProvider(fail_times=1, fail_code="LLM_TIMEOUT")
    mock_provider.return_value = flaky
    wf = SequentialWorkflow(max_step_retries=1)
    run, task, db, ctx = _make_step_args()

    with patch("app.workflows.sequential.time.sleep"):
        result = wf._run_agent_step(db, "run_x", wf._planner, ctx, sequence=1)

    assert result is not None
    assert flaky.calls == 2  # 第一次失败,重试一次后成功
    steps = _added_steps(db)
    assert len(steps) == 1
    assert steps[0].metadata_["attempts"] == 2  # 总尝试次数


@patch("app.agents.base.get_llm_provider")
def test_agent_step_does_not_retry_non_retryable_error(mock_provider) -> None:
    always_fail = AlwaysFailingProvider("LLM_JSON_PARSE")
    mock_provider.return_value = always_fail
    wf = SequentialWorkflow(max_step_retries=1)
    run, task, db, ctx = _make_step_args()

    with patch("app.workflows.sequential.time.sleep"):
        with pytest.raises(LLMError):
            wf._run_agent_step(db, "run_x", wf._planner, ctx, sequence=1)

    assert always_fail.calls == 1  # 不可重试错误,只尝试一次


@patch("app.agents.base.get_llm_provider")
def test_agent_step_no_retry_when_max_zero(mock_provider) -> None:
    flaky = FlakyLLMProvider(fail_times=1, fail_code="LLM_TIMEOUT")
    mock_provider.return_value = flaky
    wf = SequentialWorkflow(max_step_retries=0)
    run, task, db, ctx = _make_step_args()

    with patch("app.workflows.sequential.time.sleep"):
        with pytest.raises(LLMError):
            wf._run_agent_step(db, "run_x", wf._planner, ctx, sequence=1)

    assert flaky.calls == 1  # 不允许重试,只尝试一次
    steps = _added_steps(db)
    assert steps[0].metadata_["attempts"] == 1


@patch("app.agents.base.get_llm_provider")
def test_agent_step_retries_up_to_max(mock_provider) -> None:
    flaky = FlakyLLMProvider(fail_times=2, fail_code="LLM_TIMEOUT")
    mock_provider.return_value = flaky
    wf = SequentialWorkflow(max_step_retries=2)
    run, task, db, ctx = _make_step_args()

    with patch("app.workflows.sequential.time.sleep"):
        result = wf._run_agent_step(db, "run_x", wf._planner, ctx, sequence=1)

    assert result is not None
    assert flaky.calls == 3  # 首试 + 两次重试后成功
    steps = _added_steps(db)
    assert steps[0].metadata_["attempts"] == 3
