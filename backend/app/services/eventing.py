"""共享事件写入助手。

RunService / ToolRunner / SequentialWorkflow / run_worker 统一复用。

Step 2.2 并发安全(消除 SELECT MAX(sequence)+1 竞态):
1. 写入前对 run 行加 FOR UPDATE 锁,把同一 run 的事件追加串行化
   (锁随 commit 释放,事务极短);
2. (run_id, sequence) 唯一约束作数据库层兜底;
3. 若仍发生撞号(如外部进程绕过锁写入),IntegrityError 触发
   随机退避重试,重新计算 sequence 后再写。
"""

import random
import time
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Run, RunEvent

# 撞号重试上限与基础退避(秒),实际退避 = base * 2^attempt * 随机抖动
MAX_APPEND_RETRIES = 5
_RETRY_BASE_DELAY = 0.005


def append_event(
    db: Session,
    run_id: str,
    *,
    type: str,
    payload: dict[str, Any] | None = None,
    step_id: str | None = None,
    agent_id: str | None = None,
    tool_call_id: str | None = None,
) -> RunEvent:
    """向 run 追加一个事件,sequence 在该 run 内单调递增且不重复。"""
    last_exc: IntegrityError | None = None
    for attempt in range(MAX_APPEND_RETRIES):
        try:
            return _append_event_once(
                db,
                run_id,
                type=type,
                payload=payload,
                step_id=step_id,
                agent_id=agent_id,
                tool_call_id=tool_call_id,
            )
        except IntegrityError as exc:  # 并发撞号:回滚后重算 sequence 再试
            last_exc = exc
            db.rollback()
            time.sleep(_RETRY_BASE_DELAY * (2**attempt) * (0.5 + random.random()))
    # 重试耗尽仍冲突:向上抛出,由调用方决定是否失败该 run
    assert last_exc is not None
    raise last_exc


def _append_event_once(
    db: Session,
    run_id: str,
    *,
    type: str,
    payload: dict[str, Any] | None,
    step_id: str | None,
    agent_id: str | None,
    tool_call_id: str | None,
) -> RunEvent:
    # PG:锁住 run 行,串行化同一 run 的 sequence 分配
    # (SQLite 忽略 FOR UPDATE,靠下方原子 INSERT 表达式兜底)
    db.execute(select(Run.id).where(Run.id == run_id).with_for_update())
    # sequence 在 INSERT 内用 max+1 子查询计算:
    # SQLite 单写锁下语句原子执行,彻底消除「读到同一 max 后各写各的」竞态
    next_seq = (
        select(func.coalesce(func.max(RunEvent.sequence), 0) + 1)
        .where(RunEvent.run_id == run_id)
        .scalar_subquery()
    )
    event = RunEvent(
        run_id=run_id,
        step_id=step_id,
        agent_id=agent_id,
        tool_call_id=tool_call_id,
        type=type,
        sequence=next_seq,
        payload=payload,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event
