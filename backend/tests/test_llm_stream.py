"""Step 2.3 token 流式与 SSE 断线重连测试。

覆盖:
- MockLLMProvider:on_token 分片回调,拼接等于完整 content;
- OpenAICompatProvider:httpx MockTransport 模拟 SSE 流,delta 回调、
  usage 解析、非 200 报错;
- BaseAgent:Writer(stream_output=True)透传回调,Planner(默认)不透传;
- SequentialWorkflow:Writer step 产生 llm_token 事件,delta 拼接等于正文;
- SSE 端点:Last-Event-ID 请求头优先于 after_sequence,断点续传不丢事件。
"""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import httpx
from fastapi.testclient import TestClient

from app.agents import WriterAgent
from app.agents.base import AgentContext
from app.db.session import get_db
from app.llms.mock import MockLLMProvider
from app.llms.openai_compat import OpenAICompatProvider
from app.llms.types import LLMError, LLMMessage
from app.main import app
from app.models import Run, RunEvent, Task
from app.workflows import SequentialWorkflow


def _mk_msg(role: str, content: str) -> LLMMessage:
    return LLMMessage(role=role, content=content)


# ---- MockLLMProvider ----


def test_mock_provider_streams_chunks_matching_content() -> None:
    provider = MockLLMProvider(latency_ms=0, stream_chunk_chars=10)
    chunks: list[str] = []
    result = provider.chat(
        [_mk_msg("system", "你是 报告撰写 Agent"), _mk_msg("user", "任务标题: 流式测试")],
        on_token=chunks.append,
    )
    assert len(chunks) > 1  # 确实分片
    assert "".join(chunks) == result.content
    assert result.usage.model == "mock-model"


def test_mock_provider_without_callback_unchanged() -> None:
    provider = MockLLMProvider(latency_ms=0)
    result = provider.chat([_mk_msg("user", "任务标题: x")])
    assert result.content


# ---- OpenAICompatProvider ----


def _sse_transport(lines: list[str]) -> httpx.MockTransport:
    body = "\n".join(lines)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=body, headers={"Content-Type": "text/event-stream"})

    return httpx.MockTransport(handler)


def test_openai_compat_streams_deltas() -> None:
    provider = OpenAICompatProvider(
        api_key="k",
        base_url="https://llm.test/v1",
        model="test-model",
        transport=_sse_transport([
            'data: {"choices":[{"delta":{"content":"你好"}}]}',
            'data: {"choices":[{"delta":{"content":",世界"}}]}',
            ": keep-alive comment",
            'data: {"choices":[],"usage":{"prompt_tokens":7,"completion_tokens":4}}',
            "data: [DONE]",
        ]),
    )
    chunks: list[str] = []
    result = provider.chat([_mk_msg("user", "hi")], on_token=chunks.append)

    assert chunks == ["你好", ",世界"]
    assert result.content == "你好,世界"
    assert result.usage.input_tokens == 7
    assert result.usage.output_tokens == 4


def test_openai_compat_stream_estimates_usage_when_missing() -> None:
    provider = OpenAICompatProvider(
        api_key="k",
        base_url="https://llm.test/v1",
        model="m",
        transport=_sse_transport([
            'data: {"choices":[{"delta":{"content":"abcdefgh"}}]}',
            "data: [DONE]",
        ]),
    )
    result = provider.chat([_mk_msg("user", "hi")], on_token=lambda _c: None)
    # 无 usage 时按 4 字符/token 估算
    assert result.usage.output_tokens == 2


def test_openai_compat_stream_http_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    provider = OpenAICompatProvider(
        api_key="k",
        base_url="https://llm.test/v1",
        model="m",
        transport=httpx.MockTransport(handler),
    )
    try:
        provider.chat([_mk_msg("user", "hi")], on_token=lambda _c: None)
        raise AssertionError("应当抛出 LLMError")
    except LLMError as exc:
        assert exc.code == "LLM_HTTP_ERROR"


# ---- Agent 层 ----


def _make_ctx() -> AgentContext:
    run = Run(id="run_s3", task_id="task_s3", input_snapshot={})
    task = Task(id="task_s3", title="流式测试", description=None)
    return AgentContext(run=run, task=task, input={})


@patch("app.agents.base.get_llm_provider", return_value=MockLLMProvider(latency_ms=0))
def test_writer_streams_but_planner_does_not(_mock) -> None:
    ctx = _make_ctx()

    writer_chunks: list[str] = []
    WriterAgent().run(ctx, on_token=writer_chunks.append)
    assert len(writer_chunks) > 1  # Writer 开启流式

    from app.agents import PlannerAgent

    planner_chunks: list[str] = []
    PlannerAgent().run(ctx, on_token=planner_chunks.append)
    assert planner_chunks == []  # 默认 Agent 不流式


# ---- Workflow 层 ----


def _make_fake_db(run: Run, task: Task) -> MagicMock:
    db = MagicMock()
    db.get.side_effect = lambda model, id_: run if model is Run else (task if model is Task else None)
    db.scalar.return_value = None

    def _fake_refresh(obj) -> None:
        pk = type(obj).__table__.primary_key.columns[0].key
        if getattr(obj, pk, None) is None:
            setattr(obj, pk, f"fake_{type(obj).__name__.lower()}_{id(obj) % 10000}")

    db.refresh.side_effect = _fake_refresh
    return db


@patch("app.agents.base.get_llm_provider", return_value=MockLLMProvider(latency_ms=0))
def test_workflow_emits_llm_token_events_for_writer(_mock) -> None:
    """Writer 的输出应被聚合为 llm_token 事件,delta 拼接等于 Writer 正文。"""
    run = Run(id="run_wf", task_id="task_wf", input_snapshot={})
    task = Task(id="task_wf", title="流式工作流", description=None)
    db = _make_fake_db(run, task)

    summary = SequentialWorkflow(max_rewrites=0).execute(db, "run_wf")
    assert summary["artifact_id"]

    added = [c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], RunEvent)]
    token_events = [e for e in added if e.type == "llm_token"]
    assert token_events, "Writer step 应产生 llm_token 事件"
    assert all(e.agent_id == "agent_writer" for e in token_events)
    assert all(e.payload and "delta" in e.payload for e in token_events)

    full_text = "".join(e.payload["delta"] for e in token_events)
    writer_step = [e for e in added if e.type == "step_started" and e.agent_id == "agent_writer"]
    assert writer_step, "应有 Writer 步骤"
    # Writer 的最终输出(mock):正文 markdown
    assert full_text.startswith("# 流式工作流")
    assert "## 正文" in full_text


@patch("app.agents.base.get_llm_provider", return_value=MockLLMProvider(latency_ms=0))
def test_workflow_no_token_events_for_non_streaming_agents(_mock) -> None:
    """未开启 stream_output 的 Agent(Planner/Reviewer 等)不产生 llm_token 事件。"""
    run = Run(id="run_wf2", task_id="task_wf2", input_snapshot={})
    task = Task(id="task_wf2", title="无流式", description=None)
    db = _make_fake_db(run, task)

    SequentialWorkflow(max_rewrites=0).execute(db, "run_wf2")

    added = [c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], RunEvent)]
    token_agents = {e.agent_id for e in added if e.type == "llm_token"}
    assert token_agents <= {"agent_writer"}  # 只有 Writer


# ---- SSE 断线重连 ----


def _mk_event(seq: int) -> RunEvent:
    ev = RunEvent(
        id=f"evt_{seq}",
        run_id="run_sse",
        type="progress",
        sequence=seq,
        payload={"n": seq},
        created_at=datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc),
    )
    return ev


def _sse_client(events: list[RunEvent], run_status: str = "completed") -> TestClient:
    """构造带 fake SessionLocal 的 TestClient:scalars 第一次返回 events,之后返回空。"""
    run = Run(id="run_sse", task_id="task_sse", status=run_status)
    db = MagicMock()
    db.get.side_effect = lambda model, id_: run if model is Run else None
    calls = {"n": 0}

    def _scalars(_stmt):
        calls["n"] += 1
        if calls["n"] == 1:
            return iter(events)
        return iter([])

    db.scalars.side_effect = _scalars
    # SSE 端点内部用 SessionLocal() 独立会话,不走 get_db 依赖注入
    patcher = patch("app.api.runs.SessionLocal", return_value=db)
    patcher.start()
    client = TestClient(app)
    client._sse_patcher = patcher  # type: ignore[attr-defined]
    return client


def _close_sse(client: TestClient) -> None:
    client._sse_patcher.stop()  # type: ignore[attr-defined]


def test_sse_last_event_id_header_resumes_from_cursor() -> None:
    """重连带 Last-Event-ID: 1 -> 只收到 sequence 2/3,不重发 1。"""
    client = _sse_client([_mk_event(2), _mk_event(3)])
    try:
        with client.stream(
            "GET",
            "/api/runs/run_sse/events/stream?after_sequence=0",
            headers={"Last-Event-ID": "1"},
        ) as resp:
            assert resp.status_code == 200
            text = "".join(resp.iter_text())
    finally:
        _close_sse(client)

    assert "id: 2" in text and "id: 3" in text
    assert "id: 1" not in text
    # 事件体完整下发
    assert '"sequence": 2' in text.replace(", ", " ") or '"sequence":2' in text.replace(" ", "")


def test_sse_without_header_uses_after_sequence_param() -> None:
    client = _sse_client([_mk_event(2)])
    try:
        with client.stream(
            "GET", "/api/runs/run_sse/events/stream?after_sequence=1"
        ) as resp:
            text = "".join(resp.iter_text())
    finally:
        _close_sse(client)

    assert "id: 2" in text
    assert "id: 1" not in text and "id: 3" not in text
