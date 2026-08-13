"""append_event 事件写入测试。"""

from unittest.mock import MagicMock

import pytest

from app.models import RunEvent
from app.services.eventing import append_event


def _make_db(max_seq: int | None) -> MagicMock:
    db = MagicMock()
    db.scalar.return_value = max_seq
    return db


def test_append_event_sequence_starts_at_one() -> None:
    db = _make_db(max_seq=None)
    ev = append_event(db, "run_x", type="run_started")
    assert ev.sequence == 1


def test_append_event_sequence_increments() -> None:
    db = _make_db(max_seq=3)
    ev = append_event(db, "run_x", type="run_completed")
    assert ev.sequence == 4


def test_append_event_persists_fields() -> None:
    db = _make_db(max_seq=None)
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


@pytest.mark.xfail(
    reason="SELECT MAX(sequence)+1 存在并发竞态,将在 V2 Step 2.2 修复",
    strict=True,
)
def test_append_event_concurrent_sequence_is_unique() -> None:
    """模拟两个并发写入都读到相同 MAX,当前实现会生成重复 sequence。"""
    db = _make_db(max_seq=0)
    ev1 = append_event(db, "run_x", type="a")
    ev2 = append_event(db, "run_x", type="b")
    assert ev1.sequence != ev2.sequence
