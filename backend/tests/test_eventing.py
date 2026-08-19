"""append_event 事件写入测试。

sequence 的取值/并发安全由 tests/test_eventing_concurrency.py
用真实 SQLite 引擎覆盖;本文件验证字段持久化等基础行为(mock db)。
"""

from unittest.mock import MagicMock

from app.models import RunEvent
from app.services.eventing import append_event


def _make_db() -> MagicMock:
    db = MagicMock()
    db.scalar.return_value = None
    return db


def test_append_event_persists_fields() -> None:
    db = _make_db()
    ev = append_event(
        db,
        "run_x",
        type="agent_message",
        step_id="step_1",
        agent_id="agent_writer",
        tool_call_id="tc_1",
        payload={"content": "hi"},
    )
    assert ev.run_id == "run_x"
    assert ev.type == "agent_message"
    assert ev.step_id == "step_1"
    assert ev.agent_id == "agent_writer"
    assert ev.tool_call_id == "tc_1"
    assert ev.payload == {"content": "hi"}
    assert isinstance(db.add.call_args.args[0], RunEvent)
    db.commit.assert_called_once()


def test_append_event_retry_on_integrity_error() -> None:
    """撞号时回滚并重试,最终成功返回。"""
    from sqlalchemy.exc import IntegrityError

    import app.services.eventing as eventing

    db = _make_db()
    real = eventing._append_event_once
    calls = {"n": 0}

    def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise IntegrityError("INSERT", {}, Exception("dup"))
        return real(*args, **kwargs)

    eventing._append_event_once = flaky
    try:
        ev = append_event(db, "run_x", type="a")
    finally:
        eventing._append_event_once = real

    assert calls["n"] == 2
    assert ev.type == "a"
    db.rollback.assert_called_once()
