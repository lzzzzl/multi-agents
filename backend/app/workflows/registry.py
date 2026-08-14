"""Workflow Registry:按 workflow_name 注册与查找 Workflow 类。"""

from app.core.errors import WorkflowNotFound
from app.workflows.base import Workflow


class WorkflowRegistry:
    """维护 name -> Workflow 类的映射。worker 通过 run.workflow_name 查找。"""

    def __init__(self) -> None:
        self._workflows: dict[str, type[Workflow]] = {}

    def register(self, workflow_cls: type[Workflow]) -> None:
        name = workflow_cls.name
        if name in self._workflows:
            raise ValueError(f"Workflow {name!r} 已注册")
        self._workflows[name] = workflow_cls

    def get(self, name: str) -> type[Workflow]:
        workflow_cls = self._workflows.get(name)
        if workflow_cls is None:
            raise WorkflowNotFound(f"Workflow {name!r} not found")
        return workflow_cls

    def has(self, name: str) -> bool:
        return name in self._workflows

    def list(self) -> list[type[Workflow]]:
        return list(self._workflows.values())


_registry: WorkflowRegistry | None = None


def get_registry() -> WorkflowRegistry:
    """全局 Workflow Registry 单例。首次调用时注册内置 workflow。"""
    global _registry
    if _registry is None:
        _registry = WorkflowRegistry()
        from app.workflows.sequential import SequentialWorkflow

        _registry.register(SequentialWorkflow)
    return _registry
