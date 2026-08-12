"""API 层测试:错误映射与请求校验。
通过 dependency_overrides 注入 fake session,不依赖真实数据库。"""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.db.session import get_db
from app.main import app
from app.models import Run


@pytest.fixture()
def api_client() -> TestClient:
    return TestClient(app)


def _override_db(run: Run | None, *, scalar=None) -> MagicMock:
    db = MagicMock()
    db.get.side_effect = lambda model, id_: run if model is Run else None
    db.scalar.return_value = scalar
    return db


@pytest.fixture()
def running_run_db() -> MagicMock:
    return _override_db(Run(id="run_ok", task_id="task_x", status="running"))


def test_retry_running_run_returns_conflict(api_client, running_run_db) -> None:
    app.dependency_overrides[get_db] = lambda: running_run_db
    try:
        resp = api_client.post("/api/runs/run_ok/retry")
    finally:
        app.dependency_overrides.clear()

    # 之前是 ValueError -> 500;修复后应返回 409 + 具体错误信息
    assert resp.status_code == 409
    body = resp.json()
    assert body["data"] is None
    assert body["error"]["code"] == "CONFLICT"
    assert "只有失败或已取消的 run 才能重试" in body["error"]["message"]


def test_approve_non_waiting_run_returns_conflict(api_client) -> None:
    db = _override_db(Run(id="run_ok", task_id="task_x", status="running"))
    app.dependency_overrides[get_db] = lambda: db
    try:
        resp = api_client.post("/api/runs/run_ok/approve", json={"decision": "approve"})
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "CONFLICT"


def test_approve_no_pending_call_returns_conflict(api_client) -> None:
    # run 处于等待审批,但没有任何待审批 ToolCall
    db = _override_db(
        Run(id="run_wait", task_id="task_x", status="waiting_for_approval"), scalar=None
    )
    app.dependency_overrides[get_db] = lambda: db
    try:
        resp = api_client.post("/api/runs/run_wait/approve", json={"decision": "approve"})
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 409
    assert "未找到待审批的工具调用" in resp.json()["error"]["message"]


def test_approve_invalid_decision_rejected(api_client) -> None:
    db = _override_db(Run(id="run_wait", task_id="task_x", status="waiting_for_approval"))
    app.dependency_overrides[get_db] = lambda: db
    try:
        resp = api_client.post("/api/runs/run_wait/approve", json={"decision": "yes"})
    finally:
        app.dependency_overrides.clear()

    # decision 由 pydantic pattern 校验,进入 service 前即被拒绝
    assert resp.status_code == 422