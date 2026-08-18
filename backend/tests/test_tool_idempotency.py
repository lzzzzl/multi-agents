"""工具幂等测试。"""

from unittest.mock import MagicMock, patch

import pytest

from app.models import ToolCall
from app.tools.base import ApprovalRequired, Tool
from app.tools.builtin import SendNotificationTool
from app.tools.runner import ToolRunner, _make_idempotency_key


def test_idempotency_key_is_stable_across_arg_order() -> None:
    a = _make_idempotency_key("run_x", "send_notification", {"message": "hi", "channel": "email"})
    b = _make_idempotency_key("run_x", "send_notification", {"channel": "email", "message": "hi"})
    assert a == b

    c = _make_idempotency_key("run_y", "send_notification", {"message": "hi", "channel": "email"})
    assert a != c


def test_send_notification_deduplicates() -> None:
    assert SendNotificationTool().deduplicate is True


def test_idempotent_tool_returns_existing_call() -> None:
    """已完成的高风险调用按幂等键去重:resume/重试不重复执行副作用。"""
    db = MagicMock()
    runner = ToolRunner(db)
    existing = ToolCall(
        id="tc_existing",
        run_id="run_x",
        tool_name="send_notification",
        status="completed",
    )

    with patch.object(runner, "_find_any_by_key", return_value=existing):
        call = runner.run(
            run_id="run_x",
            tool_name="send_notification",
            args={"message": "hi"},
            step_id=None,
            agent_id=None,
        )

    assert call is existing
    # 命中已有成功调用时,不创建新 ToolCall,不重复执行副作用
    db.add.assert_not_called()


def test_high_risk_waiting_call_raises_instead_of_returning() -> None:
    """等待审批中的高风险调用不得被当作「进行中去重」直接返回,必须再次挂起。

    这是 Step 2.1 的关键安全语义:否则 resume 会绕过审批继续执行。
    """
    db = MagicMock()
    runner = ToolRunner(db)
    waiting = ToolCall(
        id="tc_waiting",
        run_id="run_x",
        tool_name="send_notification",
        status="waiting_for_approval",
    )

    with patch.object(runner, "_find_any_by_key", return_value=waiting):
        with pytest.raises(ApprovalRequired):
            runner.run(
                run_id="run_x",
                tool_name="send_notification",
                args={"message": "hi"},
                step_id=None,
                agent_id=None,
            )

    db.add.assert_not_called()


class _SafeDedupTool(Tool):
    """safe 且 deduplicate=True 的工具(用于验证 safe 路径的去重不受审批改造影响)。"""

    name = "safe_dedup"
    description = ""
    deduplicate = True

    def execute(self, args: dict) -> object:  # pragma: no cover - 不会真正执行
        raise AssertionError("命中去重时不应执行工具")


def test_safe_dedup_tool_returns_inflight_call() -> None:
    db = MagicMock()
    runner = ToolRunner(db)
    inflight = ToolCall(
        id="tc_inflight",
        run_id="run_x",
        tool_name="safe_dedup",
        status="running",
    )
    runner._registry.register(_SafeDedupTool())

    with patch.object(runner, "_find_active_by_key", return_value=inflight):
        call = runner.run(
            run_id="run_x",
            tool_name="safe_dedup",
            args={"x": 1},
            step_id=None,
            agent_id=None,
        )

    assert call is inflight
    db.add.assert_not_called()
