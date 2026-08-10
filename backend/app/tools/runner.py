"""ToolRunner:执行工具,创建 ToolCall 记录并写入事件。"""

import logging
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models import RunEvent, RunStep, ToolCall
from app.tools.base import Tool, ToolError
from app.tools.registry import get_registry

logger = logging.getLogger(__name__)


class ToolRunner:
    """在 workflow 内执行一次工具调用,并持久化 ToolCall + 事件。"""

    def __init__(self, db: Session) -> None:
        self.db = db
        self._registry = get_registry()

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def _append_event(
        self,
        run_id: str,
        *,
        type: str,
        payload: dict[str, Any] | None = None,
        step_id: str | None = None,
        agent_id: str | None = None,
        tool_call_id: str | None = None,
    ) -> RunEvent:
        from sqlalchemy import func, select

        current_max = self.db.scalar(
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
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)
        return event

    def run(
        self,
        *,
        run_id: str,
        tool_name: str,
        args: dict[str, Any],
        step_id: str | None = None,
        agent_id: str | None = None,
    ) -> ToolCall:
        """执行指定工具,返回持久化的 ToolCall。"""
        tool = self._registry.get(tool_name)

        call = ToolCall(
            run_id=run_id,
            step_id=step_id,
            agent_id=agent_id,
            tool_name=tool.name,
            risk_level=tool.risk_level,
            status="running",
            input=args,
            started_at=self._now(),
        )
        self.db.add(call)
        self.db.commit()
        self.db.refresh(call)

        self._append_event(
            run_id,
            type="tool_call_started",
            step_id=step_id,
            agent_id=agent_id,
            tool_call_id=call.id,
            payload={"tool": tool.name, "risk_level": tool.risk_level, "input": args},
        )

        started = time.monotonic()
        try:
            result = tool.execute(args)
        except ToolError as exc:
            call.status = "failed"
            call.error_message = str(exc)
            call.completed_at = self._now()
            call.duration_ms = int((time.monotonic() - started) * 1000)
            self.db.commit()
            self._append_event(
                run_id,
                type="tool_call_failed",
                step_id=step_id,
                agent_id=agent_id,
                tool_call_id=call.id,
                payload={"tool": tool.name, "error": str(exc), "code": exc.code},
            )
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("Tool %s failed with unexpected error", tool.name)
            call.status = "failed"
            call.error_message = str(exc)
            call.completed_at = self._now()
            call.duration_ms = int((time.monotonic() - started) * 1000)
            self.db.commit()
            self._append_event(
                run_id,
                type="tool_call_failed",
                step_id=step_id,
                agent_id=agent_id,
                tool_call_id=call.id,
                payload={"tool": tool.name, "error": str(exc)},
            )
            raise ToolError(str(exc)) from exc

        call.status = "completed"
        output = dict(result.output or {})
        if result.display:
            # 工具产生的可展示文本(如报表初稿)作为执行结果一部分持久化
            output["_display"] = result.display
        call.output = output
        call.completed_at = self._now()
        call.duration_ms = int((time.monotonic() - started) * 1000)
        self.db.commit()
        self.db.refresh(call)

        self._append_event(
            run_id,
            type="tool_call_completed",
            step_id=step_id,
            agent_id=agent_id,
            tool_call_id=call.id,
            payload={
                "tool": tool.name,
                "output": result.output,
                "duration_ms": call.duration_ms,
            },
        )
        return call