"""Workflow checkpoint 与挂起信号。"""

from copy import deepcopy
from dataclasses import dataclass
from typing import Any


class WorkflowSuspended(Exception):
    """表示 workflow 在某个节点挂起,等待外部事件(如审批)后恢复。"""

    def __init__(self, node: str, reason: str) -> None:
        super().__init__(f"Workflow suspended at {node!r}: {reason}")
        self.node = node
        self.reason = reason


@dataclass
class WorkflowCheckpoint:
    """一次挂起的可恢复快照。持久化到 Run.metadata_["checkpoint"]。"""

    workflow_name: str
    completed_nodes: list[str]
    context: dict[str, Any]
    suspended_node: str | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow_name": self.workflow_name,
            "completed_nodes": self.completed_nodes,
            "context": self.context,
            "suspended_node": self.suspended_node,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkflowCheckpoint":
        return cls(
            workflow_name=data["workflow_name"],
            completed_nodes=list(data["completed_nodes"]),
            context=deepcopy(data["context"]),
            suspended_node=data.get("suspended_node"),
            reason=data.get("reason"),
        )
