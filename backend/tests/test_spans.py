"""Step 0.3 LLM span 记录测试。

覆盖:
- 成功路径:每个 Agent step 记录一条 success span,含 model/tokens/latency。
- 失败路径:失败调用记录 failed span,带 error_code 归因。
- 重试路径:可重试错误每次尝试各记一条 span(failed attempt=1 + success attempt=2)。
- API:GET /runs/{id}/llm_spans 返回结构化 span 列表。
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.db.session import get_db
from app.llms.mock import MockLLMProvider
from app.llms.types import LLMError
from app.main import app
from app.models import LlmSpan, Run, Task
from app.workflows import SequentialWorkflow


class AlwaysFailingProvider:
    model = "always_fail"

    def __init__(self, code: str) -> None:
        self.code = code

    def chat(self, messages, *, temperature=0.7, max_tokens=None, on_token=None):
        raise LLMError("boom", code=self.code)


class FlakyLLMProvider:
    """第一次抛可重试错误,之后委托 Mock。"""

    model = "flaky"

    def __init__(self) -> None:
        self.calls = 0
        self._real = MockLLMProvider(latency_ms=0)

    def chat(self, messages, *, temperature=0.7, max_tokens=None, on_token=None):
        self.calls += 1
        if self.calls == 1:
            raise LLMError("timeout", code="LLM_TIMEOUT")
        return self._real.chat(
            messages, temperature=temperature, max_tokens=max_tokens, on_token=on_token
        )


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


def _added_spans(db: MagicMock) -> list[LlmSpan]:
    return [c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], LlmSpan)]


@patch("app.agents.base.get_llm_provider", return_value=MockLLMProvider(latency_ms=0))
def test_success_run_records_span_per_step(_mock) -> None:
    """每个 Agent step 应各有一条 success span,带 model 与 token 用量。"""
    run = Run(id="run_span_ok", task_id="task_x", input_snapshot={})
    task = Task(id="task_x", title="测试任务", description=None)
    db = _make_fake_db(run, task)

    summary = SequentialWorkflow(max_rewrites=0).execute(db, "run_span_ok")

    spans = _added_spans(db)
    # Planner + Researcher + Writer + Reviewer = 4 个 LLM step
    assert summary["steps"] == 4
    assert len(spans) == 4
    assert all(s.status == "success" for s in spans)
    assert all(s.run_id == "run_span_ok" for s in spans)
    assert all(s.step_id for s in spans)
    assert {s.agent_id for s in spans} == {
        "agent_planner",
        "agent_researcher",
        "agent_writer",
        "agent_reviewer",
    }
    # token 与 model 来自 LLMUsage,耗时应被记录(允许 0,但字段存在)
    for s in spans:
        assert isinstance(s.input_tokens, int)
        assert isinstance(s.output_tokens, int)
        assert isinstance(s.latency_ms, int)
        assert s.attempt == 1
        assert s.error_code is None


@patch("app.agents.base.get_llm_provider", return_value=AlwaysFailingProvider("LLM_HTTP_ERROR"))
@patch("app.workflows.sequential.get_llm_provider", return_value=AlwaysFailingProvider("LLM_HTTP_ERROR"))
def test_failed_call_records_span_with_error_code(_m1, _m2) -> None:
    """失败调用应记录 failed span,并带 classify_error 归因码。"""
    run = Run(id="run_span_fail", task_id="task_x", input_snapshot={})
    task = Task(id="task_x", title="测试任务", description=None)
    db = _make_fake_db(run, task)

    try:
        SequentialWorkflow(max_rewrites=0, max_step_retries=0).execute(db, "run_span_fail")
    except LLMError:
        pass  # workflow 会向上抛出,这里只关心 span 是否落库

    spans = _added_spans(db)
    assert len(spans) == 1
    s = spans[0]
    assert s.status == "failed"
    assert s.error_code == "LLM_HTTP_ERROR"
    assert s.error_message == "boom"
    assert s.attempt == 1


@patch("app.agents.base.get_llm_provider", return_value=FlakyLLMProvider())
def test_retry_records_span_per_attempt(_mock) -> None:
    """可重试错误:失败尝试与成功尝试各记一条 span。"""
    run = Run(id="run_span_retry", task_id="task_x", input_snapshot={})
    task = Task(id="task_x", title="测试任务", description=None)
    db = _make_fake_db(run, task)

    summary = SequentialWorkflow(max_rewrites=0).execute(db, "run_span_retry")

    spans = _added_spans(db)
    failed = [s for s in spans if s.status == "failed"]
    success = [s for s in spans if s.status == "success"]
    # 首个 step(Planner)失败一次后重试成功:1 failed + 4 success
    assert summary["steps"] == 4
    assert len(failed) == 1
    assert len(success) == 4
    assert failed[0].attempt == 1
    assert failed[0].error_code == "LLM_TIMEOUT"
    planner_success = [s for s in success if s.agent_id == "agent_planner"][0]
    assert planner_success.attempt == 2


def test_llm_spans_api_returns_structured_list() -> None:
    """GET /runs/{id}/llm_spans 应返回该 run 的 span 列表。"""
    now = datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc)
    span = LlmSpan(
        id="span_1",
        run_id="run_api",
        step_id="step_1",
        agent_id="agent_planner",
        model="mock",
        input_tokens=10,
        output_tokens=20,
        latency_ms=5,
        status="failed",
        attempt=1,
        error_code="LLM_TIMEOUT",
        error_message="timeout",
    )
    span.created_at = now
    span.updated_at = now

    db = MagicMock()
    db.get.side_effect = lambda model, id_: Run(id="run_api", task_id="task_x") if model is Run else None
    db.scalars.return_value = iter([span])

    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        resp = client.get("/api/runs/run_api/llm_spans")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert len(items) == 1
    body = items[0]
    assert body["agent_id"] == "agent_planner"
    assert body["status"] == "failed"
    assert body["error_code"] == "LLM_TIMEOUT"
    assert body["attempt"] == 1
    assert body["latency_ms"] == 5
