"""轻量 DAG 编排器。

支持按节点依赖声明进行拓扑排序与分层执行。同一层内相互独立的节点
可以并行执行(ThreadPoolExecutor)。节点间通过共享 context dict 传递数据,
替代 previous dict 的隐式约定。
"""

from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable

NodeExecutor = Callable[[dict[str, Any]], Any]


@dataclass
class DAGNode:
    """DAG 中的一个节点。executor 接收共享 context,返回本节点结果。"""

    name: str
    executor: NodeExecutor
    depends_on: list[str] = field(default_factory=list)


class DAGError(RuntimeError):
    """DAG 校验或执行错误。"""


class DAG:
    """声明式节点图,负责校验、拓扑排序与执行。"""

    def __init__(self, nodes: list[DAGNode]) -> None:
        self._nodes: dict[str, DAGNode] = {node.name: node for node in nodes}
        if len(self._nodes) != len(nodes):
            raise DAGError("存在重复的节点名")
        self._validate()

    def _validate(self) -> None:
        for node in self._nodes.values():
            for dep in node.depends_on:
                if dep not in self._nodes:
                    raise DAGError(f"节点 {node.name!r} 依赖不存在的节点 {dep!r}")
        # 环检测由 topological_layers 完成
        self.topological_layers()

    def topological_layers(self) -> list[list[str]]:
        """返回分层拓扑序,每层内的节点相互独立、可并行执行。"""
        indegree = {name: 0 for name in self._nodes}
        dependents: dict[str, list[str]] = defaultdict(list)
        for name, node in self._nodes.items():
            for dep in node.depends_on:
                indegree[name] += 1
                dependents[dep].append(name)

        ready = deque(sorted(name for name, degree in indegree.items() if degree == 0))
        layers: list[list[str]] = []
        remaining = len(self._nodes)
        while ready:
            layer = list(ready)
            ready.clear()
            layers.append(layer)
            remaining -= len(layer)
            for name in layer:
                for child in dependents[name]:
                    indegree[child] -= 1
                    if indegree[child] == 0:
                        ready.append(child)

        if remaining != 0:
            raise DAGError("DAG 中存在环")
        return layers

    def run(
        self,
        context: dict[str, Any] | None = None,
        *,
        parallel: bool = True,
    ) -> dict[str, Any]:
        """执行所有节点,返回以节点名映射结果的 context。

        parallel=True 时,同层内多个节点用线程池并发执行。注意:并行执行时,
        executor 应通过返回值传递结果,避免写共享可变状态造成竞争。
        """
        ctx = context if context is not None else {}
        for layer in self.topological_layers():
            if parallel and len(layer) > 1:
                with ThreadPoolExecutor(max_workers=len(layer)) as pool:
                    futures = {
                        pool.submit(self._nodes[name].executor, ctx): name
                        for name in layer
                    }
                    for future in futures:
                        name = futures[future]
                        ctx[name] = future.result()
            else:
                for name in layer:
                    ctx[name] = self._nodes[name].executor(ctx)
        return ctx
