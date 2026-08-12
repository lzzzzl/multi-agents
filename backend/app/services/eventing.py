"""共享事件写入助手。

RunService / ToolRunner / SequentialWorkflow / run_worker 统一复用,
避免各模块重复实现 sequence 递增逻辑。后续如需并发保护
(SELECT ... FOR UPDATE 或唯一约束),只需在此处统一修改。
"""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import RunEvent


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
    """向 run 追加一个事件,sequence 在该 run 内单调递增。"""
    current_max = db.scalar(
        select(func.max(RunEvent.sequence)).where(RunEvent.run_id == run_id)
    )
    next_seq = (current_max or 0) + 1
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