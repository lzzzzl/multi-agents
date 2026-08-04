"""Task 相关 Pydantic schema。"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    input: dict[str, Any] | None = None
    priority: str = "normal"
    metadata: dict[str, Any] | None = None


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    status: str | None = None
    priority: str | None = None
    input: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


class TaskOut(BaseModel):
    id: str
    project_id: str | None = None
    created_by: str | None = None
    title: str
    description: str | None = None
    status: str
    priority: str
    input: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = Field(None, alias="metadata")
    latest_run_id: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}


class TaskDetailOut(TaskOut):
    """任务详情,带 runs 摘要。"""

    runs: list["TaskRunSummary"] = []


class TaskRunSummary(BaseModel):
    id: str
    status: str
    workflow_name: str
    created_at: datetime

    model_config = {"from_attributes": True}


TaskDetailOut.model_rebuild()
