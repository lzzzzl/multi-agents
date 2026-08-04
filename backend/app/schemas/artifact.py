"""Artifact 相关 Pydantic schema。"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ArtifactOut(BaseModel):
    id: str
    run_id: str
    step_id: str | None = None
    created_by_agent_id: str | None = None
    type: str
    name: str
    mime_type: str | None = None
    content: str | None = None
    storage_url: str | None = None
    size_bytes: int | None = None
    metadata: dict[str, Any] | None = None
    created_at: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}
