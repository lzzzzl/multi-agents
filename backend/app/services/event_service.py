"""RunEvent 业务服务。负责事件查询与 SSE 订阅辅助。

Phase 1:事件写入由 RunService.append_event 完成,
本服务聚焦读取与 SSE 流的生成。
"""

import asyncio
from collections.abc import AsyncGenerator

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import RunEvent


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

    async def stream(
        self,
        run_id: str,
        after_sequence: int | None = None,
        poll_interval: float = 0.5,
        idle_timeout: float = 30.0,
    ) -> AsyncGenerator[RunEvent, None]:
        """轮询数据库生成事件流。

        Phase 1 简化实现:基于数据库轮询。后续可替换为 Redis pub/sub。
        当 run 进入终态且事件已发完时结束流。
        """
        from app.models import Run

        last_seq = after_sequence or 0
        idle = 0.0
        while True:
            # 取新事件
            stmt = (
                select(RunEvent)
                .where(RunEvent.run_id == run_id, RunEvent.sequence > last_seq)
                .order_by(RunEvent.sequence.asc())
            )
            events = list(self.db.scalars(stmt))
            for ev in events:
                last_seq = ev.sequence
                idle = 0.0
                yield ev

            # 检查 run 是否终态
            run = self.db.get(Run, run_id)
            if run and run.status in {"completed", "failed", "cancelled"}:
                # 再捞一次,确保终态事件不丢
                stmt = (
                    select(RunEvent)
                    .where(RunEvent.run_id == run_id, RunEvent.sequence > last_seq)
                    .order_by(RunEvent.sequence.asc())
                )
                for ev in self.db.scalars(stmt):
                    last_seq = ev.sequence
                    yield ev
                return

            await asyncio.sleep(poll_interval)
            idle += poll_interval
            if idle >= idle_timeout:
                return
