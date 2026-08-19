"""RunEvent 业务服务。负责事件查询与 SSE 订阅辅助。

Step 2.4:stream 从「每 0.5s 轮询 DB」升级为 Redis pub/sub 订阅驱动:
- 事件写入(append_event)后即时 publish,订阅端毫秒级收到;
- 订阅建立后先查库补齐历史(subscribe-then-poll,消除订阅间隙丢事件),
  并周期性查库兜底(publish 失败/订阅断开不丢事件),按 sequence 去重;
- 收到终态事件(run_completed/failed/cancelled)即结束流;
- Redis 不可用时整体回退为原 DB 轮询模式。
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncGenerator

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Run, RunEvent
from app.services.event_bus import (
    TERMINAL_EVENT_TYPES,
    close_subscription,
    event_to_dict,
    open_subscription,
)

logger = logging.getLogger(__name__)

TERMINAL_RUN_STATUSES = {"completed", "failed", "cancelled"}
# 订阅模式下周期性查库兜底的间隔(秒)
BACKFILL_INTERVAL_SECONDS = 2.0
# get_message 的等待时长(秒):决定空闲时的循环粒度
GET_MESSAGE_TIMEOUT = 0.2


class EventService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list(
        self,
        run_id: str,
        after_sequence: int | None = None,
        limit: int = 100,
    ) -> list[RunEvent]:
        stmt = (
            select(RunEvent)
            .where(RunEvent.run_id == run_id)
            .order_by(RunEvent.sequence.asc())
            .limit(limit)
        )
        if after_sequence is not None:
            stmt = stmt.where(RunEvent.sequence > after_sequence)
        return list(self.db.scalars(stmt))

    def _fetch_after(self, run_id: str, last_seq: int) -> list[dict]:
        """查询 last_seq 之后的事件并转为可序列化 dict。"""
        stmt = (
            select(RunEvent)
            .where(RunEvent.run_id == run_id, RunEvent.sequence > last_seq)
            .order_by(RunEvent.sequence.asc())
        )
        return [event_to_dict(ev) for ev in self.db.scalars(stmt)]

    async def stream(
        self,
        run_id: str,
        after_sequence: int | None = None,
        poll_interval: float = 0.5,
        idle_timeout: float = 30.0,
    ) -> AsyncGenerator[dict, None]:
        """生成事件流,yield 可 JSON 序列化的事件 dict。

        优先 Redis pub/sub 订阅驱动(毫秒级延迟 + 周期性查库兜底);
        Redis 不可用时回退 DB 轮询(poll_interval)。
        空闲超过 idle_timeout 或 run 进入终态后结束流
        (前端 EventSource 会自动带 Last-Event-ID 重连续传)。
        """
        last_seq = after_sequence or 0

        pubsub = None
        try:
            pubsub = await open_subscription(run_id)
        except Exception:
            logger.warning(
                "subscribe run_events channel for %s failed, fallback to DB polling",
                run_id,
                exc_info=True,
            )

        if pubsub is None:
            async for ev in self._polling_stream(
                run_id, last_seq, poll_interval, idle_timeout
            ):
                yield ev
            return

        try:
            last_activity = time.monotonic()
            last_backfill = 0.0  # 首轮立即补齐历史
            while True:
                now = time.monotonic()
                if now - last_backfill >= BACKFILL_INTERVAL_SECONDS:
                    last_backfill = now
                    batch = self._fetch_after(run_id, last_seq)
                    for data in batch:
                        last_seq = data["sequence"]
                        last_activity = now
                        yield data
                    # 终态且事件已发完 -> 结束(终态事件先于状态可见,不会漏)
                    run = self.db.get(Run, run_id)
                    if run and run.status in TERMINAL_RUN_STATUSES:
                        return

                msg = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=GET_MESSAGE_TIMEOUT
                )
                if msg and msg.get("type") == "message":
                    data = self._decode_message(msg)
                    if data is None:
                        continue
                    seq = data.get("sequence") or 0
                    if seq > last_seq:  # 重复推送(兜底已发过)按序号去重
                        last_seq = seq
                        last_activity = time.monotonic()
                        yield data
                        if data.get("type") in TERMINAL_EVENT_TYPES:
                            return

                if time.monotonic() - last_activity >= idle_timeout:
                    return
        finally:
            await close_subscription(pubsub)

    @staticmethod
    def _decode_message(msg: dict) -> dict | None:
        try:
            data = json.loads(msg.get("data"))
        except (TypeError, json.JSONDecodeError):
            return None
        return data if isinstance(data, dict) else None

    async def _polling_stream(
        self,
        run_id: str,
        last_seq: int,
        poll_interval: float,
        idle_timeout: float,
    ) -> AsyncGenerator[dict, None]:
        """DB 轮询回退模式(原 Phase 1 实现,保留作为无 Redis 时的兜底)。"""
        idle = 0.0
        while True:
            batch = self._fetch_after(run_id, last_seq)
            for data in batch:
                last_seq = data["sequence"]
                idle = 0.0
                yield data

            run = self.db.get(Run, run_id)
            if run and run.status in TERMINAL_RUN_STATUSES:
                # 再捞一次,确保终态事件不丢
                for data in self._fetch_after(run_id, last_seq):
                    last_seq = data["sequence"]
                    yield data
                return

            await asyncio.sleep(poll_interval)
            idle += poll_interval
            if idle >= idle_timeout:
                return
