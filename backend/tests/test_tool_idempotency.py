"""工具幂等测试。"""

from unittest.mock import MagicMock, patch

from app.models import ToolCall
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
    db = MagicMock()
    runner = ToolRunner(db)
    existing = ToolCall(
        id="tc_existing",
        run_id="run_x",
        tool_name="send_notification",
        status="completed",
    )

    with patch.object(runner, "_find_active_by_key", return_value=existing):
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


def test_deduplicated_tool_returns_inflight_call() -> None:
    db = MagicMock()
    runner = ToolRunner(db)
    inflight = ToolCall(
        id="tc_waiting",
        run_id="run_x",
        tool_name="send_notification",
        status="waiting_for_approval",
    )

    with patch.object(runner, "_find_active_by_key", return_value=inflight):
        call = runner.run(
            run_id="run_x",
            tool_name="send_notification",
            args={"message": "hi"},
            step_id=None,
            agent_id=None,
        )

    assert call is inflight
    # 命中进行中的调用时同样不新建,为 Step 2.1 resume 后的去重铺路
    db.add.assert_not_called()
