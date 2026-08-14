"""DAG 编排器测试。"""

import time

import pytest

from app.workflows.dag import DAG, DAGError, DAGNode


def _node(name: str, depends_on: list[str] | None = None) -> DAGNode:
    return DAGNode(name, lambda ctx: name, depends_on=depends_on or [])


def test_topological_layers() -> None:
    dag = DAG(
        [
            _node("a"),
            _node("b"),
            _node("c", ["a"]),
            _node("d", ["a", "b"]),
            _node("e", ["c", "d"]),
        ]
    )
    assert dag.topological_layers() == [["a", "b"], ["c", "d"], ["e"]]


def test_cycle_raises() -> None:
    with pytest.raises(DAGError):
        DAG([_node("a", ["b"]), _node("b", ["a"])])


def test_missing_dependency_raises() -> None:
    with pytest.raises(DAGError):
        DAG([_node("a", ["missing"])])


def test_duplicate_node_name_raises() -> None:
    with pytest.raises(DAGError):
        DAG([_node("a"), _node("a")])


def test_run_passes_context_downstream() -> None:
    def make_executor(name: str):
        def executor(ctx):
            return {"name": name, "upstream": list(ctx.keys())}

        return executor

    dag = DAG(
        [
            DAGNode("a", make_executor("a")),
            DAGNode("b", make_executor("b"), depends_on=["a"]),
        ]
    )
    result = dag.run(parallel=False)
    assert result["a"]["name"] == "a"
    assert result["b"]["name"] == "b"
    assert "a" in result["b"]["upstream"]


def test_parallel_branches_execute_concurrently() -> None:
    def make_executor(name: str, delay: float):
        def executor(ctx):
            time.sleep(delay)
            return name

        return executor

    dag = DAG(
        [
            DAGNode("a", make_executor("a", 0.25)),
            DAGNode("b", make_executor("b", 0.25)),
            DAGNode("c", make_executor("c", 0.0), depends_on=["a", "b"]),
        ]
    )
    start = time.monotonic()
    result = dag.run(parallel=True)
    elapsed = time.monotonic() - start
    assert result["c"] == "c"
    # 串行约 0.5s,并行约 0.25s,给足余量判据 < 0.4
    assert elapsed < 0.4
