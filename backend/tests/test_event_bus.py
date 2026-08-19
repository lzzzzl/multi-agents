"""Step 2.4 事件总线与订阅驱动流测试(不依赖真实 Redis)。

覆盖:
- event_bus.publish_event:序列化 ORM 事件并 publish 到正确 channel;
  序列化失败/Redis 异常时静默(不抛);
- append_event 持久化成功后调用 publish_event;
- EventService.stream 订阅模式:订阅后先补齐历史、推送消息即时 yield、
  重复消息按 sequence 去重、终态事件结束流;
- Redis 不可用时 stream 回退 DB 轮询。
"""

import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from app.models import Run, RunEvent
from app.services import event_bus
from app.services.event_service import EventService
from app.services.eventing import append_event


def _mk_run_event(seq: int, *, type: str = "progress", run_id: str = "run_bus") -> RunEvent:
    return RunEvent(
        id=f"evt_{seq}",
        run_id=run_id,
        type=type,
        sequence=seq,
        payload={"n": seq},
        created_at=datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc),
    )


# ---- publish_event ----


@patch.object(event_bus, "_get_publisher")
def test_publish_event_serializes_and_publishes(mock_get_publisher) -> None:
    publisher = MagicMock()
    mock_get_publisher.return_value = publisher

    event_bus.publish_event(_mk_run_event(3))

    publisher.publish.assert_called_once()
    channel, raw = publisher.publish.call_args.args
    assert channel == "run_events:run_bus"
    data = json.loads(raw)
    assert data["sequence"] == 3
    assert data["run_id"] == "run_bus"
    assert data["id"] == "evt_3"


@patch.object(event_bus, "_get_publisher")
def test_publish_event_swallows_redis_errors(mock_get_publisher) -> None:
    mock_get_publisher.return_value.publish.side_effect = ConnectionError("redis down")

    # 不抛错:订阅端有 DB 兜底
    event_bus.publish_event(_mk_run_event(1))


@patch.object(event_bus, "event_to_dict", side_effect=ValueError("bad event"))
def test_publish_event_swallows_serialize_errors(_mock) -> None:
    event_bus.publish_event(object())  # 不抛错


def test_channel_name() -> None:
    assert event_bus.channel_name("run_x") == "run_events:run_x"


# ---- append_event 发布集成 ----


def test_append_event_publishes_after_commit() -> None:
    db = MagicMock()
    db.scalar.return_value = None
    db.refresh.side_effect = lambda obj: None

    with patch("app.services.eventing.publish_event") as mock_publish:
        append_event(db, "run_bus", type="run_started")

    mock_publish.assert_called_once()
    published = mock_publish.call_args.args[0]
    assert isinstance(published, RunEvent)
    assert published.run_id == "run_bus"


# ---- 订阅驱动的 stream ----


class FakePubSub:
    """模拟 redis.asyncio pubsub:按序弹出预置消息,空时让出控制权。"""

    def __init__(self, payloads: list[dict]) -> None:
        self._pending = [json.dumps(p, ensure_ascii=False) for p in payloads]
        self.closed = False

    async def get_message(self, ignore_subscribe_messages=True, timeout=None):
        if self._pending:
            return {"type": "message", "data": self._pending.pop(0)}
        await asyncio.sleep(timeout or 0)
        return None

    async def aclose(self) -> None:
        self.closed = True


def _fake_db(events: list[RunEvent], run: Run | None = None):
    db = MagicMock()
    db.scalars.return_value = iter(events)
    db.get.side_effect = lambda model, id_: run if model is Run else None
    return db


@patch("app.services.event_service.close_subscription", new_callable=AsyncMock)
@patch("app.services.event_service.open_subscription")
async def test_stream_subscription_mode_history_then_push(mock_open, mock_close) -> None:
    """订阅模式:先补齐历史(seq1),推送的新事件即时 yield(seq2),
    收到终态事件(seq3 run_completed)后结束流。"""
    pubsub = FakePubSub([
        {"sequence": 2, "run_id": "run_bus", "type": "progress", "payload": {}},
        {"sequence": 3, "run_id": "run_bus", "type": "run_completed", "payload": {}},
    ])
    mock_open.return_value = pubsub
    # DB 兜底只查到历史事件;run 未终态(靠推送的终态事件结束)
    db = _fake_db([_mk_run_event(1)], run=Run(id="run_bus", task_id="t", status="running"))

    received = []
    async for ev in EventService(db).stream("run_bus"):
        received.append(ev)

    assert [e["sequence"] for e in received] == [1, 2, 3]
    # 订阅被正确关闭
    mock_close.assert_awaited_once()


@patch("app.services.event_service.close_subscription", new_callable=AsyncMock)
@patch("app.services.event_service.open_subscription")
async def test_stream_dedupes_replayed_push(mock_open, mock_close) -> None:
    """推送与兜底重复(同 sequence)时只发一次,重复推送被跳过后继续消费。"""
    pubsub = FakePubSub([
        {"sequence": 1, "run_id": "run_bus", "type": "progress", "payload": {}},  # 兜底已发,重复推送
        {"sequence": 2, "run_id": "run_bus", "type": "run_completed", "payload": {}},
    ])
    mock_open.return_value = pubsub
    # 首轮兜底发出 seq1;run 未终态,靠推送的终态事件结束
    db = _fake_db([_mk_run_event(1)], run=Run(id="run_bus", task_id="t", status="running"))

    received = []
    async for ev in EventService(db).stream("run_bus"):
        received.append(ev)

    # seq1 只出现一次(重复推送被去重),seq2(终态推送)后结束
    assert [e["sequence"] for e in received] == [1, 2]


@patch("app.services.event_service.close_subscription", new_callable=AsyncMock)
@patch("app.services.event_service.open_subscription")
async def test_stream_ignores_malformed_push(mock_open, mock_close) -> None:
    """无法解析的推送消息被跳过,流不中断。"""

    class BadPubSub(FakePubSub):
        async def get_message(self, ignore_subscribe_messages=True, timeout=None):
            if self._pending:
                return {"type": "message", "data": self._pending.pop(0)}
            raise asyncio.CancelledError  # 用取消结束测试循环

    pubsub = BadPubSub(["not-json"])
    mock_open.return_value = pubsub
    db = _fake_db([], run=Run(id="run_bus", task_id="t", status="running"))

    received = []
    try:
        async for ev in EventService(db).stream("run_bus"):
            received.append(ev)
    except asyncio.CancelledError:
        pass

    assert received == []


@patch("app.services.event_service.open_subscription", side_effect=ConnectionError("no redis"))
async def test_stream_falls_back_to_polling(mock_open) -> None:
    """Redis 不可用:回退 DB 轮询,行为与 Phase 1 一致。"""
    events = [_mk_run_event(1), _mk_run_event(2)]
    run = Run(id="run_bus", task_id="t", status="completed")
    db = MagicMock()
    # 轮询循环:第一次查全部,终态后再捞一次(空)
    db.scalars.side_effect = [iter(events), iter([])]
    db.get.side_effect = lambda model, id_: run if model is Run else None

    received = []
    async for ev in EventService(db).stream("run_bus", poll_interval=0.01):
        received.append(ev)

    assert [e["sequence"] for e in received] == [1, 2]
