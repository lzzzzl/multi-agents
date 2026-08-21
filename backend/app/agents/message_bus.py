"""Run 级消息总线(Step 3.2)。

替代 AgentContext.previous dict 的隐式依赖:上游 Agent 完成后把 output
publish 到主题(通常为 agent_id),下游 Agent 按主题订阅读取。

workflow 为同步顺序执行,因此采用「发布-留存-读取」模型:
- publish: 追加消息(保留历史,支持 Writer 重写时回看上一稿)
- latest:  读取主题最新一条(最常用)
- history: 读取主题全部消息(重写/审计场景)

挂起时经 to_state() 序列化进 checkpoint,恢复时 from_state() 重建,
跨进程传递不在此步范围(未来可演进为 Redis stream)。
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


class MessageBus:
    """Run 内的消息总线:topics -> 按发布顺序保留的消息列表。"""

    def __init__(self, topics: dict[str, list[dict[str, Any]]] | None = None) -> None:
        self._topics: dict[str, list[dict[str, Any]]] = dict(topics or {})

    def publish(self, topic: str, message: dict[str, Any]) -> None:
        """向主题发布一条消息(追加,保留历史)。"""
        self._topics.setdefault(topic, []).append(deepcopy(message))

    def latest(self, topic: str) -> dict[str, Any] | None:
        """读取主题最新一条消息;无消息返回 None。"""
        messages = self._topics.get(topic)
        return deepcopy(messages[-1]) if messages else None

    def history(self, topic: str) -> list[dict[str, Any]]:
        """读取主题全部消息(按发布顺序);订阅端入口。"""
        return deepcopy(self._topics.get(topic, []))

    def topics(self) -> list[str]:
        """当前已有消息的主题列表。"""
        return sorted(self._topics.keys())

    def to_state(self) -> dict[str, list[dict[str, Any]]]:
        """序列化为可 JSON 持久化的状态(用于 checkpoint)。"""
        return deepcopy(self._topics)

    @classmethod
    def from_state(cls, state: dict[str, list[dict[str, Any]]] | None) -> MessageBus:
        """从 checkpoint 状态重建总线。"""
        return cls(state or {})
