"""Workflow 抽象基类。

Workflow 是编排层的最小契约:执行一次 run、从 checkpoint 恢复、取消执行。
Step 1.1 只定义契约;resume/cancel 默认抛 NotImplementedError,
由 Step 1.3 在具体 workflow 中落地挂起/恢复能力。
"""

from abc import ABC, abstractmethod
from typing import Any

from sqlalchemy.orm import Session


class Workflow(ABC):
    """所有 workflow 的基类。子类需提供 name / version 并实现 execute。"""

    name: str
    version: str

    @abstractmethod
    def execute(self, db: Session, run_id: str) -> dict[str, Any]:
        """执行整个 workflow,返回汇总结果。"""
        raise NotImplementedError

    def resume(self, db: Session, run_id: str) -> dict[str, Any]:
        """从 checkpoint 恢复执行。默认不支持,由支持挂起的 workflow 覆写。"""
        raise NotImplementedError(f"Workflow {self.name} 不支持 resume")

    def cancel(self, db: Session, run_id: str) -> dict[str, Any]:
        """取消执行。默认不支持,由支持取消的 workflow 覆写。"""
        raise NotImplementedError(f"Workflow {self.name} 不支持 cancel")
