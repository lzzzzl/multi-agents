"""ToolRunner:执行工具,创建 ToolCall 记录并写入事件。

对风险等级非 safe 的工具,先进入人工审批:将 ToolCall 置为
waiting_for_approval、run 置为 waiting_for_approval,然后阻塞轮询
审批结果;获批后才真正执行,被拒则抛 ToolError 并记录错误。
"""

import logging
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models import Run, RunEvent, ToolCall
from app.services.eventing import append_event
from app.tools.base import SAFE, Tool, ToolError
from app.tools.registry import get_registry

logger = logging.getLogger(__name__)

# 审批轮询间隔与上限(秒)。超时视为审批失败,避免 worker 无限阻塞。
APPROVAL_POLL_INTERVAL = 1.0
APPROVAL_TIMEOUT_SECONDS = 300.0


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
        return append_event(
            self.db,
            run_id,
            type=type,
            payload=payload,
            step_id=step_id,
            agent_id=agent_id,
            tool_call_id=tool_call_id,
        )

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

        # 高风险工具:先挂起等待人工审批,获批后才执行
        if tool.risk_level != SAFE:
            return self._run_with_approval(
                run_id, tool, args, step_id=step_id, agent_id=agent_id
            )

        # 普通 safe 工具直接执行
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

        return self._execute_tool_call(run_id, tool, call, args, step_id=step_id, agent_id=agent_id)

    def _run_with_approval(
        self,
        run_id: str,
        tool: Tool,
        args: dict[str, Any],
        *,
        step_id: str | None,
        agent_id: str | None,
    ) -> ToolCall:
        """高风险工具:挂起等待审批,获批后执行。"""
        call = ToolCall(
            run_id=run_id,
            step_id=step_id,
            agent_id=agent_id,
            tool_name=tool.name,
            risk_level=tool.risk_level,
            status="waiting_for_approval",
            input=args,
        )
        self.db.add(call)
        self.db.commit()
        self.db.refresh(call)

        self._append_event(
            run_id,
            type="tool_call_waiting_for_approval",
            step_id=step_id,
            agent_id=agent_id,
            tool_call_id=call.id,
            payload={"tool": tool.name, "risk_level": tool.risk_level, "input": args},
        )

        run = self.db.get(Run, run_id)
        if run is not None:
            run.status = "waiting_for_approval"
            self.db.commit()

        decision = self._wait_for_approval(run_id, call.id)

        if decision == "cancelled":
            call.status = "cancelled"
            call.completed_at = self._now()
            self.db.commit()
            self._append_event(
                run_id,
                type="tool_call_cancelled",
                step_id=step_id,
                agent_id=agent_id,
                tool_call_id=call.id,
                payload={"tool": tool.name},
            )
            raise ToolError("运行已取消,工具调用未执行", code="RUN_CANCELLED")

        if decision == "rejected":
            call.status = "rejected"
            call.error_message = "工具调用被人工拒绝"
            call.completed_at = self._now()
            self.db.commit()
            self._append_event(
                run_id,
                type="tool_call_rejected",
                step_id=step_id,
                agent_id=agent_id,
                tool_call_id=call.id,
                payload={"tool": tool.name},
            )
            raise ToolError("工具调用被人工拒绝", code="TOOL_REJECTED")

        if decision == "timeout":
            call.status = "failed"
            call.error_message = "工具审批超时"
            call.completed_at = self._now()
            self.db.commit()
            self._append_event(
                run_id,
                type="tool_call_failed",
                step_id=step_id,
                agent_id=agent_id,
                tool_call_id=call.id,
                payload={"tool": tool.name, "error": "工具审批超时"},
            )
            raise ToolError("工具审批超时", code="TOOL_APPROVAL_TIMEOUT")

        # approved -> 恢复 run 为 running 并转为执行
        run = self.db.get(Run, run_id)
        if run is not None and run.status == "waiting_for_approval":
            run.status = "running"
        call.status = "running"
        call.started_at = self._now()
        self.db.commit()
        self._append_event(
            run_id,
            type="tool_call_started",
            step_id=step_id,
            agent_id=agent_id,
            tool_call_id=call.id,
            payload={"tool": tool.name, "risk_level": tool.risk_level, "input": args},
        )
        return self._execute_tool_call(run_id, tool, call, args, step_id=step_id, agent_id=agent_id)

    def _wait_for_approval(self, run_id: str, call_id: str) -> str:
        """阻塞等待审批结果,返回 approved / rejected / cancelled / timeout。

        轮询期间调用 expire_all 以读取其他会话(审批接口)写入的最新状态。
        """
        deadline = time.monotonic() + APPROVAL_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            time.sleep(APPROVAL_POLL_INTERVAL)
            self.db.expire_all()
            run = self.db.get(Run, run_id)
            if run is not None and run.status == "cancelled":
                return "cancelled"
            call = self.db.get(ToolCall, call_id)
            if call is not None:
                if call.status == "approved":
                    return "approved"
                if call.status == "rejected":
                    return "rejected"
        return "timeout"

    def _execute_tool_call(
        self,
        run_id: str,
        tool: Tool,
        call: ToolCall,
        args: dict[str, Any],
        *,
        step_id: str | None,
        agent_id: str | None,
    ) -> ToolCall:
        """以 running 状态执行工具,完成后回写记录并写完成/失败事件。"""
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