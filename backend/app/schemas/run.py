"""Run 与 RunEvent 相关 Pydantic schema。"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class RunCreate(BaseModel):
    task_id: str
    workflow_name: str = "sequential_report"
    input_override: dict[str, Any] | None = None


class RunApprove(BaseModel):
    """审批决策:approve 批准 / reject 拒绝。"""

    decision: str = Field("approve", pattern="^(approve|reject)$")


class RunOut(BaseModel):
    id: str
    task_id: str
    workflow_name: str
    workflow_version: str
    status: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    failed_at: datetime | None = None
    cancelled_at: datetime | None = None
    error_message: str | None = None
    error_code: str | None = None
    cost_summary: dict[str, Any] | None = None
    source_run_id: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RunStepOut(BaseModel):
    id: str
    run_id: str
    agent_id: str | None = None
    name: str
    type: str
    status: str
    sequence: int
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None

    model_config = {"from_attributes": True}


class RunDetailOut(RunOut):
    """运行详情,带 steps 和 cost 摘要。"""

    steps: list[RunStepOut] = []


class RunEventOut(BaseModel):
    id: str
    run_id: str
    step_id: str | None = None
    agent_id: str | None = None
    tool_call_id: str | None = None
    type: str
    sequence: int
    payload: dict[str, Any] | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class RunEventPage(BaseModel):
    items: list[RunEventOut]
    next_sequence: int | None = None


class ToolCallOut(BaseModel):
    id: str
    run_id: str
    step_id: str | None = None
    agent_id: str | None = None
    tool_name: str
    risk_level: str
    status: str
    input: dict[str, Any] | None = None
    output: dict[str, Any] | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: int | None = None

    model_config = {"from_attributes": True}


class LlmSpanOut(BaseModel):
    """单次 LLM 调用的轻量 trace 记录(Step 0.3)。"""

    id: str
    run_id: str
    step_id: str | None = None
    agent_id: str | None = None
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    status: str
    error_code: str | None = None
    error_message: str | None = None
    attempt: int
    created_at: datetime

    model_config = {"from_attributes": True}
