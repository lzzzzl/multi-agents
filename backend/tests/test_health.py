"""健康检查与统一响应格式测试。不依赖数据库与 LLM。"""

from app.schemas.common import ApiResponse


def test_health(client) -> None:
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["status"] == "ok"
    assert body["error"] is None


def test_api_response_shape() -> None:
    ok = ApiResponse.ok({"a": 1})
    assert ok.data == {"a": 1}
    assert ok.error is None

    fail = ApiResponse.fail("TASK_NOT_FOUND", "missing")
    assert ok.data == {"a": 1}
    assert fail.error.code == "TASK_NOT_FOUND"
