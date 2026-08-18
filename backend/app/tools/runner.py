"""ToolRunner:执行工具,创建 ToolCall 记录并写入事件。

对风险等级非 safe 的工具,走异步人工审批(Step 2.1):
将 ToolCall 置为 waiting_for_approval、run 置为 waiting_for_approval,
然后抛出 ApprovalRequired 信号,由 workflow 持久化 checkpoint 并释放 worker。
审批决策(approve/reject)后经 resume 重新进入本方法:
- 已批准 -> 复用同一条 ToolCall 记录继续执行(不重复创建);
- 被拒绝 -> 抛 ToolError,由上层决定后续流程;
- 仍在等待 -> 再次抛 ApprovalRequired(幂等挂起)。
"""

import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Run, RunEvent, ToolCall
from app.services.eventing import append_event
from app.tools.base import SAFE, ApprovalRequired, Tool, ToolError
from app.tools.registry import get_registry

logger = logging.getLogger(__name__)

# 幂等去重时视为「有效」的状态:完成或进行中;失败/取消/拒绝视为可重新尝试。
ACTIVE_TOOL_CALL_STATUSES = {"pending", "running", "waiting_for_approval", "completed"}


def _make_idempotency_key(run_id: str, tool_name: str, args: dict[str, Any]) -> str:
    """生成幂等键:run_id + tool_name + args 的稳定哈希(与 args 顺序无关)。"""
    payload = json.dumps(
        {"run_id": run_id, "tool_name": tool_name, "args": args},
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


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
        idempotency_key = _make_idempotency_key(run_id, tool_name, args)

        # 高风险工具统一走异步审批路径(内部按既有调用状态分流:
        # 挂起/已批准/被拒/已完成去重),不能被 safe 工具的 dedup 提前返回
        if tool.risk_level != SAFE:
            return self._run_with_approval(
                run_id,
                tool,
                args,
                step_id=step_id,
                agent_id=agent_id,
                idempotency_key=idempotency_key,
            )

        # safe 工具按需去重:相同 key 存在完成/进行中的调用时直接复用,避免重复副作用
        if tool.deduplicate:
            existing = self._find_active_by_key(run_id, idempotency_key)
            if existing is not None:
                return existing

        # 普通 safe 工具直接执行
        call = ToolCall(
            run_id=run_id,
            step_id=step_id,
            agent_id=agent_id,
            tool_name=tool.name,
            idempotency_key=idempotency_key,
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
        idempotency_key: str | None = None,
    ) -> ToolCall:
        """高风险工具:挂起等待审批,获批后执行。

        首次调用创建 waiting_for_approval 的 ToolCall 并抛 ApprovalRequired;
        resume 再次进入时按既有调用的状态分流(见模块 docstring)。
        """
        existing = self._find_any_by_key(run_id, idempotency_key) if idempotency_key else None
        if existing is not None:
            if existing.status == "waiting_for_approval":
                # 审批仍未决:幂等地再次挂起
                raise ApprovalRequired(existing.id, tool.name)
            if existing.status == "approved":
                # 已批准:复用该记录转为执行(不重复创建 ToolCall)
                return self._execute_approved(run_id, tool, existing, args, step_id=step_id, agent_id=agent_id)
            if existing.status == "rejected":
                raise ToolError("工具调用被人工拒绝", code="TOOL_REJECTED")
            if existing.status == "completed":
                return existing
            # failed / cancelled:视为可重新尝试,走下方新建流程
            logger.info(
                "ToolCall %s for %s in status %r, creating a new approval request",
                existing.id,
                tool.name,
                existing.status,
            )

        call = ToolCall(
            run_id=run_id,
            step_id=step_id,
            agent_id=agent_id,
            tool_name=tool.name,
            idempotency_key=idempotency_key,
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

        # 释放 worker:由 workflow 捕获后持久化 checkpoint
        raise ApprovalRequired(call.id, tool.name)

    def _execute_approved(
        self,
        run_id: str,
        tool: Tool,
        call: ToolCall,
        args: dict[str, Any],
        *,
        step_id: str | None,
        agent_id: str | None,
    ) -> ToolCall:
        """执行一条已批准的 ToolCall(审批回调后的 resume 路径)。"""
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

    def _find_active_by_key(self, run_id: str, idempotency_key: str) -> ToolCall | None:
        """按幂等键查找同 run 内完成或进行中的 ToolCall(排除失败/取消/拒绝)。"""
        return self.db.scalar(
            select(ToolCall).where(
                ToolCall.run_id == run_id,
                ToolCall.idempotency_key == idempotency_key,
                ToolCall.status.in_(ACTIVE_TOOL_CALL_STATUSES),
            )
            .order_by(ToolCall.created_at.desc())
            .limit(1)
        )

    def _find_any_by_key(self, run_id: str, idempotency_key: str) -> ToolCall | None:
        """按幂等键查找同 run 内最近一条任意状态的 ToolCall(含 approved/rejected)。"""
        return self.db.scalar(
            select(ToolCall)
            .where(
                ToolCall.run_id == run_id,
                ToolCall.idempotency_key == idempotency_key,
            )
            .order_by(ToolCall.created_at.desc())
            .limit(1)
        )

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
